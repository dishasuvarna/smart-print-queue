import io

from django.http.response import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db.models import Q

import razorpay
from django.conf import settings

from .models import Order, Handout, PricingSettings
from .validators import validate_pdf_upload, UploadValidationError
from .tasks import process_pdf

import logging
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .capacity import OrdersClosed, orders_open, reserve_order

from django.http import JsonResponse
from .capacity import OrdersClosed, closed_reason, release_hold, reserve_order
from .payments import process_captured_payment, recover_checkout

import re
import uuid
from .permissions import is_shopkeeper


logger = logging.getLogger("orders.payments")





# CLOSED_MESSAGES = {
#     "limit": "We've reached today's order limit. Please try again tomorrow.",
#     "holding": "The last few slots are held by students who are paying right now. Please try again in a few minutes.",
#     "storage": "We can't take new uploads right now. Please try again later today.",
# }


# def _closed_text(reason=None):
#     return CLOSED_MESSAGES.get(reason or closed_reason(), "")


def _cancel(order):
    release_hold(order.id)


def home(request):
    return render(request, "orders/home.html", {"closed": _closed_text()})


# def upload_order(request):
#     if request.method != "POST":
#         return render(request, "orders/upload.html", {"closed": _closed_text()})

#     uploaded_file = request.FILES.get("file")
#     if uploaded_file is None:
#         return render(request, "orders/upload.html", {"error": "Please choose a file to upload."})

#     copies = parse_copies(request.POST.get("copies", 1))
#     if copies is None:
#         return render(request, "orders/upload.html", {"error": f"Copies must be between 1 and {MAX_COPIES}."})

#     try:
#         page_count = validate_pdf_upload(uploaded_file)
#     except UploadValidationError as e:
#         return render(request, "orders/upload.html", {"error": str(e)})

#     is_color = request.POST.get("is_color") == "true"
#     is_double_sided = request.POST.get("is_double_sided") == "true"
#     rates = PricingSettings.get_rates()
#     per_page_rate = rates.color_rate_per_page if is_color else rates.bw_rate_per_page
#     total_price = per_page_rate * page_count * copies

#     try:
#         order = reserve_order(
#             upload_size=uploaded_file.size,
#             student_email=request.POST.get("student_email"),
#             page_count=page_count,
#             copies=copies,
#             is_color=is_color,
#             is_double_sided=is_double_sided,
#             total_price=total_price,
#         )
#     except OrdersClosed as exc:
#         return render(request, "orders/upload.html", {"closed": _closed_text(exc.reason)})

#     try:
#         order.file = uploaded_file
#         order.save(update_fields=["file"])
#         rzp = _start_payment(order, total_price)
#     except Exception:
#         logger.exception("Could not start checkout for order %s", order.id)
#         _cancel(order)
#         return render(request, "orders/upload.html", {"error": "Something went wrong starting your payment. Please try again."})

#     try:
#         process_pdf.delay(order.id)
#     except Exception:
#         logger.warning("Could not queue process_pdf for order %s", order.id)

#     return _payment_page(request, order, rzp)


# def order_handout(request, handout_id):
#     handout = get_object_or_404(Handout, id=handout_id, is_active=True)

#     if request.method != "POST":
#         return render(request, "orders/order_handout.html", {"handout": handout, "closed": _closed_text()})

#     copies = parse_copies(request.POST.get("copies", 1))
#     if copies is None:
#         return render(request, "orders/order_handout.html", {"handout": handout, "error": f"Copies must be between 1 and {MAX_COPIES}."})

#     total_price = handout.price_per_copy * copies
#     try:
#         order = reserve_order(
#             handout=handout,
#             student_email=request.POST.get("student_email"),
#             page_count=handout.page_count,
#             copies=copies,
#             total_price=total_price,
#         )
#     except OrdersClosed as exc:
#         return render(request, "orders/order_handout.html", {"handout": handout, "closed": _closed_text(exc.reason)})

#     try:
#         rzp = _start_payment(order, total_price)
#     except Exception:
#         logger.exception("Could not start checkout for order %s", order.id)
#         _cancel(order)
#         return render(request, "orders/order_handout.html", {"handout": handout, "error": "Something went wrong starting your payment. Please try again."})

