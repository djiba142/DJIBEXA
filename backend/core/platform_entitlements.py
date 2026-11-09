from django.utils import timezone

from .tenancy import tenant_for_user


MODULE_PATH_PREFIXES = (
    ('/api/v1/sales/', 'sales'),
    ('/api/sales/', 'sales'),
    ('/api/v1/products/', 'products'),
    ('/api/products/', 'products'),
    ('/api/v1/inventory/', 'inventory'),
    ('/api/inventory/', 'inventory'),
    ('/api/v1/locations/', 'inventory'),
    ('/api/locations/', 'inventory'),
    ('/api/v1/cartons/', 'inventory'),
    ('/api/cartons/', 'inventory'),
    ('/api/v1/stock-movements/', 'inventory'),
    ('/api/stock-movements/', 'inventory'),
    ('/api/v1/transfers/', 'inventory'),
    ('/api/transfers/', 'inventory'),
    ('/api/v1/units/', 'inventory'),
    ('/api/units/', 'inventory'),
    ('/api/v1/receipts/', 'purchases'),
    ('/api/receipts/', 'purchases'),
    ('/api/v1/acquisition-costs/', 'purchases'),
    ('/api/acquisition-costs/', 'purchases'),
    ('/api/v1/quarantines/', 'purchases'),
    ('/api/quarantines/', 'purchases'),
    ('/api/v1/purchase-orders/', 'purchases'),
    ('/api/purchase-orders/', 'purchases'),
    ('/api/v1/purchase-imports/', 'purchases'),
    ('/api/purchase-imports/', 'purchases'),
    ('/api/v1/purchases/', 'purchases'),
    ('/api/purchases/', 'purchases'),
    ('/api/v1/external-purchases/', 'purchases'),
    ('/api/external-purchases/', 'purchases'),
    ('/api/v1/external-payments/', 'purchases'),
    ('/api/external-payments/', 'purchases'),
    ('/api/v1/external-sales/', 'purchases'),
    ('/api/external-sales/', 'purchases'),
    ('/api/v1/suppliers/', 'purchases'),
    ('/api/suppliers/', 'purchases'),
    ('/api/v1/customers/', 'customers'),
    ('/api/customers/', 'customers'),
    ('/api/v1/partners/', 'partners'),
    ('/api/partners/', 'partners'),
    ('/api/v1/credits/', 'finance'),
    ('/api/credits/', 'finance'),
    ('/api/v1/finance/', 'finance'),
    ('/api/finance/', 'finance'),
    ('/api/v1/cash/', 'finance'),
    ('/api/cash/', 'finance'),
    ('/api/v1/cashflow/', 'finance'),
    ('/api/cashflow/', 'finance'),
    ('/api/v1/financial-summary/', 'finance'),
    ('/api/financial-summary/', 'finance'),
    ('/api/v1/payments/', 'finance'),
    ('/api/payments/', 'finance'),
    ('/api/v1/expenses/', 'finance'),
    ('/api/expenses/', 'finance'),
    ('/api/v1/invoices/', 'finance'),
    ('/api/invoices/', 'finance'),
    ('/api/v1/documents/', 'finance'),
    ('/api/documents/', 'finance'),
    ('/api/v1/reports/', 'reports'),
    ('/api/reports/', 'reports'),
    ('/api/v1/notifications/', 'notifications'),
    ('/api/notifications/', 'notifications'),
    ('/api/v1/messages/', 'notifications'),
    ('/api/messages/', 'notifications'),
    ('/api/v1/storefront/', 'storefront'),
    ('/api/storefront/', 'storefront'),
    ('/api/v1/users/', 'users'),
    ('/api/users/', 'users'),
)

AUTH_USER_PATHS = (
    '/csrf/',
    '/change-password/',
    '/login/',
    '/logout/',
    '/me/',
)


def module_for_request_path(path):
    if path.startswith(('/api/v1/users/', '/api/users/')) and path.endswith(AUTH_USER_PATHS):
        return None
    for prefix, module_code in MODULE_PATH_PREFIXES:
        if path.startswith(prefix):
            return module_code
    if path.startswith(('/api/v1/dashboard/', '/api/dashboard/')):
        return 'dashboard'
    return None


