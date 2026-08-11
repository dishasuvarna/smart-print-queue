import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


def stamp_order_banner(source_file, order_id, pickup_pin, title=None):
    source_file.seek(0)
    reader = PdfReader(source_file)
    writer = PdfWriter()

    first_page = reader.pages[0]
    page_width = float(first_page.mediabox.width)
    page_height = float(first_page.mediabox.height)

    banner_buffer = io.BytesIO()
    c = canvas.Canvas(banner_buffer, pagesize=(page_width, page_height))
    if title:
        banner_text = f"{title} | Order #{order_id} | Pickup PIN: {pickup_pin}"
    else:
        banner_text = f"Order #{order_id} | Pickup PIN: {pickup_pin}"
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20, page_height - 20, banner_text)
    c.save()
    banner_buffer.seek(0)

    banner_pdf = PdfReader(banner_buffer)
    first_page.merge_page(banner_pdf.pages[0])
    writer.add_page(first_page)

    for page in reader.pages[1:]:
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output