
import requests
from bs4 import BeautifulSoup
from pathlib import Path


def main():
    # Konfigurasi
    BASE_URL = "https://www.nusantaratv.com/"
    OUTPUT_DIR = Path("data/raw")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AcademicCrawler/1.0)"
    }

    try:
        print("=" * 50)
        print("TEST CONNECTION - NUSANTARA TV")
        print("=" * 50)

        response = requests.get(
            BASE_URL,
            headers=headers,
            timeout=30
        )

        print("Status Code :", response.status_code)
        print("Final URL   :", response.url)

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.title.get_text(strip=True) if soup.title else "Tidak ditemukan"

        print("Page Title  :", title)

        links = soup.find_all("a", href=True)

        print("Total Links :", len(links))

        # Menampilkan contoh link
        print("\n10 Contoh Link:")

        for link in links[:10]:
            print("-", link.get("href"))

        # Simpan HTML untuk inspeksi
        output_file = OUTPUT_DIR / "homepage_test.html"
        output_file.write_text(response.text, encoding="utf-8")

        print("\nHTML berhasil disimpan:")
        print(output_file)

    except requests.RequestException as error:
        print("ERROR:", error)

if __name__ == "__main__":
    main()
