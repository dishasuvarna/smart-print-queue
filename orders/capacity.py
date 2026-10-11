from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import Order, PricingSettings

PENDING_HOLD_MINUTES = 15                 # keep equal to the window in expire_stale_orders
STORAGE_BUDGET_BYTES = 800 * 1024 * 1024  # leaves ~200 MB of the 1 GB for handouts


class OrdersClosed(Exception):
    pass


def _active_orders():
    held_since = timezone.now() - timedelta(minutes=PENDING_HOLD_MINUTES)
    return Order.objects.filter(Q(status="PAID") | Q(status="PENDING", created_at__gte=held_since))


def orders_today():
    start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    return _active_orders().filter(created_at__gte=start).count()


def storage_in_use():
    total = (
        _active_orders()
        .filter(handout__isnull=True, printed_at__isnull=True)
        .aggregate(t=Sum("file_size"))["t"]
    )
    return total or 0


def orders_open():
    limit = PricingSettings.get_rates().max_orders_per_day
    return orders_today() < limit and storage_in_use() < STORAGE_BUDGET_BYTES


def reserve_order(upload_size=0, **fields):
    """Check the limits and create a PENDING order in one locked step."""
    with transaction.atomic():
        rates, _ = PricingSettings.objects.select_for_update().get_or_create(pk=1)
        if orders_today() >= rates.max_orders_per_day:
            raise OrdersClosed("daily limit")
        if storage_in_use() + upload_size > STORAGE_BUDGET_BYTES:
            raise OrdersClosed("storage")
        return Order.objects.create(status="PENDING", file_size=upload_size, **fields)