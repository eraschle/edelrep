from unittest.mock import patch

from fastapi.testclient import TestClient

from edelrep.infrastructure.updates.update_checker import UpdateStatus
from edelrep.presentation.container import Container


def _stub_status(client: TestClient, container: Container, status: UpdateStatus) -> None:
    container.update_checker.status = lambda: status  # type: ignore[method-assign]


def test_updates_page_renders_current_and_latest(
    client: TestClient, container: Container
) -> None:
    _stub_status(
        client,
        container,
        UpdateStatus(current="abc1234" * 6, latest="def5678" * 6, update_available=True),
    )
    r = client.get("/admin/updates")
    assert r.status_code == 200
    assert "Installierte Version" in r.text
    assert "Neueste Version" in r.text
    assert "abc1234" in r.text
    assert "def5678" in r.text
    assert "Eine neue Version ist verfügbar" in r.text


def test_updates_page_announces_up_to_date(
    client: TestClient, container: Container
) -> None:
    same = "abc1234" * 6
    _stub_status(client, container, UpdateStatus(current=same, latest=same, update_available=False))
    r = client.get("/admin/updates")
    assert r.status_code == 200
    assert "neueste Version" in r.text


def test_updates_page_warns_when_versions_unknown(
    client: TestClient, container: Container
) -> None:
    _stub_status(
        client, container, UpdateStatus(current="unknown", latest="unknown", update_available=False)
    )
    r = client.get("/admin/updates")
    assert r.status_code == 200
    assert "Internet-Verbindung" in r.text


def test_updates_status_endpoint_returns_json(
    client: TestClient, container: Container
) -> None:
    _stub_status(
        client,
        container,
        UpdateStatus(current="abcdef0123" * 4, latest="fedcba9876" * 4, update_available=True),
    )
    r = client.get("/admin/updates/status")
    assert r.status_code == 200
    body = r.json()
    assert body["current_short"] == "abcdef0"
    assert body["latest_short"] == "fedcba9"
    assert body["update_available"] is True


def test_apply_endpoint_schedules_shutdown(
    client: TestClient, container: Container
) -> None:
    """The apply endpoint must return 202 immediately and schedule a process
    exit via threading.Timer. We patch Timer so the test process keeps
    running (otherwise pytest itself would be killed)."""
    captured: dict[str, float | object] = {}

    class _DummyTimer:
        def __init__(self, delay: float, fn) -> None:
            captured["delay"] = delay
            captured["fn"] = fn

        def start(self) -> None:
            captured["started"] = True

    with patch("edelrep.presentation.routes.updates.threading.Timer", _DummyTimer):
        r = client.post("/admin/updates/apply")
    assert r.status_code == 202
    assert r.json() == {"status": "restarting"}
    assert captured.get("started") is True
    assert captured.get("delay") is not None
    assert callable(captured.get("fn"))


def test_nav_shows_updates_link(client: TestClient) -> None:
    r = client.get("/search")
    assert r.status_code == 200
    assert 'href="/admin/updates"' in r.text
