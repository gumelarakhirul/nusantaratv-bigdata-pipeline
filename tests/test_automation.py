import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.crawling import crawler, scrape_details
from src.analytics import export_analytics as analytics


class CrawlerTests(unittest.TestCase):
    def test_load_more_button_is_preferred(self):
        self.assertEqual(crawler.get_next_id(
            '<button id="load_more_button" data-id="123"></button><div id="999"></div>'), "123")

    def test_first_request_uses_empty_cursor(self):
        session = MagicMock()
        session.get.return_value.text = '<meta name="csrf-token" content="test">'
        session.post.return_value.text = (
            '<a href="/news/latest">Judul artikel terbaru untuk pengujian</a>'
            '<button id="load_more_button" data-id="123"></button>')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder, \
             patch.object(crawler.requests, "Session", return_value=session), \
             patch.object(crawler, "OUTPUT_DIR", Path(folder)), \
             patch.object(crawler, "TARGET_ARTICLES", 1), \
             patch.object(crawler.time, "sleep"), redirect_stdout(io.StringIO()):
            crawler.main()
            self.assertTrue((Path(folder) / "bronze_article_urls.json").exists())
        self.assertEqual(session.post.call_args.kwargs["data"]["id"], "")

    def test_failed_scrape_does_not_report_success(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            session = MagicMock()
            session.get.return_value.text = '<html></html>'
            session.get.return_value.url = 'https://example.com/news/a'
            with patch.object(scrape_details, "INPUT_FILE", root / "urls.json"), \
                 patch.object(scrape_details, "OUTPUT_FILE", root / "articles.json"), \
                 patch.object(scrape_details, "ERROR_FILE", root / "errors.json"), \
                 patch.object(scrape_details, "create_session", return_value=session), \
                 patch.object(scrape_details.time, "sleep"), redirect_stdout(io.StringIO()):
                (root / "urls.json").write_text(
                    '[{"article_id":"a","article_url":"https://example.com/news/a"}]')
                with self.assertRaises(RuntimeError):
                    scrape_details.main()
                self.assertTrue((root / "errors.json").exists())


class AnalyticsTests(unittest.TestCase):
    def test_quality_check_blocks_mismatches(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(200,), (1,)]
        with self.assertRaisesRegex(ValueError, "staging_without_silver"):
            analytics.validate(cursor)

    def test_empty_gold_is_rejected(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (0,)
        with self.assertRaisesRegex(ValueError, "Gold kosong"):
            analytics.validate(cursor)

    def test_export_failure_preserves_existing_csv(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.copy_expert.side_effect = RuntimeError("copy failed")
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            target = root / "nusantaratv_analytics.csv"
            target.write_text("previous export")
            with patch.object(analytics, "get_connection", return_value=conn), \
                 patch.object(analytics, "validate"), \
                 patch.object(analytics, "OUTPUT_DIR", root):
                with self.assertRaises(RuntimeError):
                    analytics.main()
            self.assertEqual(target.read_text(), "previous export")
            self.assertFalse(list(root.glob("*.tmp")))
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
