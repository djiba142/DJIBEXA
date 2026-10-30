from decimal import Decimal
from io import BytesIO
from math import ceil
from pathlib import Path

import qrcode
from django.conf import settings
from num2words import num2words
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from core.models import Company, Tenant
from payments.models import Payment

from .branding import get_tenant_invoice_branding, get_tenant_invoice_company_name
from .serializers import invoice_verification_url


ROWS_PER_PAGE = 25
PAGE_SIZE = A4
BRAND_BLUE = colors.HexColor('#123D60')
TABLE_BLUE = colors.HexColor('#245B82')


def build_invoice_snapshot(invoice):
    sale = invoice.sale
    tenant = sale.tenant
    if tenant is None:
        tenants = list(Tenant.objects.order_by('pk')[:2])
        tenant = tenants[0] if len(tenants) == 1 else None
    branding = get_tenant_invoice_branding(tenant)
    company = Company.objects.filter(tenant=tenant).first() if tenant else None
    company_name = get_tenant_invoice_company_name(
        tenant,
        branding,
        fallback_name=invoice.company_name,
    )
    phone_numbers = (
        branding.phone_numbers
        if branding and tenant
        else [company.phone] if company and company.phone
        else [settings.INVOICE_COMPANY_PHONE] if not tenant
        else []
    )
    phone_numbers = [phone.strip() for phone in phone_numbers if phone.strip()]
    email_addresses = (
        branding.email_addresses or ([branding.email] if branding.email else [])
        if branding and tenant
        else [company.email] if company and company.email
        else [settings.INVOICE_COMPANY_EMAIL] if not tenant
        else []
    )
    email_addresses = [email.strip() for email in email_addresses if email.strip()]
    customer = sale.customer
    items = list(sale.items.select_related('product').order_by('id'))
    payments = list(
        Payment.objects.filter(sale=sale).order_by('payment_date', 'id').values(
            'amount', 'payment_method', 'reference', 'payment_date',
        )
    )
    subtotal = sum(
        (item.unit_price * item.quantity for item in items),
        Decimal('0.00'),
    )
    return {
        'version': invoice.document_version,
        'company': {
            'name': company_name,
            'activity': branding.activity if branding else '',
            'distributor': branding.distributor_details if branding else '',
            'address': (
                branding.address if branding and tenant
                else company.address if company
                else settings.INVOICE_COMPANY_ADDRESS if not tenant
                else ''
            ),
            'phone': ' / '.join(phone_numbers),
            'phones': phone_numbers,
            'email': email_addresses[0] if email_addresses else '',
            'emails': email_addresses,
            'additional_lines': branding.additional_lines if branding else [],
            'rccm': branding.rccm if branding else settings.INVOICE_COMPANY_RCCM if not tenant else '',
            'nif': branding.nif if branding else settings.INVOICE_COMPANY_NIF if not tenant else '',
            'currency': company.currency if company else 'GNF',
            'line_display_mode': branding.line_display_mode if branding else 'compact',
            'header_alignment': branding.header_alignment if branding else 'center',
            'header_color': branding.header_color if branding else '#123D60',
            'text_color': branding.text_color if branding else '#FFFFFF',
            'show': {
                'company_name': branding.show_company_name if branding else True,
                'activity': branding.show_activity if branding else True,
                'distributor': branding.show_distributor if branding else True,
                'address': branding.show_address if branding else True,
                'phones': branding.show_phones if branding else True,
                'emails': branding.show_emails if branding else True,
                'rccm': branding.show_rccm if branding else True,
                'nif': branding.show_nif if branding else True,
                'logo': branding.show_logo if branding else True,
                'automotive_image': branding.show_automotive_image if branding else True,
                'watermark': branding.show_watermark if branding else True,
                'stamp': branding.show_stamp if branding else True,
                'seller_signature': branding.show_seller_signature if branding else True,
                'qr': branding.show_qr if branding else True,
            },
            'logo_path': branding.logo_image.path if branding and branding.logo_image else '',
            'automotive_path': (
                branding.automotive_image.path if branding and branding.automotive_image else ''
            ),
            'watermark_path': (
                branding.watermark_image.path if branding and branding.watermark_image else ''
            ),
            'stamp_path': branding.stamp_image.path if branding and branding.stamp_image else '',
            'stamp_size_mm': branding.stamp_size_mm if branding else 20,
            'stamp_opacity': branding.stamp_opacity if branding else 100,
            'stamp_position': branding.stamp_position if branding else 'center',
            'seller_signature_path': (
                branding.seller_signature_image.path
                if branding and branding.seller_signature_image
                else ''
            ),
            'seller_signature_name': branding.seller_signature_name if branding else '',
            'seller_signature_title': branding.seller_signature_title if branding else '',
        },
        'invoice_number': invoice.invoice_number,
        'issued_at': invoice.issue_date.isoformat(),
        'verification_url': invoice_verification_url(invoice),
        'validation_reference': invoice.validation_reference,
        'customer': {
            'name': customer.full_name,
            'phone': customer.phone,
            'address': customer.address,
        },
        'seller': sale.seller.get_full_name() if sale.seller else '',
        'payment_method': sale.payment_method,
        'items': [
            {
                'description': item.product.name if item.product_id else item.item_name,
                'reference': item.product.sku if item.product_id else item.item_reference,
                'quantity': item.quantity,
                'unit_price': str(item.unit_price),
                'amount': str(item.total_price),
            }
            for item in items
        ],
        'payments': [
            {
                **payment,
                'amount': str(payment['amount']),
                'payment_date': payment['payment_date'].isoformat(),
            }
            for payment in payments
        ],
        'subtotal': str(subtotal),
        'discount': str(sale.discount),
        'total': str(invoice.total_amount),
        'paid': str(invoice.paid_amount),
        'balance_due': str(invoice.balance_due),
        'stamp_text': invoice.validation_stamp,
        'commercial_note': 'LES MARCHANDISES VENDUES NE SONT NI REMBOURSÉES NI ÉCHANGÉES.',
    }


