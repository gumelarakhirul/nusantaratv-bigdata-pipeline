
import re
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

def main():
    print("\n" + "=" * 60)
    print("TRANSFORM SILVER: CLEANING + NLP")
    print("=" * 60)

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            # ---------------------------------
            # A. AMBIL DATA STAGING
            # ---------------------------------

            cursor.execute("""
                SELECT
                    article_id,
                    title,
                    content,
                    description,
                    category,
                    author,
                    published_at,
                    article_url,
                    crawled_at
                FROM staging.articles
                ORDER BY article_id
            """)

            articles = cursor.fetchall()

            if not articles:
                raise ValueError(
                    "staging.articles kosong"
                )

            print(f"Total staging: {len(articles)}")

            # ---------------------------------
            # B. DATA CLEANING
            # ---------------------------------

            valid_rows = []
            rejected = 0

            for article in articles:
                try:
                    valid_rows.append(
                        transform_article(article)
                    )
                except (ValueError, TypeError) as error:
                    rejected += 1
                    print(
                        f"[DITOLAK] {article[0]}: {error}"
                    )

            if not valid_rows:
                raise ValueError(
                    "Tidak ada artikel valid"
                )

            execute_batch(
                cursor,
                """
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
                """,
                valid_rows,
                page_size=100
            )

            print(
                f"Cleaning berhasil: {len(valid_rows)} artikel"
            )
            print(f"Data ditolak: {rejected}")

            # ---------------------------------
            # C. NLP PREPROCESSING
            # ---------------------------------

            print("\nMemulai NLP Preprocessing...")

            # Rebuild from all persisted Silver articles, including older rows.
            cursor.execute("SELECT article_id, content FROM silver.articles ORDER BY article_id")
            nlp_articles = cursor.fetchall()

            token_rows = []
            total_tokens = 0
            empty_articles = 0

            for index, article in enumerate(
                nlp_articles, start=1
            ):
                article_id = article[0]
                content = article[1]

                tokens = preprocess(content)
                frequencies = Counter(tokens)

                total_tokens += len(tokens)

                if not tokens:
                    empty_articles += 1

                for token, frequency in frequencies.items():
                    token_rows.append((
                        article_id,
                        token,
                        frequency
                    ))

                print(
                    f"[{index}/{len(nlp_articles)}] "
                    f"Tokens: {len(tokens)} | "
                    f"Unique: {len(frequencies)}",
                    flush=True
                )

            # Refresh hasil NLP.
            cursor.execute("""
                DELETE FROM silver.article_tokens
            """)

            if token_rows:
                execute_batch(
                    cursor,
                    """
                    INSERT INTO silver.article_tokens (
                        article_id,
                        token,
                        frequency
                    )
                    VALUES (%s, %s, %s)
                    """,
                    token_rows,
                    page_size=500
                )

        # Cleaning dan NLP berhasil bersama-sama
        # atau keduanya di-rollback jika terjadi error.
        conn.commit()

        print("\n" + "=" * 60)
        print("TRANSFORM SILVER BERHASIL")
        print("=" * 60)
        print(f"Artikel valid       : {len(valid_rows)}")
        print(f"Artikel ditolak     : {rejected}")
        print(f"Total token NLP     : {total_tokens}")
        print(f"Baris article_tokens: {len(token_rows)}")
        print(f"Artikel tanpa token : {empty_articles}")
        print("=" * 60)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
