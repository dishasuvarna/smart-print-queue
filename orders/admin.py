from django.contrib import admin
from django.utils import timezone
from .models import Order, Handout

PROFESSOR_FIELDS = ["title", "course_name", "lecturer_name", "semester", "contact_number", "file"]


def is_shopkeeper(user):
    return user.is_superuser or user.username == "dishag"


@admin.register(Handout)
class HandoutAdmin(admin.ModelAdmin):
    list_display = ("title", "course_name", "semester", "price_per_copy", "is_active", "created_at")
    list_filter = ("is_active", "course_name")
    search_fields = ("title", "course_name", "lecturer_name", "semester", "contact_number")

    def get_fields(self, request, obj=None):
        fields = list(PROFESSOR_FIELDS) + ["price_per_copy"]
        if is_shopkeeper(request.user):
            fields.append("is_active")
        return fields

    def get_readonly_fields(self, request, obj=None):
        readonly = ["price_per_copy"]
        if is_shopkeeper(request.user):
            readonly += PROFESSOR_FIELDS
        elif obj and obj.is_active:
            readonly += PROFESSOR_FIELDS
        return readonly


@admin.action(description="Mark selected orders as printed")
def mark_as_printed(modeladmin, request, queryset):
    queryset.update(printed_at=timezone.now())


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "printed_at", "created_at")
    actions = [mark_as_printed]