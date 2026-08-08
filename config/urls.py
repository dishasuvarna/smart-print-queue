from django.contrib import admin
from django.urls import path
from orders.views import (
    upload_order, order_placed, browse_handouts, order_handout,
    vendor_dashboard, mark_printed,
)
from orders.webhooks import razorpay_webhook

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", upload_order, name="upload_order"),
    path("order/<int:order_id>/placed/", order_placed, name="order_placed"),
    path("webhook/razorpay/", razorpay_webhook, name="razorpay_webhook"),
    path("handouts/", browse_handouts, name="browse_handouts"),
    path("handouts/<int:handout_id>/order/", order_handout, name="order_handout"),
    path("vendor/", vendor_dashboard, name="vendor_dashboard"),
    path("vendor/order/<int:order_id>/mark-printed/", mark_printed, name="mark_printed"),
]