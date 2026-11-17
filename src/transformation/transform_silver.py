import re
import ast
import hashlib
import inspect
import json
from contextlib import suppress
from importlib.metadata import version
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter
from functools import lru_cache

from psycopg2.extras import execute_batch
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import (
    StopWordRemoverFactory
)

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from config.database import get_connection


# KONFIGURASI NLP

stemmer = StemmerFactory().create_stemmer()

stopwords = set(StopWordRemoverFactory().get_stop_words())

# Kata umum tambahan khusus analisis berita
custom_stopwords = {
    "ujar", "kata", "ungkap", "tutur",
    "jelas", "sebut", "imbuh",
    "jadi", "laku", "lalu", "hingga",
    "lebih", "butuh", "jumlah",
    "nusantaratv", "com", "www",
    "baca", "artikel", "berita",
    # Bentuk hasil stemming yang terlalu umum untuk keyword topik berita.
    "bagai", "cara", "hadap", "turut", "sama",
    "beri", "milik", "nyata", "lanjut", "pihak"
}

stopwords.update(custom_stopwords)

MIN_WORD_LENGTH = 3

# Kamus terbatas untuk bentuk informal yang maknanya cukup jelas.
# Kata di luar kamus dipertahankan, termasuk nama orang dan singkatan berita.
NORMALIZATION_MAP = {
    "gw": "saya", "gue": "saya", "gua": "saya",
    "lu": "kamu", "lo": "kamu",
    "udh": "sudah", "udah": "sudah", "sdh": "sudah",
    "blm": "belum", "tdk": "tidak", "gak": "tidak",
    "ga": "tidak", "gk": "tidak", "nggak": "tidak",
    "ngga": "tidak", "enggak": "tidak",
    "yg": "yang", "dgn": "dengan", "dg": "dengan",
    "utk": "untuk", "krn": "karena", "karna": "karena",
    "dlm": "dalam", "jg": "juga", "jgn": "jangan",
    "tp": "tetapi", "tapi": "tetapi", "kalo": "kalau",
    "skrg": "sekarang", "bgt": "sangat", "aja": "saja",
    "gimana": "bagaimana", "gmn": "bagaimana",
    "gpp": "tidak apa apa",
}

# 1. VALIDASI DAN PERAPIAN KOLOM (BAGIAN PRAPEMROSESAN)

# Merapikan spasi pada kolom artikel.
def clean_field(value):
    if value is None:
        return ''

    return re.sub('\\s+', ' ', str(value)).strip()


# Membaca tanggal dan memastikan zona waktu tersedia.
def parse_datetime(value):
    if not isinstance(value, datetime):
        if not value:
            raise ValueError('Tanggal kosong')
        value = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if value.utcoffset() is None:
        raise ValueError('Tanggal harus memiliki timezone')
    return value


# Memvalidasi dan merapikan kolom artikel untuk Silver.
def transform_article(article):
    (
        article_id,
        title,
        content,
        description,
        category,
        author,
        published_at,
        article_url,
        crawled_at
    ) = article

    article_id = clean_field(article_id)
    title = clean_field(title)
    content = clean_field(content)
    description = clean_field(description)
    category = clean_field(category).lower()
    author = clean_field(author)
    article_url = clean_field(article_url)

    if not all([
        article_id,
        title,
        content,
        category,
        article_url,
        published_at
    ]):
        raise ValueError('Kolom wajib tidak lengkap')

    published_at = parse_datetime(published_at)

    crawled_at = parse_datetime(crawled_at) if crawled_at else None

    word_count = len(content.split())

    return (
        article_id,
        title,
        content,
        description or None,
        category,
        author or None,
        published_at,
        article_url,
        crawled_at,
        word_count
    )


# 2. PRAPEMROSESAN TEKS NLP

# Mengubah teks menjadi huruf kecil.
def case_folding(text):
    return (text or "").lower()


# Membersihkan URL, angka, simbol, dan spasi berlebih.
def clean_nlp_text(text):
    text = re.sub(
        r"https?://\S+|www\.\S+",
        " ",
        text
    )

    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# Memecah teks menjadi token kata.
def tokenize(text):
    return text.split()


