from django.conf import settings

from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.tenancy import tenant_for_user


class IsAdminUser(BasePermission):
    """Autorise uniquement les administrateurs à accéder à certaines ressources."""

    message = 'Accès réservé aux administrateurs.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (
                request.user.has_role('admin')
                or getattr(request.user, 'is_superuser', False)
            )
        )


class IsTenantAdminUser(IsAdminUser):
    """Restricts tenant user management to an assigned, non-platform admin."""

    message = 'La gestion des utilisateurs nécessite un administrateur rattaché à une entreprise.'

    def has_permission(self, request, view):
        return bool(
            super().has_permission(request, view)
            and request.user.tenant_id is not None
            and not request.user.is_platform_admin
        )


class IsTenantAssignedUser(BasePermission):
    """Rejects business access when a user has no unambiguous tenant context."""

    message = 'Votre compte doit être rattaché à un espace d’entreprise.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and not request.user.is_platform_admin
            and tenant_for_user(request.user) is not None
        )


class IsPlatformAdmin(BasePermission):
    """Restricts platform-control endpoints to explicitly designated accounts."""

    message = 'Accès réservé à l’administration centrale DJIBEXA.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_platform_admin
        )


class CartonAccessPermission(BasePermission):
    """Separates carton consultation from operational carton management."""

    message = 'Cette opération sur les cartons n’est pas autorisée pour votre rôle.'

    def has_permission(self, request, view):
        permission = 'cartons.view' if request.method in SAFE_METHODS else 'cartons.manage'
        return role_permission(permission)().has_permission(request, view)


class SensitiveMutationPermission(BasePermission):
    """Réserve les modifications sensibles aux administrateurs."""

    message = 'Cette opération sensible est réservée aux administrateurs.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True
        return request.user.has_role('admin')


class StockOperationsMutationPermission(BasePermission):
    """Allows stock staff to manage operational stock resources, but not approvals."""

    message = 'Cette opération est réservée à la gestion du stock ou à l’administration.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            getattr(request.user, 'is_superuser', False)
            or request.user.has_any_role('admin', 'stock')
        )


class InventoryLocationPermission(BasePermission):
    """Only administrators may create or reclassify sales shops."""

    message = 'Seul un administrateur peut créer une boutique ou convertir un emplacement en boutique.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS or not request.user or not request.user.is_authenticated:
            return True
        location_type = request.data.get('location_type')
        is_admin = (
            request.user.has_role('admin')
            or getattr(request.user, 'is_superuser', False)
        )
        if location_type == 'shop' and not is_admin:
            return False
        return True


class ProductCatalogPermission(BasePermission):
    """Limits catalogue writes to management while allowing operational reads."""

    message = 'Seuls un gestionnaire ou un administrateur peuvent modifier le catalogue.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if tenant_for_user(request.user) is None:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True
        if request.method in SAFE_METHODS:
            return request.user.has_any_role('admin', 'sales', 'stock')
        return request.user.has_any_role('admin', 'stock')


class PurchaseOrderAccessPermission(BasePermission):
    """Stock staff may prepare and submit their own drafts and inspect permitted orders."""

    message = 'La gestion des commandes fournisseurs est réservée à la gestion.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True
        if request.user.has_role('admin'):
            return True
        if not request.user.has_role('stock'):
            return False
        action = getattr(view, 'action', None) or getattr(view, 'kwargs', {}).get('action')
        return request.method in SAFE_METHODS or (
            request.method == 'POST' and action is None
        ) or (
            request.method in {'PATCH', 'PUT'} and action is None
        ) or (
            request.method == 'POST' and action in {'send', 'email'}
        )

    def has_object_permission(self, request, view, obj):
        if request.user.has_role('admin') or not request.user.has_role('stock'):
            return True
        if request.method in SAFE_METHODS:
            return True
        action = getattr(view, 'action', None) or getattr(view, 'kwargs', {}).get('action')
        if action in {'send', 'email'}:
            return obj.status == 'draft' and obj.created_by_id == request.user.id
        return (
            request.method in {'PATCH', 'PUT'}
            and obj.status == 'draft'
            and obj.created_by_id == request.user.id
        )


class SupplierWorkflowPermission(BasePermission):
    """Stock staff may read suppliers and import documents, but not administer suppliers or rates."""

    message = 'Cette opération fournisseur n’est pas autorisée pour votre rôle.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False) or request.user.has_role('admin'):
            return True
        if not request.user.has_role('stock'):
            return False
        view_name = view.__class__.__name__
        if view_name == 'SupplierImportDocumentView':
            return request.method == 'GET'
        if view_name in {'SupplierListCreateView', 'SupplierDetailView'}:
            return request.method in SAFE_METHODS
        if view_name in {'SupplierImportView', 'SupplierImportConfirmView', 'SupplierImportRowMatchView'}:
            return request.method == 'POST'
        return view_name == 'SupplierImportRowCorrectionView' and request.method == 'PATCH'


