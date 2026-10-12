import inspect
import logging

import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .capacity import active_holds, lock_capacity, paid_today, release_hold
from .models import Order
from .staging import is_staged

logger = logging.getLogger("orders.payments")


def _client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def settle_payment(order_id, payment_id):
    """Record a payment Razorpay confirmed as captured, under the capacity lock.
    Returns "confirmed", "duplicate" or "refund"."""
    with transaction.atomic():
        rates = lock_capacity()
        order = Order.objects.select_for_update().get(pk=order_id)
        same_payment = order.razorpay_payment_id == payment_id

        if order.status in ("PAID", "REFUNDED"):
            return "duplicate" if same_payment else "refund"
        if order.status == "REFUND_DUE":
            return "refund"

        # A student upload can only be printed if its file still exists.
        has_file = bool(order.handout_id or order.file or is_staged(order.id))
        if order.holds_slot:
            outcome = "confirmed" if has_file else "refund"
        else:
            room = paid_today() + active_holds() < rates.max_orders_per_day
            outcome = "confirmed" if (room and has_file) else "refund"

        order.razorpay_payment_id = payment_id
        order.holds_slot = False
        if outcome == "confirmed":
            order.status = "PAID"
            order.paid_at = timezone.now()
            if not order.pickup_pin:
                order.pickup_pin = Order._new_pin()
        else:
            order.status = "REFUND_DUE"
        order.save(update_fields=[
            "status", "holds_slot", "razorpay_payment_id", "paid_at", "pickup_pin",
        ])
        return outcome


def _refund_call(client, payment_id, amount_paise):
    # razorpay-python has changed this method's signature between versions; support both.
    if "amount" in inspect.signature(client.payment.refund).parameters:
        return client.payment.refund(payment_id, amount_paise)
    return client.payment.refund(payment_id, {"amount": amount_paise})


def issue_refund(payment_id):
    """Refund whatever is still unrefunded on a captured payment. Safe to call repeatedly."""
    client = _client()
    payment = client.payment.fetch(payment_id)
    paid = payment.get("amount", 0)
    already = payment.get("amount_refunded", 0)
    if payment.get("refund_status") == "full" or (paid > 0 and already >= paid):
        logger.info("Payment %s is already fully refunded", payment_id)
        return
    refund = _refund_call(client, payment_id, paid - already)
    if not str(refund.get("id", "")).startswith("rfnd_"):
        raise RuntimeError(f"Unexpected refund response for payment {payment_id}: {refund}")


def refund_payment(order_id, payment_id):
    issue_refund(payment_id)
    Order.objects.filter(
        pk=order_id, status="REFUND_DUE", razorpay_payment_id=payment_id
    ).update(status="REFUNDED")
    logger.warning("Refunded payment %s for order %s", payment_id, order_id)


def refund_lost_upload(order_id):
    """A paid student upload whose file exists nowhere can't be printed: refund it."""
    with transaction.atomic():
        lock_capacity()
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status != "PAID" or order.handout_id or order.file or order.printed_at:
            return
        order.status = "REFUND_DUE"
        order.pickup_pin = ""
        order.save(update_fields=["status", "pickup_pin"])
        payment_id = order.razorpay_payment_id
    if payment_id:
        refund_payment(order_id, payment_id)


def queue_promotion(order_id):
    from .tasks import promote_upload_task
    if not Order.objects.filter(pk=order_id, handout__isnull=True).exists():
        return  # handout orders have no file to move
    try:
        promote_upload_task.delay(order_id)
    except Exception:
        logger.warning("Could not queue upload for order %s; the recovery job will retry", order_id)


def process_captured_payment(order_id, payment_id):
    outcome = settle_payment(order_id, payment_id)
    if outcome == "refund":
        refund_payment(order_id, payment_id)
    elif outcome == "confirmed":
        queue_promotion(order_id)
    return outcome


def razorpay_state(order):
    items = _client().order.payments(order.razorpay_order_id).get("items", [])
    for payment in items:
        if payment["status"] == "captured":
            return "captured", payment["id"]
    if any(p["status"] in ("created", "authorized") for p in items):
        return "in_flight", None
    return "idle", None


def recover_checkout(order_id):
    """Resolve one stuck checkout: "paid", "waiting", "released" or "settled"."""
    order = Order.objects.get(pk=order_id)
    if order.status != "PENDING" or not order.holds_slot:
        return "settled"
    if not order.razorpay_order_id:
        return "released" if release_hold(order_id) else "settled"
    state, payment_id = razorpay_state(order)
    if state == "captured":
        process_captured_payment(order_id, payment_id)
        return "paid"
    if state == "in_flight":
        return "waiting"
    return "released" if release_hold(order_id) else "settled"


def retry_refund(order_id):
    order = Order.objects.get(pk=order_id)
    if order.status == "REFUND_DUE" and order.razorpay_payment_id:
        refund_payment(order_id, order.razorpay_payment_id)