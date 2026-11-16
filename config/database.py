"""Koneksi warehouse menggunakan URL Neon dari .env."""
import os
from pathlib import Path

import psycopg2
from psycopg2.extensions import parse_dsn
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / '.env')


# Membuka koneksi SSL ke warehouse Neon dari variabel lingkungan.
def get_connection():
    # Gunakan URL langsung untuk DDL dan proses ETL yang panjang.
    database_url = (os.getenv('DATABASE_URL') or '').strip()
    if not database_url:
        raise ValueError('Isi DATABASE_URL Neon di .env')
    sslmode = parse_dsn(database_url).get('sslmode', 'require')
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise ValueError('Koneksi warehouse Neon harus menggunakan SSL')
    return psycopg2.connect(database_url, connect_timeout=30, sslmode=sslmode)
