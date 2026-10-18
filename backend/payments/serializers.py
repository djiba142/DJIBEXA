from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from rest_framework import serializers
from uuid import uuid4

from core.models import AuditLog, Company
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from customers.models import Customer
from finance.models import FinancialAccount, FinancialTransaction
from notifications.models import Notification
from sales.models import Sale

from .models import CreditLedger, Payment, PaymentAllocation


class PaymentAllocationSerializer(serializers.ModelSerializer):
    invoice_number = serializers.SerializerMethodField()

    class Meta:
        model = PaymentAllocation
        fields = ['id', 'sale', 'invoice_number', 'amount']

    def get_invoice_number(self, obj):
        invoice = getattr(obj.sale, 'invoice', None)
        return invoice.invoice_number if invoice else None


class PaymentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.display_name', read_only=True)
    allocations = PaymentAllocationSerializer(many=True, read_only=True)
    payment_date = serializers.DateTimeField(required=False)

    class Meta:
        model = Payment
        fields = [
            'id', 'customer', 'sale', 'amount', 'payment_method', 'financial_account',
            'reference', 'payment_date', 'notes', 'created_by', 'created_by_name',
            'allocations',
        ]
        read_only_fields = ['id', 'created_by', 'created_by_name', 'allocations']

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if user and user.is_authenticated:
            fields['customer'].queryset = tenant_scoped_queryset(
                fields['customer'].queryset,
                user,
            )
            fields['sale'].queryset = tenant_scoped_queryset(
                fields['sale'].queryset,
                user,
            )
            fields['financial_account'].queryset = tenant_scoped_queryset(
                fields['financial_account'].queryset,
                user,
            )
        return fields

    @staticmethod
    def sync_sale_payment(sale):
        paid_total = sale.payment_allocations.aggregate(total=Sum('amount'))['total'] or 0
        sale.amount_paid = paid_total
        sale.status = 'paid' if paid_total >= sale.total_amount else 'partial'
        sale.save(update_fields=['amount_paid', 'status', 'updated_at'])
        if hasattr(sale, 'invoice'):
            sale.invoice.paid_amount = paid_total
            sale.invoice.save(update_fields=['paid_amount'])
        ledger, _ = CreditLedger.objects.get_or_create(
            customer=sale.customer,
            sale=sale,
            defaults={'total_credit': sale.total_amount},
        )
        ledger.total_credit = sale.total_amount
        ledger.total_paid = paid_total
        ledger.update_balance()

    @staticmethod
    def resolve_financial_account(
        payment_method,
        account,
        tenant,
        allow_legacy_unassigned=False,
    ):
        if account:
            if (
                account.tenant_id is None
                and tenant is not None
                and allow_legacy_unassigned
            ):
                account.tenant = tenant
                account.save(update_fields=['tenant'])
            if account.tenant_id != getattr(tenant, 'pk', None):
                raise serializers.ValidationError({
                    'financial_account': 'Le compte financier doit appartenir à votre entreprise.',
                })
            return account
        account_type = 'cash' if payment_method == 'cash' else ('bank' if payment_method == 'bank_transfer' else 'other')
        account, _ = FinancialAccount.objects.get_or_create(
            tenant=tenant,
            name='Caisse principale' if account_type == 'cash' else f'Compte {account_type}',
            defaults={'account_type': account_type, 'currency': 'GNF'},
        )
        return account

    @staticmethod
    def sync_financial_transaction(payment, user):
        tenant = tenant_for_user(user) or payment.customer.tenant
        account = PaymentSerializer.resolve_financial_account(
            payment.payment_method,
            payment.financial_account,
            tenant,
            allow_legacy_unassigned=(
                user is not None and getattr(user, 'tenant_id', None) is None
            ),
        )
        if payment.financial_account_id != account.id:
            payment.financial_account = account
            payment.save(update_fields=['financial_account'])
        transaction_item, _ = FinancialTransaction.objects.get_or_create(
            origin=f'payment:{payment.id}',
            defaults={
                'transaction_type': 'payment', 'direction': 'in', 'amount': payment.amount,
                'currency': account.currency, 'account': account,
                'tenant': account.tenant,
                'category': 'Paiement client', 'description': f'Paiement {payment.reference or payment.id}',
                'status': 'validated', 'created_by': user, 'validated_by': user,
                'validated_at': payment.payment_date,
            },
        )
        if (
            transaction_item.amount != payment.amount
            or transaction_item.account_id != account.id
            or transaction_item.transaction_date != payment.payment_date
            or transaction_item.tenant_id != account.tenant_id
        ):
            transaction_item.amount = payment.amount
            transaction_item.account = account
            transaction_item.transaction_date = payment.payment_date
            transaction_item.tenant = account.tenant
            transaction_item.validated_at = payment.payment_date
            transaction_item.save(update_fields=[
                'amount', 'account', 'tenant', 'transaction_date', 'validated_at', 'updated_at',
            ])

    @staticmethod
    def _open_credit_sales(customer_id, *, lock=False, user=None):
        queryset = Sale.objects.filter(
            customer_id=customer_id,
            payment_method='credit',
            status='partial',
            total_amount__gt=F('amount_paid'),
        ).order_by('sale_date', 'id')
        if user is not None:
            queryset = tenant_scoped_queryset(queryset, user)
        if user and user.has_role('sales') and not user.has_role('admin') and not user.is_superuser:
            queryset = queryset.filter(seller=user)
        return queryset.select_for_update() if lock else queryset

    @classmethod
    def allocate_payment(cls, payment, sales):
        remaining = payment.amount
        touched = []
        for sale in sales:
            debt = max(sale.total_amount - sale.amount_paid, 0)
            if debt <= 0:
                continue
            allocated = min(remaining, debt)
            if allocated <= 0:
                break
            PaymentAllocation.objects.create(payment=payment, sale=sale, amount=allocated)
            remaining -= allocated
            touched.append(sale)
            if remaining == 0:
                break
        if remaining:
            raise serializers.ValidationError({
                'amount': 'Le montant du paiement dépasse la dette restante.',
            })
        for sale in touched:
            cls.sync_sale_payment(sale)
        return touched

    @staticmethod
    def notify_payment(payment, user=None):
        customer = payment.customer
        company = (
            Company.objects.filter(tenant_id=customer.tenant_id).first()
            if customer.tenant_id is not None
            else Company.objects.first()
        )
        currency = getattr(company, 'currency', 'GNF') or 'GNF'
        remaining = Sale.objects.filter(
            customer=customer,
            tenant_id=customer.tenant_id,
            payment_method='credit',
            status='partial',
            total_amount__gt=F('amount_paid'),
        ).aggregate(balance=Sum(F('total_amount') - F('amount_paid')))['balance'] or 0
        balance_text = (
            f'Votre solde restant est de {remaining:.2f} {currency}.'
            if remaining
            else 'Votre compte est maintenant entièrement soldé. Merci.'
        )
        message = (
            f'Bonjour {customer.full_name}, nous confirmons la réception de votre paiement '
            f'de {payment.amount:.2f} {currency}. {balance_text}'
        )
        Notification.objects.create(
            tenant_id=customer.tenant_id,
            sale=payment.sale,
            customer=customer,
            channel='internal',
            event_type='payment_received',
            status='sent',
            message=message,
            recipient_phone=customer.phone or '',
        )
        if customer.phone:
            Notification.objects.create(
                tenant_id=customer.tenant_id,
                sale=payment.sale,
                customer=customer,
                channel='whatsapp',
                event_type='payment_received',
                status='pending',
                message=message,
                recipient_phone=customer.phone,
            )

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None

        amount = validated_data.get('amount', 0)
        if amount <= 0:
            raise serializers.ValidationError({'amount': 'Le montant du paiement doit être strictement positif.'})

        customer = Customer.objects.select_for_update().get(pk=validated_data['customer'].pk)
        validated_data['customer'] = customer
        sale = validated_data.get('sale')
        if sale:
            sale = Sale.objects.select_for_update().get(pk=sale.pk)
            validated_data['sale'] = sale
            if customer.pk != sale.customer_id:
                raise serializers.ValidationError({'customer': 'Le client du paiement doit être celui de la vente.'})
            if (
                customer.tenant_id is not None
                and sale.tenant_id is not None
                and customer.tenant_id != sale.tenant_id
            ):
                raise serializers.ValidationError({
                    'sale': 'Le client et la vente doivent appartenir à la même entreprise.',
                })
            if (
                user
                and user.has_role('sales')
                and not user.has_role('admin')
                and not user.is_superuser
                and sale.seller_id != user.id
            ):
                raise serializers.ValidationError({
                    'sale': 'Un vendeur ne peut encaisser que ses propres ventes à crédit.',
                })
            if amount > max(sale.total_amount - sale.amount_paid, 0):
                raise serializers.ValidationError({'amount': 'Le paiement dépasse le solde restant de la vente.'})
            open_sales = [sale]
        else:
            open_sales = list(self._open_credit_sales(customer.id, lock=True, user=user))
            total_due = sum(
                (max(item.total_amount - item.amount_paid, 0) for item in open_sales),
                start=0,
            )
            if not open_sales:
                raise serializers.ValidationError({'customer': 'Ce client ne possède aucune créance ouverte.'})
            if amount > total_due:
                raise serializers.ValidationError({'amount': 'Le montant du paiement dépasse la dette restante.'})

        validated_data['created_by'] = user
        validated_data['reference'] = validated_data.get('reference') or (
            f'PAY-{timezone.localdate():%Y%m%d}-{uuid4().hex[:8].upper()}'
        )
        payment = Payment.objects.create(**validated_data)
        self.sync_financial_transaction(payment, user)
        self.allocate_payment(payment, open_sales)
        self.notify_payment(payment, user)

        AuditLog.objects.create(
            user=user,
            action='payment',
            model_name='Payment',
            record_id=payment.id,
            details=(
                f"Paiement enregistré : {payment.amount} "
                f"pour la vente {payment.sale_id or 'non associée'} "
                f"via {payment.get_payment_method_display()}"
            ),
        )
        return payment

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        payment = Payment.objects.select_for_update().get(pk=instance.pk)
        if 'customer' in validated_data and validated_data['customer'].pk != payment.customer_id:
            raise serializers.ValidationError({'customer': 'Le client d’un paiement enregistré ne peut pas être modifié.'})
        if 'sale' in validated_data and (
            validated_data['sale'].pk if validated_data['sale'] else None
        ) != payment.sale_id:
            raise serializers.ValidationError({'sale': 'La vente d’un paiement enregistré ne peut pas être modifiée.'})

        customer = Customer.objects.select_for_update().get(pk=payment.customer_id)
        payment_sales = Sale.objects.filter(
            Q(payment_allocations__payment=payment) | Q(pk=payment.sale_id),
        ).distinct()
        related_sales = list(
            tenant_scoped_queryset(
                Sale.objects.select_for_update().filter(pk__in=payment_sales.values('pk')),
                user,
            ).order_by('sale_date', 'id')
        )
        if len(related_sales) != payment_sales.count():
            raise serializers.ValidationError({
                'sale': 'Le paiement est lié à une vente hors de votre entreprise.',
            })
        PaymentAllocation.objects.filter(payment=payment).delete()
        for sale in related_sales:
            self.sync_sale_payment(sale)
        validated_data['customer'] = customer
        validated_data['sale'] = payment.sale
        new_amount = validated_data.get('amount', payment.amount)
        if new_amount <= 0:
            raise serializers.ValidationError({'amount': 'Le montant du paiement doit être strictement positif.'})
        if payment.sale_id:
            open_sale = tenant_scoped_queryset(
                Sale.objects.select_for_update(),
                user,
            ).filter(pk=payment.sale_id).first()
            if open_sale is None:
                raise serializers.ValidationError({
                    'sale': 'La vente du paiement ne fait pas partie de votre entreprise.',
                })
            open_sales = [open_sale]
        else:
            open_sales = list(self._open_credit_sales(customer.id, lock=True, user=user))
        total_due = sum(
            (max(item.total_amount - item.amount_paid, 0) for item in open_sales),
            start=0,
        )
        if not open_sales or new_amount > total_due:
            raise serializers.ValidationError({'amount': 'Le montant du paiement dépasse la dette restante.'})

        for field, value in validated_data.items():
            setattr(payment, field, value)
        payment.save()
        self.allocate_payment(payment, open_sales)
        self.sync_financial_transaction(payment, user)
        AuditLog.objects.create(
            user=user,
            action='update',
            model_name='Payment',
            record_id=payment.id,
            details=f'Paiement mis à jour : {payment.amount} pour le client {customer.full_name}.',
        )
        return payment


class CreditLedgerSerializer(serializers.ModelSerializer):
    remaining_balance = serializers.SerializerMethodField()

    class Meta:
        model = CreditLedger
        fields = ['id', 'customer', 'sale', 'total_credit', 'total_paid', 'balance', 'remaining_balance', 'updated_at']
        read_only_fields = ['id', 'balance', 'remaining_balance', 'updated_at']

    def get_remaining_balance(self, obj):
        return obj.remaining_balance
