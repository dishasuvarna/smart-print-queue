from django.contrib import admin
from django.urls import path
from orders.views import upload_order

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", upload_order, name="upload_order"),
]