def _fit_text(value, font, size, max_width):
    text = str(value or '')
    if stringWidth(text, font, size) <= max_width:
        return text
    while text and stringWidth(f'{text}…', font, size) > max_width:
        text = text[:-1]
    return f'{text}…' if text else ''


def _wrap_text(value, font, size, max_width):
    words = str(value or '').split()
    if not words:
        return ['']
    lines = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if stringWidth(candidate, font, size) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        if stringWidth(word, font, size) <= max_width:
            current = word
            continue
        fragment = ''
        for character in word:
            if stringWidth(fragment + character, font, size) > max_width and fragment:
                lines.append(fragment)
                fragment = character
            else:
                fragment += character
        current = fragment
    if current:
        lines.append(current)
    return lines


def _draw_rotor_watermark(document, center_x, center_y, watermark_path=''):
    watermark_path = watermark_path or settings.INVOICE_WATERMARK_PATH
    if watermark_path and Path(watermark_path).is_file():
        document.saveState()
        document.setFillAlpha(0.08)
        document.drawImage(
            ImageReader(watermark_path),
            center_x - 74,
            center_y - 74,
            width=148,
            height=148,
            preserveAspectRatio=True,
            anchor='c',
            mask='auto',
        )
        document.restoreState()
        return

    document.saveState()
    document.setStrokeColor(colors.HexColor('#7894A7'))
    document.setStrokeAlpha(0.12)
    document.setLineWidth(12)
    document.circle(center_x, center_y, 70, stroke=1, fill=0)
    document.setLineWidth(2)
    document.circle(center_x, center_y, 49, stroke=1, fill=0)
    document.circle(center_x, center_y, 19, stroke=1, fill=0)
    for index in range(5):
        document.saveState()
        document.translate(center_x, center_y)
        document.rotate(index * 72)
        document.circle(0, 34, 5, stroke=1, fill=0)
        document.restoreState()
    document.restoreState()


