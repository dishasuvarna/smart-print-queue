from django.db import models
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
    PRICE_PER_PAGE = 2  # shop's per-page rate for handouts

    title = models.CharField(max_length=200)
    course_name = models.CharField(max_length=150, blank=True)
    lecturer_name = models.CharField(max_length=150, blank=True)
    semester = models.CharField(max_length=50)
    contact_number = models.CharField(max_length=15)
    file = models.FileField(upload_to="handouts/", help_text="PDF only, max 50MB.")
    page_count = models.PositiveIntegerField(null=True, blank=True, editable=False)
    price_per_copy = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Price is always derived from page count — never manually entered by anyone.
        if self.page_count:
            self.price_per_copy = self.page_count * self.PRICE_PER_PAGE
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
        if self.file:
            if self.file.size > 50 * 1024 * 1024:
                raise ValidationError("Handout file exceeds 50MB limit.")
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
    ]
    PROCESSING_CHOICES = [
        ("QUEUED", "Queued"),
        ("PROCESSED", "Processed"),
        ("FAILED", "Failed"),
    ]

    student_email = models.EmailField()
    file = models.FileField(upload_to="print_jobs/", null=True, blank=True)
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
    print_token = models.CharField(max_length=32, blank=True)

    def __str__(self):
        return f"Order #{self.id} — {self.status}"

class PricingSettings(models.Model):
    bw_rate_per_page = models.DecimalField(max_digits=6, decimal_places=2, default=5)
    color_rate_per_page = models.DecimalField(max_digits=6, decimal_places=2, default=10)

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton — only one row ever exists
        super().save(*args, **kwargs)

    @classmethod
    def get_rates(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Pricing Settings"