from fastapi.testclient import TestClient

from core.app import create_app
from core.db.models import DashboardConfig

KNOWN_WIDGETS = ["skills", "voice", "automations", "tasks", "notes"]


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    return TestClient(app), app


def test_get_dashboard_config_creates_default_row_on_first_read(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)

    response = client.get("/dashboard/config")

    assert response.status_code == 200
    body = response.json()
    assert body["widget_order"] == KNOWN_WIDGETS
    assert body["hidden_widgets"] == []

    with app.state.session_factory() as session:
        assert session.query(DashboardConfig).count() == 1


def test_get_dashboard_config_returns_existing_row_without_creating_another(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(DashboardConfig(widget_order=["voice", "skills", "tasks", "automations"], hidden_widgets=["tasks"]))
        session.commit()

    response = client.get("/dashboard/config")

    assert response.status_code == 200
    body = response.json()
    assert body["widget_order"] == ["voice", "skills", "tasks", "automations"]
    assert body["hidden_widgets"] == ["tasks"]
    with app.state.session_factory() as session:
        assert session.query(DashboardConfig).count() == 1


def test_put_dashboard_config_saves_and_round_trips(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": ["tasks", "automations", "voice", "skills", "notes"], "hidden_widgets": ["voice"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "widget_order": ["tasks", "automations", "voice", "skills", "notes"],
        "hidden_widgets": ["voice"],
    }

    follow_up = client.get("/dashboard/config")
    assert follow_up.json() == {
        "widget_order": ["tasks", "automations", "voice", "skills", "notes"],
        "hidden_widgets": ["voice"],
    }


def test_put_dashboard_config_rejects_missing_widget(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": ["skills", "voice", "automations"], "hidden_widgets": []},
    )

    assert response.status_code == 400


def test_put_dashboard_config_rejects_duplicate_widget(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": ["skills", "skills", "voice", "tasks"], "hidden_widgets": []},
    )

    assert response.status_code == 400


def test_put_dashboard_config_rejects_unknown_widget_id(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": ["skills", "voice", "automations", "bogus"], "hidden_widgets": []},
    )

    assert response.status_code == 400


def test_put_dashboard_config_rejects_hidden_widget_not_in_known_set(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": KNOWN_WIDGETS, "hidden_widgets": ["bogus"]},
    )

    assert response.status_code == 400


def test_put_dashboard_config_updates_updated_at_timestamp(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    client, app = _client(tmp_path, monkeypatch)
    client.get("/dashboard/config")  # creates the default row

    with app.state.session_factory() as session:
        row = session.query(DashboardConfig).one()
        row.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        session.commit()

    client.put(
        "/dashboard/config",
        json={"widget_order": KNOWN_WIDGETS, "hidden_widgets": []},
    )

    with app.state.session_factory() as session:
        updated = session.query(DashboardConfig).one()
        assert updated.updated_at.year != 2020
