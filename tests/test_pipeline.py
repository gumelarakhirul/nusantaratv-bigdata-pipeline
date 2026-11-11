import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.crawling import crawler, scrape_details
from src.ingestion import ingest_articles as ingestion
from src.transformation import transform_silver as silver
from src.transformation import transform_gold as gold


def article(**updates):
    row = dict(article_id="abc", title="Judul", content="Isi artikel", category="news",
               article_url="https://www.nusantaratv.com/news/abc",
               published_at="2026-11-11T12:00:00+07:00")
    row.update(updates)
    return row


class ValidationTests(unittest.TestCase):
    def test_valid_optional_null_fields(self):
        self.assertEqual(ingestion.validate_article(article(author=None)), (True, None))

    def test_invalid_rows_are_rejected(self):
        for updates in [dict(title={"bad": "type"}), dict(author="x" * 256),
                        dict(article_id="x" * 65), dict(category=" "), dict(title="a\x00b"),
                        dict(published_at="2026-11-11T12:00:00"), dict(crawled_at=""),
                        dict(word_count=-1), dict(word_count=True), dict(word_count=2.5),
                        dict(word_count=2147483648)]:
            with self.subTest(updates=updates):
                self.assertFalse(ingestion.validate_article(article(**updates))[0])

    def test_paths_share_bronze_directory(self):
        self.assertEqual(scrape_details.OUTPUT_FILE, ingestion.INPUT_FILE)
        self.assertEqual(crawler.OUTPUT_DIR / "bronze_article_urls.json", scrape_details.INPUT_FILE)
        self.assertTrue(ingestion.INPUT_FILE.is_absolute())

    def test_naive_silver_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            silver.parse_datetime(datetime(2026, 11, 11))

    def test_jakarta_date_boundary(self):
        value = gold.to_jakarta("2026-11-10T18:00:00Z")
        self.assertEqual(gold.get_date_id(value), 20261111)
        self.assertEqual(value.hour, 1)


class NLPTests(unittest.TestCase):
    def test_distinct_meanings(self):
        self.assertEqual(silver.preprocess("perintah pemerintah pemerintahan"),
                         ["perintah", "pemerintah", "pemerintah"])

    def test_noise_and_empty_text(self):
        self.assertEqual(silver.preprocess("dan https://example.com 123 !!!"), [])
        self.assertEqual(silver.preprocess(None), [])


class TransactionTests(unittest.TestCase):
    def run_silver(self, fail=False):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [
            [("new", "Title", "Konten", None, "news", None,
              datetime(2026, 11, 11, tzinfo=timezone.utc), "https://example.com/a", None)],
            [("old", "lama"), ("new", "baru")],
        ]
        batch = MagicMock()
        if fail:
            batch.side_effect = [None, RuntimeError("insert failed")]
        with patch.object(silver, "get_connection", return_value=conn), \
             patch.object(silver, "execute_batch", batch), \
             patch.object(silver, "preprocess", side_effect=lambda text: [text]), \
             redirect_stdout(io.StringIO()):
            if fail:
                with self.assertRaises(RuntimeError):
                    silver.main()
            else:
                silver.main()
        return conn, batch

    def test_refresh_includes_old_articles(self):
        conn, batch = self.run_silver()
        self.assertEqual(batch.call_args_list[1].args[2],
                         [("old", "lama", 1), ("new", "baru", 1)])
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        conn.close.assert_called_once()

    def test_token_failure_rolls_back_articles(self):
        conn, _ = self.run_silver(fail=True)
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_gold_accepts_empty_keywords(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [
            [("abc", "news", None, datetime(2026, 11, 11, tzinfo=timezone.utc), 2)],
            [(1, "news")], [],
        ]
        cursor.fetchone.return_value = (0,)
        with patch.object(gold, "get_connection", return_value=conn), \
             patch.object(gold, "execute_batch"), redirect_stdout(io.StringIO()):
            gold.main()
        conn.commit.assert_called_once()
        self.assertTrue(any("DELETE FROM gold.article_keywords" in call.args[0]
                            for call in cursor.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
