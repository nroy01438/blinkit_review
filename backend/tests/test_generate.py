from aisle.cluster.themes import run_theme_clustering
from aisle.db.connection import get_conn
from aisle.insights.generate import generate_insights_for_run


def test_generate_insights_for_run_produces_sane_structure():
    clustering_result = run_theme_clustering(trigger="manual")
    run_id = clustering_result["run_id"]

    result = generate_insights_for_run(run_id)

    assert result["themes_considered"] > 0
    assert result["insights_generated"] + result["skipped_too_small"] == result["themes_considered"]

    for insight in result["insights"]:
        assert insight["grade"] in ("A", "B", "C", "D")
        assert 0 <= insight["iqs_total"] <= 100
        assert isinstance(insight["confident"], bool)
        assert isinstance(insight["undermines_insight"], bool)

    with get_conn() as conn:
        db_count = conn.execute("SELECT count(*) AS n FROM insights WHERE run_id = %s", (run_id,)).fetchone()["n"]
        assert db_count == result["insights_generated"]


def test_every_persisted_insight_has_evidence_and_mandatory_counter_evidence():
    clustering_result = run_theme_clustering(trigger="manual")
    result = generate_insights_for_run(clustering_result["run_id"])
    if not result["insights"]:
        return  # nothing generated this run (e.g. all themes below the min-doc-count floor)

    with get_conn() as conn:
        for insight in result["insights"]:
            row = conn.execute(
                "SELECT counter_evidence, statement, so_what, opportunity FROM insights WHERE id = %s",
                (insight["insight_id"],),
            ).fetchone()
            assert row["counter_evidence"], "counter_evidence is mandatory (§8) even when the answer is 'none found'"
            assert row["statement"] and row["so_what"] and row["opportunity"]

            evidence_count = conn.execute(
                "SELECT count(*) AS n FROM insight_evidence WHERE insight_id = %s", (insight["insight_id"],)
            ).fetchone()["n"]
            assert evidence_count >= 1
