
import re
import sys
from pathlib import Path

from psycopg2.extras import execute_batch

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from config.database import get_connection


def clean_text(value):
    if value is None:
        return None

    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def normalize_category(value):
    text = clean_text(value)
    return text.lower() if text else None


def transform_article(row):
    (
        article_id,
        title,
        content,
        description,
        category,
        author,
        published_at,
        article_url,
        crawled_at,
    ) = row

    title = clean_text(title)
    content = clean_text(content)
    description = clean_text(description)
    category = normalize_category(category)
    author = clean_text(author)
    article_url = clean_text(article_url)

    if not all([
        article_id,
        title,
        content,
        category,
        published_at,
        article_url,
    ]):
        return None

    word_count = len(content.split())

    return (
        article_id,
        title,
        content,
        description,
        category,
        author,
        published_at,
        article_url,
        crawled_at,
        word_count,
    )


UPSERT_SQL = """
INSERT INTO silver.articles (
    article_id, title, content, description,
    category, author, published_at, article_url,
    crawled_at, word_count
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    transformed_at = CURRENT_TIMESTAMP;
"""


def main():
    print("=" * 60)
    print("TRANSFORMATION STAGING -> SILVER")
    print("=" * 60)

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    article_id, title, content, description,
                    category, author, published_at,
                    article_url, crawled_at
                FROM staging.articles
            """)
            rows = cursor.fetchall()

            transformed = []
            rejected = []

            for row in rows:
                result = transform_article(row)

                if result is None:
                    rejected.append(row[0])
                else:
                    transformed.append(result)

            if transformed:
                execute_batch(
                    cursor,
                    UPSERT_SQL,
                    transformed,
                    page_size=100,
                )

            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM silver.articles")
            total_silver = cursor.fetchone()[0]

        print(f"Total staging : {len(rows)}")
        print(f"Data valid    : {len(transformed)}")
        print(f"Data ditolak  : {len(rejected)}")
        print(f"Total silver  : {total_silver}")
        print("=" * 60)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
