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
    if order.status == "PAID" and order.pickup_pin:
        logger.info("Duplicate webhook for order %s — already PAID, ignoring", order.id)
        return HttpResponse(status=200)

    import random
    order.status = "PAID"
    order.pickup_pin = str(random.randint(100000, 999999))
    order.save(update_fields=["status", "pickup_pin"])
    logger.info("Order %s marked PAID via webhook, PIN %s", order.id, order.pickup_pin)
    # send_shopkeeper_notification.delay(order.id)
    return HttpResponse(status=200)




# import json
# import logging
# import secrets

# import razorpay
# from django.conf import settings
# from django.db import transaction
# from django.http import HttpResponse, HttpResponseBadRequest
# from django.views.decorators.csrf import csrf_exempt
# from django.views.decorators.http import require_POST

# from .models import Order

# logger = logging.getLogger("orders.payments")


# @csrf_exempt
# @require_POST
# def razorpay_webhook(request):
#     signature = request.headers.get("X-Razorpay-Signature", "")

#     client = razorpay.Client(
#         auth=(
#             settings.RAZORPAY_KEY_ID,
#             settings.RAZORPAY_KEY_SECRET,
#         )
#     )

#     # Verify the signature before trusting the payload.
#     try:
#         client.utility.verify_webhook_signature(
#             request.body.decode("utf-8"),
#             signature,
#             settings.RAZORPAY_WEBHOOK_SECRET,
#         )
#     except razorpay.errors.SignatureVerificationError:
#         logger.warning("Rejected webhook: invalid signature")
#         return HttpResponseBadRequest("Invalid signature")

#     try:
#         payload = json.loads(request.body)
#     except (json.JSONDecodeError, UnicodeDecodeError):
#         return HttpResponseBadRequest("Invalid JSON")

#     event = payload.get("event")
#     event_payload = payload.get("payload", {})

#     # Only these events confirm successful payment.
#     if event not in {"payment.captured", "order.paid"}:
#         logger.info("Ignoring non-success payment event: %s", event)
#         return HttpResponse(status=200)

#     # Extract the Razorpay order ID for the event type.
#     razorpay_order_id = None

#     if event == "payment.captured":
#         payment = event_payload.get(
#             "payment", {}
#         ).get("entity", {})

#         if payment.get("status") != "captured":
#             logger.warning("Captured event without captured status")
#             return HttpResponse(status=200)

#         razorpay_order_id = payment.get("order_id")

#     elif event == "order.paid":
#         order_entity = event_payload.get(
#             "order", {}
#         ).get("entity", {})

#         razorpay_order_id = order_entity.get("id")

#     if not razorpay_order_id:
#         logger.error(
#             "Successful payment event missing order ID: %s",
#             event,
#         )
#         return HttpResponseBadRequest("Missing order ID")

#     # Lock the row so duplicate or simultaneous webhooks cannot
#     # overwrite the PIN or process the order inconsistently.
#     with transaction.atomic():
#         order = (
#             Order.objects.select_for_update()
#             .filter(razorpay_order_id=razorpay_order_id)
#             .first()
#         )

#         if order is None:
#             logger.error(
#                 "Webhook references unknown Razorpay order: %s",
#                 razorpay_order_id,
#             )
#             return HttpResponse(status=200)

#         update_fields = []

#         if order.status != "PAID":
#             order.status = "PAID"
#             update_fields.append("status")

#         # Repair existing paid orders that have no pickup PIN.
#         if not order.pickup_pin:
#             order.pickup_pin = str(
#                 secrets.randbelow(900000) + 100000
#             )
#             update_fields.append("pickup_pin")

#         if update_fields:
#             order.save(update_fields=update_fields)
#             logger.info(
#                 "Payment processed for local order %s; PIN present=%s",
#                 order.id,
#                 bool(order.pickup_pin),
#             )

#     return HttpResponse(status=200)