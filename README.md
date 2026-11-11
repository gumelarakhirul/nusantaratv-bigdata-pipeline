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
├── config/
├── dags/
├── src/
│   ├── crawling/
│   ├── ingestion/
│   ├── transformation/
│   └── analytics/
├── sql/
│   ├── bronze/
│   ├── staging/
│   ├── silver/
│   └── gold/
├── data/
│   ├── raw/
│   └── processed/
├── logs/
├── tests/
├── tableau/
├── .gitignore
├── requirements.txt
└── README.md
```

## Project Status

| Component | Status |
|---|---|
| Web Crawling | In development |
| Bronze Data Storage | Initial implementation |
| PostgreSQL Ingestion | Planned |
| Silver Transformation | Planned |
| Gold Star Schema | Planned |
| Apache Airflow DAGs | Planned |
| Tableau Dashboard | Planned |

## Disclaimer

This project is developed for educational purposes. News content belongs to its respective publishers. Data collection should respect website access policies and applicable usage restrictions.
