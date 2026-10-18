from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q
from django.utils import timezone

from core.models import PlatformTaskRun, Tenant
from notifications.models import Notification
from notifications.reminders import (
    due_reminder_period,
    generate_weekly_credit_reminders,
)
from notifications.services import MAX_DISPATCH_ATTEMPTS, dispatch_notification


class Command(BaseCommand):
    help = 'Crée les rappels dus et envoie les notifications WhatsApp en attente.'
    task_name = 'process_credit_notifications'

    def handle(self, *args, **options):
        now = timezone.now()
        task_run = PlatformTaskRun.objects.create(
            task_name=self.task_name,
            status='running',
            started_at=now,
        )
        try:
            self._process_notifications(now)
        except Exception as error:
            self._finish_run(task_run, 'failed', error)
            raise
        else:
            self._finish_run(task_run, 'succeeded')

    def _process_notifications(self, now):
        tenant_count = Tenant.objects.count()
        tenants_exist = tenant_count > 0
        include_legacy = tenant_count == 1
        active_tenants = Tenant.objects.filter(status='active').filter(
            Q(trial_ends_at__isnull=True) | Q(trial_ends_at__gt=now),
        ).order_by('pk')
        created_ids = []
        if tenants_exist:
            for tenant in active_tenants.iterator():
                if due_reminder_period(now, tenant):
                    created_ids.extend(
                        generate_weekly_credit_reminders(
                            now,
                            tenant=tenant,
                            include_legacy=include_legacy,
                        ),
                    )
        elif due_reminder_period(now):
            created_ids = generate_weekly_credit_reminders(now)

        due_notifications = Notification.objects.filter(
            channel='whatsapp',
            status__in=['pending', 'retry'],
            attempt_count__lt=MAX_DISPATCH_ATTEMPTS,
        ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).order_by('created_at')
        if tenants_exist:
            active_tenant_ids = list(active_tenants.values_list('pk', flat=True))
            tenant_scope = (
                Q(tenant_id__in=active_tenant_ids)
                & (
                    Q(sale__isnull=True)
                    | Q(sale__tenant_id__isnull=True)
                    | Q(sale__tenant_id=F('tenant_id'))
                )
                & (
                    Q(customer__isnull=True)
                    | Q(customer__tenant_id__isnull=True)
                    | Q(customer__tenant_id=F('tenant_id'))
                )
                & (
                    Q(recipient_user__isnull=True)
                    | Q(recipient_user__tenant_id__isnull=True)
                    | Q(recipient_user__tenant_id=F('tenant_id'))
                )
                & (
                    Q(sale__customer__tenant_id__isnull=True)
                    | Q(sale__customer__tenant_id=F('tenant_id'))
                )
            )
            if include_legacy and active_tenant_ids:
                legacy_scope = (
                    Q(tenant__isnull=True)
                    & (
                        Q(sale__isnull=False)
                        | Q(customer__isnull=False)
                        | Q(recipient_user__isnull=False)
                    )
                    & (
                        Q(sale__tenant_id__isnull=True)
                        | Q(sale__tenant_id__in=active_tenant_ids)
                    )
                    & (
                        Q(customer__tenant_id__isnull=True)
                        | Q(customer__tenant_id__in=active_tenant_ids)
                    )
                    & (
                        Q(recipient_user__tenant_id__isnull=True)
                        | Q(recipient_user__tenant_id__in=active_tenant_ids)
                    )
                    & (
                        Q(sale__customer__tenant_id__isnull=True)
                        | Q(sale__customer__tenant_id__in=active_tenant_ids)
                    )
                )
                tenant_scope |= legacy_scope
            due_notifications = due_notifications.filter(tenant_scope)

        sent = 0
        failed = 0
        cancelled = 0
        for notification_id in due_notifications.values_list('id', flat=True).iterator():
            result = dispatch_notification(notification_id, now=now)
            if result.get('cancelled'):
                cancelled += 1
            elif result.get('success'):
                sent += 1
            elif not result.get('deferred'):
                failed += 1

        summary = (
            f'Rappels créés: {len(created_ids)}; WhatsApp envoyés: {sent}; '
            f'annulés: {cancelled}; échecs/réessais: {failed}.'
        )
        if failed:
            self.stderr.write(self.style.ERROR(summary))
            raise CommandError(f'{failed} notification(s) WhatsApp ont échoué et seront retentées.')
        self.stdout.write(self.style.SUCCESS(summary))

    @staticmethod
    def _finish_run(task_run, status, error=None):
        finished_at = timezone.now()
        task_run.status = status
        task_run.finished_at = finished_at
        task_run.duration_ms = max(
            0,
            round((finished_at - task_run.started_at).total_seconds() * 1000),
        )
        task_run.error_type = type(error).__name__ if error else ''
        task_run.save(update_fields=[
            'status',
            'finished_at',
            'duration_ms',
            'error_type',
        ])
