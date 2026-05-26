"""Gunicorn config for tariff_equlizer (production)."""

from __future__ import annotations

import os
from pathlib import Path

# new_project/ — корень Django-проекта
BASE_DIR = Path(__file__).resolve().parent.parent

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "1"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "300"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Тяжёлые расчёты сценариев — держите workers низкими, чтобы не упереться в RAM.
worker_class = "sync"
chdir = str(BASE_DIR)
wsgi_app = "config.wsgi:application"

accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
capture_output = True
