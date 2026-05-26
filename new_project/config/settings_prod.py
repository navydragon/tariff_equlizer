"""
Production settings for tariff_equlizer.

Usage:
    export DJANGO_SETTINGS_MODULE=config.settings_prod
    gunicorn -c deploy/gunicorn.conf.py config.wsgi:application
"""

from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403,F401
from .settings import _env_bool, _env_csv  # noqa: F401

DEBUG = False

_DEV_SECRET_KEY = "dev-secret-key-change-me"
if not SECRET_KEY or SECRET_KEY == _DEV_SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY to a unique random value in production "
        "(see .env.production.example).",
    )

if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["127.0.0.1", "localhost"]:  # noqa: F405
    raise ImproperlyConfigured(
        "Set DJANGO_ALLOWED_HOSTS to your production hostname(s).",
    )

if not USE_POSTGRES:  # noqa: F405
    raise ImproperlyConfigured("USE_POSTGRES=true is required in production.")

CSRF_TRUSTED_ORIGINS = _env_csv("DJANGO_CSRF_TRUSTED_ORIGINS")  # noqa: F405

TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Europe/Moscow")
LANGUAGE_CODE = os.environ.get("DJANGO_LANGUAGE_CODE", "ru")

# HTTPS behind reverse proxy (nginx).
if _env_bool("DJANGO_SECURE_SSL", default=True):  # noqa: F405
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", default=False)  # noqa: F405
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
