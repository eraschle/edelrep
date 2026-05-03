from fastapi.testclient import TestClient


def test_root_redirects_to_search(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/search"
