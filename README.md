# Nusantara TV Big Data Pipeline

Proyek pengolahan berita Nusantara TV: mengambil artikel, menyimpannya di
PostgreSQL Neon, membersihkan data dan token NLP, lalu mengekspor CSV untuk Tableau.

```text
Website -> Crawling -> JSON Bronze -> Staging -> Silver -> Gold -> CSV -> Tableau
                                      Database Neon
```

## 1. Persiapan

Siapkan Docker Desktop dengan Linux containers, koneksi internet, dan database
PostgreSQL di Neon. Python lokal tidak diperlukan jika menjalankan pipeline
melalui Docker. Node.js dan Neon CLI juga tidak diperlukan.

Clone repository dan buka terminal di folder proyek:

```powershell
git clone <URL_REPOSITORY>
cd nusantaratv-bigdata
```

## 2. Jalankan Docker dan Airflow

Buka Docker Desktop, lalu jalankan:

```powershell
docker compose up -d --build
```

Docker menjalankan dua layanan:

| Layanan | Fungsi |
|---|---|
| `airflow` | Menjalankan dan menjadwalkan pipeline. |
| `airflow-db` | Menyimpan metadata internal Airflow, bukan data berita. |

Data berita berada di **Neon**. Metadata Airflow berada di **Docker volume**.

Buka **http://localhost:18080** (sesuaikan jika port diubah), lalu login:

- Username: `admin`
- Password: nilai `AIRFLOW_ADMIN_PASSWORD` pada `.env`

Tunggu startup selesai jika dashboard belum dapat dibuka.

## 3. Jalankan pipeline

Di menu **Dags**, unpause keempat DAG. Untuk menjalankan sekarang, trigger
**hanya `ntv_01_crawling`**. DAG berikutnya dipicu otomatis secara berurutan.

| DAG | Proses | Hasil |
|---|---|---|
| `ntv_01_crawling` | Mengambil URL dan detail artikel. | JSON di `data/bronze/`. |
| `ntv_02_ingestion` | Membuat tabel yang belum ada, validasi, dan upsert artikel. | `staging.articles` di Neon. |
| `ntv_03_transformation` | Cleaning, NLP, dan pembentukan star schema. | Tabel Silver dan Gold di Neon. |
| `ntv_04_analytics` | Memeriksa konsistensi data dan mengekspor hasil. | Dua CSV di `data/processed/`. |

Setelah seluruh rantai selesai, run keempat DAG akan berstatus **Success**.
Status **Deferred** pada task pemicu berarti menunggu DAG berikutnya selesai.
Jika gagal, buka task yang merah lalu baca **Logs** sebelum menjalankan ulang.

Jadwal otomatis adalah **setiap hari pukul 07.00 WIB**. Komputer, Docker Desktop,
container, dan koneksi internet perlu aktif. Jangan trigger DAG 02-04 sendiri
saat rantai berjalan karena proses dapat saling tumpang tindih.

Crawler mengambil maksimal 200 URL per run. Artikel detail yang sudah tersimpan
dilewati; total data dapat bertambah pada run berikutnya. Pengambilan ini tidak
menjamin seluruh publikasi situs tercakup. Tabel yang sudah ada tidak dihapus
saat inisialisasi; perubahan struktur tabel lama memerlukan migrasi tersendiri.

## 4. Buka hasil di Tableau

Pipeline menghasilkan:

| File | Digunakan untuk |
|---|---|
| `data/processed/nusantaratv_analytics.csv` | KPI, tren tanggal, kategori, penulis, dan heatmap hari/jam. |
| `data/processed/nusantaratv_keywords.csv` | Frekuensi keyword untuk treemap atau grafik keyword. |

Buka `tableau/Tableau Big Data.twb`. Jika Tableau tidak menemukan CSV setelah
clone atau pindah laptop, arahkan koneksi kedua sumber data ke file CSV di
folder `data/processed` milik laptop tersebut.

Setelah DAG analytics selesai, refresh kedua sumber melalui menu Tableau:

- **Data -> nusantaratv_analytics -> Refresh**
- **Data -> nusantaratv_keywords -> Refresh**

Ekspor CSV otomatis, tetapi **refresh Tableau dilakukan manual**. Grafik tidak
perlu dibuat ulang. Workbook `.twb` menyimpan definisi dashboard; CSV sumbernya
tetap dibutuhkan. Folder data tidak ikut Git dan akan diisi pipeline.

