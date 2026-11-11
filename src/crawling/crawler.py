
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import time

BASE_URL = "https://www.nusantaratv.com"
LOADMORE_URL = BASE_URL + "/loadmore/load_data"

TARGET_ARTICLES = 200
MAX_BATCHES = 20
REQUEST_DELAY = 2

VALID_CATEGORIES = {
    "news", "finance", "sport", "otomotif",
    "tekno", "showbiz", "kamutau", "opini"
}

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "data" / "bronze"


def extract_articles(html):
    soup = BeautifulSoup(html, "html.parser")
    articles = {}

    for link in soup.select("a[href]"):
        url = urljoin(BASE_URL, link["href"])
        parsed = urlparse(url)

        if parsed.netloc not in {
            "www.nusantaratv.com",
            "nusantaratv.com"
        }:
            continue

        parts = parsed.path.strip("/").split("/")

        if len(parts) != 2:
            continue

        category, slug = parts

        if category not in VALID_CATEGORIES:
            continue

        title = link.get_text(" ", strip=True)

        if len(title) < 20:
            continue

        article_id = hashlib.sha256(
            slug.encode("utf-8")
        ).hexdigest()[:16]

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


def get_next_id(html):
    soup = BeautifulSoup(html, "html.parser")

    button = soup.select_one("#load_more_button[data-id]")
    if button and str(button["data-id"]).isdigit():
        return str(button["data-id"])

    ids = []

    for element in soup.select("[data-id], [id]"):
        value = element.get("data-id") or element.get("id")

        if value and str(value).isdigit():
            ids.append(int(value))

    return str(ids[-1]) if ids else None


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL + "/news",
        "X-Requested-With": "XMLHttpRequest"
    })

    print("[1] Mengakses homepage...")

    homepage = session.get(BASE_URL + "/news", timeout=30)
    homepage.raise_for_status()

    soup = BeautifulSoup(homepage.text, "html.parser")

    token_meta = soup.select_one(
        'meta[name="csrf-token"]'
    )
    token_input = soup.select_one(
        'input[name="_token"]'
    )

    token = (
        token_meta.get("content") if token_meta
        else token_input.get("value") if token_input
        else None
    )

    if not token:
        raise RuntimeError("CSRF token tidak ditemukan")

    print("[OK] Session dan CSRF token siap")

    # An empty cursor asks the site's AJAX endpoint for the latest batch.
    all_articles = {}
    current_id = ""
    used_ids = set()

    for batch in range(1, MAX_BATCHES + 1):

        if len(all_articles) >= TARGET_ARTICLES:
            break

        if current_id in used_ids:
            print("ID pagination berulang. Berhenti.")
            break

        used_ids.add(current_id)

        print(
            f"\nBatch {batch} | ID {current_id}"
        )

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
        all_articles.update(articles)
        added = len(all_articles) - before

        print("Artikel ditemukan:", len(articles))
        print("Artikel baru:", added)
        print("Total unik:", len(all_articles))

        if not articles or added == 0:
            print("Tidak ada artikel baru.")
            break

        next_id = get_next_id(response.text)

        if not next_id or next_id == current_id:
            print("ID berikutnya tidak valid.")
            break

        if current_id and int(next_id) >= int(current_id):
            print("ID tidak menurun. Berhenti.")
            break

        current_id = next_id
        time.sleep(REQUEST_DELAY)

    result = list(all_articles.values())[
        :TARGET_ARTICLES
    ]

    output_file = OUTPUT_DIR / "bronze_article_urls.json"

    if not result:
        raise RuntimeError("Crawler tidak menghasilkan artikel")
    temp_file = output_file.with_suffix(".json.tmp")
    temp_file.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    temp_file.replace(output_file)

    print("\n" + "=" * 55)
    print("CRAWLING SELESAI")
    print("Total artikel:", len(result))
    print("Output:", output_file)
    print("=" * 55)


if __name__ == "__main__":
    main()
