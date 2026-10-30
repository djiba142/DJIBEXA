from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from core.models import AppSetting, AuditLog, Company
from sales.models import Sale

from .models import Notification, TenantCreditReminderSettings

REMINDER_DEFAULTS = {
    'enabled': 'true',
    'frequency': 'weekly',
    'day_of_week': '4',
    'time': '17:00',
}


def _company_identity(customer):
    company = Company.objects.filter(tenant_id=customer.tenant_id).first()
    tenant_name = customer.tenant.name if customer.tenant_id else ''
    return (
        company.name if company and company.name else tenant_name or 'DJIBEXA',
        company.currency if company and company.currency else 'GNF',
    )


def _credit_reminder_message(customer, balance):
    company_name, currency = _company_identity(customer)
    amount = f'{balance:,.0f}'.replace(',', ' ')
    return (
        f'Bonjour {customer.full_name}, votre solde total restant auprès de '
        f'{company_name} est de {amount} {currency}. '
        'Nous vous remercions de bien vouloir régulariser votre compte.'
    )


def refresh_credit_reminder(notification):
    if not notification.customer_id:
        return False

    customer = notification.customer
    tenant = notification.tenant or customer.tenant
    if not get_reminder_settings(tenant)['enabled']:
        return False
    balance = Sale.objects.filter(
        customer=customer,
        tenant_id=customer.tenant_id,
        payment_method='credit',
        status='partial',
        total_amount__gt=F('amount_paid'),
    ).aggregate(balance=Sum(F('total_amount') - F('amount_paid')))['balance'] or Decimal(0)
    if balance <= 0 or not customer.is_active or not customer.phone:
        return False

    notification.message = _credit_reminder_message(customer, balance)
    notification.recipient_phone = customer.phone
    notification.save(update_fields=['message', 'recipient_phone', 'updated_at'])
    return True


def get_reminder_settings(tenant=None):
    if tenant is not None:
        setting = TenantCreditReminderSettings.objects.filter(tenant=tenant).first()
        if setting is None:
            return {
                'enabled': True,
                'frequency': 'weekly',
                'day_of_week': 4,
                'time': time.fromisoformat('17:00'),
                'timezone': timezone.get_current_timezone_name(),
            }
        return {
            'enabled': setting.enabled,
            'frequency': setting.frequency,
            'day_of_week': setting.day_of_week,
            'time': setting.time,
            'timezone': timezone.get_current_timezone_name(),
        }

    stored = dict(AppSetting.objects.filter(
        key__in=[f'credit_reminder_{key}' for key in REMINDER_DEFAULTS]
    ).values_list('key', 'value'))
    values = {
        key: stored.get(f'credit_reminder_{key}', default)
        for key, default in REMINDER_DEFAULTS.items()
    }
    return {
        'enabled': values['enabled'].lower() == 'true',
        'frequency': values['frequency'],
        'day_of_week': int(values['day_of_week']),
        'time': time.fromisoformat(values['time']),
        'timezone': timezone.get_current_timezone_name(),
    }


def persist_reminder_settings(validated_data, user, tenant=None):
    if tenant is not None:
        with transaction.atomic():
            setting, created = TenantCreditReminderSettings.objects.get_or_create(
                tenant=tenant,
            )
            for key, value in validated_data.items():
                setattr(setting, key, value)
            setting.save(update_fields=[*validated_data, 'updated_at'])
            AuditLog.objects.create(
                user=user,
                action='create' if created else 'update',
                model_name='TenantCreditReminderSettings',
                record_id=setting.pk,
                details=f'Paramètres des rappels modifiés pour {tenant.name}.',
            )
        return get_reminder_settings(tenant)

    with transaction.atomic():
        for key, value in validated_data.items():
            normalized = value.strftime('%H:%M') if isinstance(value, time) else str(value).lower() if isinstance(value, bool) else str(value)
            setting, created = AppSetting.objects.update_or_create(
                key=f'credit_reminder_{key}',
                defaults={'value': normalized, 'description': 'Configuration des rappels de crédit'},
            )
            AuditLog.objects.create(
                user=user,
                action='create' if created else 'update',
                model_name='AppSetting',
                record_id=setting.id,
                details=f'Paramètre modifié: credit_reminder_{key}',
            )
    return get_reminder_settings()


def due_reminder_period(now=None, tenant=None):
    now = timezone.localtime(now or timezone.now())
    config = get_reminder_settings(tenant)
    if not config['enabled']:
        return None

    iso_year, iso_week, _ = now.isocalendar()
    monday = now.date() - timedelta(days=now.weekday())
    reminder_date = monday + timedelta(days=config['day_of_week'])
    due_at = timezone.make_aware(
        datetime.combine(reminder_date, config['time']),
        timezone.get_current_timezone(),
    )
    if now < due_at:
        return None
    return f'{iso_year}-W{iso_week:02d}'


def generate_weekly_credit_reminders(
    now=None,
    tenant=None,
    include_legacy=False,
):
    now = now or timezone.now()
    if not get_reminder_settings(tenant)['enabled']:
        return []
    local_now = timezone.localtime(now)
    iso_year, iso_week, _ = local_now.isocalendar()
    period = f'{iso_year}-W{iso_week:02d}'
    balances = {}
    sales = Sale.objects.filter(
        payment_method='credit',
        status='partial',
        total_amount__gt=F('amount_paid'),
    ).select_related('customer', 'customer__tenant')
    if tenant is not None:
        tenant_scope = Q(tenant=tenant, customer__tenant=tenant)
        if include_legacy:
            tenant_scope |= Q(tenant__isnull=True, customer__tenant__isnull=True)
        sales = sales.filter(tenant_scope)
    for sale in sales.iterator():
        if sale.customer.tenant_id != sale.tenant_id:
            continue
        if not sale.customer.is_active:
            continue
        entry = balances.setdefault(sale.customer_id, {
            'customer': sale.customer,
            'balance': Decimal('0'),
        })
        entry['balance'] += sale.total_amount - sale.amount_paid

    created_ids = []
    for entry in balances.values():
        customer = entry['customer']
        if not customer.phone or entry['balance'] <= 0:
            continue
        message = _credit_reminder_message(customer, entry['balance'])
        try:
            with transaction.atomic():
                notification, created = Notification.objects.get_or_create(
                    customer=customer,
                    reminder_period=period,
                    event_type='credit_reminder',
                    channel='whatsapp',
                    defaults={
                        'tenant_id': customer.tenant_id,
                        'status': 'pending',
                        'message': message,
                        'recipient_phone': customer.phone,
                    },
                )
        except IntegrityError:
            continue
        if created:
            created_ids.append(notification.id)
    return created_ids
