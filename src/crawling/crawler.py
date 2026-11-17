"""Mengumpulkan URL dan detail berita dengan Requests dan BeautifulSoup."""
import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))
from config.database import get_connection

BASE_URL = 'https://www.nusantaratv.com'
LOADMORE_URL = BASE_URL + '/loadmore/load_data'

TARGET_ARTICLES = 100
MAX_BATCHES = 100
URL_REQUEST_DELAY = 2

VALID_CATEGORIES = {'news', 'finance', 'sport', 'otomotif', 'tekno', 'showbiz', 'kamutau', 'opini'}

OUTPUT_DIR = BASE_DIR / 'data' / 'bronze'


# Baca ID yang sudah ada di staging dan checkpoint lokal agar tidak diambil ulang.
def load_existing_ids():
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('staging.articles')")
            if cursor.fetchone()[0] is None:
                known_ids = set()
            else:
                cursor.execute('SELECT article_id FROM staging.articles')
                known_ids = {row[0] for row in cursor.fetchall()}
    finally:
        connection.close()
    checkpoint = OUTPUT_DIR / 'bronze_articles.json'
    if checkpoint.exists():
        articles = json.loads(checkpoint.read_text(encoding='utf-8'))
        known_ids.update(article['article_id'] for article in articles if article.get('article_id'))
    return known_ids


# Mengambil URL artikel valid dan membuang duplikasi slug.
def extract_articles(html):
    soup = BeautifulSoup(html, 'html.parser')
    articles = {}

    for link in soup.select("a[href]"):
        url = urljoin(BASE_URL, link['href'])
        parsed = urlparse(url)

        if parsed.netloc not in {
            "www.nusantaratv.com",
            "nusantaratv.com"
        }:
            continue

        parts = parsed.path.strip('/').split('/')

        if len(parts) != 2:
            continue

        category, slug = parts

        if category not in VALID_CATEGORIES:
            continue

        title = link.get_text(' ', strip=True)

        if len(title) < 20:
            continue

        article_id = hashlib.sha256(slug.encode('utf-8')).hexdigest()[:16]

        articles[slug] = {
            "article_id": article_id,
            "title": title,
            "category": category,
            "article_url": url,
            "crawled_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

    return articles


# Mencari cursor pagination untuk batch berikutnya.
def get_next_id(html):
    soup = BeautifulSoup(html, 'html.parser')

    button = soup.select_one("#load_more_button[data-id]")
    if button and str(button["data-id"]).isdigit():
        return str(button['data-id'])

    ids = []

    for element in soup.select("[data-id], [id]"):
        value = element.get('data-id') or element.get('id')

        if value and str(value).isdigit():
            ids.append(int(value))

    return str(ids[-1]) if ids else None


# Mencari maksimal 100 URL artikel yang belum tersimpan lalu menyimpan JSON Bronze.
def collect_urls():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    known_ids = load_existing_ids()
    print(f'Target: {TARGET_ARTICLES} artikel belum tersimpan | ID lama: {len(known_ids)}')
    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL + "/news",
        "X-Requested-With": "XMLHttpRequest"
    })

    print('[1] Mengakses homepage...')

    homepage = session.get(BASE_URL + '/news', timeout=30)
    homepage.raise_for_status()

    soup = BeautifulSoup(homepage.text, 'html.parser')

    token_meta = soup.select_one('meta[name="csrf-token"]')
    token_input = soup.select_one('input[name="_token"]')

    token = (
        token_meta.get("content") if token_meta
        else token_input.get("value") if token_input
        else None
    )

    if not token:
        raise RuntimeError('CSRF token tidak ditemukan')

    print('[OK] Session dan CSRF token siap')

    # Cursor kosong meminta kelompok artikel terbaru dari endpoint AJAX situs.
    all_articles = {}
    current_id = ''
    used_ids = set()

    for batch in range(1, MAX_BATCHES + 1):

        if len(all_articles) >= TARGET_ARTICLES:
            break

        if current_id in used_ids:
            print('ID pagination berulang. Berhenti.')
            break

        used_ids.add(current_id)

        print(f'\nBatch {batch} | ID {current_id}')

        response = session.post(
            LOADMORE_URL,
            data={
                "id": current_id,
                "_token": token
            },
            headers={
                "X-CSRF-TOKEN": token
            },
            timeout=30
        )

        response.raise_for_status()

        articles = extract_articles(response.text)

        before = len(all_articles)
        all_articles.update({slug: article for slug, article in articles.items()
                             if article['article_id'] not in known_ids})
        added = len(all_articles) - before

        print('Artikel ditemukan:', len(articles))
        print('Artikel belum tersimpan:', added)
        print('Total unik:', len(all_articles))

        if not articles:
            print('Tidak ada artikel pada halaman berikutnya.')
            break

        next_id = get_next_id(response.text)

        if not next_id or next_id == current_id:
            print('ID berikutnya tidak valid.')
            break

        if current_id and int(next_id) >= int(current_id):
            print('ID tidak menurun. Berhenti.')
            break

        current_id = next_id
        time.sleep(URL_REQUEST_DELAY)

    result = list(all_articles.values())[:TARGET_ARTICLES]

    output_file = OUTPUT_DIR / 'bronze_article_urls.json'

    session.close()
    if not result:
        print('Tidak ditemukan artikel yang belum tersimpan dalam batas pencarian.')
    elif len(result) < TARGET_ARTICLES:
        print('Target belum tercapai: batas halaman atau akhir pagination telah dicapai.')
    temp_file = output_file.with_suffix('.json.tmp')
    temp_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    temp_file.replace(output_file)

    print('\n' + '=' * 55)
    print('CRAWLING SELESAI')
    print('Total artikel:', len(result))
    print('Output:', output_file)
    print('=' * 55)


