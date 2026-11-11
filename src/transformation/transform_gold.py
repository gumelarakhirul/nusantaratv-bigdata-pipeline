
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

from psycopg2.extras import execute_batch

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from config.database import get_connection


JAKARTA_TZ = ZoneInfo("Asia/Jakarta")


# =========================================
# DATE HELPER
# =========================================

def to_jakarta(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    if value.tzinfo is None:
        raise ValueError(
            "published_at harus memiliki timezone"
        )

    return value.astimezone(JAKARTA_TZ)


def get_date_id(value):
    return int(value.strftime("%Y%m%d"))


# =========================================
# TRANSFORM GOLD
# =========================================

def main():
    print("\n" + "=" * 60)
    print("TRANSFORMATION SILVER -> GOLD")
    print("=" * 60)

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            # ---------------------------------
            # 1. AMBIL ARTIKEL SILVER
            # ---------------------------------

            cursor.execute("""
                SELECT
                    article_id,
                    category,
                    author,
                    published_at,
                    word_count
                FROM silver.articles
                ORDER BY article_id
            """)

            articles = cursor.fetchall()

            if not articles:
                raise ValueError(
                    "silver.articles masih kosong"
                )

            print(f"Total Silver: {len(articles)}")

            # ---------------------------------
            # 2. DIM DATE
            # ---------------------------------

            dates = {}

            for article in articles:
                published = to_jakarta(article[3])
                date_id = get_date_id(published)
                date_value = published.date()

                dates[date_id] = (
                    date_id,
                    date_value,
                    date_value.day,
                    date_value.month,
                    date_value.year,
                    published.strftime("%A"),
                    published.strftime("%B")
                )

            execute_batch(
                cursor,
                """
                INSERT INTO gold.dim_date (
                    date_id,
                    full_date,
                    day,
                    month,
                    year,
                    day_name,
                    month_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date_id)
                DO UPDATE SET
                    full_date = EXCLUDED.full_date,
                    day = EXCLUDED.day,
                    month = EXCLUDED.month,
                    year = EXCLUDED.year,
                    day_name = EXCLUDED.day_name,
                    month_name = EXCLUDED.month_name
                """,
                list(dates.values()),
                page_size=100
            )

            # ---------------------------------
            # 3. DIM CATEGORY
            # ---------------------------------

            categories = sorted({
                article[1]
                for article in articles
                if article[1]
            })

            execute_batch(
                cursor,
                """
                INSERT INTO gold.dim_category (
                    category_name
                )
                VALUES (%s)
                ON CONFLICT (category_name)
                DO NOTHING
                """,
                [(category,) for category in categories],
                page_size=100
            )

            cursor.execute("""
                SELECT category_id, category_name
                FROM gold.dim_category
            """)

            category_map = {
                name: category_id
                for category_id, name in cursor.fetchall()
            }

            # ---------------------------------
            # 4. DIM AUTHOR
            # ---------------------------------

            authors = sorted({
                article[2]
                for article in articles
                if article[2]
            })

            if authors:
                execute_batch(
                    cursor,
                    """
                    INSERT INTO gold.dim_author (
                        author_name
                    )
                    VALUES (%s)
                    ON CONFLICT (author_name)
                    DO NOTHING
                    """,
                    [(author,) for author in authors],
                    page_size=100
                )

            cursor.execute("""
                SELECT author_id, author_name
                FROM gold.dim_author
            """)

            author_map = {
                name: author_id
                for author_id, name in cursor.fetchall()
            }

            # ---------------------------------
            # 5. FACT ARTICLES
            # ---------------------------------

            fact_rows = []

            for (
                article_id,
                category,
                author,
                published_at,
                word_count
            ) in articles:

                published = to_jakarta(published_at)

                fact_rows.append((
                    article_id,
                    get_date_id(published),
                    category_map[category],
                    author_map.get(author),
                    published.hour,
                    word_count,
                    1
                ))

            execute_batch(
                cursor,
                """
                INSERT INTO gold.fact_articles (
                    article_id,
                    date_id,
                    category_id,
                    author_id,
                    published_hour,
                    word_count,
                    article_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (article_id)
                DO UPDATE SET
                    date_id = EXCLUDED.date_id,
                    category_id = EXCLUDED.category_id,
                    author_id = EXCLUDED.author_id,
                    published_hour = EXCLUDED.published_hour,
                    word_count = EXCLUDED.word_count,
                    article_count = EXCLUDED.article_count
                """,
                fact_rows,
                page_size=100
            )

            # ---------------------------------
            # 6. KEYWORD SILVER -> GOLD
            # ---------------------------------

            cursor.execute("""
                SELECT COUNT(*)
                FROM silver.article_tokens
            """)

            total_silver_tokens = cursor.fetchone()[0]

            if total_silver_tokens == 0:
                raise ValueError(
                    "silver.article_tokens kosong. "
                    "Jalankan transform_silver.py dahulu."
                )

            # Hapus keyword lama agar hasil Gold
            # sesuai dengan preprocessing terbaru.
            cursor.execute("""
                DELETE FROM gold.article_keywords
            """)

            cursor.execute("""
                INSERT INTO gold.article_keywords (
                    article_id,
                    keyword,
                    frequency
                )
                SELECT
                    s.article_id,
                    s.token,
                    s.frequency
                FROM silver.article_tokens s
                INNER JOIN gold.fact_articles f
                    ON s.article_id = f.article_id
            """)

            # ---------------------------------
            # 7. VERIFIKASI
            # ---------------------------------

            tables = {
                "Dim Date": "gold.dim_date",
                "Dim Category": "gold.dim_category",
                "Dim Author": "gold.dim_author",
                "Fact Articles": "gold.fact_articles",
                "Article Keywords": "gold.article_keywords"
            }

            results = {}

            for label, table in tables.items():
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table}"
                )
                results[label] = cursor.fetchone()[0]

        conn.commit()

        print("-" * 60)
        print("TRANSFORMATION GOLD BERHASIL")

        for label, count in results.items():
            print(f"{label:18}: {count}")

        print("=" * 60)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
