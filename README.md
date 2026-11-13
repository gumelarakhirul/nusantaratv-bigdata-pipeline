# Nusantara TV Big Data Pipeline

End-to-end Big Data pipeline for collecting, processing, storing, and analyzing news articles from [Nusantara TV](https://www.nusantaratv.com/).

## Project Overview

Proyek ini bertujuan membangun sistem pengolahan data berita secara terstruktur, mulai dari pengambilan data melalui web crawling hingga penyajian informasi menggunakan dashboard interaktif.

Pipeline dirancang menggunakan Python, Requests, BeautifulSoup, PostgreSQL, Apache Airflow, dan Tableau.

## System Architecture

```text
Nusantara TV Website
         |
         v
DAG 1: Crawling
Python + Requests + BeautifulSoup
         |
         v
Bronze Layer
Raw JSON
         |
         v
DAG 2: Ingestion
Validation + PostgreSQL Staging
         |
         v
DAG 3: Transformation
Cleaning + Deduplication
         |
         v
Silver Layer
Cleaned Data
         |
         v
Gold Layer
Star Schema
         |
         v
DAG 4: Analytics
Aggregation + Analytical Queries
         |
         v
Tableau Dashboard
```

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Data processing and ETL |
| Requests | HTTP requests |
| BeautifulSoup | HTML parsing |
| PostgreSQL | Data storage and warehouse |
| Apache Airflow | Workflow orchestration |
| Tableau | Data visualization |
| Git & GitHub | Version control |

## Data Collection

Data berita yang dikumpulkan meliputi:

- Article ID
- Title
- Content
- Category
- Author
- Publication Date
- Article URL
- Crawling Timestamp
- Word Count

Nama penulis diambil dari informasi penulis artikel yang tersedia pada halaman. Artikel tanpa informasi penulis tetap dapat disimpan dengan nilai `NULL`.

## Data Warehouse

Data warehouse menggunakan pendekatan **Star Schema**.

**Fact Table:**
- `fact_articles`

**Dimension Tables:**
- `dim_date`
- `dim_category`
- `dim_author`

Model ini dirancang untuk mendukung analisis tren berita berdasarkan tanggal, kategori, waktu publikasi, dan penulis.

## Data Analytics & Visualization

Dashboard Tableau direncanakan menampilkan:

1. Daily News Publication Trends
2. News Distribution by Category
3. Publication Activity by Day and Hour
4. Top 10 News Authors
5. Most Frequent Keywords

## Project Structure

```text
nusantaratv-bigdata/
|-- config/                   # Koneksi database
|-- dags/                     # Definisi 4 DAG Airflow
|-- docker/                   # Dockerfile dan dependensi Airflow
|-- scripts/diagnostics/       # Pemeriksaan jaringan manual
|-- src/
|   |-- crawling/             # URL dan detail artikel
|   |-- ingestion/            # Inisialisasi schema dan ingestion
|   |-- transformation/       # Silver dan Gold
|   `-- analytics/            # Validasi dan ekspor CSV
|-- sql/
|   |-- staging/
|   |-- silver/
|   `-- gold/
|-- data/
|   |-- bronze/               # JSON hasil crawling
|   |-- processed/            # CSV untuk Tableau
|   `-- diagnostics/          # HTML pemeriksaan manual (dibuat saat dipakai)
|-- tableau/                  # Workbook dan dokumentasi visualisasi
|-- tests/                    # Pengujian otomatis tanpa jaringan
|-- .env.example
|-- docker-compose.yml
|-- requirements.txt
`-- README.md
```

## Menjalankan Pipeline

Gunakan Python 3.10+ dan instal dependensi dengan `python -m pip install -r requirements.txt`.
Siapkan `.env` berisi `DB_HOST`, `DB_PORT` (default `5433`), `DB_NAME`,
`DB_USER`, dan `DB_PASSWORD`, lalu jalankan PostgreSQL dengan `docker compose up -d`.
Buat tabel dengan menjalankan SQL staging, Silver, dan Gold sesuai nomor urut
(di setiap layer); `sql/gold/02_analytics_dataset.sql` merupakan query analitik.

Jalankan dari root proyek:

```powershell
python -m src.crawling.crawler
python -m src.crawling.scrape_details
python -m src.ingestion.ingest_articles
python -m src.transformation.transform_silver
python -m src.transformation.transform_gold
```

Crawler, scraper, dan ingestion menggunakan `data/bronze/` dengan path absolut
berdasarkan lokasi proyek. Timestamp input harus menyertakan timezone.
Silver membangun ulang token dari seluruh artikel Silver yang tersimpan dalam
satu transaksi dengan pembaruan artikel. Artikel lama tetap dipertahankan bila
input staging ditolak; token dihitung dari konten Silver terakhir yang valid.
Gold menyegarkan keyword dari token Silver, termasuk ketika hasil token kosong.

## Pengujian

```powershell
python -m unittest discover -s tests -v
```

Pengujian otomatis berjalan tanpa jaringan atau PostgreSQL, menggunakan mock
untuk memeriksa commit/rollback dan refresh token. Pemeriksaan koneksi situs
bersifat manual: `python scripts/diagnostics/check_connection.py` dan
`python scripts/diagnostics/check_loadmore.py`.

## Project Status

| Component | Status |
|---|---|
| Web Crawling | In development |
| Bronze Data Storage | Initial implementation |
| PostgreSQL Ingestion | Implemented |
| Silver Transformation | Implemented |
| Gold Star Schema | Implemented |
| Apache Airflow DAGs | Implemented: four chained DAGs |
| Tableau Dashboard | Planned |

## Disclaimer

This project is developed for educational purposes. News content belongs to its respective publishers. Data collection should respect website access policies and applicable usage restrictions.

## Otomatisasi Airflow (4 DAG)

Airflow 3.3.1 memakai mode standalone dalam container Linux untuk proyek lokal.
Database metadata Airflow terpisah dari warehouse; UI hanya dibuka di localhost.

1. Pastikan Docker Desktop memakai Linux containers.
2. Lengkapi `.env` sesuai `.env.example` tanpa menimpa konfigurasi database lama.
   `AIRFLOW_DB_PASSWORD` harus acak alfanumerik agar dapat dipakai dalam URI.
3. Jalankan:

```powershell
docker compose up -d --build
```

Buka http://localhost:18080 dan login sebagai `admin`. Password dibuat otomatis.
Lihat secara lokal (jangan bagikan outputnya):

```powershell
docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

Unpause **keempat DAG**, kemudian trigger hanya `ntv_01_crawling`.
DAG awal dijadwalkan setiap hari **07.00 WIB**, tanpa catchup.

```text
ntv_01_crawling        collect_urls -> scrape_details
       |
ntv_02_ingestion       initialize_schema -> ingest_articles
       |
ntv_03_transformation  transform_silver -> transform_gold
       |
ntv_04_analytics       validate_and_export
```

DAG induk menunggu seluruh rantai selesai sehingga run terjadwal berikutnya
menunggu file Bronze selesai digunakan. Jangan trigger downstream secara
terpisah selama rantai berjalan. Task pengolahan retry dua kali, jeda lima
menit. Scraping tidak lengkap menyebabkan task gagal; retry melanjutkan
checkpoint. Setelah memperbaiki kegagalan, clear task gagal pada DAG terkait.
Clear task `trigger_next_dag` akan mereset run downstream terkait untuk diulang.

Crawler memulai pagination dengan cursor kosong untuk batch terbaru, kemudian
mengikuti tombol Load More. Maksimum 200 URL per run; pengambilan ini tidak
menjamin semua berita di antara jadwal tercakup. Artikel tersimpan tidak
diambil ulang. Ingestion membuat tabel yang belum ada tanpa menghapus data;
perubahan struktur tabel lama tetap memerlukan migrasi tersendiri.

Analytics memvalidasi artikel antarlayer, dimensi fakta, dan kesamaan keyword,
lalu menghasilkan dua CSV UTF-8 untuk Tableau:

- `data/processed/nusantaratv_analytics.csv`
- `data/processed/nusantaratv_keywords.csv`

Setiap CSV dipublikasikan melalui penggantian file atomik. Kedua CSV tidak
diganti dalam satu transaksi filesystem. Refresh Tableau Server/Cloud belum
termasuk otomatisasi ini.

Validasi DAG di dalam container:

```powershell
docker compose exec airflow airflow dags list-import-errors
docker compose exec airflow airflow dags list
```

## Memperbarui data di Tableau

Airflow memperbarui kedua CSV di `data/processed` secara otomatis.
Tableau menggunakan CSV tersebut; setelah pipeline selesai, pilih
**Data -> nusantaratv_analytics -> Refresh** dan
**Data -> nusantaratv_keywords -> Refresh**. Refresh Tableau dilakukan manual.
