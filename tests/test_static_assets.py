"""Static asset delivery — stylesheet must load so pages are not raw HTML."""

from pathlib import Path


def test_style_css_is_served_with_text_css(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200
    content_type = response.headers.get("Content-Type", "")
    assert "text/css" in content_type
    body = response.get_data(as_text=True)
    assert body.strip()
    assert "@import url(" not in body
    assert ".navbar" in body
    assert ".dashboard-grid" in body


def test_login_page_references_stylesheet(client):
    response = client.get("/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/static/style.css" in html
    assert 'rel="stylesheet"' in html


def test_admin_dashboard_references_stylesheet(client):
    from tests.conftest import login_as

    login_as(client, "admin", "admin123")
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/static/style.css" in html
    assert "Admin Dashboard" in html


def test_style_css_file_exists_on_disk():
    css_path = Path(__file__).resolve().parents[1] / "static" / "style.css"
    assert css_path.is_file()
    assert css_path.stat().st_size > 1000
