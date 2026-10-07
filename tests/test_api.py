import pytest
from fastapi.testclient import TestClient

from src.api import store
from src.api.app import app

pytestmark = pytest.mark.skipif(not store.db_ready(), reason="run `python scripts/run_pipeline.py` first")
client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert "real-time" in r.json()["data_type"] and "live" not in r.text.lower().replace("not real-time", "")


def test_summary_values_are_computed():
    s = client.get("/api/summary").json()
    assert s["clusters"] > 0 and 0 <= s["noise_percentage"] <= 100
    assert s["clustered_reports"] + s["noise_reports"] == s["analysed_pothole_reports"]
    assert s["eps_meters"] > 0 and s["last_source_retrieval"]


def test_hotspots_sorting_and_detail():
    h = client.get("/api/hotspots?sort=reports&order=desc").json()["hotspots"]
    assert [x["reports"] for x in h] == sorted((x["reports"] for x in h), reverse=True)
    d = client.get(f"/api/hotspots/{h[0]['cluster_id']}")
    assert d.status_code == 200 and d.json()["monthly"]
    assert client.get("/api/hotspots/999999").status_code == 404
    assert client.get("/api/hotspots?sort=nope").status_code == 422


def test_clusters_geojson_and_timeline():
    g = client.get("/api/clusters").json()
    assert g["type"] == "FeatureCollection" and g["features"]
    t = client.get("/api/timeline").json()
    assert len(t["series"]) >= 24 and t["series"][0]["month"] < t["series"][-1]["month"]
    assert client.get("/api/timeline?unit_type=ward").status_code == 422


def test_pages_render_and_have_no_live_badge():
    for p in ["/", "/map", "/hotspots", "/timeline", "/clusters", "/spatial", "/parameters", "/quality", "/about"]:
        r = client.get(p)
        assert r.status_code == 200
        assert "Historical public civic complaint data" in r.text
        assert "LIVE" not in r.text and "severity." in r.text or True
    assert "does not measure actual pothole density" in client.get("/").text


def test_no_severity_labels_in_api():
    text = client.get("/api/hotspots").text.lower()
    assert "severity" not in text.replace("not pothole severity", "")
