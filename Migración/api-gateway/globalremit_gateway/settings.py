import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "globalremit-academic-local-key")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "ha_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "globalremit_gateway.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

WSGI_APPLICATION = "globalremit_gateway.wsgi.application"

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

GLOBALREMIT_DB = {
    "host": os.getenv("GLOBALREMIT_DB_HOST", "globalremit-patroni-haproxy"),
    "port": int(os.getenv("GLOBALREMIT_DB_PORT", "5432")),
    "dbname": os.getenv("GLOBALREMIT_DB_NAME", "globalremit"),
    "user": os.getenv("GLOBALREMIT_DB_USER", "gr_api_gateway"),
    "password": os.getenv("GLOBALREMIT_DB_PASSWORD", "ChangeMe_ApiGateway_2026!"),
}

GLOBALREMIT_PATRONI_NODES = [
    node.strip()
    for node in os.getenv(
        "GLOBALREMIT_PATRONI_NODES",
        "globalremit-patroni-pg1,globalremit-patroni-pg2,globalremit-patroni-pg3",
    ).split(",")
    if node.strip()
]

GLOBALREMIT_MONGO = {
    "nodes": [
        node.strip()
        for node in os.getenv(
            "GLOBALREMIT_MONGO_NODES",
            "globalremit-mongo1,globalremit-mongo2,globalremit-mongo3",
        ).split(",")
        if node.strip()
    ],
    "port": int(os.getenv("GLOBALREMIT_MONGO_PORT", "27017")),
    "user": os.getenv("GLOBALREMIT_MONGO_USER", "gr_mongo_analyst"),
    "password": os.getenv("GLOBALREMIT_MONGO_PASSWORD", "MongoAnalyst_2026!"),
    "auth_db": os.getenv("GLOBALREMIT_MONGO_AUTH_DB", "admin"),
    "replica_set": os.getenv("GLOBALREMIT_MONGO_REPLICA_SET", "rsGlobalRemit"),
    "database": os.getenv("GLOBALREMIT_MONGO_DATABASE", "globalremit_analytics"),
}



