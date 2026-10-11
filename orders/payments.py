import logging

import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .capacity import active_holds, lock_capacity, paid_today, release_hold
from .models import Order

logger = logging.getLogger("orders.payments")


def _client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def settle_payment(order_id, payment_id):
    """
    Record a payment Razorpay confirmed as captured, under the capacity lock.
    Returns "confirmed", "duplicate" or "refund".
    """
    with transaction.atomic():
        rates = lock_capacity()
        order = Order.objects.select_for_update().get(pk=order_id)
        same_payment = order.razorpay_payment_id == payment_id

        if order.status in ("PAID", "REFUNDED"):
            return "duplicate" if same_payment else "refund"
        if order.status == "REFUND_DUE":
            return "refund"

        if order.holds_slot:
            outcome = "confirmed"  # a slot was reserved for exactly this checkout
        else:
            # Late payment: its slot was released. Accept only if there is room
            # and, for a student upload, the file still exists.
            has_file = bool(order.handout_id or order.file)
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


def issue_refund(order, payment_id):
    try:
        _client().payment.refund(payment_id, int(order.total_price * 100))
    except razorpay.errors.BadRequestError as exc:
        message = str(exc).lower()
        if "already" in message and "refund" in message:
            logger.info("Payment %s was already refunded", payment_id)
            return
        raise


def refund_payment(order_id, payment_id):
    order = Order.objects.get(pk=order_id)
    issue_refund(order, payment_id)
    if order.razorpay_payment_id == payment_id:
        Order.objects.filter(pk=order_id, status="REFUND_DUE").update(status="REFUNDED")
    logger.warning("Refunded payment %s for order %s", payment_id, order_id)


def process_captured_payment(order_id, payment_id):
    outcome = settle_payment(order_id, payment_id)
    if outcome == "refund":
        refund_payment(order_id, payment_id)
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