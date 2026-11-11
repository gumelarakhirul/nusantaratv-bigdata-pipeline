
import sys
from pathlib import Path
from datetime import timezone, timedelta

from psycopg2.extras import execute_batch

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from config.database import get_connection


JAKARTA_TZ = timezone(timedelta(hours=7))


def main():
    print("=" * 60)
    print("TRANSFORMATION SILVER -> GOLD")
    print("=" * 60)

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            # 1. Ambil artikel dari Silver
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
                raise ValueError("Silver kosong. Tidak ada artikel.")

            print(f"Total Silver : {len(articles)}")

            # 2. Siapkan data dimensi
            dates = {}
            categories = set()
            authors = set()
            facts = []

            for (
                article_id,
                category,
                author,
                published_at,
                word_count
            ) in articles:

                if published_at is None:
                    raise ValueError(
                        f"published_at kosong: {article_id}"
                    )

                local_dt = published_at.astimezone(JAKARTA_TZ)
                local_date = local_dt.date()

                date_id = int(local_date.strftime("%Y%m%d"))

                dates[date_id] = (
                    date_id,
                    local_date,
                    local_date.day,
                    local_date.month,
                    local_date.year,
                    local_date.strftime("%A"),
                    local_date.strftime("%B")
                )

                category = (category or "unknown").strip().lower()
                author = (author or "").strip() or None

                categories.add(category)

                if author:
                    authors.add(author)

                facts.append((
                    article_id,
                    date_id,
                    category,
                    author,
                    local_dt.hour,
                    word_count
                ))

            # 3. Isi dim_date
            execute_batch(cursor, """
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
            """, list(dates.values()))

            # 4. Isi dim_category
            execute_batch(cursor, """
                INSERT INTO gold.dim_category (category_name)
                VALUES (%s)
                ON CONFLICT (category_name) DO NOTHING
            """, [(c,) for c in sorted(categories)])

            # 5. Isi dim_author
            if authors:
                execute_batch(cursor, """
                    INSERT INTO gold.dim_author (author_name)
                    VALUES (%s)
                    ON CONFLICT (author_name) DO NOTHING
                """, [(a,) for a in sorted(authors)])

            # 6. Ambil mapping ID dimensi
            cursor.execute("""
                SELECT category_id, category_name
                FROM gold.dim_category
            """)
            category_map = {
                name: category_id
                for category_id, name in cursor.fetchall()
            }

            cursor.execute("""
                SELECT author_id, author_name
                FROM gold.dim_author
            """)
            author_map = {
                name: author_id
                for author_id, name in cursor.fetchall()
            }

            # 7. Susun data fact_articles
            fact_rows = []

            for (
                article_id,
                date_id,
                category,
                author,
                published_hour,
                word_count
            ) in facts:

                fact_rows.append((
                    article_id,
                    date_id,
                    category_map[category],
                    author_map.get(author) if author else None,
                    published_hour,
                    word_count,
                    1
                ))

            # 8. Isi fact_articles
            execute_batch(cursor, """
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
            """, fact_rows)

            # 9. Validasi hasil
            cursor.execute("""
                SELECT COUNT(*) FROM gold.fact_articles
            """)
            total_gold = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM gold.dim_date
            """)
            total_dates = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM gold.dim_category
            """)
            total_categories = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM gold.dim_author
            """)
            total_authors = cursor.fetchone()[0]

            conn.commit()

        print("-" * 60)
        print("TRANSFORMATION GOLD BERHASIL")
        print(f"Dim Date     : {total_dates}")
        print(f"Dim Category : {total_categories}")
        print(f"Dim Author   : {total_authors}")
        print(f"Fact Articles: {total_gold}")
        print("=" * 60)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
