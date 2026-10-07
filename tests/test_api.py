import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch, regions_with_data):
    from webapp import app as app_module
    monkeypatch.setattr(app_module, "PROFILE_PATH", str(tmp_path / "profile.json"))
    return TestClient(app_module.app)


def test_profile_roundtrip_whitelists_fields(client):
    r = client.put("/api/profile", json={
        "personal":    {"name": "Asha", "password": "nope"},
        "immigration": {"status": "F1-OPT", "unemployment_days_used": 12, "unemployment_as_of": "2026-10-01",
                        "authorized_countries": ["in", "IN"]},
        "preferences": {"sponsor_filter": "strict", "job_country": "gb"},
        "secrets":     {"x": 1},
    })
    assert r.json() == {"ok": True}
    p = client.get("/api/profile").json()
    assert p["personal"] == {"name": "Asha"}
    assert p["immigration"]["authorized_countries"] == ["IN"]
    assert p["preferences"]["job_country"] == "GB"
    assert "secrets" not in p


def test_profile_rejects_bad_values(client):
    assert client.put("/api/profile", json={"immigration": {"status": "Martian"}}).status_code == 400
    assert client.put("/api/profile", json={"preferences": {"sponsor_filter": "x"}}).status_code == 400
    assert client.put("/api/profile", json={"preferences": {"job_country": "ZZ"}}).status_code == 400
    assert client.put("/api/profile", json={"immigration": {"authorized_countries": ["XX"]}}).status_code == 400
    assert client.put("/api/profile", json={"immigration": {"authorized_countries": "IN"}}).status_code == 400


def test_regions_endpoint(client):
    regions = client.get("/api/regions").json()
    by_code = {r["code"]: r for r in regions}
    assert by_code["US"]["available"] and by_code["US"]["rows"] == 16
    assert by_code["GB"]["available"] and by_code["GB"]["detail"] == "2 licensed employers"
    assert by_code["IN"]["has_data"] is False


def test_visa_endpoint_follows_job_country(client):
    client.put("/api/profile", json={"immigration": {"status": "F1-OPT", "unemployment_days_used": 5}})
    v = client.get("/api/visa").json()
    assert v["job_country"]["code"] == "US" and v["needs_sponsorship"]
    assert v["opt"]["applicable"] and v["opt"]["limit"] == 90
    client.put("/api/profile", json={"preferences": {"job_country": "GB"}})
    v = client.get("/api/visa").json()
    assert v["job_country"]["code"] == "GB" and v["opt"] == {"applicable": False}


def test_sponsor_endpoint(client):
    client.put("/api/profile", json={"immigration": {"status": "F1-OPT"}})
    d = client.get("/api/sponsor", params={"company": "Acme Software", "title": "Software Engineer"}).json()
    assert d["verdict"] == "likely" and d["country"]["code"] == "US"
    uk = client.get("/api/sponsor", params={"company": "Globex Software", "country": "GB"}).json()
    assert uk["verdict"] == "likely" and uk["region"]["code"] == "GB"
    assert client.get("/api/sponsor", params={"company": " "}).status_code == 400
    assert client.get("/api/sponsor", params={"company": "X", "country": "ZZ"}).status_code == 400
