from django.contrib import admin
from django.utils import timezone
from django.utils.safestring import mark_safe

from .models import Handout, Order, PricingSettings
from .permissions import is_shopkeeper

PROFESSOR_FIELDS = ["title", "course_name", "lecturer_name", "semester", "contact_number", "file"]


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

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["title"] = mark_safe(
            'Select handout to change &nbsp; <a href="/vendor/" style="font-size:14px;">← Back to Vendor Dashboard</a>'
        )
        return super().changelist_view(request, extra_context=extra_context)


@admin.action(description="Mark selected orders as printed")
def mark_as_printed(modeladmin, request, queryset):
    from notifications.tasks import send_student_ready_notification
    for order in queryset.filter(status="PAID", printed_at__isnull=True):
        order.printed_at = timezone.now()
        if order.file and not order.handout:
            order.file.delete(save=False)
        order.save(update_fields=["printed_at", "file"])
        send_student_ready_notification.delay(order.id)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "printed_at", "created_at")
    actions = [mark_as_printed]


@admin.register(PricingSettings)
class PricingSettingsAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return is_shopkeeper(request.user)

    def has_view_permission(self, request, obj=None):
        return is_shopkeeper(request.user)

    def has_change_permission(self, request, obj=None):
        return is_shopkeeper(request.user)

    def has_add_permission(self, request):
        return is_shopkeeper(request.user) and not PricingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False