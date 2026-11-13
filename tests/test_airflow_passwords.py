import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit, unquote

from config.start_airflow import configure, sync_database_password


class AirflowPasswordTests(unittest.TestCase):
    def test_passwords_written_and_special_characters_encoded(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            env = {"AIRFLOW_HOME": folder, "AIRFLOW_ADMIN_PASSWORD": "chosen admin!",
                   "AIRFLOW_DB_PASSWORD": "db@:/#%'\\pass"}
            configure(env)
            target = Path(env["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE"])
            self.assertEqual(json.loads(target.read_text()), {"admin": "chosen admin!"})
            uri = urlsplit(env["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"])
            self.assertEqual(unquote(uri.password), env["AIRFLOW_DB_PASSWORD"])
            self.assertEqual(uri.hostname, "airflow-db")
            env["AIRFLOW_ADMIN_PASSWORD"] = "new chosen password"
            configure(env)
            self.assertEqual(json.loads(target.read_text())["admin"], "new chosen password")

    def test_empty_passwords_rejected(self):
        with self.assertRaises(ValueError):
            configure({})

    @patch("config.start_airflow.psycopg2.connect")
    def test_sync_uses_local_socket_and_commits(self, connect):
        sync_database_password({"AIRFLOW_DB_PASSWORD": "new-password"})
        self.assertEqual(connect.call_args.kwargs["host"], "/var/run/airflow-postgres")
        conn = connect.return_value
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    @patch("config.start_airflow.psycopg2.connect")
    def test_sync_failure_rolls_back(self, connect):
        conn = connect.return_value
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("failed")
        with self.assertRaises(RuntimeError):
            sync_database_password({"AIRFLOW_DB_PASSWORD": "new-password"})
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
