# Nusantara TV Big Data Pipeline

Pipeline pengumpulan dan analisis berita Nusantara TV menggunakan Python,
Apache Airflow, PostgreSQL Neon, dan Tableau. Pengambilan data menggunakan
Requests dan BeautifulSoup.

```text
Website -> JSON Bronze -> Staging -> Silver -> Gold -> CSV -> Tableau
                           PostgreSQL Neon
```

## Persiapan

Siapkan Git, Docker Desktop dengan Linux containers, koneksi internet, database
Neon, dan file `.env` proyek. Tableau diperlukan untuk membuka dashboard.
Seluruh pipeline dapat dijalankan melalui Docker tanpa instalasi Python lokal.

Clone repository, lalu buka terminal di folder proyek:

```powershell
git clone <URL_REPOSITORY>
cd nusantaratv-bigdata
```

## Menjalankan pipeline

1. Buka Docker Desktop dan tunggu hingga siap.
2. Jalankan perintah berikut dari folder proyek:

   ```powershell
   docker compose up -d --build
   ```

3. Buka **http://localhost:18080**. Jika port disesuaikan, gunakan nilai
   `AIRFLOW_UI_PORT` pada `.env`.
4. Login dengan username **admin** dan password dari `AIRFLOW_ADMIN_PASSWORD`.
5. Buka menu **Dags**, lalu aktifkan atau unpause keempat DAG.
6. Pastikan tidak ada rangkaian yang sedang berjalan. Klik tombol **Trigger (ikon segitiga)** pada
   **ntv_01_crawling**, pilih **Single Run**, lalu klik **Trigger**.
7. Tunggu seluruh rangkaian berstatus **Success**.

| DAG | Task | Hasil |
|---|---|---|
| `ntv_01_crawling` | `collect_urls` -> `scrape_details` | Daftar URL dan detail artikel dalam JSON. |
| `ntv_02_ingestion` | `initialize_schema` -> `ingest_articles` | Struktur tabel dan artikel pada staging Neon. |
| `ntv_03_transformation` | `transform_silver` -> `transform_gold` | Artikel bersih, token NLP, dimensi, fakta, dan keyword. |
| `ntv_04_analytics` | `validate_and_export` | Dua CSV untuk Tableau. |

DAG pertama memicu DAG berikutnya secara berurutan. Status **Deferred** pada
task pemicu berarti menunggu DAG berikutnya selesai. Jika gagal, buka task yang
merah dan baca **Logs**.

Jadwal otomatis dimulai **setiap hari pukul 07.00 WIB**. Komputer, Docker,
container, dan internet harus aktif. Jalankan hanya DAG pertama untuk memulai
rangkaian lengkap.

## Pengumpulan data

Crawler mencari maksimal **100 artikel yang belum tersimpan per run** dengan
membandingkan ID pada staging Neon dan checkpoint JSON lokal. Artikel yang
sudah tersimpan dilewati dan detailnya tidak diambil ulang, sehingga revisi
artikel lama di website tidak ikut diperbarui.

Pencarian dilanjutkan melalui pagination hingga target tercapai, akhir
pagination ditemukan, atau batas 100 batch tercapai. Setiap permintaan diberi
jeda. Hasil dapat kurang dari 100 karena keterbatasan pencarian, kegagalan
scraping, atau penolakan validasi. Artikel yang belum tersimpan dapat berasal
dari tanggal terbit sebelumnya.

| File | Isi |
|---|---|
| `data/bronze/bronze_article_urls.json` | URL yang dipilih untuk diambil detailnya. |
| `data/bronze/bronze_articles.json` | Kumpulan artikel yang berhasil diambil. |
| `data/bronze/scraping_errors.json` | Catatan kegagalan pengambilan detail. |

Checkpoint menyimpan kemajuan agar retry dapat melanjutkan pengambilan detail.
Jika tidak ada URL baru, tahap berikutnya menggunakan data yang sudah tersedia.

## Pengolahan data

**Staging** menyimpan artikel dari JSON setelah pemeriksaan field wajib, tipe,
panjang nilai, tanggal, dan jumlah kata. Data dimasukkan melalui upsert
berdasarkan ID artikel.

**Silver** merapikan field artikel sekaligus menjalankan preprocessing NLP:

```text
Case Folding -> RegEx -> Tokenisasi -> Normalisasi -> Stemming -> Stopword Removal
```

Normalisasi menggunakan kamus `NORMALIZATION_MAP` di `transform_silver.py`.
Artikel yang sudah dirapikan disimpan pada `silver.articles`, sedangkan token
dan frekuensinya pada `silver.article_tokens`.

Status `silver.article_processing` menentukan artikel yang perlu diproses NLP.
Isi dan aturan NLP yang sama dilewati. Pemrosesan NLP berlangsung tanpa koneksi
Neon aktif; perubahan disimpan dalam satu transaksi setelah sumber diperiksa
kembali.

**Gold** membentuk star schema:

