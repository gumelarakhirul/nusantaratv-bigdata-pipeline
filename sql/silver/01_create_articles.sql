
CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.articles (
    article_id VARCHAR(64) PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    description TEXT,
    category VARCHAR(100) NOT NULL,
    author VARCHAR(255),
    published_at TIMESTAMPTZ NOT NULL,
    article_url TEXT NOT NULL,
    crawled_at TIMESTAMPTZ,
    word_count INTEGER NOT NULL CHECK (word_count >= 0),
    transformed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
