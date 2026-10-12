"""
Celery tasks — same code path in local development and production.
Retry policy is defined once per task and applies identically everywhere
(points 4, 9).
"""

from django.db.models import Q
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Order

logger = logging.getLogger("orders.queue")
pdf_logger = logging.getLogger("orders.pdf")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,     # exponential backoff: 1s, 2s, 4s...
    retry_backoff_max=60,
    max_retries=3,
)
def process_pdf(self, order_id):
    """
    Parses page count / color detection in the background. Retries
    automatically on transient failures (e.g. a momentary disk hiccup)
    with no special-case code for local vs. production.
    """
    pdf_logger.info("Processing PDF for order %s", order_id)
    order = Order.objects.get(id=order_id)
    # ... page counting / color detection using pypdf. The file has
    # already passed validators.validate_pdf_upload() at upload time,
    # so failures here should be rare and are worth logging loudly. ...
    order.processing_status = "PROCESSED"
    order.save(update_fields=["processing_status"])
    pdf_logger.info("Finished processing order %s", order_id)


# @shared_task
# def expire_stale_orders():
#     """
#     Celery Beat task, runs every 5 minutes. Marks unpaid orders older
#     than 15 minutes as EXPIRED, and decrements the cached Redis queue
#     counter so the "N orders ahead of you" number on the homepage
#     doesn't silently drift out of sync with reality.
#     """
#     cutoff = timezone.now() - timedelta(minutes=15)
#     stale_orders = Order.objects.filter(status="PENDING", created_at__lt=cutoff)
#     count = stale_orders.count()
#     if count:
#         logger.info("Expiring %d stale unpaid orders", count)
#     for order in stale_orders:
#         order.status = "EXPIRED"
#         order.save(update_fields=["status"])
#         # decrement_queue_cache(order.shop_id)  # your Redis cache update


# @shared_task
# def reconcile_pending_payments():
#     """
#     Celery Beat task, runs every 10 minutes. Safety net for the case
#     where Razorpay's webhook never arrives (network blip, a cold-starting
#     Render instance at the wrong moment). Queries Razorpay directly for
#     orders still PENDING despite the student likely having already paid.
#     """
#     import razorpay
#     from django.conf import settings

#     client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
#     cutoff = timezone.now() - timedelta(minutes=5)
#     pending = Order.objects.filter(status="PENDING", created_at__lt=cutoff)

#     for order in pending:
#         try:
#             payments = client.order.payments(order.razorpay_order_id)
#         except Exception as exc:
#             logger.error("Reconciliation check failed for order %s: %s", order.id, exc)
#             continue

#         if any(p["status"] == "captured" for p in payments["items"]):
#             logger.warning("Order %s was paid but no webhook arrived, reconciling now", order.id)
#             order.mark_paid()

#         paid_entries = [p for p in payments["items"] if p["status"] == "captured"]
#         if paid_entries:
#             logger.warning(
#                 "Order %s was paid but no webhook arrived — reconciling now", order.id
#             )
#             order.status = "PAID"
#             order.save(update_fields=["status"])
#             from notifications.tasks import send_shopkeeper_notification
#             send_shopkeeper_notification.delay(order.id)



RECOVERY_GRACE = timedelta(minutes=20)  # only decides when a stuck checkout is checked


@shared_task
def recover_stuck_checkouts():
    """Settle stuck checkouts, file paid uploads that aren't in storage yet, retry refunds."""
    from .payments import recover_checkout, refund_lost_upload, retry_refund
    from .staging import promote_upload

    cutoff = timezone.now() - RECOVERY_GRACE
    stuck = Order.objects.filter(
        status="PENDING", holds_slot=True, created_at__lt=cutoff
    ).order_by("created_at")[:50]
    for order in stuck:
        try:
            logger.info("Checkout %s: %s", order.id, recover_checkout(order.id))
        except Exception:
            logger.exception("Recovery failed for order %s", order.id)

    unfiled = (
        Order.objects.filter(status="PAID", handout__isnull=True, printed_at__isnull=True)
        .filter(Q(file="") | Q(file__isnull=True))[:50]
    )
    for order in unfiled:
        try:
            if promote_upload(order.id) == "lost":
                refund_lost_upload(order.id)
        except Exception:
            logger.exception("Could not file upload for order %s", order.id)

    for order in Order.objects.filter(status="REFUND_DUE")[:50]:
        try:
            retry_refund(order.id)
        except Exception:
            logger.exception("Refund retry failed for order %s", order.id)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=5)
def promote_upload_task(self, order_id):
    from .payments import refund_lost_upload
    from .staging import promote_upload
    if promote_upload(order_id) == "lost":
        refund_lost_upload(order_id)


@shared_task
def purge_staged_files():
    """Delete temporary uploads whose order no longer needs them."""
    import os
    import time
    from .staging import STAGING_DIR, discard_staged

    if not os.path.isdir(STAGING_DIR):
        return
    for name in os.listdir(STAGING_DIR):
        stem, ext = os.path.splitext(name)
        if ext != ".pdf" or not stem.isdigit():
            continue
        order = Order.objects.filter(pk=int(stem)).first()
        needed = order is not None and (
            (order.status == "PENDING" and order.holds_slot)
            or (order.status == "PAID" and not order.file and not order.printed_at)
        )
        too_old = time.time() - os.path.getmtime(os.path.join(STAGING_DIR, name)) > 24 * 3600
        if not needed or too_old:
            discard_staged(int(stem))
            
@shared_task
def cleanup_expired_order_files():
    """
    Deletes uploaded files for orders that expired or were cancelled
    without ever being printed — these files serve no further purpose
    and would otherwise sit in storage indefinitely. Never touches
    Handout files, which are shared and long-lived by design.
    """
    stale_orders = Order.objects.filter(
        status__in=["EXPIRED", "CANCELLED", "REFUND_DUE", "REFUNDED"],
        handout__isnull=True,
    ).exclude(file="")
    count = 0
    for order in stale_orders:
        if order.file:
            order.file.delete(save=False)
            order.save(update_fields=["file"])
            count += 1
    if count:
        logger.info("Cleaned up %d expired/cancelled order files", count)