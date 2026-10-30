from django.http import HttpResponseForbidden
from django.http import JsonResponse


class PasswordChangeRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            user
            and user.is_authenticated
            and getattr(user, 'must_change_password', False)
            and request.path.startswith('/api/')
        ):
            allowed_methods = {
                '/api/users/csrf/': {'GET'},
                '/api/v1/users/csrf/': {'GET'},
                '/api/users/me/': {'GET'},
                '/api/v1/users/me/': {'GET'},
                '/api/users/change-password/': {'POST'},
                '/api/v1/users/change-password/': {'POST'},
                '/api/users/logout/': {'POST'},
                '/api/v1/users/logout/': {'POST'},
            }
            if request.method not in allowed_methods.get(request.path, set()):
                return JsonResponse(
                    {
                        'detail': 'Vous devez modifier votre mot de passe avant de continuer.',
                        'code': 'password_change_required',
                    },
                    status=403,
                )
        return self.get_response(request)


class PlatformAdminDjangoAdminIsolationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            user
            and user.is_authenticated
            and getattr(user, 'is_platform_admin', False)
            and (
                request.path == '/admin'
                or request.path.startswith('/admin/')
                or request.path.startswith('/media/')
            )
        ):
            return HttpResponseForbidden(
                'Cette ressource n’est pas accessible depuis un compte de plateforme.'
            )
        return self.get_response(request)
