"""Phase 6: the frontend's backend surface. Mainly a regression test for the
`psycopg.errors.IndeterminateDatatype` bug found while building the /insights
and /quality/negative-control routers (a bare `%s IS NULL OR col = %s` needs
an explicit cast when every call site passes None) — these run every
endpoint the frontend actually calls, with no filters, exactly the request
shape that triggered it.
"""
from fastapi.testclient import TestClient

from aisle.api.main import app
from aisle.cluster.themes import run_theme_clustering
from aisle.insights.generate import generate_insights_for_run

client = TestClient(app)


def test_overview_endpoint_returns_funnel_and_health():
    resp = client.get("/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["funnel"]) == 5
    assert "kappa" in body["pmgate_health"]


def test_themes_list_and_detail_with_no_filters():
    resp = client.get("/themes")
    assert resp.status_code == 200
    themes = resp.json()
    if not themes:
        run_theme_clustering(trigger="manual")
        themes = client.get("/themes").json()
    assert resp.headers["content-type"].startswith("application/json")
    detail = client.get(f"/themes/{themes[0]['id']}")
    assert detail.status_code == 200
    assert "centroid" not in detail.json(), "raw vector must never leak into the API response"
    assert "members" in detail.json()


def test_insights_list_with_no_filters_does_not_500():
    resp = client.get("/insights")
    assert resp.status_code == 200


def test_insights_list_with_grade_filter_does_not_500():
    resp = client.get("/insights?grade=A")
    assert resp.status_code == 200


def test_insight_detail_and_status_update():
    insights = client.get("/insights").json()
    if not insights:
        cluster_result = run_theme_clustering(trigger="manual")
        generate_insights_for_run(cluster_result["run_id"])
        insights = client.get("/insights").json()
    insight_id = insights[0]["id"]

    detail = client.get(f"/insights/{insight_id}")
    assert detail.status_code == 200
    assert "evidence" in detail.json()

    update = client.post(f"/insights/{insight_id}/status", json={"status": "human_approved"})
    assert update.status_code == 200
    assert client.get(f"/insights/{insight_id}").json()["status"] == "human_approved"


def test_runs_list():
    resp = client.get("/runs")
    assert resp.status_code == 200


def test_quality_negative_control_with_no_run_id_does_not_500():
    resp = client.get("/quality/negative-control")
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] in ("PASS", "FAIL")


def test_admin_sources_list():
    resp = client.get("/admin/sources")
    assert resp.status_code == 200
    assert len(resp.json()) > 0
