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
|   `-- processed/            # CSV untuk Tableau
|-- tableau/                  # Workbook dashboard
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
untuk memeriksa validasi, commit/rollback, refresh token, crawling, dan ekspor CSV.

## Project Status

| Component | Status |
|---|---|
| Web Crawling | Implemented |
| Bronze Data Storage | Implemented |
| PostgreSQL Ingestion | Implemented |
| Silver Transformation | Implemented |
| Gold Star Schema | Implemented |
| Apache Airflow DAGs | Implemented: four chained DAGs |
| Tableau Dashboard | Workbook tersedia di tableau/ |

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

## Pylance dan dependensi DAG

Python lokal dipakai untuk script pipeline dan pengujian. Airflow, provider,
dan Pendulum tersedia di image Docker Airflow, sehingga interpreter Windows
lokal tidak dapat menyelesaikan import DAG tersebut.

Peringatan import DAG dari Pylance lokal dapat muncul karena dependensi
berada di Docker. Validasi import DAG dilakukan dalam container dengan
`docker compose exec airflow airflow dags list-import-errors`.

Untuk analisis lengkap dan autocomplete DAG, gunakan VS Code yang terhubung ke
container Airflow melalui Dev Containers.

## Fungsi masing-masing file

| File | Fungsi |
|---|---|
| `README.md` | Panduan instalasi, menjalankan pipeline, Airflow, pengujian, dan refresh Tableau. |
| `.env` | Konfigurasi dan password lokal; tidak masuk Git. |
| `.env.example` | Contoh variabel konfigurasi tanpa password asli. |
| `.gitignore` | Mengecualikan rahasia, dataset, cache, dan file sementara dari Git. |
| `.dockerignore` | Membatasi file yang dikirim saat build image Airflow. |
| `requirements.txt` | Dependensi script Python yang dijalankan lokal. |
| `docker-compose.yml` | Menjalankan warehouse PostgreSQL, database metadata, dan Airflow. |
| `docker/airflow.Dockerfile` | Membangun image Airflow beserta dependensi pipeline. |
| `docker/requirements-airflow.txt` | Dependensi pipeline di container, mengikuti constraints Airflow. |
| `config/database.py` | Membaca konfigurasi dan membuka koneksi PostgreSQL. |
| `dags/news_pipeline.py` | Mendefinisikan empat DAG, jadwal, retry, dan pemicu antartahap. |
| `src/crawling/crawler.py` | Mengumpulkan URL artikel dari pagination situs. |
| `src/crawling/article_parser.py` | Mengekstrak isi dan metadata dari HTML artikel. |
| `src/crawling/scrape_details.py` | Mengambil halaman artikel, retry, dan menyimpan checkpoint JSON. |
| `src/ingestion/initialize_schema.py` | Menjalankan SQL pembuatan schema dan tabel yang belum ada. |
| `src/ingestion/ingest_articles.py` | Memvalidasi JSON Bronze dan upsert artikel ke staging. |
| `src/transformation/transform_silver.py` | Membersihkan artikel, menghitung kata, dan membuat token NLP. |
| `src/transformation/transform_gold.py` | Mengisi dimensi, fakta artikel, dan keyword Gold. |
| `src/analytics/export_analytics.py` | Memeriksa konsistensi warehouse dan mengekspor dua CSV Tableau. |
| `sql/staging/01_create_schemas.sql` | Membuat schema staging, Silver, dan Gold. |
| `sql/staging/02_create_articles.sql` | Membuat tabel artikel staging. |
| `sql/silver/01_create_articles.sql` | Membuat tabel artikel bersih. |
| `sql/silver/02_create_article_tokens.sql` | Membuat tabel token, frekuensi, dan relasinya ke artikel Silver. |
| `sql/gold/01_create_star_schema.sql` | Membuat dimensi tanggal, kategori, penulis, dan fakta artikel. |
| `sql/gold/02_analytics_dataset.sql` | Query gabungan fakta dan dimensi untuk ekspor analytics; dipakai exporter. |
| `sql/gold/03_create_article_keywords.sql` | Membuat tabel keyword Gold dan relasinya ke fakta artikel. |
| `tests/test_pipeline.py` | Menguji validasi, NLP, timezone, refresh token, dan transaksi. |
| `tests/test_automation.py` | Menguji cursor crawling, kegagalan scraping, dan validasi/ekspor analytics. |
| `data/bronze/bronze_article_urls.json` | Daftar URL input untuk scraper detail. |
| `data/bronze/bronze_articles.json` | Detail artikel serta checkpoint untuk ingestion. |
| `data/bronze/scraping_errors.json` | Catatan artikel gagal agar bisa ditelusuri dan dicoba lagi. |
| `data/processed/nusantaratv_analytics.csv` | Sumber grafik artikel, KPI, kategori, penulis, dan heatmap. |
| `data/processed/nusantaratv_keywords.csv` | Sumber visualisasi keyword. |
| `tableau/Tableau Big Data.twb` | Definisi worksheet, kalkulasi, koneksi CSV, dan dashboard Tableau. |

Database tersimpan dalam Docker volume, bukan folder `data`. File `.twb`
menyimpan definisi dashboard dan merujuk CSV; jangan menghapus CSV sumbernya.

## Setup database manual melalui SQL

Di pgAdmin atau aplikasi SQL lain, buka Query Tool pada database `postgres`.
Jalankan `sql/00_create_database.sql` untuk membuat `nusantaratv_dw`.
Lewati CREATE DATABASE bila database sudah ada. Sesuaikan nama database
jika `DB_NAME` di `.env` berbeda.

Pindahkan koneksi Query Tool ke `nusantaratv_dw`, lalu jalankan:

1. `sql/staging/01_create_schemas.sql`
2. `sql/staging/02_create_articles.sql`
3. `sql/silver/01_create_articles.sql`
4. `sql/silver/02_create_article_tokens.sql`
5. `sql/gold/01_create_star_schema.sql`
6. `sql/gold/03_create_article_keywords.sql`

Semua file memakai SQL biasa. `sql/gold/02_analytics_dataset.sql` adalah
query SELECT untuk analisis dan ekspor, bukan pembuatan tabel.
Setup manual ini tidak mengubah inisialisasi tabel yang sudah dipakai DAG.