#     return _payment_page(request, order, rzp)


@require_POST
def verify_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    params = {
        "razorpay_order_id": request.POST.get("razorpay_order_id", ""),
        "razorpay_payment_id": request.POST.get("razorpay_payment_id", ""),
        "razorpay_signature": request.POST.get("razorpay_signature", ""),
    }
    if order.razorpay_order_id and params["razorpay_order_id"] == order.razorpay_order_id:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        try:
            client.utility.verify_payment_signature(params)
        except razorpay.errors.SignatureVerificationError:
            logger.warning("Checkout signature failed for order %s", order.id)
        else:
            try:
                outcome = process_captured_payment(order.id, params["razorpay_payment_id"])
                logger.info("Order %s: checkout payment %s -> %s",
                            order.id, params["razorpay_payment_id"], outcome)
            except Exception:
                logger.exception("Could not settle order %s now; webhook and recovery will retry", order.id)
    return redirect("order_placed", order_id=order.id)


@require_POST
def abandon_checkout(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if not order.razorpay_order_id or request.POST.get("razorpay_order_id") != order.razorpay_order_id:
        return JsonResponse({"state": "settled"})
    try:
        state = recover_checkout(order.id)
    except Exception:
        logger.exception("Could not check checkout %s on dismiss", order.id)
        state = "waiting"
    return JsonResponse({"state": state})

# @require_POST
# def verify_payment(request, order_id):
#     order = get_object_or_404(Order, id=order_id)
#     params = {
#         "razorpay_order_id": request.POST.get("razorpay_order_id", ""),
#         "razorpay_payment_id": request.POST.get("razorpay_payment_id", ""),
#         "razorpay_signature": request.POST.get("razorpay_signature", ""),
#     }
#     if params["razorpay_order_id"] == order.razorpay_order_id:
#         client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
#         try:
#             client.utility.verify_payment_signature(params)
#             order.mark_paid()
#         except razorpay.errors.SignatureVerificationError:
#             logger.warning("Checkout signature failed for order %s", order.id)
#     return redirect("order_placed", order_id=order.id)







# def parse_copies(raw, max_copies):
#     try:
#         copies = int(raw)
#     except (TypeError, ValueError):
#         return None
#     return copies if 1 <= copies <= max_copies else None


TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")

CLOSED_MESSAGES = {
    "limit": "We've reached today's order limit. Please try again tomorrow.",
    "holding": "The last few slots are held by students who are paying right now. Please try again in a few minutes.",
    "storage": "We can't take new uploads right now. Please try again later today.",
    "setup": "Ordering isn't open yet. Please check back soon.",
}


def _closed_text(reason=None, for_upload=False):
    return CLOSED_MESSAGES.get(reason or closed_reason(for_upload=for_upload), "")


def _clean_token(raw):
    return raw if raw and TOKEN_RE.match(raw) else ""


def _form(request, template, ctx=None):
    """Render a form with a fresh one-time token and the current copy limits."""
    ctx = dict(ctx or {})
    rates = PricingSettings.get_rates()
    ctx.setdefault("token", uuid.uuid4().hex)
    ctx.setdefault("max_copies_bw", rates.max_copies_bw)
    ctx.setdefault("max_copies_color", rates.max_copies_color)
    return render(request, template, ctx)


def parse_copies(raw, max_copies):
    try:
        copies = int(raw)
    except (TypeError, ValueError):
        return None
    return copies if 1 <= copies <= max_copies else None


def _resume(request, order, template, ctx):
    """A repeated submit lands on the order the first submit created."""
    if order.status in ("PAID", "REFUND_DUE", "REFUNDED"):
        return redirect("order_placed", order_id=order.id)
    if order.status == "PENDING" and order.razorpay_order_id:
        return _payment_page(request, order, {"id": order.razorpay_order_id})
    ctx = dict(ctx, error="We're already processing this order. If the payment page doesn't open in a few seconds, go back and submit again.")
    return _form(request, template, ctx)


def upload_order(request):
    if request.method != "POST":
        return _form(request, "orders/upload.html", {"closed": _closed_text(for_upload=True)})

    rates = PricingSettings.get_rates()
    if rates.bw_rate_per_page is None or rates.color_rate_per_page is None:
        return _form(request, "orders/upload.html", {"closed": CLOSED_MESSAGES["setup"]})

    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return _form(request, "orders/upload.html", {"error": "Please choose a file to upload."})

    is_color = request.POST.get("is_color") == "true"
    is_double_sided = request.POST.get("is_double_sided") == "true"
    max_copies = rates.max_copies_color if is_color else rates.max_copies_bw
    copies = parse_copies(request.POST.get("copies", 1), max_copies)
    if copies is None:
        kind = "color" if is_color else "black & white"
        return _form(request, "orders/upload.html", {"error": f"You can order 1 to {max_copies} copies for {kind} prints."})

    try:
        page_count = validate_pdf_upload(uploaded_file)
    except UploadValidationError as e:
        return _form(request, "orders/upload.html", {"error": str(e)})

    per_page_rate = rates.color_rate_per_page if is_color else rates.bw_rate_per_page
    total_price = per_page_rate * page_count * copies
    if total_price < 1:
        return _form(request, "orders/upload.html", {"error": "The minimum order is ₹1. Please add pages or copies."})

    try:
        order, created = reserve_order(
            upload_size=uploaded_file.size,
            token=_clean_token(request.POST.get("submission_token")),
            student_email=request.POST.get("student_email"),
            page_count=page_count,
            copies=copies,
            is_color=is_color,
            is_double_sided=is_double_sided,
            total_price=total_price,
        )
    except OrdersClosed as exc:
        return _form(request, "orders/upload.html", {"closed": _closed_text(exc.reason)})

    if not created:
        return _resume(request, order, "orders/upload.html", {})

    try:
        order.file = uploaded_file
        order.save(update_fields=["file"])
        rzp = _start_payment(order, total_price)
    except Exception:
        logger.exception("Could not start checkout for order %s", order.id)
        _cancel(order)
        return _form(request, "orders/upload.html", {"error": "Something went wrong starting your payment. Please try again."})

    try:
        process_pdf.delay(order.id)
    except Exception:
        logger.warning("Could not queue process_pdf for order %s", order.id)

    return _payment_page(request, order, rzp)


def order_handout(request, handout_id):
    handout = get_object_or_404(Handout, id=handout_id, is_active=True)
    ctx = {"handout": handout}

    if request.method != "POST":
        return _form(request, "orders/order_handout.html", {**ctx, "closed": _closed_text()})

    if handout.price_per_copy is None:
        return _form(request, "orders/order_handout.html", {**ctx, "closed": CLOSED_MESSAGES["setup"]})

    max_copies = PricingSettings.get_rates().max_copies_bw
    copies = parse_copies(request.POST.get("copies", 1), max_copies)
    if copies is None:
        return _form(request, "orders/order_handout.html", {**ctx, "error": f"You can order 1 to {max_copies} copies."})

    total_price = handout.price_per_copy * copies
    if total_price < 1:
        return _form(request, "orders/order_handout.html", {**ctx, "error": "The minimum order is ₹1. Please add copies."})

    try:
        order, created = reserve_order(
            token=_clean_token(request.POST.get("submission_token")),
            handout=handout,
            student_email=request.POST.get("student_email"),
            page_count=handout.page_count,
            copies=copies,
            total_price=total_price,
        )
    except OrdersClosed as exc:
        return _form(request, "orders/order_handout.html", {**ctx, "closed": _closed_text(exc.reason)})

    if not created:
        return _resume(request, order, "orders/order_handout.html", ctx)

    try:
        rzp = _start_payment(order, total_price)
    except Exception:
        logger.exception("Could not start checkout for order %s", order.id)
        _cancel(order)
        return _form(request, "orders/order_handout.html", {**ctx, "error": "Something went wrong starting your payment. Please try again."})

    return _payment_page(request, order, rzp)

def _start_payment(order, total_price):
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    rzp = client.order.create({
        "amount": int(total_price * 100),
        "currency": "INR",
        "receipt": f"order_{order.id}",
    })
    order.razorpay_order_id = rzp["id"]
    order.save(update_fields=["razorpay_order_id"])
    return rzp


def _payment_page(request, order, rzp):
    return render(request, "orders/payment.html", {
        "order": order,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "razorpay_order_id": rzp["id"],
        "amount": int(order.total_price * 100),
    })


# def _cancel(order):
#     order.status = "CANCELLED"
#     order.save(update_fields=["status"])


# def home(request):
#     return render(request, "orders/home.html", {"orders_open": orders_open()})


# def upload_order(request):
#     if request.method != "POST":
#         return render(request, "orders/upload.html", {"closed": not orders_open()})

#     uploaded_file = request.FILES.get("file")
#     if uploaded_file is None:
#         return render(request, "orders/upload.html", {"error": "Please choose a file to upload."})

#     copies = parse_copies(request.POST.get("copies", 1))
#     if copies is None:
#         return render(request, "orders/upload.html", {"error": f"Copies must be between 1 and {MAX_COPIES}."})

#     try:
#         page_count = validate_pdf_upload(uploaded_file)
#     except UploadValidationError as e:
#         return render(request, "orders/upload.html", {"error": str(e)})

#     is_color = request.POST.get("is_color") == "true"
#     is_double_sided = request.POST.get("is_double_sided") == "true"
#     rates = PricingSettings.get_rates()
#     per_page_rate = rates.color_rate_per_page if is_color else rates.bw_rate_per_page
#     total_price = per_page_rate * page_count * copies

#     try:
#         order = reserve_order(
#             upload_size=uploaded_file.size,
#             student_email=request.POST.get("student_email"),
#             page_count=page_count,
#             copies=copies,
#             is_color=is_color,
#             is_double_sided=is_double_sided,
#             total_price=total_price,
#         )
#     except OrdersClosed:
#         return render(request, "orders/upload.html", {"closed": True})

#     try:
#         order.file = uploaded_file
#         order.save(update_fields=["file"])
#         rzp = _start_payment(order, total_price)
#     except Exception:
#         logger.exception("Could not start checkout for order %s", order.id)
#         _cancel(order)
#         return render(request, "orders/upload.html", {"error": "Something went wrong starting your payment. Please try again."})

#     try:
#         process_pdf.delay(order.id)
#     except Exception:
#         logger.warning("Could not queue process_pdf for order %s", order.id)

#     return _payment_page(request, order, rzp)


# def order_handout(request, handout_id):
#     handout = get_object_or_404(Handout, id=handout_id, is_active=True)

#     if request.method != "POST":
#         return render(request, "orders/order_handout.html", {"handout": handout, "closed": not orders_open()})

#     copies = parse_copies(request.POST.get("copies", 1))
#     if copies is None:
#         return render(request, "orders/order_handout.html", {"handout": handout, "error": f"Copies must be between 1 and {MAX_COPIES}."})

#     total_price = handout.price_per_copy * copies
#     try:
#         order = reserve_order(
#             handout=handout,
#             student_email=request.POST.get("student_email"),
#             page_count=handout.page_count,
#             copies=copies,
#             total_price=total_price,
#         )
#     except OrdersClosed:
#         return render(request, "orders/order_handout.html", {"handout": handout, "closed": True})

#     try:
#         rzp = _start_payment(order, total_price)
#     except Exception:
#         logger.exception("Could not start checkout for order %s", order.id)
#         _cancel(order)
#         return render(request, "orders/order_handout.html", {"handout": handout, "error": "Something went wrong starting your payment. Please try again."})

#     return _payment_page(request, order, rzp)

# def home(request):
#     return render(request, "orders/home.html")

def health_check(request):
    return HttpResponse("OK")

# def upload_order(request):
#     if request.method == "POST":
#         uploaded_file = request.FILES.get("file")
#         student_email = request.POST.get("student_email")
#         copies = int(request.POST.get("copies", 1))
#         is_color = request.POST.get("is_color") == "true"
#         is_double_sided = request.POST.get("is_double_sided") == "true"

#         try:
#             page_count = validate_pdf_upload(uploaded_file)
#         except UploadValidationError as e:
#             return render(request, "orders/upload.html", {"error": str(e)})

#         rates = PricingSettings.get_rates()
#         per_page_rate = rates.color_rate_per_page if is_color else rates.bw_rate_per_page
#         total_price = per_page_rate * page_count * copies

#         order = Order.objects.create(
#             student_email=student_email,
#             file=uploaded_file,
#             page_count=page_count,
#             copies=copies,
#             is_color=is_color,
#             is_double_sided=is_double_sided,
#             total_price=total_price,
#             status="PENDING",
#         )

#         client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
#         razorpay_order = client.order.create({
#             "amount": int(total_price * 100),
#             "currency": "INR",
#             "receipt": f"order_{order.id}",
#         })
#         order.razorpay_order_id = razorpay_order["id"]
#         order.save(update_fields=["razorpay_order_id"])

#         process_pdf.delay(order.id)

#         return render(request, "orders/payment.html", {
#             "order": order,
#             "razorpay_key_id": settings.RAZORPAY_KEY_ID,
#             "razorpay_order_id": razorpay_order["id"],
#             "amount": int(total_price * 100),
#         })

#     return render(request, "orders/upload.html")


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


# def order_handout(request, handout_id):
#     handout = Handout.objects.get(id=handout_id, is_active=True)

#     if request.method == "POST":
#         student_email = request.POST.get("student_email")
#         copies = int(request.POST.get("copies", 1))
#         total_price = handout.price_per_copy * copies

#         order = Order.objects.create(
#             student_email=student_email,
#             handout=handout,
#             page_count=handout.page_count,
#             copies=copies,
#             total_price=total_price,
#             status="PENDING",
#         )

#         client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
#         razorpay_order = client.order.create({
#             "amount": int(total_price * 100),
#             "currency": "INR",
#             "receipt": f"order_{order.id}",
#         })
#         order.razorpay_order_id = razorpay_order["id"]
#         order.save(update_fields=["razorpay_order_id"])

#         return render(request, "orders/payment.html", {
#             "order": order,
#             "razorpay_key_id": settings.RAZORPAY_KEY_ID,
#             "razorpay_order_id": razorpay_order["id"],
#             "amount": int(total_price * 100),
#         })

#     return render(request, "orders/order_handout.html", {"handout": handout})


def is_shopkeeper(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.groups.filter(name="Shopkeeper").exists()
    )


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
@user_passes_test(is_shopkeeper)
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
@user_passes_test(is_shopkeeper)
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
@user_passes_test(is_shopkeeper)
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
    if not is_shopkeeper(request.user):
        return HttpResponse(status=403)
    from .models import Handout
    count = Handout.objects.filter(is_active=False).count()
    return HttpResponse(str(count))

from django.http import FileResponse

@login_required
@user_passes_test(is_shopkeeper)
def print_order(request, order_id):
    from .pdf_utils import stamp_order_banner
    order = Order.objects.get(id=order_id)
    source = order.handout.file if order.handout else order.file
    with source.open("rb") as f:
        file_bytes = f.read()
    stamped = stamp_order_banner(file_bytes, order.id, order.pickup_pin)
    return FileResponse(stamped, content_type="application/pdf")


@login_required
@user_passes_test(is_shopkeeper)
def print_batch(request):
    from .pdf_utils import stamp_order_banner
    from pypdf import PdfWriter, PdfReader
    import io

    order_ids = request.GET.get("orders", "").split(",")
    orders = Order.objects.filter(id__in=order_ids, status="PAID", printed_at__isnull=True)
    if not orders:
        return HttpResponse("No orders found", status=404)

    handout = orders.first().handout
    with handout.file.open("rb") as f:
        file_bytes = f.read()

    combined = PdfWriter()
    for order in orders:
        stamped = stamp_order_banner(file_bytes, order.id, order.pickup_pin, title=handout.title)
        for _ in range(order.copies):
            stamped.seek(0)
            stamped_reader = PdfReader(stamped)
            for page in stamped_reader.pages:
                combined.add_page(page)

    output = io.BytesIO()
    combined.write(output)
    output.seek(0)
    return FileResponse(output, content_type="application/pdf")