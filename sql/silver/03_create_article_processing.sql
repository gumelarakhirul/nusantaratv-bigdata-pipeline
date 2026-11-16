-- Status pemrosesan membedakan token kosong yang valid dari artikel belum diproses.
CREATE TABLE IF NOT EXISTS silver.article_processing (
    article_id VARCHAR(64) PRIMARY KEY REFERENCES silver.articles(article_id) ON DELETE CASCADE,
    content_hash VARCHAR(64) NOT NULL,
    nlp_signature VARCHAR(64) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