def _draw_header(document, snapshot, page_number, page_count):
    width, height = PAGE_SIZE
    company = snapshot['company']
    visibility = company.get('show', {})
    visibility = {
        key: visibility.get(key, True)
        for key in (
            'company_name', 'activity', 'distributor', 'address', 'phones', 'emails',
            'rccm', 'nif', 'logo', 'automotive_image', 'watermark', 'stamp', 'qr',
        )
    }
    phone_numbers = (company.get('phones') or [company.get('phone', '')]) if visibility['phones'] else []
    email_addresses = (company.get('emails') or [company.get('email', '')]) if visibility['emails'] else []
    contact_values = [f'Tél. {phone}' for phone in phone_numbers]
    contact_values.extend(f'E-mail : {email}' for email in email_addresses)
    content_rows = []
    legal = '  |  '.join(
        value for value in (
            f"RCCM {company.get('rccm', '')}" if visibility['rccm'] and company.get('rccm') else '',
            f"NIF {company.get('nif', '')}" if visibility['nif'] and company.get('nif') else '',
        ) if value
    )
    centered_values = []
    if visibility['activity'] and company.get('activity'):
        centered_values.append(company['activity'])
    if visibility['distributor'] and company.get('distributor'):
        centered_values.append(company['distributor'])
    if visibility['address'] and company.get('address') and company['address'] not in company.get('distributor', ''):
        centered_values.append(company['address'])
    if legal:
        centered_values.append(legal)
    logo_path = company.get('logo_path', '')
    logo_path = logo_path if visibility['logo'] and logo_path and Path(logo_path).is_file() else ''
    automotive_path = company.get('automotive_path', '')
    automotive_path = (
        automotive_path
        if visibility['automotive_image'] and automotive_path and Path(automotive_path).is_file()
        else ''
    )
    content_left = 28 + (76 if logo_path else 0)
    content_right = width - 28 - (118 if automotive_path else 0)
    content_width = content_right - content_left
    for value in centered_values:
        content_rows.append(_wrap_text(value, 'Helvetica', 8, content_width))
    for index in range(0, len(contact_values), 2):
        contact_row = '    '.join(contact_values[index:index + 2])
        content_rows.append(_wrap_text(contact_row, 'Helvetica', 8, content_width))
    for value in company.get('additional_lines', []):
        content_rows.append(_wrap_text(value, 'Helvetica', 8, content_width))
    content_line_count = sum(len(row_lines) for row_lines in content_rows)
    title_lines = (
        _wrap_text(company.get('name', '').upper(), 'Helvetica-Bold', 20, content_width)
        if visibility['company_name'] else []
    )
    title_line_count = max(1, len(title_lines))
    header_height = max(
        118,
        64 + max(0, title_line_count - 1) * 22 + content_line_count * 11,
    )

    header_color = colors.HexColor(company.get('header_color', '#123D60'))
    text_color = colors.HexColor(company.get('text_color', '#FFFFFF'))
    document.setFillColor(header_color)
    document.rect(0, height - header_height, width, header_height, stroke=0, fill=1)
    header_bottom = height - header_height
    if logo_path:
        logo_size = min(64, header_height - 24)
        document.drawImage(
            ImageReader(logo_path),
            20,
            header_bottom + (header_height - logo_size) / 2,
            width=logo_size,
            height=logo_size,
            preserveAspectRatio=True, anchor='c', mask='auto',
        )
    document.setFillColor(text_color)
    if visibility['company_name']:
        document.setFont('Helvetica-Bold', 20)
        for index, title_line in enumerate(title_lines):
            baseline = height - 31 - index * 22
            document.drawCentredString((content_left + content_right) / 2, baseline, title_line)
    if automotive_path:
        automotive_height = min(88, header_height - 20)
        document.drawImage(
            ImageReader(automotive_path),
            width - 122,
            header_bottom + (header_height - automotive_height) / 2,
            width=108,
            height=automotive_height,
            preserveAspectRatio=True,
            anchor='c',
            mask='auto',
        )
    document.setFont('Helvetica', 8)
    line_offset = 0
    for row_lines in content_rows:
        for row_text in row_lines:
            baseline = height - 52 - max(0, title_line_count - 1) * 19 - line_offset * 11
            document.drawCentredString((content_left + content_right) / 2, baseline, row_text)
            line_offset += 1
    if visibility['watermark']:
        _draw_rotor_watermark(
            document, width / 2, height - header_height / 2,
            watermark_path=company.get('watermark_path', ''),
        )
    document.setFillColor(text_color)
    document.setFont('Helvetica-Bold', 8)
    document.drawRightString(width - 28, height - 16, f'PAGE {page_number}/{page_count}')
    return height - header_height


def _draw_qr(document, verification_url, x=498, y=43, size=64):
    qr = qrcode.make(verification_url)
    image = BytesIO()
    qr.save(image, format='PNG')
    image.seek(0)
    document.drawImage(ImageReader(image), x, y, width=size, height=size, mask='auto')


