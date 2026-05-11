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
