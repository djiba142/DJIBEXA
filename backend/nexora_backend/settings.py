"""Django settings for the NEXORA backend."""

import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def _get_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


DJANGO_ENV = os.getenv('DJANGO_ENV', 'development').strip().lower()
IS_PRODUCTION = DJANGO_ENV in {'production', 'prod'}
configured_secret_key = os.getenv('DJANGO_SECRET_KEY', '')
configured_hosts = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', '').split(',')
    if host.strip()
]

if IS_PRODUCTION:
    if (
        len(configured_secret_key) < 50
        or len(set(configured_secret_key)) < 5
        or configured_secret_key.startswith('django-insecure-')
    ):
        raise ImproperlyConfigured(
            'En production, DJANGO_SECRET_KEY doit être une clé secrète forte d’au moins 50 caractères.'
        )
    if not configured_hosts or '*' in configured_hosts:
        raise ImproperlyConfigured(
            'En production, DJANGO_ALLOWED_HOSTS doit définir explicitement les hôtes autorisés.'
        )

SECRET_KEY = configured_secret_key or 'django-insecure-nexora-dev-key-change-me'
DEBUG = _get_bool(os.getenv('DJANGO_DEBUG'), not IS_PRODUCTION)
if IS_PRODUCTION and DEBUG:
    raise ImproperlyConfigured('DJANGO_DEBUG doit être désactivé en production.')
ALLOWED_HOSTS = configured_hosts or ([] if IS_PRODUCTION else ['*'])

SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
COOKIE_SAMESITE = (
    'None'
    if _get_bool(os.getenv('DJANGO_CROSS_SITE_COOKIES'), False)
    else 'Lax'
)
SESSION_COOKIE_SAMESITE = COOKIE_SAMESITE
CSRF_COOKIE_SAMESITE = COOKIE_SAMESITE
SECURE_SSL_REDIRECT = _get_bool(
    os.getenv('DJANGO_SECURE_SSL_REDIRECT'),
    IS_PRODUCTION,
)
if IS_PRODUCTION and not SECURE_SSL_REDIRECT:
    raise ImproperlyConfigured(
        'En production, DJANGO_SECURE_SSL_REDIRECT doit être activé.'
    )
SECURE_HSTS_SECONDS = int(
    os.getenv('DJANGO_SECURE_HSTS_SECONDS', '31536000' if IS_PRODUCTION else '0')
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _get_bool(
    os.getenv('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS'),
    False,
)
SECURE_HSTS_PRELOAD = _get_bool(os.getenv('DJANGO_SECURE_HSTS_PRELOAD'), False)
if IS_PRODUCTION and _get_bool(os.getenv('DJANGO_TRUST_X_FORWARDED_PROTO'), False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'corsheaders',
    'core',
    'users',
    'products',
    'suppliers',
    'customers',
    'inventory',
    'purchases',
    'sales',
    'invoices',
    'payments',
    'notifications',
    'expenses',
    'documents',
    'finance',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'users.middleware.PasswordChangeRequiredMiddleware',
    'users.middleware.PlatformAdminDjangoAdminIsolationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'nexora_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'nexora_backend.wsgi.application'
TEST_RUNNER = 'nexora_backend.test_runner.NexoraTestRunner'

DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite').lower()
if IS_PRODUCTION and DB_ENGINE not in {'postgres', 'postgresql'}:
    raise ImproperlyConfigured(
        'En production, DB_ENGINE doit être configuré sur postgresql.'
    )

if DB_ENGINE in {'postgres', 'postgresql'}:
    database_url = os.getenv('DATABASE_URL', '').strip()
    if database_url:
        try:
            parsed_database_url = urlsplit(database_url)
            database_port = parsed_database_url.port or 5432
        except ValueError as error:
            raise ImproperlyConfigured(
                'DATABASE_URL contient un hôte ou un port PostgreSQL invalide.'
            ) from error
        database_name = unquote(parsed_database_url.path.lstrip('/'))
        if (
            parsed_database_url.scheme not in {'postgres', 'postgresql'}
            or not parsed_database_url.hostname
            or not database_name
        ):
            raise ImproperlyConfigured(
                'DATABASE_URL doit être une URL PostgreSQL valide avec hôte et nom de base.'
            )
        database_options = {}
        sslmode = parse_qs(parsed_database_url.query).get('sslmode', [])
        if sslmode:
            database_options['sslmode'] = sslmode[-1]
        postgres_database = {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': database_name,
            'USER': unquote(parsed_database_url.username or ''),
            'PASSWORD': unquote(parsed_database_url.password or ''),
            'HOST': parsed_database_url.hostname,
            'PORT': str(database_port),
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
        }
        if database_options:
            postgres_database['OPTIONS'] = database_options
    else:
        postgres_database = {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'db_nexora'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '5432'),
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
        }
    DATABASES = {'default': postgres_database}
elif DB_ENGINE == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'db_gestion'),
            'USER': os.getenv('DB_USER', 'root'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
elif DB_ENGINE == 'sqlite':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv('DB_NAME', str(BASE_DIR / 'db.sqlite3')),
        }
    }