def _draw_company_stamp(document, snapshot, center_x, center_y):
    company = snapshot['company']
    size = float(company.get('stamp_size_mm', 20)) * 72 / 25.4
    opacity = max(0.2, min(1.0, float(company.get('stamp_opacity', 100)) / 100))

    document.saveState()
    document.setFillAlpha(opacity)
    document.setStrokeAlpha(opacity)
    stamp_path = company.get('stamp_path', '')
    if stamp_path and Path(stamp_path).is_file():
        document.drawImage(
            ImageReader(stamp_path),
            center_x - size / 2,
            center_y - size / 2,
            width=size,
            height=size,
            preserveAspectRatio=True,
            anchor='c',
            mask='auto',
        )
    else:
        radius = size / 2
        stamp_text = str(snapshot.get('stamp_text') or 'VALIDEE').upper()
        is_cancelled = 'ANNULEE' in stamp_text or 'ANNULÉE' in stamp_text
        stamp_color = colors.HexColor(
            '#B42318' if is_cancelled else company.get('header_color', '#123D60')
        )
        document.setStrokeColor(stamp_color)
        document.setFillColor(stamp_color)
        document.setLineWidth(max(0.8, size / 48))
        document.circle(center_x, center_y, radius, stroke=1, fill=0)
        document.setLineWidth(max(0.35, size / 120))
        document.circle(center_x, center_y, radius * 0.88, stroke=1, fill=0)

        name_font_size = max(3.2, min(4.8, size / 15))
        name_lines = _wrap_text(
            company['name'].upper(),
            'Helvetica-Bold',
            name_font_size,
            size * 0.72,
        )
        if len(name_lines) > 2:
            name_lines = [
                _fit_text(company['name'].upper(), 'Helvetica-Bold', 3.2, size * 0.72)
            ]
            name_font_size = 3.2
        document.setFont('Helvetica-Bold', name_font_size)
        for index, line in enumerate(name_lines):
            document.drawCentredString(
                center_x,
                center_y + size * 0.24 - index * (name_font_size + 1),
                line,
            )

        band_height = size * 0.2
        band_width = size * 0.72
        band_bottom = center_y - band_height * 0.55
        document.roundRect(
            center_x - band_width / 2,
            band_bottom,
            band_width,
            band_height,
            band_height / 3,
            stroke=0,
            fill=1,
        )
        status_font_size = max(4.2, min(6.2, size / 11))
        document.setFillColor(colors.white)
        document.setFont('Helvetica-Bold', status_font_size)
        document.drawCentredString(
            center_x,
            band_bottom + (band_height - status_font_size) / 2 + status_font_size * 0.12,
            _fit_text(stamp_text, 'Helvetica-Bold', status_font_size, band_width - 5),
        )
        document.setFillColor(stamp_color)
        document.setFont('Helvetica-Bold', max(3.2, min(4.2, size / 16)))
        document.drawCentredString(center_x, center_y - size * 0.3, 'FACTURE')
    document.restoreState()


