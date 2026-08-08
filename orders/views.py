from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db.models import Q

import razorpay
from django.conf import settings

from .models import Order, Handout
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

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        razorpay_order = client.order.create({
            "amount": int(total_price * 100),
            "currency": "INR",
            "receipt": f"order_{order.id}",
        })
        order.razorpay_order_id = razorpay_order["id"]
        order.save(update_fields=["razorpay_order_id"])

        process_pdf.delay(order.id)

        return render(request, "orders/payment.html", {
            "order": order,
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "razorpay_order_id": razorpay_order["id"],
            "amount": int(total_price * 100),
        })

    return render(request, "orders/upload.html")


def order_placed(request, order_id):
    order = Order.objects.get(id=order_id)
    return render(request, "orders/success.html", {"order": order})


def browse_handouts(request):
    query = request.GET.get("q", "").strip()
    handouts = Handout.objects.filter(is_active=True)

    if query:
        handouts = handouts.filter(
            Q(title__icontains=query) |
            Q(course_name__icontains=query) |
            Q(lecturer_name__icontains=query)
        )

    return render(request, "orders/browse_handouts.html", {
        "handouts": handouts,
        "query": query,
    })


def order_handout(request, handout_id):
    handout = Handout.objects.get(id=handout_id, is_active=True)

    if request.method == "POST":
        student_email = request.POST.get("student_email")
        copies = int(request.POST.get("copies", 1))
        total_price = handout.price_per_copy * copies

        order = Order.objects.create(
            student_email=student_email,
            handout=handout,
            page_count=handout.page_count,
            copies=copies,
            total_price=total_price,
            status="PENDING",
        )

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        razorpay_order = client.order.create({
            "amount": int(total_price * 100),
            "currency": "INR",
            "receipt": f"order_{order.id}",
        })
        order.razorpay_order_id = razorpay_order["id"]
        order.save(update_fields=["razorpay_order_id"])

        return render(request, "orders/payment.html", {
            "order": order,
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "razorpay_order_id": razorpay_order["id"],
            "amount": int(total_price * 100),
        })

    return render(request, "orders/order_handout.html", {"handout": handout})


@login_required
@user_passes_test(lambda u: u.is_staff)
def vendor_dashboard(request):
    pending_orders = Order.objects.filter(status="PAID", printed_at__isnull=True).order_by("created_at")
    return render(request, "orders/vendor.html", {"orders": pending_orders})


@login_required
@user_passes_test(lambda u: u.is_staff)
def mark_printed(request, order_id):
    order = Order.objects.get(id=order_id)
    if not order.printed_at:
        order.printed_at = timezone.now()
        order.save(update_fields=["printed_at"])
        from notifications.tasks import send_student_ready_notification
        send_student_ready_notification.delay(order.id)
    return redirect("vendor_dashboard")