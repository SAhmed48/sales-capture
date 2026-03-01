# Sales Capture - Single-Page Form with Click Tracking

A Django application that collects user information via a form, saves it to PostgreSQL, sends confirmation via email and SMS, and tracks metadata when users click the confirmation link.

## Quick Start

### Using Docker (recommended)

1. Copy `.env.example` to `.env` and configure your credentials:
   ```bash
   cp .env.example .env
   ```

2. Build and run:
   ```bash
   docker-compose up --build
   ```

3. Open http://localhost:8000

### Local Development (without Docker)

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```

2. Create a PostgreSQL database and set `DATABASE_URL` in `.env`.

3. Run migrations:
   ```bash
   python manage.py migrate
   ```

4. Start the server:
   ```bash
   python manage.py runserver
   ```

## Configuration

Set these environment variables (see `.env.example`):

- **Django:** `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
- **Database:** `DATABASE_URL` or `POSTGRES_*` vars for Docker
- **Email:** `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_FROM`
- **SMS (Twilio):** `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`

## Flow

1. User fills the form (name, phone, email, address, zip, country, city) and submits.
2. Data is saved to PostgreSQL; email and SMS are sent with a unique tracking link.
3. When the user clicks the link, a page loads that collects browser/device/screen metadata via JavaScript.
4. Metadata is POSTed to the API; the server adds IP, headers, geo (from IP), and saves to the database.

## Troubleshooting

**"Error handling request (no URI read)"** – This appears when a client disconnects before sending a full HTTP request (e.g., quick refresh, tab close, health checks). It is harmless; Gunicorn restarts the worker automatically. For production, use a reverse proxy (nginx) with `proxy_ignore_client_abort on` to reduce these logs.

## Admin

Create a superuser and access the admin at `/admin/`:

```bash
python manage.py createsuperuser
```