## Mengubah konfigurasi dan mengecek layanan

Setelah mengganti URL Neon atau password Airflow di `.env`, simpan lalu jalankan:

```powershell
docker compose up -d
```

Konfigurasi baru dimuat saat container dibuat ulang. Startup menyinkronkan
password metadata dan login admin; tidak perlu script password terpisah.
Terapkan perubahan ketika tidak ada task aktif. `docker compose restart` saja
tidak memuat nilai environment baru.

Perintah pemeriksaan:

```powershell
docker compose ps
docker compose exec airflow airflow dags list-import-errors
docker compose exec airflow airflow dags list
```

Untuk menghentikan layanan tanpa menghapus data:

```powershell
docker compose stop
```

Hindari `docker compose down -v` jika ingin mempertahankan metadata dan riwayat
Airflow, karena opsi `-v` menghapus volume yang dikelola Compose.

## Pemakaian bersama tim

Semua anggota dapat mengakses database Neon yang sama melalui koneksi untuk
akun masing-masing. Cukup **satu Airflow utama** menjalankan jadwal pipeline;
jangan aktifkan scheduler di semua laptop untuk warehouse yang sama.

CSV berada di laptop yang menjalankan exporter. Anggota yang memakai Tableau
perlu menerima CSV terbaru atau mengekspornya dari Neon. Akses Neon yang sama
tidak otomatis membagikan dashboard Airflow maupun CSV lokal.

## Struktur dan fungsi file

| Lokasi | Fungsi |
|---|---|
| `config/database.py` | Membuka koneksi SSL ke Neon dari `DATABASE_URL`. |
| `config/start_airflow.py` | Mengatur password dari environment dan memulai Airflow. |
| `dags/news_pipeline.py` | Definisi empat DAG, jadwal, retry, dan urutan proses. |
| `docker-compose.yml` | Layanan Airflow, metadata PostgreSQL, jaringan, dan volume. |
| `docker/airflow.Dockerfile` | Image Airflow beserta dependensi pipeline. |
| `docker/requirements-airflow.txt` | Dependensi Python di container. |
| `requirements.txt` | Dependensi jika menjalankan script lewat Python lokal. |
| `src/crawling/crawler.py` | Mengumpulkan URL artikel. |
| `src/crawling/article_parser.py` | Mengambil isi dan metadata dari HTML artikel. |
| `src/crawling/scrape_details.py` | Scraping detail, retry, checkpoint, dan catatan error. |
| `src/ingestion/initialize_schema.py` | Membuat schema dan tabel yang belum ada. |
| `src/ingestion/ingest_articles.py` | Memvalidasi Bronze dan mengisi staging. |
| `src/transformation/transform_silver.py` | Cleaning artikel dan pemrosesan token NLP. |
| `src/transformation/transform_gold.py` | Mengisi dimensi, fakta, dan keyword Gold. |
| `src/analytics/export_analytics.py` | Validasi warehouse dan ekspor CSV. |
| `sql/staging/` | DDL schema dan tabel staging. |
| `sql/silver/` | DDL artikel bersih dan token. |
| `sql/gold/` | DDL star schema, keyword, dan query analytics untuk ekspor. |
| `data/bronze/` | Daftar URL, detail artikel, dan error scraping. |
| `data/processed/` | CSV hasil ekspor untuk Tableau. |
| `tableau/Tableau Big Data.twb` | Worksheet, kalkulasi, dan dashboard Tableau. |
| `.env.example` | Template konfigurasi tanpa kredensial asli. |
| `.gitignore` | Mengecualikan rahasia, data, dan cache dari Git. |
| `.dockerignore` | Membatasi file yang dikirim saat build image. |

Untuk SQL manual, buat database melalui Neon Console, lalu jalankan DDL staging,
Silver, dan Gold sesuai urutan dependensinya. Biasanya tidak perlu dilakukan
manual karena DAG ingestion sudah menjalankan `initialize_schema.py`.
`sql/gold/02_analytics_dataset.sql` adalah query SELECT, bukan pembuatan tabel.

Jika Pylance menandai import Airflow/Pendulum tidak ditemukan pada Windows,
dependensi tersebut tersedia di container Airflow. Gunakan perintah pemeriksaan
DAG di atas untuk memverifikasi import pada lingkungan yang menjalankannya.

Proyek ini dibuat untuk pendidikan. Konten berita merupakan milik penerbitnya;
pengambilan data perlu mengikuti kebijakan akses situs.
