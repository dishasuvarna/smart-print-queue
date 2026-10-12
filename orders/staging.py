import logging
import os
import tempfile

from django.core.files import File
from django.db import transaction

from .models import Order

logger = logging.getLogger("orders.payments")

STAGING_DIR = os.path.join(tempfile.gettempdir(), "queuedrop_pending")


def staged_path(order_id):
    return os.path.join(STAGING_DIR, f"{int(order_id)}.pdf")


def stage_upload(order_id, uploaded_file):
    os.makedirs(STAGING_DIR, exist_ok=True)
    try:
        with open(staged_path(order_id), "wb") as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)
    except Exception:
        discard_staged(order_id)
        raise


def is_staged(order_id):
    return os.path.isfile(staged_path(order_id))


def discard_staged(order_id):
    try:
        os.remove(staged_path(order_id))
    except FileNotFoundError:
        pass


def promote_upload(order_id):
    """Move a paid student upload from temporary staging into Supabase.
    Returns "ready" (nothing left to do) or "lost" (the file exists nowhere)."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.handout_id or order.status != "PAID" or order.printed_at:
            return "ready"
        if order.file:
            discard_staged(order_id)
            return "ready"
        path = staged_path(order_id)
        if not os.path.isfile(path):
            return "lost"
        try:
            with open(path, "rb") as source:
                order.file.save("upload.pdf", File(source), save=False)
            order.processing_status = "PROCESSED"
            order.save(update_fields=["file", "processing_status"])
        except Exception:
            if order.file:
                order.file.delete(save=False)  # don't leave a half-saved copy behind
            raise
    discard_staged(order_id)
    return "ready"