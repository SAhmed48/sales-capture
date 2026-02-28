FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh

# Collect static files during build (admin CSS/JS, etc.)
ENV DJANGO_SETTINGS_MODULE=config.settings
ENV DEBUG=True
ENV SECRET_KEY=build-only
RUN python manage.py collectstatic --noinput --clear

ENTRYPOINT ["/app/entrypoint.sh"]
