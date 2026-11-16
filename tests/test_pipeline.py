import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from src.crawling.article_parser import parse_article, parse_date
from src.crawling.crawler import get_next_id
from src.transformation import transform_silver as silver
from src.transformation.nlp_cache import NLPCache


# Fixture mewakili baris Silver beserta status pemrosesannya.
def row(content="roket", signature=None):
    date = datetime(2026, 11, 16, tzinfo=timezone.utc)
    base = ("a", "Judul", content, None, "news", None, date, "https://example.com/news/a", date, len(content.split()))
    return base + (hashlib.sha256(content.encode()).hexdigest(), signature or silver.NLP_SIGNATURE)


class PipelineTests(unittest.TestCase):

    # Tanggal harus mempertahankan WIB dan tanggal tidak valid ditolak.
    def test_parser_dates(self):
        self.assertEqual(parse_date("16 November 2026 08:30"), "2026-11-16T08:30:00+07:00")
        self.assertIsNone(parse_date("31 Februari 2026 08:30"))

    # Konten rekomendasi tidak boleh masuk isi berita.
    def test_parser_excludes_recommendations(self):
        soup = BeautifulSoup('<h1 class="post-title">Judul</h1><section id="content"><div class="post-body"><p>Isi</p><div class="bacajuga"><p>Iklan</p></div></div><p>Penulis: Ani</p></section>', "html.parser")
        result = parse_article(soup, "https://example.com/news/a")
        self.assertEqual(result["content"], "Isi")
        self.assertEqual(result["author"], "Ani")

    # Cursor tombol dipilih sebelum ID elemen lain.
    def test_cursor(self):
        self.assertEqual(get_next_id('<button id="load_more_button" data-id="123"></button><div id="999"></div>'), "123")


    # Normalisasi tidak mengubah nama dan singkatan di luar kamus.
    def test_preprocessing(self):
        self.assertEqual(silver.normalize_tokens(["gw", "udh", "prabowo", "dpr", "dpt"]), ["saya", "sudah", "prabowo", "dpr", "dpt"])
        self.assertEqual(silver.preprocess("perintah pemerintah"), ["perintah", "pemerintah"])
        self.assertEqual(silver.preprocess("dan yg utk 123 https://example.com"), [])

    # Rencana inkremental memisahkan pembaruan metadata dari NLP.
    def test_incremental_plan(self):
        old = row()
        self.assertEqual(silver.plan_changes([old[:10]], [old]), ([], []))
        metadata = list(old[:10]); metadata[5] = "Ani"
        changed, pending = silver.plan_changes([tuple(metadata)], [old])
        self.assertEqual(len(changed), 1); self.assertEqual(pending, [])
        self.assertEqual(len(silver.plan_changes([row("astronaut")[:10]], [old])[1]), 1)
        self.assertEqual(len(silver.plan_changes([old[:10]], [old], signature="new")[1]), 1)

    # Status artikel kosong mencegah penghitungan NLP berulang.
    def test_empty_tokens_have_processing_state(self):
        old = row("dan yang")
        self.assertEqual(silver.plan_changes([old[:10]], [old]), ([], []))
        self.assertEqual(len(silver.plan_changes([old[:10]], [old[:10] + (None, None)])[1]), 1)

    # Cache bertahan setelah koneksi ditutup, termasuk hasil token kosong.
    def test_sqlite_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cache.sqlite3"
            with NLPCache(path) as cache:
                cache.put("a", {}); cache.put("b", {"roket": 2})
            with NLPCache(path) as cache:
                self.assertEqual(cache.get("a"), {})
                self.assertEqual(cache.get("b"), {"roket": 2})
                self.assertIsNone(cache.get("missing"))



if __name__ == "__main__":
    unittest.main()
