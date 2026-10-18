from django.db.models import Q, Sum
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from core.tenancy import tenant_for_user, tenant_scoped_queryset
from users.permissions import IsTenantAssignedUser, role_permission
from .models import Customer
from .serializers import CustomerSerializer
from core.serializers import JsonResponseSerializer


class CustomerListCreateView(generics.ListCreateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('customers'),
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            Customer.objects.all(),
            self.request.user,
        )
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) |
                Q(phone__icontains=search) |
                Q(email__icontains=search) |
                Q(company_name__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for_user(self.request.user))


class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('customers'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(Customer.objects.all(), self.request.user)


class CustomerHistoryView(generics.GenericAPIView):
    queryset = Customer.objects.all()
    serializer_class = JsonResponseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('customers'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(Customer.objects.all(), self.request.user)


class CustomerSalesHistoryView(CustomerHistoryView):

    def get(self, request, pk):
        from sales.models import Sale

        customer = self.get_object()
        sales = Sale.objects.filter(customer=customer).values(
            'id', 'sale_date', 'status', 'total_amount', 'amount_paid',
        )
        return Response(list(sales), status=status.HTTP_200_OK)


class CustomerInvoicesHistoryView(CustomerHistoryView):

    def get(self, request, pk):
        from sales.models import Invoice

        customer = self.get_object()
        invoices = Invoice.objects.filter(sale__customer=customer).values(
            'id', 'invoice_number', 'qr_code', 'issue_date', 'total_amount', 'paid_amount',
        )
        return Response(list(invoices), status=status.HTTP_200_OK)


class CustomerPaymentsHistoryView(CustomerHistoryView):

    def get(self, request, pk):
        from payments.models import Payment

        customer = self.get_object()
        payments = Payment.objects.filter(customer=customer).values(
            'id', 'sale_id', 'amount', 'payment_method', 'reference', 'payment_date',
        )
        return Response(list(payments), status=status.HTTP_200_OK)


class CustomerCreditView(CustomerHistoryView):

    def get(self, request, pk):
        from payments.models import Payment
        from sales.models import Sale

        customer = self.get_object()
        sales_total = Sale.objects.filter(customer=customer).aggregate(total=Sum('total_amount'))['total'] or 0
        paid_total = Payment.objects.filter(customer=customer).aggregate(total=Sum('amount'))['total'] or 0
        return Response({
            'customer_id': customer.pk,
            'total_credit': float(sales_total),
            'total_paid': float(paid_total),
            'balance': float(sales_total - paid_total),
        }, status=status.HTTP_200_OK)
