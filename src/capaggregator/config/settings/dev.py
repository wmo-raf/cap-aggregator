from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Hot reload from the capagg-vite dev server unless explicitly disabled
DJANGO_VITE["default"]["dev_mode"] = env.bool("DJANGO_VITE_DEV_MODE", default=True)  # noqa: F405

# Local dev origins (runserver + nginx) unless explicitly configured
if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    CSRF_TRUSTED_ORIGINS = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
