# """
# Celery application factory — identical in local dev and production.
# Broker/result backend come from Django settings, which come from REDIS_URL
# in .env. Nothing in this file changes between environments (points 2, 4).
# """

# import os

# from celery import Celery

# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# app = Celery("smart_print")
# app.config_from_object("django.conf:settings", namespace="CELERY")
# app.conf.broker_transport_options = {
#     "polling_interval": 30.0,
# }
# app.autodiscover_tasks()
# app.conf.worker_send_task_events = False
# app.conf.task_send_sent_event = False

# # Celery Beat schedule — same schedule, same tasks, in both environments.
# app.conf.beat_schedule = {
#     "expire-stale-orders": {
#         "task": "orders.tasks.expire_stale_orders",
#         "schedule": 300.0,  # every 5 minutes
#     },
#     "reconcile-pending-payments": {
#         "task": "orders.tasks.reconcile_pending_payments",
#         "schedule": 600.0,  # every 10 minutes
#     },
#     "cleanup-expired-order-files": {
#         "task": "orders.tasks.cleanup_expired_order_files",
#         "schedule": 3600.0,  # every hour
#     },
# }



import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("smart_print")
# Loads CELERY_BROKER_TRANSPORT_OPTIONS directly from settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
app.conf.worker_send_task_events = False
app.conf.task_send_sent_event = False
app.conf.worker_enable_remote_control = False

app.conf.update(
    worker_enable_remote_control=False,  # Stops celery.pidbox control queue polling & PUBLISH spam
    worker_send_task_events=False,       # Disables task event publishing
    task_send_sent_event=False,          # Disables task sent event publishing
    # result_expires=3600,
)
app.conf.beat_schedule = {
    "expire-stale-orders": {
        "task": "orders.tasks.expire_stale_orders",
        "schedule": 300.0,
    },
    "reconcile-pending-payments": {
        "task": "orders.tasks.reconcile_pending_payments",
        "schedule": 600.0,
    },
    "cleanup-expired-order-files": {
        "task": "orders.tasks.cleanup_expired_order_files",
        "schedule": 3600.0,
    },
}
