
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

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


def get_meta(soup, selector):
    tag = soup.select_one(selector)

    if not tag:
        return None

    value = tag.get("content")
    return value.strip() if value else None


def parse_date(text):
    pattern = (
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})"
        r"\s+(\d{1,2}):(\d{2})"
    )

    match = re.search(pattern, text)

    if not match:
        return None

    day, month, year, hour, minute = match.groups()

    month_number = MONTHS.get(month.lower())

    if not month_number:
        return None

    try:
        date = datetime(
            int(year),
            month_number,
            int(day),
            int(hour),
            int(minute),
            tzinfo=WIB
        )

        return date.isoformat()

    except ValueError:
        return None



def extract_author(soup):
    # Cari link penulis di bagian konten utama
    content_section = soup.select_one("section#content")

    if content_section:
        for link in content_section.select("a[href]"):
            href = link.get("href", "")

            if "/penulis/" in href:
                name = link.get_text(" ", strip=True)

                if name:
                    return name

    # Fallback: cari teks "Penulis:" pada paragraf
    if content_section:
        for p in content_section.find_all("p"):
            text = p.get_text(" ", strip=True)

            if text.lower().startswith("penulis:"):
                name = text.split(":", 1)[1].strip()

                if name:
                    return name

    return None




def extract_content(soup):
    content_tag = soup.select_one(
        "section#content .post-body"
    )

    if not content_tag:
        return ""

    # Hindari memasukkan artikel rekomendasi
    for unwanted in content_tag.select(
        ".bacajuga, script, style"
    ):
        unwanted.decompose()

    paragraphs = []

    for p in content_tag.find_all("p"):
        text = p.get_text(" ", strip=True)

        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs)


def parse_article(soup, url):
    # 1. Judul
    title_tag = soup.select_one("h1.post-title")

    title = (
        title_tag.get_text(" ", strip=True)
        if title_tag else None
    )

    if not title:
        title = get_meta(
            soup,
            'meta[property="og:title"]'
        )

    # 2. Tanggal dan jam publikasi
    date_tag = soup.select_one("h2.post-title")

    date_text = (
        date_tag.get_text(" ", strip=True)
        if date_tag else ""
    )

    published_at = parse_date(date_text)

    # 3. Konten utama
    content = extract_content(soup)

    # 4. Penulis asli
    author = extract_author(soup)

    # 5. Ringkasan
    description = get_meta(
        soup,
        'meta[name="description"]'
    )

    # 6. Kategori dari URL
    parts = urlparse(url).path.strip("/").split("/")
    category_slug = parts[0] if parts else ""

    category = CATEGORIES.get(
        category_slug,
        category_slug
    )

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