else:
    raise ImproperlyConfigured(
        'DB_ENGINE doit être sqlite, mysql ou postgresql.'
    )

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG
    else 'django.core.mail.backends.smtp.EmailBackend',
)
if IS_PRODUCTION and EMAIL_BACKEND in {
    'django.core.mail.backends.console.EmailBackend',
    'django.core.mail.backends.locmem.EmailBackend',
}:
    raise ImproperlyConfigured(
        'En production, EMAIL_BACKEND doit permettre un véritable envoi d’e-mail.'
    )
EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = _get_bool(os.getenv('EMAIL_USE_TLS'))
EMAIL_USE_SSL = _get_bool(os.getenv('EMAIL_USE_SSL'))
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@example.invalid')
frontend_base_url = os.getenv('FRONTEND_BASE_URL', '').strip()
if IS_PRODUCTION:
    try:
        frontend_url = urlsplit(frontend_base_url)
        frontend_url.port
        frontend_url_is_valid = (
            frontend_url.scheme == 'https'
            and frontend_url.hostname is not None
            and not frontend_url.username
            and not frontend_url.password
            and not frontend_url.query
            and not frontend_url.fragment
        )
    except ValueError:
        frontend_url_is_valid = False
    if not frontend_url_is_valid:
        raise ImproperlyConfigured(
            'En production, FRONTEND_BASE_URL doit définir une URL HTTPS valide.'
        )
FRONTEND_BASE_URL = (
    frontend_base_url or 'http://localhost:3000'
).rstrip('/')

LANGUAGE_CODE = 'fr'
LANGUAGES = [
    ('fr', 'Français'),
    ('en', 'English'),
    ('ar', 'العربية'),
    ('zh', '中文'),
]
TIME_ZONE = 'Africa/Conakry'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', BASE_DIR / 'media'))
PRIVATE_INVOICE_ROOT = Path(os.getenv('PRIVATE_INVOICE_ROOT', BASE_DIR / 'private_invoices'))
PRIVATE_STOREFRONT_ROOT = Path(os.getenv('PRIVATE_STOREFRONT_ROOT', BASE_DIR / 'private_storefronts'))
PRIVATE_SUPPLIER_IMPORT_ROOT = Path(
    os.getenv('PRIVATE_SUPPLIER_IMPORT_ROOT', BASE_DIR / 'private_supplier_imports'),
)
INVOICE_COMPANY_NAME = os.getenv('INVOICE_COMPANY_NAME', 'KOUROUMA AUTO PARTS')
INVOICE_COMPANY_ACTIVITY = os.getenv(
    'INVOICE_COMPANY_ACTIVITY',
    'VENDEUR DE PIÈCES DE VOITURE ET DES ROULEMENTS',
)
INVOICE_COMPANY_DISTRIBUTOR = os.getenv(
    'INVOICE_COMPANY_DISTRIBUTOR',
    '',
)
INVOICE_COMPANY_ADDRESS = os.getenv(
    'INVOICE_COMPANY_ADDRESS',
    '',
)
INVOICE_COMPANY_PHONE = os.getenv(
    'INVOICE_COMPANY_PHONE',
    '',
)
INVOICE_COMPANY_EMAIL = os.getenv('INVOICE_COMPANY_EMAIL', '')
INVOICE_COMPANY_RCCM = os.getenv('INVOICE_COMPANY_RCCM', '')
INVOICE_COMPANY_NIF = os.getenv('INVOICE_COMPANY_NIF', '')
INVOICE_WATERMARK_PATH = os.getenv('INVOICE_WATERMARK_PATH', '')
PDF_SIGNING_PKCS12_PATH = os.getenv('PDF_SIGNING_PKCS12_PATH', '')
PDF_SIGNING_PKCS12_PASSPHRASE = os.getenv('PDF_SIGNING_PKCS12_PASSPHRASE', '')
PDF_SIGNING_TRUST_ROOT_PATH = os.getenv('PDF_SIGNING_TRUST_ROOT_PATH', '')
PDF_TSA_URL = os.getenv('PDF_TSA_URL', '')
PDF_SIGNING_REVOCATION_MODE = os.getenv('PDF_SIGNING_REVOCATION_MODE', 'hard-fail')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'users.User'

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'users.authentication.PlatformAdminSessionAuthentication',
        'users.authentication.PlatformAdminBasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.VersionedApiPagination',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'DJIBEXA API',
    'DESCRIPTION': 'API de gestion commerciale, stocks, achats et ventes.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