class SalesReportAccessPermission(BasePermission):
    """Allow sales staff to access sales reports while retaining core report access."""

    message = 'Accès non autorisé à ce rapport.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True

        if request.user.has_role('admin'):
            return True

        allowed_modules = {
            module
            for role in request.user.roles
            for module in settings.ROLE_PERMISSIONS.get(role, set())
        }
        return 'all' in allowed_modules or 'sales' in allowed_modules


class DashboardOverviewAccessPermission(BasePermission):
    """Dashboard summaries are scoped by role in the corresponding view."""

    message = 'Accès non autorisé au tableau de bord.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True
        return request.user.has_any_role('admin', 'sales', 'stock')


class PurchaseReceiptAccessPermission(BasePermission):
    """Stock staff can draft receipts; only administrators can validate them."""

    message = 'Cette opération de réception n’est pas autorisée pour votre rôle.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False):
            return True
        if request.user.has_role('admin'):
            return True
        if not request.user.has_role('stock'):
            return False
        return request.method in SAFE_METHODS or request.method in {'POST', 'PATCH', 'PUT'}

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if obj.status != 'draft' or request.method == 'DELETE':
            return False
        return request.user.has_any_role('admin', 'stock')


class StockMovementAccessPermission(BasePermission):
    """Stock history is readable by operations roles; direct adjustments are managerial."""

    message = 'La création directe de mouvements de stock est réservée à la gestion.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False) or request.user.has_role('admin'):
            return True
        return request.user.has_role('stock') and request.method in SAFE_METHODS


class StockTransferAccessPermission(BasePermission):
    """Stock staff can request, ship and receive only approved transfers."""

    message = 'Cette étape du transfert n’est pas autorisée pour votre rôle.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False) or request.user.has_role('admin'):
            return True
        if not request.user.has_role('stock'):
            return False
        if request.method in SAFE_METHODS or (
            request.method == 'POST' and not getattr(view, 'kwargs', {}).get('action')
        ):
            return True
        return request.method == 'POST' and getattr(view, 'kwargs', {}).get('action') in {'ship', 'receive'}


class StockReplenishmentRequestAccessPermission(BasePermission):
    """Sales staff may request stock; only stock managers and admins may review."""

    message = 'Cette opération de ravitaillement n’est pas autorisée pour votre rôle.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False) or request.user.has_role('admin'):
            return True
        action = getattr(view, 'kwargs', {}).get('action')
        if action in {'accept', 'reject'}:
            return request.user.has_role('stock') and request.method == 'POST'
        if request.method in SAFE_METHODS:
            return request.user.has_any_role('sales', 'stock')
        return request.method == 'POST' and request.user.has_any_role('sales', 'stock')

    def has_object_permission(self, request, view, obj):
        if getattr(request.user, 'is_superuser', False) or request.user.has_role('admin'):
            return True
        action = getattr(view, 'kwargs', {}).get('action')
        if request.user.has_role('stock') and action in {'accept', 'reject'}:
            from inventory.access import accessible_locations

            return accessible_locations(request.user).filter(pk=obj.shop_id).exists()
        if request.user.has_role('sales'):
            return request.method in SAFE_METHODS and obj.requested_by_id == request.user.id
        if request.user.has_role('stock'):
            from inventory.access import accessible_locations

            return accessible_locations(request.user).filter(pk=obj.shop_id).exists()
        return False


class InventoryCountAccessPermission(BasePermission):
    """Stock staff can prepare and edit their draft counts, never apply differences."""

    message = 'Cette opération d’inventaire n’est pas autorisée pour votre rôle.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_superuser', False) or request.user.has_role('admin'):
            return True
        if not request.user.has_role('stock'):
            return False
        if request.method in SAFE_METHODS or request.method == 'POST' and getattr(view, 'action', None) == 'submit':
            return True
        return request.method in {'POST', 'PATCH', 'PUT'} and getattr(view, 'action', None) is None

    def has_object_permission(self, request, view, obj):
        if request.user.has_role('admin') or not request.user.has_role('stock'):
            return True
        if request.method in SAFE_METHODS:
            return True
        if getattr(view, 'action', None) == 'submit':
            return obj.status == 'draft' and obj.created_by_id == request.user.id
        return (
            request.method in {'PATCH', 'PUT'}
            and obj.status == 'draft'
            and obj.created_by_id == request.user.id
        )


def role_permission(module_name):
    """Factory de permission par rôle métier."""

    class RolePermission(BasePermission):
        message = 'Accès non autorisé pour votre rôle.'

        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False

            if getattr(request.user, 'is_superuser', False):
                return True

            if request.user.has_role('admin'):
                return True
            if (
                request.user.has_role('stock')
                and module_name == 'notifications'
                and not request.user.has_role('sales')
            ):
                return request.method in SAFE_METHODS

            allowed_modules = {
                module
                for role in request.user.roles
                for module in settings.ROLE_PERMISSIONS.get(role, set())
            }
            return 'all' in allowed_modules or module_name in allowed_modules

    return RolePermission
