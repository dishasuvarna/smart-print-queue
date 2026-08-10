"""
Email notifications via Brevo's transactional API — queued through Celery
so sending behaves identically, and doesn't block the request-response
cycle, whether Brevo answers in 50ms or 5s, locally or in production
(points 6, 9).
"""

import base64
import logging

import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger("notifications.email")

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"

EMAIL_FOOTER = (
    '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 12px;">'
    '<p style="font-size:12px;color:#9ca3af;margin:0;">'
    'Smart Print Queue &middot; Canara Engineering College, Sudhindra Nagar, '
    'Bantwal Taluk, Mangaluru, DK District, Karnataka, India &middot; 574219'
    '</p>'
)


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
    f"<p>A new handout was submitted and is awaiting verification:</p>"
    f"<p><b>{handout.title}</b><br>"
    f"{handout.course_name}{' · ' + handout.lecturer_name if handout.lecturer_name else ''}<br>"
    f"Semester {handout.semester} · Pages: {handout.page_count} · Price: ₹{handout.price_per_copy}/copy</p>"
    f"<p>Contact: {handout.contact_number}</p>"
    f"<p>Please review the file and mark it Active if correct. "
    f"Contact the professor above if anything needs clarification.</p>"
    f"{EMAIL_FOOTER}"
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


@shared_task(
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=5,
)
def send_student_ready_notification(self, order_id):
    from orders.models import Order

    order = Order.objects.get(id=order_id)
    payload = {
        "sender": {"email": settings.DEFAULT_FROM_EMAIL, "name": "Smart Print Queue"},
        "to": [{"email": order.student_email}],
        "subject": f"Your printout is ready — Order #{order.id}",
        "htmlContent": (
            f"<p>Your order is printed and ready for pickup.</p>"
            f"<p>Pickup PIN: <b>{order.pickup_pin}</b></p>"
            f"{EMAIL_FOOTER}"
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
        response.raise_for_status()
    logger.info("Ready notification sent for order %s", order_id)