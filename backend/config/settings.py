"""Django settings for the weather-aware truck router."""

import os
from pathlib import Path

from dotenv import load_dotenv

from routing.constants import (
    OPEN_METEO_BASE_URL as DEFAULT_OPEN_METEO_BASE_URL,
    OPEN_METEO_GEOCODE_URL as DEFAULT_OPEN_METEO_GEOCODE_URL,
    OPENROUTESERVICE_BASE_URL as DEFAULT_OPENROUTESERVICE_BASE_URL,
    OSRM_BASE_URL as DEFAULT_OSRM_BASE_URL,
)

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me",
)
DEBUG = _env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = _env_list(
    "DJANGO_ALLOWED_HOSTS",
    ["localhost", "127.0.0.1", ".onrender.com"],
)
render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_host and render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_host)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))

if os.environ.get("RENDER"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS if host and not host.startswith(".")]
    if render_host:
        CSRF_TRUSTED_ORIGINS.append(f"https://{render_host}")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "truck-router",
    }
}

CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}

OPENROUTESERVICE_BASE_URL = os.environ.get(
    "OPENROUTESERVICE_BASE_URL",
    DEFAULT_OPENROUTESERVICE_BASE_URL,
).rstrip("/")
OPENROUTESERVICE_API_KEY = os.environ.get("OPENROUTESERVICE_API_KEY", "")
OPEN_METEO_BASE_URL = os.environ.get(
    "OPEN_METEO_BASE_URL",
    DEFAULT_OPEN_METEO_BASE_URL,
).rstrip("/")
OPEN_METEO_GEOCODE_URL = os.environ.get(
    "OPEN_METEO_GEOCODE_URL",
    DEFAULT_OPEN_METEO_GEOCODE_URL,
).rstrip("/")
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", DEFAULT_OSRM_BASE_URL).rstrip("/")
