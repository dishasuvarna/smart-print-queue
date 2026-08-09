from django.contrib import admin
from .models import Order, Handout

from django.utils import timezone

admin.site.register(Order)

SHOPKEEPER_ONLY_FIELDS = ["price_per_copy", "is_active"]


# @admin.register(Handout)
# class HandoutAdmin(admin.ModelAdmin):
#     list_display = ("title", "course_name", "lecturer_name", "price_per_copy", "is_active", "created_at")
#     list_filter = ("is_active", "course_name")
#     search_fields = ("title", "course_name", "lecturer_name")

#     def get_fields(self, request, obj=None):
#         fields = ["title", "course_name", "lecturer_name", "file", "page_count", "price_per_copy", "is_active"]
#         if not request.user.is_superuser:
#             fields = [f for f in fields if f not in SHOPKEEPER_ONLY_FIELDS]
#         return fields

#     def get_readonly_fields(self, request, obj=None):
#         if not request.user.is_superuser:
#             return SHOPKEEPER_ONLY_FIELDS
#         return []


PROFESSOR_FIELDS = ["title", "course_name", "lecturer_name", "semester", "contact_number", "file", "page_count"]


@admin.register(Handout)
class HandoutAdmin(admin.ModelAdmin):
    list_display = ("title", "course_name", "semester", "price_per_copy", "is_active", "created_at")
    list_filter = ("is_active", "course_name")
    search_fields = ("title", "course_name", "lecturer_name", "semester", "contact_number")

    def get_fields(self, request, obj=None):
        fields = list(PROFESSOR_FIELDS) + ["price_per_copy"]
        if request.user.is_superuser:
            fields.append("is_active")
        return fields

    def get_readonly_fields(self, request, obj=None):
        readonly = ["price_per_copy"]  # always auto-calculated, no one types it in
        if request.user.is_superuser:
            # Shopkeeper: can view everything, can only toggle is_active — cannot edit content.
            readonly += PROFESSOR_FIELDS
        elif obj and obj.is_active:
            # Professor: locked out once shopkeeper has verified and activated it.
            readonly += PROFESSOR_FIELDS
        return readonly

@admin.action(description="Mark selected orders as printed")
def mark_as_printed(modeladmin, request, queryset):
    queryset.update(printed_at=timezone.now())

class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "printed_at", "created_at")
    actions = [mark_as_printed]

admin.site.unregister(Order)
admin.site.register(Order, OrderAdmin)