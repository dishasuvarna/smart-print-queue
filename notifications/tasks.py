"""
Email notifications via Brevo's transactional API — queued through Celery
so sending behaves identically, and doesn't block the request-response
cycle, whether Brevo answers in 50ms or 5s, locally or in production
(points 6, 9).
"""

import logging

import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger("notifications.email")

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


@shared_task(
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=5,
)
def send_shopkeeper_notification(self, order_id):
    from orders.models import Order

    order = Order.objects.get(id=order_id)
    payload = {
        "sender": {"email": settings.DEFAULT_FROM_EMAIL, "name": "Smart Print Queue"},
        "to": [{"email": settings.SHOPKEEPER_EMAIL}],
        "subject": f"New order #{order.id} — pickup PIN {order.pickup_pin}",
        "htmlContent": (
            f"<p>New paid order #{order.id}.</p>"
            f"<p>Pages: {order.page_count} | Copies: {order.copies}</p>"
            f"<p>Pickup PIN: <b>{order.pickup_pin}</b></p>"
        ),
    }
    response = requests.post(
        BREVO_SEND_URL,
        json=payload,
        headers={"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"},
        timeout=10,
    )
    if response.status_code >= 400:
        logger.error(
            "Brevo send failed for order %s: %s %s", order_id, response.status_code, response.text
        )
        response.raise_for_status()  # triggers autoretry above
    logger.info("Notification email sent for order %s", order_id)


@shared_task(
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=5,
)
def send_student_confirmation(self, order_id):
    """Same pattern as above — confirmation email to the student who placed the order."""
    from orders.models import Order

    order = Order.objects.get(id=order_id)
    payload = {
        "sender": {"email": settings.DEFAULT_FROM_EMAIL, "name": "Smart Print Queue"},
        "to": [{"email": order.student_email}],
        "subject": f"Order #{order.id} confirmed",
        "htmlContent": f"<p>Your print job is confirmed. Pickup PIN: <b>{order.pickup_pin}</b></p>",
    }
    response = requests.post(
        BREVO_SEND_URL,
        json=payload,
        headers={"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"},
        timeout=10,
    )
    if response.status_code >= 400:
        logger.error(
            "Brevo send failed for order %s: %s %s", order_id, response.status_code, response.text
        )
        response.raise_for_status()
    logger.info("Confirmation email sent for order %s", order_id)


@shared_task(
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=5,
)
def send_new_handout_alert(self, handout_id):
    from orders.models import Handout

    handout = Handout.objects.get(id=handout_id)
    payload = {
        "sender": {"email": settings.DEFAULT_FROM_EMAIL, "name": "Smart Print Queue"},
        "to": [{"email": settings.SHOPKEEPER_EMAIL}],
        "subject": f"New handout awaiting price: {handout.title}",
        "htmlContent": (
            f"<p>A new handout was submitted and needs a price before it goes live:</p>"
            f"<p><b>{handout.title}</b><br>"
            f"{handout.course_name}{' · ' + handout.lecturer_name if handout.lecturer_name else ''}</p>"
            f"<p>Go to the admin panel to set a price and activate it.</p>"
        ),
    }
    response = requests.post(
        BREVO_SEND_URL,
        json=payload,
        headers={"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json"},
        timeout=10,
    )
    if response.status_code >= 400:
        logger.error(
            "Brevo send failed for handout %s: %s %s", handout_id, response.status_code, response.text
        )
        response.raise_for_status()
    logger.info("New handout alert sent for handout %s", handout_id)
