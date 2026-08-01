from django.shortcuts import render, redirect
from django.http import HttpResponse

from .models import Order
from .validators import validate_pdf_upload, UploadValidationError
from .tasks import process_pdf

PRICE_PER_PAGE = 2  # ₹2 per page, adjust as needed


def upload_order(request):
    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        student_email = request.POST.get("student_email")
        copies = int(request.POST.get("copies", 1))

        try:
            page_count = validate_pdf_upload(uploaded_file)
        except UploadValidationError as e:
            return render(request, "orders/upload.html", {"error": str(e)})

        total_price = PRICE_PER_PAGE * page_count * copies

        order = Order.objects.create(
            student_email=student_email,
            file=uploaded_file,
            page_count=page_count,
            copies=copies,
            total_price=total_price,
            status="PENDING",
        )

        process_pdf.delay(order.id)

        return render(request, "orders/success.html", {"order": order})

    return render(request, "orders/upload.html")