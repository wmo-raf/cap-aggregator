#!/bin/bash
# Entry-point modes. Dev modes auto-reload:
#   django-dev                    runserver (Django autoreload)
#   celery-*-worker-dev           watchmedo auto-restart around celery
set -e

cd /app/src

# Wait for required services (docker-compose-wait; reads WAIT_HOSTS / WAIT_TIMEOUT env)
/wait


run_celery_worker() {
  local queue="$1" concurrency="$2" name="$3"
  exec celery -A capaggregator.config worker -Q "$queue" -c "$concurrency" \
    -l "${CAPAGG_CELERY_WORKER_LOG_LEVEL:-INFO}" -n "$name@%h"
}

run_celery_worker_dev() {
  local queue="$1" concurrency="$2" name="$3"
  # Auto-restart the worker when source files change (requires watchdog, dev image)
  exec watchmedo auto-restart --directory=/app/src --pattern='*.py' --recursive -- \
    celery -A capaggregator.config worker -Q "$queue" -c "$concurrency" \
    -l "${CAPAGG_CELERY_WORKER_LOG_LEVEL:-INFO}" -n "$name@%h"
}

case "$1" in
django-dev)
  capagg migrate --noinput
  capagg create_alerts_tile_function
  # Collect in dev too so nginx (WEB_PORT) can serve /static/ from the shared
  # mount; runserver still serves statics directly on APP_PORT via finders
  capagg collectstatic --noinput
  exec capagg runserver 0.0.0.0:8000
  ;;
gunicorn)
  capagg migrate --noinput
  capagg create_alerts_tile_function
  capagg collectstatic --noinput
  exec gunicorn capaggregator.config.wsgi:application -b 0.0.0.0:8000 \
    -w "${GUNICORN_WORKERS:-4}" --timeout "${GUNICORN_TIMEOUT:-120}"
  ;;
celery-default-worker)
  run_celery_worker capagg-default "${CAPAGG_CELERY_DEFAULT_WORKER_CONCURRENCY:-2}" default
  ;;
celery-default-worker-dev)
  run_celery_worker_dev capagg-default "${CAPAGG_CELERY_DEFAULT_WORKER_CONCURRENCY:-2}" default
  ;;
celery-ingestion-worker)
  run_celery_worker capagg-ingestion "${CAPAGG_CELERY_INGESTION_WORKER_CONCURRENCY:-2}" ingestion
  ;;
celery-ingestion-worker-dev)
  run_celery_worker_dev capagg-ingestion "${CAPAGG_CELERY_INGESTION_WORKER_CONCURRENCY:-2}" ingestion
  ;;
celery-beat)
  exec celery -A capaggregator.config beat -l INFO \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
  ;;
mqtt-consumer)
  exec capagg mqtt_consumer
  ;;
*)
  exec "$@"
  ;;
esac
