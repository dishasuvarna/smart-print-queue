import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


def stamp_order_banner(file_bytes, order_id, pickup_pin, title=None):
    reader = PdfReader(io.BytesIO(file_bytes))
    writer = PdfWriter()

    first_page = reader.pages[0]

    # Bake any page rotation into the actual content first — otherwise a
    # rotated source PDF (common from scans or phone exports) causes the
    # banner overlay to misalign with the visible content.
    if first_page.get("/Rotate", 0):
        first_page.transfer_rotation_to_content()

    page_width = float(first_page.mediabox.width)
    page_height = float(first_page.mediabox.height)

    banner_buffer = io.BytesIO()
    c = canvas.Canvas(banner_buffer, pagesize=(page_width, page_height))

    banner_height = 26
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, page_height - banner_height, page_width, banner_height, fill=1, stroke=0)

    banner_text = f"{title} | Order #{order_id} | Pickup PIN: {pickup_pin}" if title else f"Order #{order_id} | Pickup PIN: {pickup_pin}"
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20, page_height - 20, banner_text)
    c.save()
    banner_buffer.seek(0)

    banner_pdf = PdfReader(banner_buffer)
    first_page.merge_page(banner_pdf.pages[0])
    writer.add_page(first_page)

    for page in reader.pages[1:]:
        if page.get("/Rotate", 0):
            page.transfer_rotation_to_content()
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output