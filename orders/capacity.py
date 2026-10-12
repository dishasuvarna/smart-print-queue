from datetime import datetime, time

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Order, PricingSettings
from .staging import discard_staged

STORAGE_BUDGET_BYTES = 800 * 1024 * 1024  # eventual Supabase use; leaves ~200 MB for handouts
STAGING_BUDGET_BYTES = 300 * 1024 * 1024  # temporary local space for uploads awaiting payment


class OrdersClosed(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason  # "limit", "holding" or "storage"


def lock_capacity():
    rates, _ = PricingSettings.objects.select_for_update().get_or_create(pk=1)
    return rates


def day_start():
    return timezone.make_aware(datetime.combine(timezone.localdate(), time.min))


def paid_today():
    return (
        Order.objects.filter(status="PAID")
        .annotate(confirmed_at=Coalesce("paid_at", "created_at"))
        .filter(confirmed_at__gte=day_start())
        .count()
    )


def active_holds():
    return Order.objects.filter(status="PENDING", holds_slot=True).count()


def storage_in_use():
    """Space student uploads will occupy in Supabase once their payments land."""
    total = (
        Order.objects.filter(handout__isnull=True, printed_at__isnull=True)
        .filter(Q(status="PAID") | Q(status="PENDING", holds_slot=True))
        .aggregate(t=Sum("file_size"))["t"]
    )
    return total or 0


def staged_bytes():
    """Temporary local space used by uploads still waiting for payment."""
    total = (
        Order.objects.filter(status="PENDING", holds_slot=True, handout__isnull=True)
        .aggregate(t=Sum("file_size"))["t"]
    )
    return total or 0


def closed_reason(for_upload=False):
    """None if students can order, otherwise "setup", "limit", "holding" or "storage"."""
    rates = PricingSettings.get_rates()
    if for_upload and (rates.bw_rate_per_page is None or rates.color_rate_per_page is None):
        return "setup"
    paid = paid_today()
    if paid >= rates.max_orders_per_day:
        return "limit"
    if paid + active_holds() >= rates.max_orders_per_day:
        return "holding"
    if for_upload and (
        storage_in_use() >= STORAGE_BUDGET_BYTES or staged_bytes() >= STAGING_BUDGET_BYTES
    ):
        return "storage"
    return None


def reserve_order(upload_size=0, token="", **fields):
    """Check the limits and create the order in one locked step.
    Returns (order, created). A repeated submit with the same token returns the first order."""
    with transaction.atomic():
        rates = lock_capacity()
        if token:
            existing = Order.objects.filter(submission_token=token).first()
            if existing:
                return existing, False
        paid = paid_today()
        if paid >= rates.max_orders_per_day:
            raise OrdersClosed("limit")
        if paid + active_holds() >= rates.max_orders_per_day:
            raise OrdersClosed("holding")
        if upload_size and (
            storage_in_use() + upload_size > STORAGE_BUDGET_BYTES
            or staged_bytes() + upload_size > STAGING_BUDGET_BYTES
        ):
            raise OrdersClosed("storage")
        order = Order.objects.create(
            status="PENDING", holds_slot=True, file_size=upload_size,
            submission_token=token, **fields,
        )
        return order, True


def release_hold(order_id):
    """Free a checkout's slot and delete its temporary file. False if it no longer held one."""
    released = False
    with transaction.atomic():
        lock_capacity()
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status == "PENDING" and order.holds_slot:
            order.status = "CANCELLED"
            order.holds_slot = False
            order.submission_token = ""
            order.save(update_fields=["status", "holds_slot", "submission_token"])
            released = True
    if released:
        discard_staged(order_id)
    return released

def orders_open():
    """Return whether new orders can currently be accepted."""
    return closed_reason() is None