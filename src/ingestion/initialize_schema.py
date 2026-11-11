"""Create missing warehouse tables without deleting existing data."""
from pathlib import Path
from config.database import get_connection

BASE_DIR = Path(__file__).resolve().parents[2]
DDL_FILES = [
    "staging/01_create_schemas.sql", "staging/02_create_articles.sql",
    "silver/01_create_articles.sql", "silver/02_create_article_tokens.sql",
    "gold/01_create_star_schema.sql", "gold/03_create_article_keywords.sql",
]


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for name in DDL_FILES:
                cursor.execute((BASE_DIR / "sql" / name).read_text(encoding="utf-8"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
