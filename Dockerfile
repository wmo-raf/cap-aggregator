FROM python:3.12-slim-bookworm

# DEV=true (set by docker-compose.dev.yml build args) additionally installs
# dev tooling (watchdog for celery auto-reload, debug toolbar, pytest, ruff).
ARG DEV=false

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev libgeos-dev libproj-dev \
    libxml2-dev libxslt1-dev \
    mosquitto-clients \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install docker-compose-wait (reads WAIT_HOSTS / WAIT_TIMEOUT env at runtime)
ARG DOCKER_COMPOSE_WAIT_VERSION=2.12.1
ARG TARGETARCH
RUN case "${TARGETARCH}" in \
      arm64) WAIT_SUFFIX="_aarch64" ;; \
      *)     WAIT_SUFFIX="" ;; \
    esac \
    && curl -fsSL -o /wait \
       "https://github.com/ufoscout/docker-compose-wait/releases/download/${DOCKER_COMPOSE_WAIT_VERSION}/wait${WAIT_SUFFIX}" \
    && chmod +x /wait

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system -e . \
    && if [ "$DEV" = "true" ]; then \
         uv pip install --system watchdog django-debug-toolbar pytest pytest-django ruff; \
       fi

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["gunicorn"]