# Mengubah bentuk tidak baku dengan kamus normalisasi.
def normalize_tokens(tokens):
    # Pisahkan hasil normalisasi yang terdiri dari beberapa kata menjadi token.
    return [
        word
        for token in tokens
        for word in NORMALIZATION_MAP.get(token, token).split()
    ]


# Membuang kata umum dan token yang terlalu pendek.
def remove_stopwords(tokens):
    return [
        token
        for token in tokens
        if token not in stopwords
        and len(token) >= MIN_WORD_LENGTH
    ]


# Mengambil kata dasar dengan pengecualian makna tertentu.
@lru_cache(maxsize=50000)
def stem_word(word):
    # Pertahankan makna kata yang bisa tercampur akibat pembentukan kata dasar.
    if word in {"perintah", "pemerintah", "pemerintahan"}:
        return "pemerintah" if word != "perintah" else "perintah"
    return stemmer.stem(word)


# Menerapkan pembentukan kata dasar pada setiap token.
def stemming(tokens):
    return [
        stem_word(token)
        for token in tokens
    ]


# Menjalankan enam tahap preprocessing teks secara berurutan.
def preprocess(text):
    # 1. Penyeragaman huruf kecil
    text = case_folding(text)

    # 2. Ekspresi reguler: bersihkan URL, angka, simbol, dan emoji
    text = clean_nlp_text(text)

    # 3. Tokenisasi
    tokens = tokenize(text)

    # 4. Normalisasi kata tidak baku
    tokens = normalize_tokens(tokens)

    # 5. Pembentukan kata dasar
    tokens = stemming(tokens)

    # 6. Penghapusan kata umum
    tokens = remove_stopwords(tokens)

    return [
        token
        for token in tokens
        if len(token) <= 100
    ]


# 3. ALUR TRANSFORMASI SILVER

STAGING_QUERY = """
    SELECT article_id, title, content, description, category, author,
           published_at, article_url, crawled_at
    FROM staging.articles ORDER BY article_id
"""
SILVER_QUERY = """
    SELECT s.article_id, s.title, s.content, s.description, s.category, s.author,
           s.published_at, s.article_url, s.crawled_at, s.word_count,
           p.content_hash, p.nlp_signature
    FROM silver.articles s LEFT JOIN silver.article_processing p USING (article_id)
    ORDER BY s.article_id
"""
# Tandai perubahan algoritma, konfigurasi NLP, atau versi Sastrawi.
NLP_SIGNATURE = hashlib.sha256((
    "\n".join(ast.dump(ast.parse(inspect.getsource(function))) for function in (
        case_folding, clean_nlp_text, tokenize, normalize_tokens, remove_stopwords,
        stem_word, stemming, preprocess,
    )) + json.dumps(sorted(stopwords))
    + json.dumps(NORMALIZATION_MAP, sort_keys=True, ensure_ascii=False)
    + str(MIN_WORD_LENGTH) + version("Sastrawi")
).encode("utf-8")).hexdigest()


# Membaca salinan konsisten staging dan Silver lalu menutup koneksi.
def read_snapshot():
    conn = get_connection()
    try:
        conn.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with conn.cursor() as cursor:
            cursor.execute(STAGING_QUERY)
            articles = cursor.fetchall()
            cursor.execute(SILVER_QUERY)
            existing = cursor.fetchall()
        return (articles, existing)
    finally:
        conn.close()


# Memilih hanya artikel berubah serta token yang perlu dihitung ulang.
def plan_changes(valid_rows, existing, signature=None):
    signature = NLP_SIGNATURE if signature is None else signature
    previous = {row[0]: row for row in existing}
    changed = [row for row in valid_rows if row != previous.get(row[0], ())[:10]]
    contents = {row[0]: row[2] for row in existing}
    contents.update({row[0]: row[2] for row in valid_rows})
    pending = []
    for article_id, content in sorted(contents.items()):
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        state = previous.get(article_id, ())
        if len(state) < 12 or state[10:] != (content_hash, signature):
            pending.append((article_id, content, content_hash, signature))
    return changed, pending


