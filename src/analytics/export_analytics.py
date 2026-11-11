"""Validate warehouse consistency and atomically publish Tableau CSVs."""
from pathlib import Path
from config.database import get_connection

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "data" / "processed"
CHECKS = {
    "staging_without_silver": "SELECT COUNT(*) FROM staging.articles s LEFT JOIN silver.articles v USING(article_id) WHERE v.article_id IS NULL",
    "silver_gold_article_mismatch": "SELECT COUNT(*) FROM silver.articles s FULL JOIN gold.fact_articles f USING(article_id) WHERE s.article_id IS NULL OR f.article_id IS NULL",
    "keyword_mismatch": "SELECT COUNT(*) FROM silver.article_tokens s FULL JOIN gold.article_keywords g ON s.article_id=g.article_id AND s.token=g.keyword WHERE s.article_id IS NULL OR g.article_id IS NULL OR s.frequency<>g.frequency",
    "fact_mismatch": "SELECT COUNT(*) FROM silver.articles s JOIN gold.fact_articles f USING(article_id) JOIN gold.dim_category c USING(category_id) LEFT JOIN gold.dim_author a USING(author_id) WHERE s.word_count<>f.word_count OR s.category<>c.category_name OR s.author IS DISTINCT FROM a.author_name OR f.date_id<>TO_CHAR(s.published_at AT TIME ZONE 'Asia/Jakarta','YYYYMMDD')::integer OR f.published_hour<>EXTRACT(HOUR FROM s.published_at AT TIME ZONE 'Asia/Jakarta')",
}


def validate(cursor):
    cursor.execute("SELECT COUNT(*) FROM gold.fact_articles")
    if cursor.fetchone()[0] == 0:
        raise ValueError("Gold kosong; ekspor dibatalkan")
    for name, query in CHECKS.items():
        cursor.execute(query)
        count = cursor.fetchone()[0]
        if count:
            raise ValueError(f"Quality check {name}: {count} baris tidak sesuai")


def main():
    conn = get_connection()
    pending = []
    try:
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with conn.cursor() as cursor:
            validate(cursor)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            queries = {
                "nusantaratv_analytics.csv": (BASE_DIR / "sql/gold/02_analytics_dataset.sql").read_text(encoding="utf-8").strip().rstrip(";"),
                "nusantaratv_keywords.csv": "SELECT article_id, keyword, frequency FROM gold.article_keywords ORDER BY article_id, keyword",
            }
            for filename, query in queries.items():
                target = OUTPUT_DIR / filename
                temp = target.with_suffix(".csv.tmp")
                pending.append((temp, target))
                with temp.open("w", encoding="utf-8", newline="") as output:
                    cursor.copy_expert(f"COPY ({query}) TO STDOUT WITH CSV HEADER", output)
        conn.commit()
        for temp, target in pending:
            temp.replace(target)
            print(f"Exported: {target}")
    except Exception:
        conn.rollback()
        raise
    finally:
        for temp, _ in pending:
            temp.unlink(missing_ok=True)
        conn.close()


if __name__ == "__main__":
    main()
