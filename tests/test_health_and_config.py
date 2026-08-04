"""Focused health + config tests (MySQL test DB only via conftest)."""

from urllib.parse import quote_plus

import pytest

import app as hotel_app
from config import ConfigError, _engine_options, _mysql_uri


def test_healthz_ok_when_database_up(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["database"] == "up"


def test_healthz_unauthenticated(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert "password" not in response.get_data(as_text=True).lower()


def test_mysql_uri_url_encodes_special_password(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_USER", "hotel_app")
    monkeypatch.setenv("MYSQL_PASSWORD", "p@ss:word/1")
    uri = _mysql_uri("hotel_management_test")
    assert quote_plus("p@ss:word/1") in uri
    assert "p@ss:word/1" not in uri


def test_engine_options_enable_ssl_when_required(monkeypatch):
    monkeypatch.delenv("MYSQL_SSL_CA", raising=False)
    monkeypatch.setenv("MYSQL_SSL_REQUIRED", "true")
    options = _engine_options()
    assert options["pool_pre_ping"] is True
    assert options["connect_args"]["ssl"] is True


def test_engine_options_use_ca_file_when_set(monkeypatch):
    monkeypatch.setenv("MYSQL_SSL_CA", "/tmp/rds-ca.pem")
    monkeypatch.setenv("MYSQL_SSL_REQUIRED", "false")
    options = _engine_options()
    assert options["connect_args"]["ssl"]["ca"] == "/tmp/rds-ca.pem"


def test_config_error_message_has_no_secret_values():
    with pytest.raises(ConfigError) as excinfo:
        raise ConfigError("Missing required environment variable: MYSQL_PASSWORD.")
    assert "replace-me" not in str(excinfo.value)


def test_app_uses_sqlalchemy_uri():
    # App already configured by conftest against the test database.
    uri = hotel_app.app.config["SQLALCHEMY_DATABASE_URI"]
    assert uri.startswith("mysql+pymysql://")
    assert "c270_hotel_management_test" in uri