# MEMBACA ISI HTML ARTIKEL


WIB = timezone(timedelta(hours=7))

MONTHS = {
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12
}

CATEGORIES = {
    "news": "News",
    "finance": "Ekonomi",
    "sport": "Sport & Bola",
    "otomotif": "Otomotif",
    "tekno": "Tekno & Sains",
    "showbiz": "Show Biz",
    "kamutau": "Kamu Tau",
    "opini": "Opini"
}


# Mengambil nilai metadata HTML jika tersedia.
def get_meta(soup, selector):
    tag = soup.select_one(selector)

    if not tag:
        return None

    value = tag.get('content')
    return value.strip() if value else None


# Mengubah tanggal berbahasa Indonesia ke ISO dengan zona WIB.
def parse_date(text):
    pattern = r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+(\d{1,2}):(\d{2})"

    match = re.search(pattern, text)

    if not match:
        return None

    day, month, year, hour, minute = match.groups()

    month_number = MONTHS.get(month.lower())

    if not month_number:
        return None

    try:
        date = datetime(int(year), month_number, int(day), int(hour), int(minute), tzinfo=WIB)

        return date.isoformat()

    except ValueError:
        return None


# Mencari penulis dari link profil atau label pada artikel.
def extract_author(soup):
    content_section = soup.select_one("section#content")
    if not content_section:
        return None

    for link in content_section.select("a[href]"):
        if "/penulis/" in link.get("href", ""):
            name = link.get_text(" ", strip=True)
            if name:
                return name

    # Gunakan label penulis jika link profil tidak tersedia.
    for paragraph in content_section.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        if text.lower().startswith("penulis:"):
            name = text.split(":", 1)[1].strip()
            if name:
                return name
    return None


# Mengambil paragraf utama tanpa elemen rekomendasi.
def extract_content(soup):
    content_tag = soup.select_one(
        "section#content .post-body"
    )

    if not content_tag:
        return ''

    # Hindari memasukkan artikel rekomendasi
    for unwanted in content_tag.select(
        ".bacajuga, script, style"
    ):
        unwanted.decompose()

    paragraphs = []

    for p in content_tag.find_all("p"):
        text = p.get_text(' ', strip=True)

        if text:
            paragraphs.append(text)

    return '\n'.join(paragraphs)


# Menyusun isi dan metadata halaman menjadi satu artikel.
def parse_article(soup, url):
    # 1. Judul
    title_tag = soup.select_one('h1.post-title')

    title = title_tag.get_text(' ', strip=True) if title_tag else None

    if not title:
        title = get_meta(soup, 'meta[property="og:title"]')

    # 2. Tanggal dan jam publikasi
    date_tag = soup.select_one('h2.post-title')

    date_text = date_tag.get_text(' ', strip=True) if date_tag else ''

    published_at = parse_date(date_text)

    # 3. Konten utama
    content = extract_content(soup)

    # 4. Penulis asli
    author = extract_author(soup)

    # 5. Ringkasan
    description = get_meta(soup, 'meta[name="description"]')

    # 6. Kategori dari URL
    parts = urlparse(url).path.strip('/').split('/')
    category_slug = parts[0] if parts else ''

    category = CATEGORIES.get(category_slug, category_slug)

    # 7. Jumlah kata
    word_count = len(content.split())

    return {
        "title": title,
        "content": content,
        "category": category,
        "author": author,
        "description": description,
        "published_at": published_at,
        "article_url": url,
        "word_count": word_count
    }

# MENGAMBIL DETAIL DAN MENYIMPAN CHECKPOINT


# KONFIGURASI

BRONZE_DIR = BASE_DIR / 'data' / 'bronze'
INPUT_FILE = BRONZE_DIR / 'bronze_article_urls.json'
OUTPUT_FILE = BRONZE_DIR / 'bronze_articles.json'
ERROR_FILE = BRONZE_DIR / 'scraping_errors.json'

MAX_ARTICLES = 100
REQUEST_DELAY = 3
CHECKPOINT_EVERY = 5


