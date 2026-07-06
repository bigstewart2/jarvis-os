from fastapi.testclient import TestClient

from core.app import create_app


def test_list_skills_includes_echo():
    app = create_app()
    client = TestClient(app)

    response = client.get("/skills")

    assert response.status_code == 200
    ids = [skill["id"] for skill in response.json()]
    assert "echo" in ids
