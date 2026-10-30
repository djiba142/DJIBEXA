from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def create_branded_email(subject, message, recipient_list, from_email=None):
    plain_message = str(message)
    logo_url = f'{settings.FRONTEND_BASE_URL.rstrip("/")}/brand/kourouma-logo.svg'
    html_message = f'''\
<!doctype html>
<html lang="fr">
  <body style="margin:0;background:#f3f4f6;padding:32px 16px;font-family:Arial,sans-serif;color:#172033">
    <table role="presentation" style="width:100%;max-width:600px;margin:0 auto;background:#fff;border-radius:12px">
      <tr>
        <td style="padding:28px 32px 20px;text-align:center;border-bottom:1px solid #e5e7eb">
          <img src="{escape(logo_url, quote=True)}" alt="DJIBEXA" width="180" style="display:inline-block;width:180px;max-width:100%;height:auto">
        </td>
      </tr>
      <tr>
        <td style="padding:28px 32px;font-size:15px;line-height:1.6;white-space:pre-line">
          {escape(plain_message)}
        </td>
      </tr>
      <tr>
        <td style="padding:16px 32px 24px;color:#6b7280;font-size:12px;text-align:center">
          DJIBEXA — Gestion commerciale
        </td>
      </tr>
    </table>
  </body>
</html>'''
    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=list(recipient_list),
    )
    email.attach_alternative(html_message, 'text/html')
    return email


def send_branded_mail(
    subject,
    message,
    recipient_list,
    from_email=None,
    fail_silently=False,
):
    email = create_branded_email(
        subject=subject,
        message=message,
        recipient_list=recipient_list,
        from_email=from_email,
    )
    return email.send(fail_silently=fail_silently)
