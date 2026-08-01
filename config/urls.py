from django.contrib import admin
from django.urls import path
from orders.views import upload_order, order_placed

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", upload_order, name="upload_order"),
    path("order/<int:order_id>/placed/", order_placed, name="order_placed"),
]