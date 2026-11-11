
import re
import sys
from pathlib import Path
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


# ==========================================
# KONFIGURASI NLP
# ==========================================

stemmer = StemmerFactory().create_stemmer()

stopwords = set(
    StopWordRemoverFactory().get_stop_words()
)

custom_stopwords = {
    "ujar", "kata", "ungkap", "tutur",
    "jelas", "sebut", "imbuh",
    "nusantaratv", "com",
    "baca", "artikel", "berita"
}

stopwords.update(custom_stopwords)

MIN_WORD_LENGTH = 3


# ==========================================
# FUNGSI PREPROCESSING
# ==========================================

def case_folding(text):
    return (text or "").lower()


def clean_text(text):
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text):
    return text.split()


def remove_stopwords(tokens):
    return [
        token for token in tokens
        if token not in stopwords
        and len(token) >= MIN_WORD_LENGTH
    ]


@lru_cache(maxsize=50000)
def stem_word(word):
    return stemmer.stem(word)


def stemming(tokens):
    return [stem_word(word) for word in tokens]


def preprocess(text):
    text = case_folding(text)
    text = clean_text(text)

    tokens = tokenize(text)
    tokens = remove_stopwords(tokens)
    tokens = stemming(tokens)

    return [
        token for token in tokens
        if token not in stopwords
        and len(token) >= MIN_WORD_LENGTH
    ]


# ==========================================
# SIMPAN HASIL NLP KE SILVER
# ==========================================

def main():
    print("=" * 60)
    print("NLP PREPROCESSING SILVER")
    print("=" * 60)

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT article_id, content
                FROM silver.articles
                ORDER BY article_id
            """)

            articles = cursor.fetchall()

            if not articles:
                raise ValueError("silver.articles kosong.")

            print(f"Total artikel : {len(articles)}")

            rows = []
            total_tokens = 0
            processed_articles = 0

            for index, (article_id, content) in enumerate(
                articles, start=1
            ):
                tokens = preprocess(content)
                frequencies = Counter(tokens)

                total_tokens += len(tokens)

                for token, frequency in frequencies.items():
                    if len(token) <= 100:
                        rows.append((
                            article_id,
                            token,
                            frequency
                        ))

                processed_articles += 1

                print(
                    f"[{index}/{len(articles)}] "
                    f"Token: {len(tokens)} | "
                    f"Unik: {len(frequencies)}",
                    flush=True
                )

            # Sinkronisasi ulang hasil preprocessing
            cursor.execute("""
                DELETE FROM silver.article_tokens
            """)

            if rows:
                execute_batch(cursor, """
                    INSERT INTO silver.article_tokens (
                        article_id,
                        token,
                        frequency
                    )
                    VALUES (%s, %s, %s)
                """, rows, page_size=500)

            conn.commit()

            print("-" * 60)
            print("NLP PREPROCESSING BERHASIL")
            print(f"Artikel diproses : {processed_articles}")
            print(f"Total token      : {total_tokens}")
            print(f"Baris token unik : {len(rows)}")
            print("=" * 60)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
