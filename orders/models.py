from django.db import models

import secrets
import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models, transaction

def order_upload_path(instance, filename):
    return f"print_jobs/{uuid.uuid4().hex}.pdf"


def handout_upload_path(instance, filename):
    return f"handouts/{uuid.uuid4().hex}.pdf"


# from pypdf import PdfReader
# from pypdf.errors import PdfReadError


# class Handout(models.Model):
#     title = models.CharField(max_length=200)
#     course_name = models.CharField(max_length=150, blank=True)
#     lecturer_name = models.CharField(max_length=150, blank=True)
#     file = models.FileField(upload_to="handouts/")
#     page_count = models.PositiveIntegerField(null=True, blank=True)
#     price_per_copy = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
#     is_active = models.BooleanField(default=False)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def clean(self):
#         from django.core.exceptions import ValidationError
#         if self.is_active and self.price_per_copy is None:
#             raise ValidationError("Set a price before activating this handout.")

#     def __str__(self):
#         status = "Active" if self.is_active else "Awaiting price"
#         return f"{self.title} ({self.course_name}) — {status}"



class Handout(models.Model):

    title = models.CharField(max_length=200)
    course_name = models.CharField(max_length=150, blank=True)
    lecturer_name = models.CharField(max_length=150, blank=True)
    semester = models.CharField(max_length=50)
    contact_number = models.CharField(max_length=15)
    # file = models.FileField(upload_to="handouts/", help_text="PDF only, max 50MB.")
    file = models.FileField(upload_to=handout_upload_path, help_text="PDF only, max 50MB.")
    page_count = models.PositiveIntegerField(null=True, blank=True, editable=False)
    price_per_copy = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)



    def save(self, *args, **kwargs):
        old_file = None
        if self.pk:
            old = Handout.objects.filter(pk=self.pk).first()
            if old and old.file and old.file.name != self.file.name:
                old_file = old.file
        rate = PricingSettings.get_rates().handout_rate_per_page
        if self.page_count and rate is not None:
            self.price_per_copy = self.page_count * rate
        super().save(*args, **kwargs)
        if old_file:
            old_file.delete(save=False)

    def clean(self):
        from django.core.exceptions import ValidationError
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
        if self.file:
                    if self.is_active and self.price_per_copy is None:
                        raise ValidationError("Set the handout rate in Shop settings before activating handouts.")
        try:
            self.file.seek(0)
            reader = PdfReader(self.file)
            self.page_count = len(reader.pages)
            self.file.seek(0)
        except PdfReadError:
            raise ValidationError("This PDF appears to be corrupted or invalid.")

        if self.is_active and self.price_per_copy is None:
            raise ValidationError("Price could not be calculated — page count is missing.")

    def __str__(self):
        status = "Active" if self.is_active else "Awaiting verification"
        return f"{self.title} ({self.course_name}) — {status}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("EXPIRED", "Expired"),
        ("CANCELLED", "Cancelled"),
        ("REFUND_DUE", "Refund due"),
        ("REFUNDED", "Refunded"),
    ]
    PROCESSING_CHOICES = [
        ("QUEUED", "Queued"),
        ("PROCESSED", "Processed"),
        ("FAILED", "Failed"),
    ]

    student_email = models.EmailField()
    # file = models.FileField(upload_to="print_jobs/", null=True, blank=True)
    file = models.FileField(upload_to=order_upload_path, null=True, blank=True)
    handout = models.ForeignKey(
        Handout, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    page_count = models.PositiveIntegerField(null=True, blank=True)
    copies = models.PositiveIntegerField(default=1)
    is_color = models.BooleanField(default=False)
    is_double_sided = models.BooleanField(default=True)
    total_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    processing_status = models.CharField(max_length=20, choices=PROCESSING_CHOICES, default="QUEUED")
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    pickup_pin = models.CharField(max_length=6, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    printed_at = models.DateTimeField(null=True, blank=True)
    # print_token = models.CharField(max_length=32, blank=True)
    submission_token = models.CharField(max_length=32, blank=True, default="", db_default="")


    max_orders_per_day = models.PositiveIntegerField(default=100, help_text="Set to 0 to close ordering.")
    
    file_size = models.PositiveBigIntegerField(default=0)

    holds_slot = models.BooleanField(default=False, db_default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, default="", db_default="")

    @staticmethod
    def _new_pin():
        while True:
            pin = str(secrets.randbelow(900000) + 100000)
            if not Order.objects.filter(pickup_pin=pin, printed_at__isnull=True).exists():
                return pin

        file = models.FileField(upload_to=order_upload_path, null=True, blank=True)
    submission_token = models.CharField(max_length=32, blank=True, default="", db_default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission_token"],
                condition=~models.Q(submission_token=""),
                name="unique_submission_token",
            )
        ]

    # def mark_paid(self):
    #     """Safe to call from the webhook, the backup job and checkout verification."""
    #     with transaction.atomic():
    #         order = Order.objects.select_for_update().get(pk=self.pk)
    #         if order.status == "PAID" and order.pickup_pin:
    #             self.status, self.pickup_pin = order.status, order.pickup_pin
    #             return False
    #         order.status = "PAID"
    #         if not order.pickup_pin:
    #             order.pickup_pin = Order._new_pin()
    #         order.save(update_fields=["status", "pickup_pin"])
    #         self.status, self.pickup_pin = order.status, order.pickup_pin
    #         return True

    def __str__(self):
        return f"Order #{self.id} — {self.status}"

class PricingSettings(models.Model):
    # No price exists in code. These stay empty until the shopkeeper fills them in.
    bw_rate_per_page = models.DecimalField(
        max_digits=6, decimal_places=2, null=True,
        validators=[MinValueValidator(Decimal("0.01"))], verbose_name="B&W rate per page (₹)")
    color_rate_per_page = models.DecimalField(
        max_digits=6, decimal_places=2, null=True,
        validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Color rate per page (₹)")
    handout_rate_per_page = models.DecimalField(
        max_digits=6, decimal_places=2, null=True,
        validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Handout rate per page (₹)")
    max_copies_bw = models.PositiveIntegerField(
        default=10, validators=[MinValueValidator(1)],
        verbose_name="Max copies per order (black & white and handouts)")
    max_copies_color = models.PositiveIntegerField(
        default=5, validators=[MinValueValidator(1)],
        verbose_name="Max copies per order (color)")
    max_orders_per_day = models.PositiveIntegerField(
        default=100, help_text="Set to 0 to close ordering.")

    class Meta:
        verbose_name = "Shop settings"
        verbose_name_plural = "Shop settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        if self.handout_rate_per_page is not None:
            # Handouts follow the shop's rate. Placed orders keep the price they were created with.
            Handout.objects.filter(page_count__isnull=False).update(
                price_per_copy=models.ExpressionWrapper(
                    models.F("page_count") * self.handout_rate_per_page,
                    output_field=models.DecimalField(max_digits=8, decimal_places=2),
                )
            )

    @classmethod
    def get_rates(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Shop settings"