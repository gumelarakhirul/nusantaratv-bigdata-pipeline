
SELECT
    f.article_id,
    d.full_date AS publication_date,
    d.day_name,
    d.month_name,
    d.year,
    c.category_name AS category,
    COALESCE(a.author_name, 'Tidak diketahui') AS author,
    f.published_hour,
    f.word_count,
    f.article_count
FROM gold.fact_articles f
JOIN gold.dim_date d
    ON f.date_id = d.date_id
JOIN gold.dim_category c
    ON f.category_id = c.category_id
LEFT JOIN gold.dim_author a
    ON f.author_id = a.author_id
ORDER BY d.full_date DESC, f.published_hour DESC;
