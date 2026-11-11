
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin
import re


def main():
    BASE_URL = "https://www.nusantaratv.com"
    LOADMORE_URL = f"{BASE_URL}/loadmore/load_data"

    OUTPUT_DIR = Path("data/raw")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ID dari pengujian DevTools.
    # Hanya digunakan untuk menguji satu request.
    LAST_ID = "145735"

    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Referer": f"{BASE_URL}/news",
        "X-Requested-With": "XMLHttpRequest"
    })

    try:
        # 1. GET homepage untuk mendapatkan cookies dan token
        print("[1] Mengakses homepage...")

        homepage = session.get(
            BASE_URL,
            timeout=30
        )
        homepage.raise_for_status()

        soup = BeautifulSoup(homepage.text, "html.parser")

        # 2. Ambil CSRF token
        token_meta = soup.select_one('meta[name="csrf-token"]')
        token_input = soup.select_one('input[name="_token"]')

        if token_meta:
            csrf_token = token_meta.get("content")
        elif token_input:
            csrf_token = token_input.get("value")
        else:
            raise ValueError("CSRF token tidak ditemukan")

        print("[OK] CSRF token ditemukan")

        # 3. Kirim request Load More
        print("[2] Mengirim POST Load More...")

        response = session.post(
            LOADMORE_URL,
            data={
                "id": LAST_ID,
                "_token": csrf_token
            },
            headers={
                "X-CSRF-TOKEN": csrf_token
            },
            timeout=30
        )

        print("Status Code:", response.status_code)
        print("Response Length:", len(response.text))

        response.raise_for_status()

        # 4. Simpan HTML
        output_file = OUTPUT_DIR / "loadmore_test.html"
        output_file.write_text(
            response.text,
            encoding="utf-8"
        )

        print("[OK] Response disimpan:", output_file)

        # 5. Parsing HTML
        result_soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        articles = []

        for link in result_soup.select("a[href]"):
            href = urljoin(BASE_URL, link["href"])
            title = link.get_text(" ", strip=True)

            if len(title) < 20:
                continue

            if href.startswith(BASE_URL):
                articles.append((title, href))

        print("\nArtikel ditemukan:", len(articles))

        for i, (title, url) in enumerate(articles[:10], 1):
            print(f"\n{i}. {title[:100]}")
            print("   ", url)

    except requests.RequestException as error:
        print("[ERROR REQUEST]", error)

    except ValueError as error:
        print("[ERROR TOKEN]", error)

if __name__ == "__main__":
    main()
