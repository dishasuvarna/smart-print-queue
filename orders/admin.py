from django.contrib import admin
from .models import Order, Handout

from django.utils import timezone

admin.site.register(Order)

SHOPKEEPER_ONLY_FIELDS = ["price_per_copy", "is_active"]


@admin.register(Handout)
class HandoutAdmin(admin.ModelAdmin):
    list_display = ("title", "course_name", "lecturer_name", "price_per_copy", "is_active", "created_at")
    list_filter = ("is_active", "course_name")
    search_fields = ("title", "course_name", "lecturer_name")

    def get_fields(self, request, obj=None):
        fields = ["title", "course_name", "lecturer_name", "file", "page_count", "price_per_copy", "is_active"]
        if not request.user.is_superuser:
            fields = [f for f in fields if f not in SHOPKEEPER_ONLY_FIELDS]
        return fields

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:
            return SHOPKEEPER_ONLY_FIELDS
        return []


@admin.action(description="Mark selected orders as printed")
def mark_as_printed(modeladmin, request, queryset):
    queryset.update(printed_at=timezone.now())

class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "printed_at", "created_at")
    actions = [mark_as_printed]

admin.site.unregister(Order)
admin.site.register(Order, OrderAdmin)