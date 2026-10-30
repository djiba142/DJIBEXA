from datetime import timedelta

import requests
from django.db import transaction
from django.utils import timezone

from core.models import AppSetting

from .models import Notification

MAX_DISPATCH_ATTEMPTS = 5


def _get_setting(key, default=''):
    value = AppSetting.objects.filter(key=key).values_list('value', flat=True).first()
    return value if value not in (None, '') else default


def dispatch_whatsapp_notification(notification):
    if not notification.recipient_phone:
        return {'success': False, 'error': 'Aucun destinataire WhatsApp configuré.'}

    endpoint = _get_setting('whatsapp_api_endpoint')
    api_key = _get_setting('whatsapp_api_key')
    sender_id = _get_setting('whatsapp_sender_id')
    if not endpoint:
        return {'success': False, 'error': 'Le fournisseur WhatsApp n’est pas configuré.'}

    payload = {
        'to': notification.recipient_phone,
        'message': f'DJIBEXA | {notification.message}',
        'sender': sender_id,
        'event_type': notification.event_type,
    }
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        if response.status_code >= 400 or not getattr(response, 'ok', True):
            return {'success': False, 'error': f'Erreur provider WhatsApp: {response.status_code}'}
        return {'success': True, 'provider_response': response.json()}
    except requests.RequestException as exc:
        return {'success': False, 'error': str(exc)}
    except ValueError as exc:
        return {'success': False, 'error': f'Réponse WhatsApp invalide : {exc}'}


def dispatch_notification(notification_id, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        notification = Notification.objects.select_for_update().get(pk=notification_id)
        if notification.status == 'sent':
            return {'success': True, 'already_sent': True}
        if notification.attempt_count >= MAX_DISPATCH_ATTEMPTS:
            notification.status = 'failed'
            notification.save(update_fields=['status', 'updated_at'])
            return {'success': False, 'error': 'Nombre maximal de tentatives atteint.'}
        if notification.next_attempt_at and notification.next_attempt_at > now:
            return {'success': False, 'deferred': True}
        if notification.event_type == 'credit_reminder':
            from .reminders import refresh_credit_reminder

            if not refresh_credit_reminder(notification):
                notification.status = 'cancelled'
                notification.last_error = 'Rappel annulé : le solde est nul ou les rappels sont désactivés.'
                notification.next_attempt_at = None
                notification.save(update_fields=[
                    'status', 'last_error', 'next_attempt_at', 'updated_at',
                ])
                return {'success': True, 'cancelled': True}

        result = dispatch_whatsapp_notification(notification)
        notification.attempt_count += 1
        notification.is_read = False
        if result.get('success'):
            notification.status = 'sent'
            notification.last_error = ''
            notification.next_attempt_at = None
        else:
            notification.last_error = result.get('error', 'Échec de l’envoi WhatsApp.')
            if notification.attempt_count >= MAX_DISPATCH_ATTEMPTS:
                notification.status = 'failed'
                notification.next_attempt_at = None
            else:
                notification.status = 'retry'
                retry_minutes = min(5 * (2 ** (notification.attempt_count - 1)), 60)
                notification.next_attempt_at = now + timedelta(minutes=retry_minutes)
        notification.save(update_fields=[
            'status', 'attempt_count', 'last_error', 'next_attempt_at', 'is_read', 'updated_at',
        ])
        return result
