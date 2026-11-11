
import json
import sys
from pathlib import Path
from datetime import datetime

from psycopg2.extras import execute_batch

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from config.database import get_connection


INPUT_FILE = BASE_DIR / "data" / "bronze" / "bronze_articles.json"

REQUIRED_FIELDS = [
    "article_id",
    "title",
    "content",
    "article_url",
    "published_at",
]


def load_bronze_data():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"File Bronze tidak ditemukan: {INPUT_FILE}"
        )

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        articles = json.load(file)

    if not isinstance(articles, list):
        raise ValueError("Data Bronze harus berupa list artikel.")

    return articles


def validate_article(article):
    if not isinstance(article, dict):
        return False, "Format artikel bukan object"

    for field in REQUIRED_FIELDS:
        if not article.get(field):
            return False, f"Field {field} kosong"

    for field in ["published_at", "crawled_at"]:
        value = article.get(field)

        if value:
            try:
                datetime.fromisoformat(
                    str(value).replace("Z", "+00:00")
                )
            except ValueError:
                return False, f"Format {field} tidak valid"

    try:
        word_count = int(article.get("word_count") or 0)
        if word_count < 0:
            return False, "word_count negatif"
    except (ValueError, TypeError):
        return False, "word_count tidak valid"

    return True, None


def prepare_article(article):
    return (
        article["article_id"],
        article["title"],
        article["content"],
        article.get("description"),
        article.get("category"),
        article.get("author"),
        article.get("published_at"),
        article["article_url"],
        article.get("crawled_at"),
        int(article.get("word_count") or 0),
    )


UPSERT_QUERY = """
INSERT INTO staging.articles (
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
    ingested_at = CURRENT_TIMESTAMP;
"""


def main():
    print("=" * 60)
    print("INGESTION BRONZE JSON -> POSTGRESQL STAGING")
    print("=" * 60)

    articles = load_bronze_data()

    valid_articles = []
    rejected_articles = []
    seen_ids = set()

    for index, article in enumerate(articles, start=1):
        is_valid, error = validate_article(article)

        if not is_valid:
            rejected_articles.append((index, error))
            continue

        article_id = article["article_id"]

        if article_id in seen_ids:
            rejected_articles.append(
                (index, "Duplikasi article_id dalam Bronze")
            )
            continue

        seen_ids.add(article_id)
        valid_articles.append(prepare_article(article))

    print(f"Total Bronze  : {len(articles)}")
    print(f"Data valid    : {len(valid_articles)}")
    print(f"Data ditolak  : {len(rejected_articles)}")

    for index, error in rejected_articles[:10]:
        print(f"[DITOLAK] Artikel #{index}: {error}")

    if not valid_articles:
        print("Tidak ada artikel valid untuk dimasukkan.")
        return

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            execute_batch(
                cursor,
                UPSERT_QUERY,
                valid_articles,
                page_size=100,
            )

        connection.commit()

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM staging.articles"
            )
            total_database = cursor.fetchone()[0]

        print("-" * 60)
        print("INGESTION BERHASIL")
        print(f"Data diproses : {len(valid_articles)}")
        print(f"Total staging : {total_database}")
        print("Tabel         : staging.articles")
        print("=" * 60)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()
