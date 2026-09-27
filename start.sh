# #!/usr/bin/env bash
# set -e

# python manage.py collectstatic --noinput

# celery -A config worker --loglevel=info --concurrency=2 --without-gossip --without-mingle --without-heartbeat &
# celery -A config beat --loglevel=info &

# exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}


#!/usr/bin/env bash
set -e

python manage.py collectstatic --noinput

celery -A config worker --loglevel=info --concurrency=1 --without-gossip --without-mingle --without-heartbeat &
celery -A config beat --loglevel=info &

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers 2 \
  --threads 2 \
  --timeout 60 \
  --max-requests 200 \
  --max-requests-jitter 50