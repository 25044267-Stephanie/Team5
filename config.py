import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing from the environment."""


def _require(name):
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill in real values."
        )
    return value


def _mysql_uri(database):
    host = _require("MYSQL_HOST")
    port = os.environ.get("MYSQL_PORT", "3306")
    user = quote_plus(_require("MYSQL_USER"))
    password = quote_plus(_require("MYSQL_PASSWORD"))
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"


def _engine_options():
    """Pool settings plus optional TLS for Amazon RDS."""
    options = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }
    ssl_ca = os.environ.get("MYSQL_SSL_CA", "").strip()
    ssl_required = os.environ.get("MYSQL_SSL_REQUIRED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if ssl_ca:
        options["connect_args"] = {"ssl": {"ca": ssl_ca}}
    elif ssl_required:
        # Require TLS without a pinned CA path (download RDS CA when hardening further).
        options["connect_args"] = {"ssl": True}
    return options


class Config:
    SECRET_KEY = _require("FLASK_SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _mysql_uri(_require("MYSQL_DATABASE"))
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options()
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = _mysql_uri(_require("MYSQL_TEST_DATABASE"))
    TESTING = True
