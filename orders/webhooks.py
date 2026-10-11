"""Razorpay webhook: signature-verified, idempotent, capacity-aware."""

import json
import logging

import razorpay
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Order
from .payments import process_captured_payment

logger = logging.getLogger("orders.payments")


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    signature = request.headers.get("X-Razorpay-Signature", "")
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    try:
        client.utility.verify_webhook_signature(
            request.body.decode("utf-8"), signature, settings.RAZORPAY_WEBHOOK_SECRET
        )
    except razorpay.errors.SignatureVerificationError:
        logger.warning("Rejected webhook: invalid signature")
        return HttpResponseBadRequest("Invalid signature")

    try:
        payload = json.loads(request.body)
        if payload.get("event") != "payment.captured":
            return HttpResponse(status=200)
        payment = payload["payload"]["payment"]["entity"]
        razorpay_order_id, payment_id, amount = payment["order_id"], payment["id"], payment["amount"]
    except (ValueError, KeyError, TypeError):
        logger.error("Malformed webhook payload")
        return HttpResponse(status=200)  # a signed bad payload won't fix itself on retry

    order = Order.objects.filter(razorpay_order_id=razorpay_order_id).first()
    if order is None:
        logger.error("Webhook for unknown order_id %s", razorpay_order_id)
        return HttpResponse(status=200)

    if amount != int(order.total_price * 100):
        logger.error("Amount mismatch for order %s: paid %s, expected %s",
                     order.id, amount, int(order.total_price * 100))
        return HttpResponse(status=200)

    try:
        outcome = process_captured_payment(order.id, payment_id)
    except Exception:
        logger.exception("Could not settle payment %s for order %s", payment_id, order.id)
        return HttpResponse(status=500)  # Razorpay retries

    logger.info("Order %s: webhook payment %s -> %s", order.id, payment_id, outcome)
    return HttpResponse(status=200)