def evaluate_tenant_module(tenant, module_code, now=None, checked=None):
    now = now or timezone.now()
    checked = checked or set()
    if tenant is None:
        return {
            'technicalAvailable': False,
            'inherited': False,
            'override': None,
            'enabled': False,
            'reason': 'tenant_missing',
            'validUntil': None,
        }
    if module_code in checked:
        return {
            'technicalAvailable': False,
            'inherited': False,
            'override': None,
            'enabled': False,
            'reason': 'dependency_cycle',
            'validUntil': None,
        }

    from .models import PlatformModule

    module = PlatformModule.objects.filter(code=module_code).first()
    if module is None:
        return {
            'technicalAvailable': False,
            'inherited': False,
            'override': None,
            'enabled': False,
            'reason': 'feature_not_found',
            'validUntil': None,
        }

    technical_available = (
        module.is_active and module.technical_status == 'available'
    )
    if not technical_available:
        return {
            'technicalAvailable': False,
            'inherited': False,
            'override': None,
            'enabled': False,
            'reason': 'feature_unavailable',
            'validUntil': None,
        }

    if tenant.status_at(now) != 'active':
        return {
            'technicalAvailable': True,
            'inherited': False,
            'override': None,
            'enabled': False,
            'reason': f'tenant_{tenant.status_at(now)}',
            'validUntil': tenant.trial_ends_at,
        }

    override = tenant.module_overrides.filter(module=module).first()
    override_is_current = bool(
        override
        and (override.starts_at is None or override.starts_at <= now)
        and (override.ends_at is None or override.ends_at > now)
    )
    override_effect = (
        override.status
        if override_is_current
        else None
    )

    subscription = tenant.subscriptions.order_by('-created_at', '-id').first()
    if subscription is not None:
        subscription_is_current = (
            subscription.status == 'active'
            and subscription.ends_at is not None
            and subscription.ends_at > now
        )
        snapshot = subscription.feature_snapshot or {}
        if module_code in snapshot:
            snapshot_feature = snapshot[module_code]
            inherited = bool(
                subscription_is_current
                and snapshot_feature.get('enabled', False)
            )
        else:
            inherited = bool(
                subscription_is_current
                and module_code in subscription.included_modules
            )
        valid_until = subscription.ends_at
    elif tenant.enabled_modules:
        inherited = module_code in tenant.enabled_modules
        valid_until = tenant.trial_ends_at
    else:
        # Preserve access for legacy tenants until an explicit entitlement exists.
        inherited = True
        valid_until = tenant.trial_ends_at

    if override_effect == 'enabled':
        granted = True
        reason = 'tenant_override_enabled'
    elif override_effect in {'disabled', 'suspended'}:
        granted = False
        reason = f'tenant_override_{override_effect}'
    else:
        granted = inherited
        reason = 'plan_entitlement' if subscription else 'legacy_entitlement'

    if not granted:
        return {
            'technicalAvailable': True,
            'inherited': inherited,
            'override': override_effect or 'inherit',
            'enabled': False,
            'reason': reason,
            'validUntil': (
                override.ends_at
                if override_effect and override and override.ends_at
                else valid_until
            ),
        }

    checked = checked | {module_code}
    for dependency in module.dependencies:
        dependency_result = evaluate_tenant_module(
            tenant,
            dependency,
            now=now,
            checked=checked,
        )
        if not dependency_result['enabled']:
            return {
                'technicalAvailable': True,
                'inherited': inherited,
                'override': override_effect or 'inherit',
                'enabled': False,
                'reason': f'dependency_unavailable:{dependency}',
                'validUntil': valid_until,
            }

    return {
        'technicalAvailable': True,
        'inherited': inherited,
        'override': override_effect or 'inherit',
        'enabled': True,
        'reason': reason,
        'validUntil': (
            override.ends_at
            if override_effect and override and override.ends_at
            else valid_until
        ),
    }


def tenant_module_is_enabled(tenant, module_code, checked=None):
    return evaluate_tenant_module(
        tenant,
        module_code,
        checked=checked,
    )['enabled']


def user_has_required_module(user, path):
    module_code = module_for_request_path(path)
    if module_code is None:
        return True
    tenant = tenant_for_user(user)
    return tenant_module_is_enabled(tenant, module_code)


def add_calendar_months(value, months):
    month_offset = value.month - 1 + months
    year = value.year + month_offset // 12
    month = month_offset % 12 + 1
    import calendar

    return value.replace(
        year=year,
        month=month,
        day=min(value.day, calendar.monthrange(year, month)[1]),
    )
