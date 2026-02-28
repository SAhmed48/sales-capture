#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
while ! python -c "
import os
import psycopg2
from urllib.parse import urlparse
try:
    url = os.environ.get('DATABASE_URL', '')
    if url:
        result = urlparse(url)
        conn = psycopg2.connect(
            dbname=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port or 5432
        )
        conn.close()
        exit(0)
except Exception:
    exit(1)
" 2>/dev/null; do
    sleep 2
done

echo "PostgreSQL is ready. Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Starting application..."
exec gunicorn config.wsgi:application -c gunicorn.conf.py
