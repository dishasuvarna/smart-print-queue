from django.contrib import admin
from django.utils import timezone
from .models import Order, Handout, PricingSettings

PROFESSOR_FIELDS = ["title", "course_name", "lecturer_name", "semester", "contact_number", "file"]


def is_shopkeeper(user):
    return user.is_superuser or user.username == "dishag"

from django.utils.html import format_html

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

    change_form_template = None  # keep default template

    def render_change_form(self, request, context, *args, **kwargs):
        context["title"] = format_html(
            '{} &nbsp; <a href="/vendor/" style="font-size:14px;">← Back to Vendor Dashboard</a>',
            context["title"],
        )
        return super().render_change_form(request, context, *args, **kwargs)


@admin.action(description="Mark selected orders as printed")
def mark_as_printed(modeladmin, request, queryset):
    queryset.update(printed_at=timezone.now())


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
        # Allow adding only if no row exists yet — enforces the singleton
        # without permanently hiding the Add button.
        return is_shopkeeper(request.user) and not PricingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False