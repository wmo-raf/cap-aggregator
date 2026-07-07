"""Base settings"""

import os
from pathlib import Path

import dj_database_url
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # src/capaggregator

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False),
)

dev_env_path = BASE_DIR.parent.parent / ".env"  # .env file in the project root

# reading .env file
if dev_env_path.exists():
    environ.Env.read_env(dev_env_path)

SECRET_KEY = env("SECRET_KEY", default="insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
# Origins (with scheme) allowed for cross-origin POSTs — must include every
# public URL the site is served from (e.g. the nginx port)
CSRF_TRUSTED_ORIGINS = [o for o in env.list("CSRF_TRUSTED_ORIGINS", default=[]) if o]

INSTALLED_APPS = [
    # Local apps
    "capaggregator.sources",
    "capaggregator.ingestion",
    "capaggregator.alerts",
    "capaggregator.geocodes",
    "capaggregator.tiles",
    "capaggregator.api",
    # Wagtail
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.settings",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    # Third party
    "rest_framework",
    "rest_framework_gis",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
    "task_ferry",
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.postgres",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "capaggregator.config.urls"
WSGI_APPLICATION = "capaggregator.config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "config" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "wagtail.contrib.settings.context_processors.settings",
            ],
        },
    },
]

# Database — configured via DATABASE_URL (postgis:// scheme selects the PostGIS engine)
DB_CONNECTION_MAX_AGE = env.int("DB_CONNECTION_MAX_AGE", default=0)
DB_CONN_HEALTH_CHECKS = env.bool("DB_CONN_HEALTH_CHECKS", default=False)
DB_DISABLE_SERVER_SIDE_CURSORS = env.bool("DB_DISABLE_SERVER_SIDE_CURSORS", default=False)
DB_SSL_REQUIRE = env.bool("DB_SSL_REQUIRE", default=False)

DATABASES = {
    "default": dj_database_url.config(
        conn_max_age=DB_CONNECTION_MAX_AGE,
        conn_health_checks=DB_CONN_HEALTH_CHECKS,
        disable_server_side_cursors=DB_DISABLE_SERVER_SIDE_CURSORS,
        ssl_require=DB_SSL_REQUIRE,
    )
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

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

# Collected on startup (entrypoint) into the shared mount served by nginx at
# /static/ and /media/ (compose sets STATIC_ROOT=/app/staticfiles etc.)
STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", default=os.path.join(BASE_DIR, "static_root"))
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=os.path.join(BASE_DIR, "media"))

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

WAGTAIL_SITE_NAME = "CAP Aggregator"
WAGTAILADMIN_BASE_URL = env("WAGTAILADMIN_BASE_URL", default="http://localhost:8000")

VERSION = "0.1.0"

# --- Cache (redis) ---
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "capagg-default-cache",
        "VERSION": VERSION,
    },
}

# --- Celery ---
CELERY_BROKER_URL = REDIS_URL
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# celery-singleton reuses the django-redis connection instead of opening its own
CELERY_SINGLETON_BACKEND_CLASS = (
    "capaggregator.celery_singleton_backend.RedisBackendForSingleton"
)

# Results stored in the database (django-celery-results) — inspectable in the
# admin and survives Redis restarts
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True

CELERY_CACHE_BACKEND = "default"

# Late ack — task only acknowledged after completion.
# If a worker crashes mid-task, the message returns to the queue.
CELERY_TASK_ACKS_LATE = True

# Reject tasks back to the queue on worker lost (OOM kill, SIGKILL)
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Prefetch 1 task at a time per worker slot.
# Prevents one worker from hoarding tasks while others are idle.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Static schedule; django_celery_beat's DatabaseScheduler syncs these into
# editable PeriodicTask rows on startup, so a fresh deploy ingests with no manual
# step while operators can still pause/retune at runtime. The poll dispatcher
# decides per-authority who is due (adaptive fast/reconcile interval); beat only ticks.
CELERY_BEAT_SCHEDULE = {
    "poll-all-feeds": {
        "task": "capaggregator.ingestion.tasks.poll_all_feeds",
        "schedule": 60,
    },
    "sweep-unprocessed": {
        "task": "capaggregator.ingestion.tasks.sweep_unprocessed",
        "schedule": 300,
    },
}

# --- django-task-ferry (async jobs with progress, served at /api/jobs/) ---
TASK_FERRY = {
    "EXECUTOR": "task_ferry.executors.celery.CeleryExecutor",
    "CELERY_QUEUE": "capagg-ingestion",
    "PROGRESS_CACHE_TIMEOUT": 7200,  # 2 hours
    "JOB_EXPIRY_DAYS": 14,
}

# --- MQTT (aggregator's own broker) ---
MQTT_HOST = env("MQTT_HOST", default="capagg-mosquitto")
MQTT_PORT = env.int("MQTT_PORT", default=1883)
MQTT_CONSUMER_USERNAME = env("MQTT_CONSUMER_USERNAME", default="capagg-consumer")
MQTT_CONSUMER_PASSWORD = env("MQTT_CONSUMER_PASSWORD", default="")
MQTT_IN_TOPIC = env("MQTT_IN_TOPIC", default="cap/in/#")

# Fernet key for encrypting stored secrets (mirrors cap-composer's CAP_MQTT_SECRET_KEY)
CAPAGG_SECRET_KEY = env("CAPAGG_SECRET_KEY", default="")

# Mosquitto auth files — rewritten automatically on SourceAuthority save
# (shared mount with the broker container, which self-reloads on change)
MOSQUITTO_AUTH_DIR = env("MOSQUITTO_AUTH_DIR", default="/mosquitto-config")
MOSQUITTO_UID = env.int("MOSQUITTO_UID", default=1883)  # mosquitto user in eclipse-mosquitto image

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "CAP Aggregator API",
    "VERSION": "0.1.0",
}
