from datetime import datetime, time

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Order, PricingSettings

STORAGE_BUDGET_BYTES = 800 * 1024 * 1024  # leaves ~200 MB of the 1 GB for handouts


class OrdersClosed(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason  # "limit", "holding" or "storage"


def lock_capacity():
    """The one lock every capacity decision takes: the pricing settings row."""
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
    total = (
        Order.objects.filter(handout__isnull=True, printed_at__isnull=True)
        .filter(Q(status="PAID") | Q(status="PENDING", holds_slot=True))
        .aggregate(t=Sum("file_size"))["t"]
    )
    return total or 0


def closed_reason():
    """None if students can order, otherwise "limit", "holding" or "storage"."""
    limit = PricingSettings.get_rates().max_orders_per_day
    paid = paid_today()
    if paid >= limit:
        return "limit"
    if paid + active_holds() >= limit:
        return "holding"
    if storage_in_use() >= STORAGE_BUDGET_BYTES:
        return "storage"
    return None


def reserve_order(upload_size=0, **fields):
    """Check the limits and create the order, holding one slot, in one locked step."""
    with transaction.atomic():
        rates = lock_capacity()
        paid = paid_today()
        if paid >= rates.max_orders_per_day:
            raise OrdersClosed("limit")
        if paid + active_holds() >= rates.max_orders_per_day:
            raise OrdersClosed("holding")
        if storage_in_use() + upload_size > STORAGE_BUDGET_BYTES:
            raise OrdersClosed("storage")
        return Order.objects.create(
            status="PENDING", holds_slot=True, file_size=upload_size, **fields
        )


def release_hold(order_id):
    """Free a checkout's slot. Returns False if it no longer held one."""
    with transaction.atomic():
        lock_capacity()
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status == "PENDING" and order.holds_slot:
            order.status = "CANCELLED"
            order.holds_slot = False
            order.save(update_fields=["status", "holds_slot"])
            return True
        return False


def orders_open():
    """Return whether new orders can currently be accepted."""
    return closed_reason() is None
