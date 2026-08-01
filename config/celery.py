"""
Celery application factory — identical in local dev and production.
Broker/result backend come from Django settings, which come from REDIS_URL
in .env. Nothing in this file changes between environments (points 2, 4).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("smart_print")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Celery Beat schedule — same schedule, same tasks, in both environments.
app.conf.beat_schedule = {
    "expire-stale-orders": {
        "task": "orders.tasks.expire_stale_orders",
        "schedule": 300.0,  # every 5 minutes
    },
    "reconcile-pending-payments": {
        "task": "orders.tasks.reconcile_pending_payments",
        "schedule": 600.0,  # every 10 minutes
    },
}