# UTILITAS JSON

# Membaca JSON atau memakai nilai awal jika file belum ada.
def load_json(path, default):
    if not path.exists():
        return default

    with open(path, encoding="utf-8") as file:
        return json.load(file)


# Mengganti file JSON melalui file sementara.
def save_json(path, data):
    temp_file = path.with_suffix(path.suffix + '.tmp')

    temp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    temp_file.replace(path)


# Menyimpan titik simpan artikel dan error.
def save_checkpoint(results, errors):
    save_json(OUTPUT_FILE, list(results.values()))
    save_json(ERROR_FILE, list(errors.values()))


# SESI HTTP DAN PERCOBAAN ULANG

# Menyiapkan sesi HTTP dengan header dan percobaan ulang.
def create_session():
    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"
    })

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=2,
        status_forcelist=[
            429, 500, 502, 503, 504
        ],
        allowed_methods=["GET"],
        respect_retry_after_header=True
    )

    adapter = HTTPAdapter(max_retries=retry)

    session.mount('https://', adapter)
    session.mount('http://', adapter)

    return session


# PROSES SCRAPING

# Mengambil detail artikel sambil melanjutkan titik simpan sebelumnya.
def scrape_details():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f'File URL Bronze tidak ditemukan: {INPUT_FILE}')
    articles = load_json(INPUT_FILE, [])
    existing = load_json(OUTPUT_FILE, [])

    results = {item['article_id']: item for item in existing if item.get('article_id')}

    previous_errors = load_json(ERROR_FILE, [])

    errors = {item['article_id']: item for item in previous_errors if item.get('article_id')}

    if not articles:
        if not results:
            raise ValueError('Tidak ada artikel untuk diproses')
        print('Tidak ada URL baru; data sebelumnya tetap digunakan.')
        return
    session = create_session()

    target_articles = articles[:MAX_ARTICLES]

    print('=' * 60)
    print('SCRAPING DETAIL NUSANTARA TV')
    print('Target URL:', len(target_articles))
    print('Data sebelumnya:', len(results))
    print('=' * 60)

    try:
        for index, article in enumerate(
            target_articles, 1
        ):
            article_id = article['article_id']
            url = article['article_url']

            if article_id in results:
                print(f'[{index}/{len(target_articles)}] SKIP - sudah tersimpan')
                continue

            print(f'\n[{index}/{len(target_articles)}] {url}')

            try:
                response = session.get(url, timeout=(10, 30))

                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')

                parsed = parse_article(soup, response.url)

                parsed['article_id'] = article_id

                parsed['crawled_at'] = datetime.now(timezone.utc).isoformat()

                # Validasi data utama
                if not parsed["title"]:
                    raise ValueError('Judul artikel kosong')

                if not parsed["content"]:
                    raise ValueError('Konten artikel kosong')

                if not parsed["published_at"]:
                    raise ValueError('Tanggal publikasi kosong')

                results[article_id] = parsed

                # Hapus error jika sudah berhasil
                errors.pop(article_id, None)

                print(
                    "   OK |",
                    parsed["category"],
                    "|",
                    parsed["word_count"],
                    "kata | Penulis:",
                    parsed["author"] or "Tidak tersedia"
                )

            except (
                requests.RequestException,
                ValueError
            ) as error:

                errors[article_id] = {
                    "article_id": article_id,
                    "article_url": url,
                    "error": str(error)
                }

                print('   ERROR:', error)

            # Penyimpanan kemajuan
            if index % CHECKPOINT_EVERY == 0:
                save_checkpoint(results, errors)

                print('   [CHECKPOINT] Data disimpan')

            # Jeda antarpermintaan
            time.sleep(REQUEST_DELAY + random.uniform(0, 1))

    except KeyboardInterrupt:
        print('\n[INFO] Scraping dihentikan pengguna')

    finally:
        save_checkpoint(results, errors)

        session.close()

        target_ids = {item['article_id'] for item in target_articles}

        successful = len(target_ids.intersection(results))

        print('\n' + '=' * 60)
        print('SCRAPING DETAIL SELESAI')
        print('Target:', len(target_articles))
        print('Berhasil:', successful)
        print('Gagal / belum diproses:', len(target_articles) - successful)
        print('Total tersimpan:', len(results))
        print('Output:', OUTPUT_FILE)
        print('=' * 60)

    if successful != len(target_articles):
        raise RuntimeError('Scraping belum lengkap; retry akan melanjutkan checkpoint')


# Jalankan tahap yang diminta Airflow atau seluruh crawling dari terminal.
def main():
    if len(sys.argv) == 1:
        collect_urls()
        scrape_details()
    elif sys.argv[1:] == ['collect_urls']:
        collect_urls()
    elif sys.argv[1:] == ['scrape_details']:
        scrape_details()
    else:
        raise ValueError('Pilihan tahap: collect_urls atau scrape_details')


if __name__ == "__main__":
    main()
