
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from article_parser import parse_article


# ==================================================
# KONFIGURASI
# ==================================================

INPUT_FILE = Path("data/raw/bronze_article_urls.json")
OUTPUT_FILE = Path("data/raw/bronze_articles.json")
ERROR_FILE = Path("data/raw/scraping_errors.json")

MAX_ARTICLES = 200
REQUEST_DELAY = 3
CHECKPOINT_EVERY = 5

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


# ==================================================
# UTILITAS JSON
# ==================================================

def load_json(path, default):
    if not path.exists():
        return default

    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    temp_file = path.with_suffix(
        path.suffix + ".tmp"
    )

    temp_file.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    temp_file.replace(path)


# ==================================================
# SESSION DAN RETRY
# ==================================================

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

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# ==================================================
# PROSES SCRAPING
# ==================================================

def main():
    articles = load_json(INPUT_FILE, [])
    existing = load_json(OUTPUT_FILE, [])

    results = {
        item["article_id"]: item
        for item in existing
        if item.get("article_id")
    }

    previous_errors = load_json(ERROR_FILE, [])

    errors = {
        item["article_id"]: item
        for item in previous_errors
        if item.get("article_id")
    }

    session = create_session()

    target_articles = articles[:MAX_ARTICLES]

    print("=" * 60)
    print("SCRAPING DETAIL NUSANTARA TV")
    print("Target URL:", len(target_articles))
    print("Data sebelumnya:", len(results))
    print("=" * 60)

    try:
        for index, article in enumerate(
            target_articles, 1
        ):
            article_id = article["article_id"]
            url = article["article_url"]

            if article_id in results:
                print(
                    f"[{index}/{len(target_articles)}] "
                    "SKIP - sudah tersimpan"
                )
                continue

            print(
                f"\n[{index}/{len(target_articles)}] "
                f"{url}"
            )

            try:
                response = session.get(
                    url,
                    timeout=(10, 30)
                )

                response.raise_for_status()

                soup = BeautifulSoup(
                    response.text,
                    "html.parser"
                )

                parsed = parse_article(
                    soup,
                    response.url
                )

                parsed["article_id"] = article_id

                parsed["crawled_at"] = datetime.now(
                    timezone.utc
                ).isoformat()

                # Validasi data utama
                if not parsed["title"]:
                    raise ValueError(
                        "Judul artikel kosong"
                    )

                if not parsed["content"]:
                    raise ValueError(
                        "Konten artikel kosong"
                    )

                if not parsed["published_at"]:
                    raise ValueError(
                        "Tanggal publikasi kosong"
                    )

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

                print("   ERROR:", error)

            # Checkpoint
            if index % CHECKPOINT_EVERY == 0:
                save_json(
                    OUTPUT_FILE,
                    list(results.values())
                )

                save_json(
                    ERROR_FILE,
                    list(errors.values())
                )

                print(
                    "   [CHECKPOINT] Data disimpan"
                )

            # Jeda antar-request
            time.sleep(
                REQUEST_DELAY +
                random.uniform(0, 1)
            )

    except KeyboardInterrupt:
        print(
            "\n[INFO] Scraping dihentikan pengguna"
        )

    finally:
        save_json(
            OUTPUT_FILE,
            list(results.values())
        )

        save_json(
            ERROR_FILE,
            list(errors.values())
        )

        session.close()

        target_ids = {
            item["article_id"]
            for item in target_articles
        }

        successful = len(
            target_ids.intersection(results)
        )

        print("\n" + "=" * 60)
        print("SCRAPING DETAIL SELESAI")
        print("Target:", len(target_articles))
        print("Berhasil:", successful)
        print(
            "Gagal / belum diproses:",
            len(target_articles) - successful
        )
        print(
            "Total tersimpan:",
            len(results)
        )
        print("Output:", OUTPUT_FILE)
        print("=" * 60)


if __name__ == "__main__":
    main()
