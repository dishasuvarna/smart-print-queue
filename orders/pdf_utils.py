import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch


def stamp_order_banner(file_bytes, order_id, pickup_pin, title=None):
    reader = PdfReader(io.BytesIO(file_bytes))
    writer = PdfWriter()
    writer.append(reader)  # copy all pages as-is, unmodified, no merge tricks

    first_page = writer.pages[0]
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

    banner_page = PdfReader(banner_buffer).pages[0]
    first_page.merge_page(banner_page, expand=False)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

# import io
# from pypdf import PdfReader, PdfWriter, Transformation
# from reportlab.pdfgen import canvas

# def stamp_order_banner(file_bytes, order_id, pickup_pin, title=None):
#     reader = PdfReader(io.BytesIO(file_bytes))
#     writer = PdfWriter()
#     writer.append(reader)

#     first_page = writer.pages[0]
#     page_width = float(first_page.mediabox.width)
#     page_height = float(first_page.mediabox.height)

#     # Hard-shrink the PDF page to leave a safe border around all sides
#     scale_factor = 0.85
#     new_width = page_width * scale_factor
#     new_height = page_height * scale_factor
    
#     x_offset = (page_width - new_width) / 2
#     y_offset = (page_height - new_height) / 2 - 20 

#     # Scale the content inward away from printer dead-zones
#     op = Transformation().scale(scale_factor, scale_factor).translate(x_offset, y_offset)
#     first_page.add_transformation(op)

#     # Draw the white banner at the top
#     banner_buffer = io.BytesIO()
#     c = canvas.Canvas(banner_buffer, pagesize=(page_width, page_height))
#     banner_height = 30
#     c.setFillColorRGB(1, 1, 1)
#     c.rect(0, page_height - banner_height, page_width, banner_height, fill=1, stroke=0)
    
#     banner_text = f"{title} | Order #{order_id} | Pickup PIN: {pickup_pin}" if title else f"Order #{order_id} | Pickup PIN: {pickup_pin}"
#     c.setFillColorRGB(0, 0, 0)
#     c.setFont("Helvetica-Bold", 12)
#     c.drawString(40, page_height - 22, banner_text)
#     c.save()
#     banner_buffer.seek(0)

#     banner_page = PdfReader(banner_buffer).pages[0]
#     first_page.merge_page(banner_page, expand=False)

#     output = io.BytesIO()
#     writer.write(output)
#     output.seek(0)
#     return output