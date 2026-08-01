from django.db import models

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
    file = models.FileField(upload_to="print_jobs/")
    page_count = models.PositiveIntegerField(null=True, blank=True)
    copies = models.PositiveIntegerField(default=1)
    is_color = models.BooleanField(default=False)
    is_double_sided = models.BooleanField(default=True)
    total_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    pickup_pin = models.CharField(max_length=6, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    processing_status = models.CharField(max_length=20, choices=PROCESSING_CHOICES, default="QUEUED")

    def __str__(self):
        return f"Order #{self.id} — {self.status}"