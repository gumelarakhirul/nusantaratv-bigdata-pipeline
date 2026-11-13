-- Jalankan sekali dari database maintenance "postgres" di Query Tool.
-- Jika database sudah ada, lewati langkah ini.
-- Jalankan CREATE DATABASE secara terpisah, di luar transaksi.
CREATE DATABASE nusantaratv_dw;

-- Setelah berhasil, pindahkan koneksi Query Tool ke nusantaratv_dw.
-- Jalankan file berikut secara berurutan:
-- 1. staging/01_create_schemas.sql
-- 2. staging/02_create_articles.sql
-- 3. silver/01_create_articles.sql
-- 4. silver/02_create_article_tokens.sql
-- 5. gold/01_create_star_schema.sql
-- 6. gold/03_create_article_keywords.sql
-- gold/02_analytics_dataset.sql adalah query SELECT untuk analisis/ekspor.
