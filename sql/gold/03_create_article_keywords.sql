
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.article_keywords (
    article_id VARCHAR(64) NOT NULL
        REFERENCES gold.fact_articles(article_id)
        ON DELETE CASCADE,
    keyword VARCHAR(100) NOT NULL,
    frequency INTEGER NOT NULL CHECK (frequency > 0),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (article_id, keyword)
);

CREATE INDEX IF NOT EXISTS idx_gold_article_keywords_keyword
ON gold.article_keywords(keyword);
