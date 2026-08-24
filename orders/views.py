import io

from django.http.response import HttpResponse
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

def health_check(request):
    return HttpResponse("OK")

def upload_order(request):
    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        student_email = request.POST.get("student_email")
        copies = int(request.POST.get("copies", 1))
        is_color = request.POST.get("is_color") == "true"
        is_double_sided = request.POST.get("is_double_sided") == "true"

        try:
            page_count = validate_pdf_upload(uploaded_file)
        except UploadValidationError as e:
            return render(request, "orders/upload.html", {"error": str(e)})

        # Flat per-page rate based on color only — sides doesn't affect price.
        per_page_rate = 10 if is_color else 5
        total_price = per_page_rate * page_count * copies

        order = Order.objects.create(
            student_email=student_email,
            file=uploaded_file,
            page_count=page_count,
            copies=copies,
            is_color=is_color,
            is_double_sided=is_double_sided,
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


def is_authorized_vendor(user):
    return user.is_superuser or user.username == "dishag"


# @login_required
# @user_passes_test(is_authorized_vendor)
# def vendor_dashboard(request):
#     pending = Order.objects.filter(status="PAID", printed_at__isnull=True).order_by("created_at")

#     upload_orders = pending.filter(handout__isnull=True)

#     handout_orders = pending.filter(handout__isnull=False)
#     handout_batches = {}
#     for order in handout_orders:
#         h = order.handout
#         if h.id not in handout_batches:
#             handout_batches[h.id] = {
#                 "handout": h,
#                 "orders": [],
#                 "total_copies": 0,
#             }
#         handout_batches[h.id]["orders"].append(order)
#         handout_batches[h.id]["total_copies"] += order.copies

#     return render(request, "orders/vendor.html", {
#         "upload_orders": upload_orders,
#         "handout_batches": handout_batches.values(),
#     })

MAX_PAGES_PER_BATCH = 200

@login_required
@user_passes_test(is_authorized_vendor)
def vendor_dashboard(request):
    pending = Order.objects.filter(status="PAID", printed_at__isnull=True).order_by("created_at")

    upload_orders = pending.filter(handout__isnull=True)

    handout_orders = pending.filter(handout__isnull=False)
    handout_groups = {}
    for order in handout_orders:
        h = order.handout
        handout_groups.setdefault(h.id, {"handout": h, "orders": []})
        handout_groups[h.id]["orders"].append(order)

    handout_batches = []
    for group in handout_groups.values():
        h = group["handout"]
        current_batch = {"handout": h, "orders": [], "total_copies": 0, "total_pages": 0, "part": 1}
        for order in group["orders"]:
            order_pages = order.copies * h.page_count
            if current_batch["total_pages"] + order_pages > MAX_PAGES_PER_BATCH and current_batch["orders"]:
                handout_batches.append(current_batch)
                current_batch = {"handout": h, "orders": [], "total_copies": 0, "total_pages": 0, "part": current_batch["part"] + 1}
            current_batch["orders"].append(order)
            current_batch["total_copies"] += order.copies
            current_batch["total_pages"] += order_pages
        handout_batches.append(current_batch)

    return render(request, "orders/vendor.html", {
        "upload_orders": upload_orders,
        "handout_batches": handout_batches,
    })


@login_required
@user_passes_test(is_authorized_vendor)
def mark_printed(request, order_id):
    order = Order.objects.get(id=order_id)
    if not order.printed_at:
        order.printed_at = timezone.now()

        # Delete the actual file from storage now that it's been printed —
        # keeps storage usage from growing forever. Only applies to student
        # uploads; handout files are shared across many orders and must
        # never be deleted here.
        if order.file and not order.handout:
            order.file.delete(save=False)

        order.save(update_fields=["printed_at", "file"])
        from notifications.tasks import send_student_ready_notification
        send_student_ready_notification.delay(order.id)
    return redirect("vendor_dashboard")

@login_required
@user_passes_test(is_authorized_vendor)
def mark_batch_printed(request):
    order_ids = request.POST.get("orders", "").split(",")
    orders = Order.objects.filter(id__in=order_ids, status="PAID", printed_at__isnull=True)
    for order in orders:
        order.printed_at = timezone.now()
        order.save(update_fields=["printed_at"])
        from notifications.tasks import send_student_ready_notification
        send_student_ready_notification.delay(order.id)
    return redirect("vendor_dashboard")


def pending_handout_count(request):
    if not is_authorized_vendor(request.user):
        return HttpResponse(status=403)
    from .models import Handout
    count = Handout.objects.filter(is_active=False).count()
    return HttpResponse(str(count))

from django.http import FileResponse

@login_required
@user_passes_test(is_authorized_vendor)
def print_order(request, order_id):
    from .pdf_utils import stamp_order_banner
    order = Order.objects.get(id=order_id)
    source = order.handout.file if order.handout else order.file
    stamped = stamp_order_banner(source, order.id, order.pickup_pin)
    return FileResponse(stamped, content_type="application/pdf")

# @login_required
# @user_passes_test(is_authorized_vendor)
# def print_batch(request, handout_id):
#     from .pdf_utils import stamp_order_banner
#     from .models import Handout
#     from pypdf import PdfWriter

#     handout = Handout.objects.get(id=handout_id)
#     orders = Order.objects.filter(handout_id=handout_id, status="PAID", printed_at__isnull=True)

#     combined = PdfWriter()
#     for order in orders:
#         stamped = stamp_order_banner(handout.file, order.id, order.pickup_pin, title=handout.title)
#         from pypdf import PdfReader
#         stamped_reader = PdfReader(stamped)
#         for page in stamped_reader.pages:
#             combined.add_page(page)

#     output = io.BytesIO()
#     combined.write(output)
#     output.seek(0)
#     return FileResponse(output, content_type="application/pdf")

@login_required
@user_passes_test(is_authorized_vendor)
def print_batch(request):
    order_ids = request.GET.get("orders", "").split(",")
    orders = Order.objects.filter(id__in=order_ids, status="PAID", printed_at__isnull=True)
    if not orders:
        return HttpResponse("No orders found", status=404)

    handout = orders.first().handout
    from .pdf_utils import stamp_order_banner
    from pypdf import PdfWriter, PdfReader
    import io

    combined = PdfWriter()
    for order in orders:
        stamped = stamp_order_banner(handout.file, order.id, order.pickup_pin, title=handout.title)
        for _ in range(order.copies):
            stamped.seek(0)
            stamped_reader = PdfReader(stamped)
            for page in stamped_reader.pages:
                combined.add_page(page)

    output = io.BytesIO()
    combined.write(output)
    output.seek(0)
    return FileResponse(output, content_type="application/pdf")