def _draw_signature_boxes(document, snapshot, visibility, left, right):
    bottom = 37
    box_height = 94
    gap = 5
    widths = [130, 130, 145, right - left - 130 - 130 - 145 - gap * 3]
    positions = []
    current_left = left
    for box_width in widths:
        positions.append((current_left, box_width))
        current_left += box_width + gap

    document.saveState()
    document.setStrokeColor(colors.HexColor('#73A9E8'))
    document.setLineWidth(0.65)
    document.setFillColor(colors.white)
    for x, box_width in positions:
        document.roundRect(x, bottom, box_width, box_height, 5, stroke=1, fill=1)

    client_x, client_width = positions[0]
    document.setFillColor(BRAND_BLUE)
    document.setFont('Helvetica-Bold', 7)
    document.drawString(client_x + 8, bottom + box_height - 13, 'Signature du client')
    document.setFont('Helvetica', 6)
    document.drawString(client_x + 8, bottom + box_height - 27, 'Nom et signature')
    document.setStrokeColor(colors.HexColor('#A8C9EE'))
    document.line(client_x + 8, bottom + 15, client_x + client_width - 8, bottom + 15)

    seller_x, seller_width = positions[1]
    document.setFillColor(BRAND_BLUE)
    document.setFont('Helvetica-Bold', 7)
    document.drawString(seller_x + 8, bottom + box_height - 13, 'Signature du vendeur')
    company = snapshot['company']
    signature_name = company.get('seller_signature_name') or snapshot.get('seller', '')
    signature_title = company.get('seller_signature_title', '')
    document.setFont('Helvetica', 6)
    if signature_name:
        document.drawString(
            seller_x + 8,
            bottom + box_height - 26,
            _fit_text(signature_name, 'Helvetica', 6, seller_width - 16),
        )
    if signature_title:
        document.drawString(
            seller_x + 8,
            bottom + box_height - 35,
            _fit_text(signature_title, 'Helvetica', 6, seller_width - 16),
        )
    signature_path = company.get('seller_signature_path', '')
    if visibility.get('seller_signature', True) and signature_path and Path(signature_path).is_file():
        document.drawImage(
            ImageReader(signature_path),
            seller_x + 12,
            bottom + 5,
            width=seller_width - 24,
            height=36,
            preserveAspectRatio=True,
            anchor='c',
            mask='auto',
        )
    else:
        document.setStrokeColor(colors.HexColor('#A8C9EE'))
        document.line(seller_x + 8, bottom + 15, seller_x + seller_width - 8, bottom + 15)

    stamp_x, stamp_width = positions[2]
    document.setFillColor(BRAND_BLUE)
    document.setFont('Helvetica-Bold', 6)
    document.drawCentredString(
        stamp_x + stamp_width / 2,
        bottom + box_height - 10,
        'Validation et cachet',
    )
    if visibility.get('stamp', True):
        stamp_size = float(company.get('stamp_size_mm', 20)) * 72 / 25.4
        stamp_offset = stamp_size / 2 + 6
        stamp_centers = {
            'left': stamp_x + stamp_offset,
            'center': stamp_x + stamp_width / 2,
            'right': stamp_x + stamp_width - stamp_offset,
        }
        _draw_company_stamp(
            document,
            snapshot,
            stamp_centers.get(company.get('stamp_position'), stamp_x + stamp_width / 2),
            bottom + box_height / 2 - 5,
        )

    qr_x, qr_width = positions[3]
    if visibility.get('qr', True):
        qr_size = 48
        _draw_qr(
            document,
            snapshot['verification_url'],
            qr_x + (qr_width - qr_size) / 2,
            bottom + 24,
            qr_size,
        )
        document.setFillColor(BRAND_BLUE)
        document.setFont('Helvetica', 5)
        document.drawCentredString(
            qr_x + qr_width / 2,
            bottom + 14,
            'Vérification de la facture',
        )
        document.setFont('Helvetica', 4.5)
        document.drawCentredString(
            qr_x + qr_width / 2,
            bottom + 6,
            _fit_text(
                f"Réf. {snapshot['validation_reference']}",
                'Helvetica',
                4.5,
                qr_width - 8,
            ),
        )
    document.restoreState()


