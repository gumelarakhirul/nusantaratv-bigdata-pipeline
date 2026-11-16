"""Cache NLP yang tersimpan dalam satu file SQLite lokal."""
import json
import sqlite3
from collections import Counter
from pathlib import Path


# Memeriksa format token dan frekuensi pada cache.
def valid_frequencies(value):
    return isinstance(value, dict) and all(
        isinstance(token, str) and 0 < len(token) <= 100
        and type(count) is int and count > 0
        for token, count in value.items()
    )


class NLPCache:
    # Menyimpan lokasi file cache SQLite.
    def __init__(self, path):
        self.path = Path(path)
        self.connection = None

    # Membuka SQLite dan membuat tabel cache jika belum ada.
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        try:
            with self.connection:
                self.connection.execute("""
                    CREATE TABLE IF NOT EXISTS nlp_cache (
                        cache_key TEXT PRIMARY KEY,
                        frequencies TEXT NOT NULL,
                        cached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        except Exception:
            self.connection.close()
            raise
        return self

    # Mengambil frekuensi valid dari cache berdasarkan kunci.
    def get(self, key):
        row = self.connection.execute(
            "SELECT frequencies FROM nlp_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row[0])
        except ValueError:
            return None
        return Counter(value) if valid_frequencies(value) else None

    # Menyimpan satu hasil NLP agar dapat dipakai ulang.
    def put(self, key, frequencies):
        if not valid_frequencies(frequencies):
            raise ValueError('Frekuensi cache NLP tidak valid')
        # Simpan setiap hasil artikel agar percobaan ulang dapat melanjutkan cache.
        with self.connection:
            self.connection.execute("""
                INSERT INTO nlp_cache (cache_key, frequencies) VALUES (?, ?)
                ON CONFLICT (cache_key) DO UPDATE SET
                    frequencies = excluded.frequencies,
                    cached_at = CURRENT_TIMESTAMP
            """, (key, json.dumps(frequencies, ensure_ascii=False)))

    # Menutup koneksi cache SQLite.
    def __exit__(self, exc_type, exc_value, traceback):
        self.connection.close()
