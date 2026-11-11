
CREATE TABLE IF NOT EXISTS staging.articles (
    article_id VARCHAR(64) PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    description TEXT,
    category VARCHAR(100),
    author VARCHAR(255),
    published_at TIMESTAMPTZ,
    article_url TEXT NOT NULL,
    crawled_at TIMESTAMPTZ,
    word_count INTEGER,
    ingested_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