ROLE_PERMISSIONS = {
    'admin': {'all'},
    'stock': {
        'products',
        'inventory',
        'purchases',
        'notifications',
        'cartons.view',
        'cartons.manage',
    },
    'sales': {'products', 'customers', 'sales', 'payments', 'notifications'},
}

def _get_origins(environment_variable, defaults):
    custom = os.getenv(environment_variable)
    if custom:
        return [origin.strip() for origin in custom.split(',') if origin.strip()]
    return defaults


CSRF_TRUSTED_ORIGINS = _get_origins('CSRF_TRUSTED_ORIGINS', [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:5500',
    'http://127.0.0.1:5500',
])

CORS_ALLOWED_ORIGINS = _get_origins('CORS_ALLOWED_ORIGINS', [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:5500',
    'http://127.0.0.1:5500',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
])
CORS_ALLOW_ALL_ORIGINS = _get_bool(os.getenv('CORS_ALLOW_ALL_ORIGINS'), False)
if IS_PRODUCTION:
    if CORS_ALLOW_ALL_ORIGINS:
        raise ImproperlyConfigured(
            'CORS_ALLOW_ALL_ORIGINS ne peut pas être activé en production.'
        )
    for setting_name, origins in (
        ('CSRF_TRUSTED_ORIGINS', CSRF_TRUSTED_ORIGINS),
        ('CORS_ALLOWED_ORIGINS', CORS_ALLOWED_ORIGINS),
    ):
        if not origins:
            raise ImproperlyConfigured(
                f'En production, {setting_name} doit définir les origines HTTPS autorisées.'
            )
        for origin in origins:
            try:
                parsed_origin = urlsplit(origin)
                parsed_origin.port
                origin_is_valid = (
                    parsed_origin.scheme == 'https'
                    and bool(parsed_origin.hostname)
                    and not parsed_origin.username
                    and not parsed_origin.password
                    and parsed_origin.path in {'', '/'}
                    and not parsed_origin.query
                    and not parsed_origin.fragment
                    and '*' not in parsed_origin.hostname
                    and parsed_origin.hostname not in {'localhost', '127.0.0.1', '::1'}
                )
            except ValueError:
                origin_is_valid = False
            if not origin_is_valid:
                raise ImproperlyConfigured(
                    f'Chaque valeur de {setting_name} doit être une origine HTTPS exacte.'
                )
    parsed_frontend_url = urlsplit(FRONTEND_BASE_URL)
    frontend_origin = (
        f'{parsed_frontend_url.scheme}://{parsed_frontend_url.netloc}'
    )
    if frontend_origin not in CORS_ALLOWED_ORIGINS or frontend_origin not in CSRF_TRUSTED_ORIGINS:
        raise ImproperlyConfigured(
            'FRONTEND_BASE_URL doit aussi figurer dans CORS_ALLOWED_ORIGINS et CSRF_TRUSTED_ORIGINS.'
        )
CORS_ALLOW_CREDENTIALS = True

INVOICE_VERIFICATION_BASE_URL = os.getenv(
    'INVOICE_VERIFICATION_BASE_URL',
    f'{FRONTEND_BASE_URL}/verifier/',
)
