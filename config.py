import os

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
    user = _require("MYSQL_USER")
    password = _require("MYSQL_PASSWORD")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"


class Config:
    SECRET_KEY = _require("FLASK_SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _mysql_uri(_require("MYSQL_DATABASE"))
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = _mysql_uri(_require("MYSQL_TEST_DATABASE"))
    TESTING = True
