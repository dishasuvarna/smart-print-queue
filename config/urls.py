from django.contrib import admin
from django.urls import path

from orders.views import pending_handout_count
from orders.views import mark_batch_printed

from orders.views import print_order, print_batch

from orders.views import (
    upload_order, order_placed, browse_handouts, order_handout,
    vendor_dashboard, mark_printed,
)
from orders.webhooks import razorpay_webhook

from orders.views import health_check

from orders.views import home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("upload/", upload_order, name="upload_order"),
    path("order/<int:order_id>/placed/", order_placed, name="order_placed"),
    path("webhook/razorpay/", razorpay_webhook, name="razorpay_webhook"),
    path("handouts/", browse_handouts, name="browse_handouts"),
    path("handouts/<int:handout_id>/order/", order_handout, name="order_handout"),
    path("vendor/", vendor_dashboard, name="vendor_dashboard"),
    path("vendor/order/<int:order_id>/mark-printed/", mark_printed, name="mark_printed"),
    path("vendor/print-batch/", print_batch, name="print_batch"),
    path("vendor/mark-batch-printed/", mark_batch_printed, name="mark_batch_printed"),
    path("vendor/order/<int:order_id>/print/", print_order, name="print_order"),
    path("vendor/pending-count/", pending_handout_count, name="pending_handout_count"),
    path("health/", health_check, name="health_check"),
]

from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)