| Tabel | Isi |
|---|---|
| `gold.dim_date` | Informasi tanggal publikasi. |
| `gold.dim_category` | Kategori berita. |
| `gold.dim_author` | Penulis berita. |
| `gold.fact_articles` | Fakta artikel, jam publikasi, jumlah kata, dan relasi dimensi. |
| `gold.article_keywords` | Keyword dan frekuensi per artikel. |

Tabel dibuat otomatis oleh DAG ingestion jika belum tersedia. Data yang sudah
ada dipertahankan. File `sql/gold/02_analytics_dataset.sql` merupakan query
penggabungan fakta dan dimensi untuk ekspor.

## Membuka hasil di Tableau

Setelah DAG analytics berhasil, tersedia dua file:

| File | Penggunaan |
|---|---|
| `data/processed/nusantaratv_analytics.csv` | KPI, tren publikasi, kategori, penulis, dan heatmap hari/jam. |
| `data/processed/nusantaratv_keywords.csv` | Frekuensi keyword untuk treemap atau grafik keyword. |

Buka `tableau/Tableau Big Data.twb`. Jika sumber data tidak ditemukan, arahkan
kedua koneksi ke CSV pada folder `data/processed` di laptop yang digunakan.

Untuk menampilkan hasil ekspor terbaru, refresh kedua sumber data:

- **Data -> nusantaratv_analytics -> Refresh**
- **Data -> nusantaratv_keywords -> Refresh**

Ekspor CSV berjalan otomatis melalui Airflow. Refresh Tableau dilakukan manual.
Workbook membutuhkan kedua CSV tersebut. Folder data tidak disertakan dalam Git.

## Pemeriksaan dan pengelolaan layanan

Docker menjalankan dua layanan:

| Layanan | Fungsi |
|---|---|
| `airflow` | Menjadwalkan dan menjalankan pipeline. |
| `airflow-db` | Menyimpan metadata dan riwayat Airflow pada Docker volume. |

Data berita berada di PostgreSQL Neon. Untuk memeriksa layanan dan DAG:

```powershell
docker compose ps
docker compose exec airflow python /opt/project/config/start_airflow.py dags list-import-errors
docker compose exec airflow python /opt/project/config/start_airflow.py dags list
```

Setelah mengubah konfigurasi `.env`, terapkan saat tidak ada task aktif:

```powershell
docker compose up -d
```

Untuk menghentikan layanan sambil mempertahankan data:

```powershell
docker compose stop
```

Perintah `docker compose down -v` menghapus volume metadata Airflow yang
dikelola Compose.

Jika Pylance pada Windows menandai import Airflow atau Pendulum tidak ditemukan,
periksa import melalui container menggunakan perintah di atas. Dependensi
Airflow tersedia di lingkungan Docker.

## Struktur proyek

| Lokasi | Fungsi |
|---|---|
| `config/database.py` | Koneksi SSL ke Neon melalui `DATABASE_URL`. |
| `config/start_airflow.py` | Konfigurasi kredensial dan startup Airflow. |
| `dags/news_pipeline.py` | Empat DAG, jadwal, retry, dan urutan task. |
| `src/crawling/crawler.py` | Pengumpulan URL, parsing HTML, pengambilan detail, dan checkpoint. |
| `src/ingestion/initialize_schema.py` | Pembuatan schema dan tabel. |
| `src/ingestion/ingest_articles.py` | Validasi JSON dan upsert staging. |
| `src/transformation/transform_silver.py` | Cleaning artikel dan enam tahap NLP. |
| `src/transformation/transform_gold.py` | Pembentukan dimensi, fakta, dan keyword. |
| `src/analytics/export_analytics.py` | Pemeriksaan konsistensi dan ekspor CSV. |
| `sql/staging/` | Definisi schema dan tabel staging. |
| `sql/silver/` | Definisi artikel bersih, token, dan status pemrosesan. |
| `sql/gold/` | Definisi star schema, keyword, dan query analytics. |
| `data/bronze/` | JSON hasil crawling dan catatan error. |
| `data/processed/` | CSV untuk Tableau. |
| `tableau/Tableau Big Data.twb` | Worksheet, kalkulasi, dan dashboard. |
| `docker-compose.yml` | Pengaturan layanan, port, dan volume Docker. |
| `docker/airflow.Dockerfile` | Image Airflow beserta dependensi. |
| `docker/requirements-airflow.txt` | Dependensi Python untuk container. |
| `requirements.txt` | Dependensi untuk menjalankan script dengan Python lokal. |
| `.env.example` | Template variabel konfigurasi. |
| `.gitignore` | Pengecualian rahasia dan file lokal dari Git. |
| `.dockerignore` | Batasan berkas yang dikirim saat build Docker. |

Untuk menjalankan script dengan Python lokal, pasang dependensinya:

```powershell
python -m pip install -r requirements.txt
```

Proyek digunakan untuk pendidikan. Konten berita merupakan milik penerbitnya;
pengumpulan data mengikuti kebijakan akses situs.
