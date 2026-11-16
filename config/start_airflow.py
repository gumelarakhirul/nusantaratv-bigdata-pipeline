"""Menyiapkan kredensial dari lingkungan container sebelum memulai Airflow."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg2
from psycopg2 import sql


# Menyiapkan password admin dan URL database metadata.
def configure(environ):
    admin_password = environ.get('AIRFLOW_ADMIN_PASSWORD', '')
    db_password = environ.get('AIRFLOW_DB_PASSWORD', '')
    if not admin_password.strip() or not db_password.strip():
        raise ValueError('Isi AIRFLOW_ADMIN_PASSWORD dan AIRFLOW_DB_PASSWORD di .env')
    # Enkode karakter khusus agar password aman dimasukkan ke URL.
    environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = (
        "postgresql+psycopg2://airflow:" + quote(db_password, safe="")
        + "@airflow-db:5432/airflow"
    )
    password_file = Path(environ.get('AIRFLOW_HOME', '/opt/airflow')) / 'admin_passwords.json'
    password_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = password_file.with_suffix('.json.tmp')
    temp_file.write_text(json.dumps({'admin': admin_password}), encoding='utf-8')
    temp_file.chmod(384)
    temp_file.replace(password_file)
    environ['AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE'] = str(password_file)


# Menyamakan password role metadata dengan nilai variabel lingkungan.
def sync_database_password(environ):
    # Socket lokal memakai autentikasi trust dari image PostgreSQL.
    # Password dapat disesuaikan tanpa memerlukan nilai sebelumnya.
    conn = psycopg2.connect(host="/var/run/airflow-postgres", user="airflow",
                            dbname="airflow", connect_timeout=30)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("ALTER ROLE airflow WITH PASSWORD {}").format(
                sql.Literal(environ["AIRFLOW_DB_PASSWORD"])))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Menyiapkan konfigurasi lalu menjalankan Airflow standalone.
def main():
    configure(os.environ)
    arguments = sys.argv[1:]
    if not arguments:
        sync_database_password(os.environ)
    os.execvp('airflow', ['airflow', *(arguments or ['standalone'])])


if __name__ == "__main__":
    main()
