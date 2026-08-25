#!/usr/bin/env bash
set -e

python manage.py collectstatic --noinput

celery -A config worker --loglevel=info --concurrency=2 --without-gossip --without-mingle --without-heartbeat &
celery -A config beat --loglevel=info &

exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}