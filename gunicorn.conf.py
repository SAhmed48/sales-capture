"""
Gunicorn configuration.
"""
import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", 2))
worker_tmp_dir = "/tmp"  # /dev/shm can cause issues on macOS Docker
worker_class = "sync"
timeout = 30
graceful_timeout = 30
keepalive = 2
max_requests = 500  # Recycle workers to prevent memory leaks
max_requests_jitter = 50

no_control_socket = True

capture_output = True
accesslog = "-"
errorlog = "-"
loglevel = "info"
