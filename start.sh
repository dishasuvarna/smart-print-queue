#!/usr/bin/env bash
# Render "Start Command". Runs Django, a Celery worker, and Celery Beat
# inside one free-tier instance. This is a documented cost-saving trade-off
# (point 15) — see README for how to split it into separate services with
# zero application code changes once you move to paid hosting.
set -e

python manage.py collectstatic --noinput

celery -A config worker --loglevel=info --concurrency=2 &
celery -A config beat --loglevel=info &

exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}
