"""
Configurações do Agendu - agenda, clientes, caixa e estoque para estética.

Valores sensíveis vêm de variáveis de ambiente. Em desenvolvimento os padrões
abaixo já funcionam com SQLite; em produção ficam em /etc/agendu/env.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(nome, padrao=False):
    return os.environ.get(nome, str(padrao)).lower() in ("1", "true", "sim", "yes")


CHAVE_DE_DESENVOLVIMENTO = "dev-inseguro-troque-em-producao-agendu"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", CHAVE_DE_DESENVOLVIMENTO)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

if not DEBUG and SECRET_KEY == CHAVE_DE_DESENVOLVIMENTO:
    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY antes de rodar com DJANGO_DEBUG=false.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Apps do projeto
    "core",
    "clientes",
    "agenda",
    "estoque",
    "financeiro",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.LoginObrigatorioMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Banco: SQLite em desenvolvimento; PostgreSQL quando DB_NAME estiver definido.
if os.environ.get("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("DJANGO_SQLITE", BASE_DIR / "db.sqlite3"),
        }
    }

# Cache em arquivo: guarda as tentativas de login (vale para os 3 processos do gunicorn).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.environ.get("DJANGO_CACHE_DIR", str(BASE_DIR / ".cache")),
    }
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "painel"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.environ.get("DJANGO_STATIC_ROOT", BASE_DIR / "staticfiles"))

# Fotos dos clientes: pasta PRIVADA. Nunca é servida pelo nginx; só sai por uma
# view que exige login (dados de saúde e imagem: LGPD).
PRIVADO_ROOT = Path(os.environ.get("DJANGO_PRIVADO_ROOT", BASE_DIR / "privado"))
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 40 * 1024 * 1024  # várias fotos de uma vez
FOTO_TAMANHO_MAXIMO = 2000  # px do lado maior; foto de celular é reduzida ao salvar

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Produção (HTTPS atrás do nginx)
# ---------------------------------------------------------------------------
ATRAS_DE_PROXY = env_bool("DJANGO_ATRAS_DE_PROXY", False)
if ATRAS_DE_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SEGUNDOS", "3600"))
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_HTTPONLY = True

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 dias logado no mesmo aparelho

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simples": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simples"}},
    "root": {"handlers": ["console"], "level": "INFO" if not DEBUG else "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

# Login: bloqueia 15 minutos depois de 5 senhas erradas seguidas do mesmo IP.
LOGIN_MAX_TENTATIVAS = int(os.environ.get("LOGIN_MAX_TENTATIVAS", "5"))
LOGIN_BLOQUEIO_SEGUNDOS = int(os.environ.get("LOGIN_BLOQUEIO_SEGUNDOS", str(15 * 60)))

# E-mail (opcional: "esqueci minha senha"). Sem EMAIL_HOST, aparece só no terminal.
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
    EMAIL_TIMEOUT = 15
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Agendu <nao-responda@ativix.co>")
