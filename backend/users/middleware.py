from django.http import HttpResponseForbidden


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
