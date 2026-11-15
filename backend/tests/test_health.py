
"""
KiranaAI health endpoint tests.
"""


def test_health_endpoint(client):
    """Verify that the backend health endpoint responds correctly."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "KiranaAI",
    }


def test_home_endpoint(client):
    """Verify that the backend welcome endpoint is available."""

    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "Running successfully"