# Menyimpan artikel dan token setelah memastikan sumber belum berubah.
def save_results(articles, existing, valid_rows, token_rows, processing_rows):
    # Buka koneksi baru setelah seluruh pemrosesan NLP selesai.
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '30s'")
            cursor.execute('LOCK TABLE staging.articles IN SHARE MODE')
            cursor.execute("LOCK TABLE silver.articles, silver.article_tokens, silver.article_processing IN SHARE ROW EXCLUSIVE MODE")
            cursor.execute(STAGING_QUERY)
            current_articles = cursor.fetchall()
            cursor.execute(SILVER_QUERY)
            if current_articles != articles or cursor.fetchall() != existing:
                raise RuntimeError("Data sumber berubah selama NLP; ulangi task. ")
            execute_batch(cursor, """
                INSERT INTO silver.articles (
                    article_id,
                    title,
                    content,
                    description,
                    category,
                    author,
                    published_at,
                    article_url,
                    crawled_at,
                    word_count
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (article_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    author = EXCLUDED.author,
                    published_at = EXCLUDED.published_at,
                    article_url = EXCLUDED.article_url,
                    crawled_at = EXCLUDED.crawled_at,
                    word_count = EXCLUDED.word_count,
                    transformed_at = CURRENT_TIMESTAMP

            """, valid_rows, page_size=100)
            article_ids = [row[0] for row in processing_rows]
            if article_ids:
                cursor.execute("DELETE FROM silver.article_tokens WHERE article_id = ANY(%s)", (article_ids,))
            if token_rows:
                execute_batch(cursor, """
                    INSERT INTO silver.article_tokens (article_id, token, frequency)
                    VALUES (%s, %s, %s)
                """, token_rows, page_size=500)
            if processing_rows:
                execute_batch(cursor, """
                    INSERT INTO silver.article_processing (article_id, content_hash, nlp_signature)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (article_id) DO UPDATE SET
                        content_hash = EXCLUDED.content_hash,
                        nlp_signature = EXCLUDED.nlp_signature,
                        processed_at = CURRENT_TIMESTAMP
                """, processing_rows)
        conn.commit()
    except Exception:
        # Pertahankan error asli jika pembatalan transaksi juga gagal.
        with suppress(Exception):
            conn.rollback()
        raise
    finally:
        conn.close()


# Menjalankan preprocessing tanpa koneksi database dan menyimpan hasil Silver.
def main():
    print('TRANSFORM SILVER: PREPROCESSING DATA DAN TEKS NLP', flush=True)
    articles, existing = read_snapshot()
    if not articles:
        raise ValueError('staging.articles kosong')
    print(f'Total staging: {len(articles)}', flush=True)
    valid_rows = []
    rejected_rows = []
    for index, article in enumerate(articles, 1):
        try:
            valid_rows.append(transform_article(article))
        except (ValueError, TypeError) as error:
            rejected_rows.append((index, article[0], str(error)))
            print(f'[DITOLAK] {article[0]}: {error}', flush=True)
    if not valid_rows:
        raise ValueError('Tidak ada artikel valid')

    changed_rows, pending = plan_changes(valid_rows, existing)
    print(f"Artikel berubah: {len(changed_rows)} | Perlu NLP: {len(pending)}", flush=True)
    if not changed_rows and not pending:
        print("SILVER SUDAH TERBARU: tidak ada penulisan database", flush=True)
        return
    print("Koneksi baca ditutup. NLP berjalan tanpa koneksi Neon.", flush=True)
    token_rows, processing_rows = [], []
    total_tokens = empty_articles = 0
    for index, (article_id, content, content_hash, signature) in enumerate(pending, 1):
        frequencies = Counter(preprocess(content))
        count = sum(frequencies.values())
        total_tokens += count
        empty_articles += int(not frequencies)
        token_rows.extend((article_id, token, frequency) for token, frequency in frequencies.items())
        processing_rows.append((article_id, content_hash, signature))
        print(f"[{index}/{len(pending)}] Token: {count}", flush=True)
    print('NLP selesai. Membuka koneksi baru untuk menyimpan hasil...', flush=True)
    save_results(articles, existing, changed_rows, token_rows, processing_rows)
    print('TRANSFORM SILVER BERHASIL', flush=True)
    print(f'Artikel valid: {len(valid_rows)} | Ditolak: {len(rejected_rows)}')
    print(f'Token: {total_tokens} | Baris token: {len(token_rows)}')
    print(f'Artikel tanpa token: {empty_articles}')


if __name__ == "__main__":
    main()
