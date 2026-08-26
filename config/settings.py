"""
Django settings — identical in local development and production.

Every environment-specific value comes from an environment variable (.env),
never from an if-else on "am I local or deployed." That's what makes local
and deployed behavior match exactly (points 1, 2, 3, 13).
"""

from pathlib import Path

import dj_database_url
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")  # .env.local or .env.production, copied to .env

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "orders",
    "notifications",
    "axes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ---------------------------------------------------------------------------
# Login rate limiting (django-axes)
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = 3
AXES_COOLOFF_TIME = 0.0084  # ~30 seconds, in hours (30/3600)
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database — Postgres everywhere, dev included (point 1).
# No SQLite anywhere, so query behavior, constraints, and migrations behave
# identically in both environments. DATABASE_URL points at Docker Postgres
# locally and at Supabase Postgres in production — same variable, same code.
# ---------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.parse(env("DATABASE_URL"), conn_max_age=600)
}

# ---------------------------------------------------------------------------
# Redis + Celery — one broker URL used identically for local Docker Redis
# and Upstash Redis in production. Nothing here branches on environment.
# (points 2, 4)
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL")

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"
CELERY_TASK_TRACK_STARTED = True

CELERY_TASK_RESULT_EXPIRES = 3600 
CELERY_TASK_IGNORE_RESULT = True 
# Late acks + reject-on-lost-worker: a task that dies mid-run (e.g. a Render
# free-tier restart) gets redelivered instead of silently vanishing.
# Per-task retry/backoff is layered on top of this in orders/tasks.py
# and notifications/tasks.py (point 9).
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "polling_interval": 30.0,  # check Redis every 30s instead of ~every 1s
}

USE_TZ = True
TIME_ZONE = "Asia/Kolkata"

# ---------------------------------------------------------------------------
# Razorpay / Brevo — read purely from env. Switching Razorpay test -> live
# is a key swap in the environment, nothing else (points 5, 6).
# ---------------------------------------------------------------------------
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET")

BREVO_API_KEY = env("BREVO_API_KEY")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="orders@yourcollegeproject.com")
SHOPKEEPER_EMAIL = env("SHOPKEEPER_EMAIL")

# ---------------------------------------------------------------------------
# Security — toggled by DEBUG, not by a separate settings file (point 12).
# When DEBUG=False (your production .env), these switch on automatically.
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7  # start at 1 week, raise once confident
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

STATIC_URL = "static/"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "access_key": env("SUPABASE_S3_ACCESS_KEY_ID"),
            "secret_key": env("SUPABASE_S3_SECRET_ACCESS_KEY"),
            "bucket_name": env("SUPABASE_S3_BUCKET"),
            "endpoint_url": env("SUPABASE_S3_ENDPOINT"),
            "region_name": env("SUPABASE_S3_REGION"),
            "default_acl": "public-read",
            "querystring_auth": False,
            "file_overwrite": False,
            "custom_domain": f"{env('SUPABASE_PROJECT_REF')}.supabase.co/storage/v1/object/public/{env('SUPABASE_S3_BUCKET')}",
        },
    }

# ---------------------------------------------------------------------------
# Logging — same handlers in both environments; only LOG_LEVEL differs via
# env var. Named loggers per subsystem make debugging targeted without
# touching application logic (point 11).
# ---------------------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "orders.payments": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "orders.queue": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "orders.pdf": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "notifications.email": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "celery": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

LOGIN_URL = "/admin/login/"