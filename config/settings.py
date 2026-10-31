import os
from pathlib import Path

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def env_required(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(
            f"Переменная окружения {name} не задана. Скопируйте .env.example в .env."
        )
    return value


SECRET_KEY = env_required("SECRET_KEY")

DEBUG = env_bool("DEBUG")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "crispy_forms",
    "crispy_bootstrap5",
    "dashboard",
    "user",
    "strategies",
    "monitoring",
    "rest_framework",
    "django_filters",
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "main_format": {
            "format": "[{module} {asctime} {levelname}] {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "main_format"},
        "file": {
            "class": "logging.FileHandler",
            "formatter": "main_format",
            "filename": BASE_DIR / "app.logs",
        },
    },
    "loggers": {
        "dashboard": {"handlers": ["console", "file"], "level": "INFO", "propagate": False}
    },
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "monitoring.context_processors.unread_notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "investing"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": env_required("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "ru"

TIME_ZONE = "Europe/Moscow"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

"""Market data"""
MARKET_DATA_PROVIDER = os.environ.get("MARKET_DATA_PROVIDER", "iss").strip().lower()
MARKET_DATA_TIMEOUT = int(os.environ.get("MARKET_DATA_TIMEOUT", "30"))
ISS_BASE_URL = os.environ.get("ISS_BASE_URL", "https://iss.moex.com/iss")
ISS_BOARD = os.environ.get("ISS_BOARD", "TQBR")
TINVEST_TOKEN = os.environ.get("TINVEST_TOKEN", "")
TINVEST_TARGET = os.environ.get("TINVEST_TARGET", "invest-public-api.tbank.ru:443")
TINVEST_ROOT_CA_PATH = os.environ.get("TINVEST_ROOT_CA_PATH", "")

"""Price history"""
HISTORY_BACKFILL_DAYS = int(os.environ.get("HISTORY_BACKFILL_DAYS", "365"))
HISTORY_QUOTE_RETENTION_DAYS = int(os.environ.get("HISTORY_QUOTE_RETENTION_DAYS", "30"))
HISTORY_REQUEST_PAUSE = float(os.environ.get("HISTORY_REQUEST_PAUSE", "0.2"))

"""Monitoring"""
MONITORING_REARM_PERCENT = float(os.environ.get("MONITORING_REARM_PERCENT", "0.1"))

"""Celery Configuration Options"""
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

PRICE_UPDATE_INTERVAL = int(os.environ.get("PRICE_UPDATE_INTERVAL", "300"))
CELERY_BEAT_SCHEDULE = {
    "update-last-price": {
        "task": "dashboard.tasks.update_last_price",
        "schedule": PRICE_UPDATE_INTERVAL,
        "options": {"expires": PRICE_UPDATE_INTERVAL},
    },
    "update-price-history": {
        "task": "dashboard.tasks.update_price_history",
        "schedule": crontab(hour=1, minute=0),
    },
    "update-strategies": {
        "task": "strategies.tasks.update_strategies",
        "schedule": crontab(hour=1, minute=30),
    },
}

"""Debug Celery"""
CELERY_TASK_ALWAYS_EAGER = False
