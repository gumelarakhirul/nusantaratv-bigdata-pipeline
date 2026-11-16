
import re
import hashlib
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


# =========================================
# KONFIGURASI NLP
# =========================================

stemmer = StemmerFactory().create_stemmer()

stopwords = set(
    StopWordRemoverFactory().get_stop_words()
)

# Stopword tambahan khusus analisis berita
custom_stopwords = {
    "ujar", "kata", "ungkap", "tutur",
    "jelas", "sebut", "imbuh",
    "jadi", "laku", "lalu", "hingga",
    "lebih", "butuh", "jumlah",
    "nusantaratv", "com", "www",
    "baca", "artikel", "berita"
}

stopwords.update(custom_stopwords)

MIN_WORD_LENGTH = 3

# =========================================
# 1. DATA CLEANING
# =========================================

def clean_field(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+", " ", str(value)
    ).strip()


def parse_datetime(value):
    if not isinstance(value, datetime):
        if not value:
            raise ValueError("Tanggal kosong")
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.utcoffset() is None:
        raise ValueError("Tanggal harus memiliki timezone")
    return value


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
        raise ValueError(
            "Kolom wajib tidak lengkap"
        )

    published_at = parse_datetime(published_at)

    crawled_at = (
        parse_datetime(crawled_at)
        if crawled_at else None
    )

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


# =========================================
# 2. NLP PREPROCESSING
# =========================================

def case_folding(text):
    return (text or "").lower()


def clean_nlp_text(text):
    text = re.sub(
        r"https?://\S+|www\.\S+",
        " ",
        text
    )

    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def tokenize(text):
    return text.split()


def remove_stopwords(tokens):
    return [
        token
        for token in tokens
        if token not in stopwords
        and len(token) >= MIN_WORD_LENGTH
    ]


@lru_cache(maxsize=50000)
def stem_word(word):
    # Preserve meaning before stemming conflates these distinct words.
    if word in {"perintah", "pemerintah", "pemerintahan"}:
        return "pemerintah" if word != "perintah" else "perintah"
    return stemmer.stem(word)


def stemming(tokens):
    return [
        stem_word(token)
        for token in tokens
    ]


def preprocess(text):
    # Case folding
    text = case_folding(text)

    # Text cleaning
    text = clean_nlp_text(text)

    # Tokenization
    tokens = tokenize(text)

    # Stopword removal sebelum stemming
    tokens = remove_stopwords(tokens)

    # Stemming
    tokens = stemming(tokens)

    # Stopword removal setelah stemming
    tokens = remove_stopwords(tokens)

    return [
        token
        for token in tokens
        if len(token) <= 100
    ]


# =========================================
# 3. TRANSFORM SILVER PIPELINE
# =========================================

STAGING_QUERY = """
    SELECT article_id, title, content, description, category, author,
           published_at, article_url, crawled_at
    FROM staging.articles ORDER BY article_id
"""
SILVER_QUERY = "SELECT article_id, content FROM silver.articles ORDER BY article_id"
CACHE_DIR = BASE_DIR / "data" / "processed" / "nlp_cache"
# Source/dependency changes invalidate cached NLP automatically.
NLP_SIGNATURE = hashlib.sha256(
    Path(__file__).read_bytes() + version("Sastrawi").encode()
).hexdigest()


def get_frequencies(content):
    key = hashlib.sha256((NLP_SIGNATURE + content).encode("utf-8")).hexdigest()
    path = CACHE_DIR / (key + ".json")
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(cached, dict) and all(
            isinstance(token, str) and 0 < len(token) <= 100
            and type(count) is int and count > 0
            for token, count in cached.items()
        ):
            return Counter(cached), True
    except (OSError, ValueError):
        pass
    frequencies = Counter(preprocess(content))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(frequencies, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)
    return frequencies, False


def read_snapshot():
    conn = get_connection()
    try:
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with conn.cursor() as cursor:
            cursor.execute(STAGING_QUERY)
            articles = cursor.fetchall()
            cursor.execute(SILVER_QUERY)
            existing = cursor.fetchall()
        return articles, existing
    finally:
        conn.close()


def save_results(articles, existing, valid_rows, token_rows):
    # Open a NEW connection only after all CPU-heavy NLP has finished.
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '30s'")
            cursor.execute("LOCK TABLE staging.articles IN SHARE MODE")
            cursor.execute("LOCK TABLE silver.articles, silver.article_tokens IN SHARE ROW EXCLUSIVE MODE")
            cursor.execute(STAGING_QUERY)
            current_articles = cursor.fetchall()
            cursor.execute(SILVER_QUERY)
            if current_articles != articles or cursor.fetchall() != existing:
                raise RuntimeError("Data sumber berubah selama NLP; ulangi task. Cache NLP tetap tersedia.")
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
            cursor.execute("DELETE FROM silver.article_tokens")
            if token_rows:
                execute_batch(cursor, """
                    INSERT INTO silver.article_tokens (article_id, token, frequency)
                    VALUES (%s, %s, %s)
                """, token_rows, page_size=500)
        conn.commit()
    except Exception:
        # Do not replace the original connection error with a rollback error.
        with suppress(Exception):
            conn.rollback()
        raise
    finally:
        conn.close()


def main():
    print("TRANSFORM SILVER: CLEANING + NLP", flush=True)
    articles, existing = read_snapshot()
    if not articles:
        raise ValueError("staging.articles kosong")
    print(f"Total staging: {len(articles)}", flush=True)
    valid_rows = []
    rejected = 0
    for article in articles:
        try:
            valid_rows.append(transform_article(article))
        except (ValueError, TypeError) as error:
            rejected += 1
            print(f"[DITOLAK] {article[0]}: {error}", flush=True)
    if not valid_rows:
        raise ValueError("Tidak ada artikel valid")

    # Preserve retained Silver articles, but use newly cleaned content for upserts.
    nlp_articles = dict(existing)
    nlp_articles.update({row[0]: row[2] for row in valid_rows})
    print("Koneksi baca ditutup. NLP berjalan offline dengan cache.", flush=True)
    token_rows = []
    total_tokens = empty_articles = cache_hits = 0
    for index, (article_id, content) in enumerate(sorted(nlp_articles.items()), 1):
        frequencies, cached = get_frequencies(content)
        cache_hits += int(cached)
        count = sum(frequencies.values())
        total_tokens += count
        empty_articles += int(not frequencies)
        token_rows.extend((article_id, token, frequency)
                          for token, frequency in frequencies.items())
        print(f"[{index}/{len(nlp_articles)}] Tokens: {count} | "
              f"Unique: {len(frequencies)} | Cache: {cached}", flush=True)
    print("NLP selesai. Membuka koneksi baru untuk menyimpan hasil...", flush=True)
    save_results(articles, existing, valid_rows, token_rows)
    print("TRANSFORM SILVER BERHASIL", flush=True)
    print(f"Artikel valid: {len(valid_rows)} | Ditolak: {rejected}")
    print(f"Token: {total_tokens} | Baris token: {len(token_rows)}")
    print(f"Artikel tanpa token: {empty_articles} | Cache hit: {cache_hits}")


if __name__ == "__main__":
    main()
