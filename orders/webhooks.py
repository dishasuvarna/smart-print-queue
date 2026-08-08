"""
Razorpay webhook handler — signature-verified and idempotent (points 7, 8).
"""

import json
import logging

import razorpay
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# from notifications.tasks import send_shopkeeper_notification
from .models import Order

logger = logging.getLogger("orders.payments")


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    signature = request.headers.get("X-Razorpay-Signature", "")
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    # Point 7 — verify before trusting anything in the payload. A request
    # without a valid signature could be anyone claiming an order was paid.
    try:
        client.utility.verify_webhook_signature(
            request.body.decode("utf-8"),
            signature,
            settings.RAZORPAY_WEBHOOK_SECRET,
        )
    except razorpay.errors.SignatureVerificationError:
        logger.warning("Rejected webhook: invalid signature")
        return HttpResponseBadRequest("Invalid signature")

    payload = json.loads(request.body)
    razorpay_order_id = payload["payload"]["payment"]["entity"]["order_id"]

    try:
        order = Order.objects.get(razorpay_order_id=razorpay_order_id)
    except Order.DoesNotExist:
        logger.error("Webhook for unknown order_id %s", razorpay_order_id)
        return HttpResponseBadRequest("Unknown order")

    # Point 8 — idempotency. Razorpay retries webhooks that don't get a
    # fast 2xx response. A retried webhook on an already-paid order is
    # treated as a successful no-op, not reprocessed into a duplicate
    # notification or a double-decremented queue count.
    if order.status == "PAID":
        logger.info("Duplicate webhook for order %s — already PAID, ignoring", order.id)
        return HttpResponse(status=200)

    import random
    import uuid
    order.status = "PAID"
    order.pickup_pin = str(random.randint(100000, 999999))
    order.print_token = uuid.uuid4().hex
    order.save(update_fields=["status", "pickup_pin"])
    #logger.info("Order %s marked PAID via webhook, PIN %s", order.id, order.pickup_pin)

    # send_shopkeeper_notification.delay(order.id)
    return HttpResponse(status=200)