def render_invoice_pdf(snapshot):
    items = snapshot['items']
    if not items:
        raise ValueError('Une facture sans ligne de produit ne peut pas être émise.')
    if any(int(item['quantity']) < 1 or Decimal(item['unit_price']) < 0 for item in items):
        raise ValueError('La facture contient une quantité ou un prix invalide.')

    page_count = max(1, ceil(len(items) / ROWS_PER_PAGE))
    buffer = BytesIO()
    document = canvas.Canvas(buffer, pagesize=PAGE_SIZE, pageCompression=1)
    document.setTitle(f"Facture {snapshot['invoice_number']}")
    document.setAuthor(snapshot['company']['name'])
    document.setSubject(f"Document {snapshot['validation_reference']}")

    for page_index in range(page_count):
        page_number = page_index + 1
        page_items = items[page_index * ROWS_PER_PAGE:(page_index + 1) * ROWS_PER_PAGE]
        header_bottom = _draw_header(document, snapshot, page_number, page_count)
        visibility = snapshot['company'].get('show', {})
        width, height = PAGE_SIZE
        document.setFillColor(colors.black)
        document.setFont('Helvetica-Bold', 10)
        details_top = header_bottom - 24
        document.drawString(32, details_top, f"FACTURE N° {snapshot['invoice_number']}")
        document.setFont('Helvetica', 9)
        document.drawRightString(width - 32, details_top, f"Date : {snapshot['issued_at'][:10]}")
        document.drawString(32, details_top - 20, f"Client : {snapshot['customer']['name']}")
        document.drawString(32, details_top - 35, f"Téléphone : {snapshot['customer']['phone'] or '-'}")
        document.drawString(32, details_top - 50, f"Adresse : {snapshot['customer']['address'] or '-'}")

        left = 32
        right = width - 32
        column_edges = [left, left + 38, left + 330, left + 382, left + 463, right]
        table_top = details_top - 65
        heading_height = 20
        row_height = 15
        reserved_table_bottom = table_top - heading_height - ROWS_PER_PAGE * row_height
        line_mode = snapshot['company'].get('line_display_mode', 'compact')
        rows_to_draw = ROWS_PER_PAGE if line_mode == 'carnet' else len(page_items)
        table_bottom = table_top - heading_height - rows_to_draw * row_height
        if reserved_table_bottom < 180:
            raise ValueError(
                'Les informations configurées de l’en-tête ne laissent pas assez de place au tableau et au pied de page.'
            )
        if visibility.get('watermark', True):
            _draw_rotor_watermark(
                document,
                width / 2,
                (table_top + reserved_table_bottom) / 2,
                watermark_path=snapshot['company'].get('watermark_path', ''),
            )

        table_header_color = colors.HexColor(snapshot['company'].get('header_color', '#123D60'))
        table_text_color = colors.HexColor(snapshot['company'].get('text_color', '#FFFFFF'))
        document.setFillColor(table_header_color)
        document.rect(left, table_top - heading_height, right - left, heading_height, stroke=0, fill=1)
        document.setFillColor(table_text_color)
        document.setFont('Helvetica-Bold', 8)
        headings = ['N°', 'Désignation', 'Qté', 'Prix unit.', 'Montant']
        for index, heading in enumerate(headings):
            document.drawString(column_edges[index] + 5, table_top - 14, heading)

        document.setStrokeColor(TABLE_BLUE)
        document.setLineWidth(0.45)
        document.rect(left, table_bottom, right - left, table_top - heading_height - table_bottom, stroke=1, fill=0)
        for edge in column_edges[1:-1]:
            document.line(edge, table_bottom, edge, table_top)
        for row_index in range(rows_to_draw + 1):
            y = table_top - heading_height - row_index * row_height
            document.line(left, y, right, y)

        document.setFillColor(colors.HexColor('#18252E'))
        for row_index in range(rows_to_draw):
            item_index = page_index * ROWS_PER_PAGE + row_index
            y = table_top - heading_height - row_index * row_height - 10
            document.setFont('Helvetica', 8)
            document.drawString(column_edges[0] + 6, y, str(item_index + 1))
            if row_index >= len(page_items):
                continue
            item = page_items[row_index]
            document.setFont('Helvetica', 8)
            document.drawString(
                column_edges[1] + 5,
                y,
                _fit_text(item['description'], 'Helvetica', 8, column_edges[2] - column_edges[1] - 10),
            )
            document.drawRightString(column_edges[3] - 5, y, str(item['quantity']))
            document.drawRightString(column_edges[4] - 5, y, item['unit_price'])
            document.drawRightString(column_edges[5] - 5, y, item['amount'])

        if page_number == page_count:
            footer_top = reserved_table_bottom - 14
            document.setFont('Helvetica-Bold', 9)
            document.drawRightString(right - 80, footer_top, 'Total')
            document.drawRightString(right - 5, footer_top, f"{snapshot['total']} GNF")
            document.setFont('Helvetica', 8)
            document.drawRightString(right - 80, footer_top - 14, 'Montant payé')
            document.drawRightString(right - 5, footer_top - 14, f"{snapshot['paid']} GNF")
            document.drawRightString(right - 80, footer_top - 28, 'Reste à payer')
            document.drawRightString(right - 5, footer_top - 28, f"{snapshot['balance_due']} GNF")
            document.setFont('Helvetica', 7)
            payment_summary = ', '.join(
                f"{payment['amount']} GNF ({payment['payment_method']})"
                for payment in snapshot['payments'][:3]
            ) or snapshot['payment_method']
            document.drawString(left, footer_top - 14, _fit_text(f'Paiement(s) : {payment_summary}', 'Helvetica', 7, 245))
            try:
                amount_words = num2words(int(Decimal(snapshot['total'])), lang='fr')
            except (NotImplementedError, TypeError, ValueError):
                amount_words = snapshot['total']
            document.setFont('Helvetica-Bold', 7)
            document.drawString(
                left,
                footer_top - 31,
                _fit_text(f'Arrêtée à la somme de : {amount_words} francs guinéens.', 'Helvetica-Bold', 7, 320),
            )

            _draw_signature_boxes(document, snapshot, visibility, left, right)
            document.setFillColor(BRAND_BLUE)
            document.roundRect(left, 17, right - left, 16, 3, stroke=0, fill=1)
            document.setFillColor(colors.white)
            document.setFont('Helvetica-Bold', 7)
            document.drawCentredString(width / 2, 22, snapshot['commercial_note'])
        else:
            document.setFont('Helvetica-Oblique', 8)
            document.drawString(left, 72, 'Suite de la facture sur la page suivante.')

        document.showPage()

    document.save()
    return buffer.getvalue(), page_count