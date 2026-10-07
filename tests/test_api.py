import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch, sponsor_db):
    import sponsorship
    from webapp import app as app_module
    monkeypatch.setattr(app_module, "PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setattr(sponsorship, "_db", sponsor_db)
    return TestClient(app_module.app)


def test_profile_roundtrip_whitelists_fields(client):
    r = client.put("/api/profile", json={
        "personal":    {"name": "Asha", "password": "nope"},
        "immigration": {"status": "F1-OPT", "unemployment_days_used": 12, "unemployment_as_of": "2026-10-01"},
        "preferences": {"sponsor_filter": "strict"},
        "secrets":     {"x": 1},
    })
    assert r.json() == {"ok": True}
    p = client.get("/api/profile").json()
    assert p["personal"] == {"name": "Asha"}
    assert p["immigration"]["unemployment_days_used"] == 12
    assert "secrets" not in p


def test_profile_rejects_bad_enums(client):
    assert client.put("/api/profile", json={"immigration": {"status": "Martian"}}).status_code == 400
    assert client.put("/api/profile", json={"preferences": {"sponsor_filter": "x"}}).status_code == 400


def test_visa_endpoint(client):
    client.put("/api/profile", json={"immigration": {"status": "F1-OPT", "unemployment_days_used": 5}})
    v = client.get("/api/visa").json()
    assert v["needs_sponsorship"] is True
    assert v["opt"]["applicable"] and v["opt"]["limit"] == 90
    assert v["sponsor_db"]["available"] and v["sponsor_db"]["rows"] == 16


def test_sponsor_endpoint(client):
    client.put("/api/profile", json={"immigration": {"status": "F1-OPT"}})
    d = client.get("/api/sponsor", params={"company": "Acme Software", "title": "Software Engineer"}).json()
    assert d["verdict"] == "likely" and d["h1b"]["filings"] == 12
    assert client.get("/api/sponsor", params={"company": " "}).status_code == 400
