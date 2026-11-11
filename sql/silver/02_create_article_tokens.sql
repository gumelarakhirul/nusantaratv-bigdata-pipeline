
CREATE TABLE IF NOT EXISTS silver.article_tokens (
    article_id VARCHAR(64) NOT NULL
        REFERENCES silver.articles(article_id)
        ON DELETE CASCADE,
    token VARCHAR(100) NOT NULL,
    frequency INTEGER NOT NULL CHECK (frequency > 0),
    processed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (article_id, token)
);

CREATE INDEX IF NOT EXISTS idx_silver_tokens
ON silver.article_tokens(token);
