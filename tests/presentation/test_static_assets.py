from fastapi.testclient import TestClient


def test_logo_is_served(client: TestClient) -> None:
    r = client.get("/static/edelmann-logo.png")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")


def test_favicon_is_served(client: TestClient) -> None:
    r = client.get("/static/favicon.ico")
    assert r.status_code == 200
    ctype = r.headers["content-type"]
    assert "icon" in ctype or "octet-stream" in ctype or ctype.startswith("image/")


def test_missing_static_asset_returns_404(client: TestClient) -> None:
    r = client.get("/static/does-not-exist.png")
    assert r.status_code == 404


def test_base_template_includes_favicon_link(client: TestClient) -> None:
    r = client.get("/search")
    assert r.status_code == 200
    assert '<link rel="icon"' in r.text
    assert "/static/favicon.ico" in r.text


def test_base_template_includes_logo_image(client: TestClient) -> None:
    r = client.get("/search")
    assert r.status_code == 200
    assert '<img src="/static/edelmann-logo.png"' in r.text
    assert 'alt="Edelmann Motos"' in r.text
