from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.exceptions import PermissionDenied

from core.tenancy import tenant_for_user


PLATFORM_ADMIN_API_PREFIXES = (
    '/api/v1/platform/',
)
PLATFORM_ADMIN_AUTH_PATHS = {
    '/api/users/login/',
    '/api/users/logout/',
    '/api/users/me/',
    '/api/v1/users/login/',
    '/api/v1/users/logout/',
    '/api/v1/users/me/',
}


def _check_platform_admin_access(user, request):
    is_platform_admin = getattr(user, 'is_platform_admin', False)
    is_platform_path = (
        request.path in PLATFORM_ADMIN_AUTH_PATHS
        or request.path.startswith(PLATFORM_ADMIN_API_PREFIXES)
    )
    if is_platform_admin and not is_platform_path:
        raise PermissionDenied(
            'Les comptes de la plateforme ne peuvent pas consulter les API métier.'
        )
    if not is_platform_admin:
        tenant = tenant_for_user(user)
        if tenant is None or tenant.status_at() != 'active':
            raise PermissionDenied(
                'L’accès à cet espace est indisponible. Vérifiez son activation ou sa licence.',
            )


class PlatformAdminSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            _check_platform_admin_access(result[0], request)
        return result


class PlatformAdminBasicAuthentication(BasicAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            _check_platform_admin_access(result[0], request)
        return result
