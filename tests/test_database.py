import os
import unittest
from unittest.mock import patch
from config import database


class DatabaseConnectionTests(unittest.TestCase):
    @patch.object(database.psycopg2, "connect")
    def test_neon_direct_url_wins(self, connect):
        with patch.dict(os.environ, {"DATABASE_URL_UNPOOLED": "postgresql://direct/db?sslmode=require",
                                    "DATABASE_URL": "postgresql://pooled/db?sslmode=require"}, clear=True):
            database.get_connection()
        connect.assert_called_once_with("postgresql://direct/db?sslmode=require", connect_timeout=30, sslmode="require")

    @patch.object(database.psycopg2, "connect")
    def test_neon_pooled_url_fallback(self, connect):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://pooled/db?sslmode=require"}, clear=True):
            database.get_connection()
        connect.assert_called_once_with("postgresql://pooled/db?sslmode=require", connect_timeout=30, sslmode="require")

    @patch.object(database.psycopg2, "connect")
    def test_missing_url_fails_without_local_fallback(self, connect):
        with patch.dict(os.environ, {"DB_PASSWORD": "old-local-password"}, clear=True):
            with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
                database.get_connection()
        connect.assert_not_called()

    @patch.object(database.psycopg2, "connect")
    def test_insecure_ssl_mode_rejected(self, connect):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://host/db?sslmode=disable"}, clear=True):
            with self.assertRaisesRegex(ValueError, "SSL"):
                database.get_connection()
        connect.assert_not_called()

    @patch.object(database.psycopg2, "connect")
    def test_stronger_ssl_preserved(self, connect):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://host/db?sslmode=verify-full"}, clear=True):
            database.get_connection()
        self.assertEqual(connect.call_args.kwargs["sslmode"], "verify-full")


if __name__ == "__main__":
    unittest.main()
