from aisle.cluster.themes import run_theme_clustering
from aisle.db.connection import get_conn


def test_run_theme_clustering_produces_sane_structure():
    result = run_theme_clustering(trigger="manual")

    assert result["doc_total"] > 0
    assert 0.0 <= result["noise_pct"] <= 1.0
    assert len(result["themes"]) > 0

    for theme in result["themes"]:
        assert theme["ci_low"] <= theme["prevalence"] <= theme["ci_high"]
        assert 0.0 <= theme["prevalence"] <= 1.0
        assert theme["doc_count"] > 0
        assert theme["status"] in ("new", "growing", "stable", "decaying")
        assert theme["source_spread"]["n_distinct_sources"] >= 1

    with get_conn() as conn:
        row = conn.execute("SELECT count(*) AS n FROM themes WHERE run_id = %s", (result["run_id"],)).fetchone()
        assert row["n"] == len(result["themes"])

        member_count = conn.execute(
            "SELECT count(*) AS n FROM theme_documents td JOIN themes t ON t.id = td.theme_id WHERE t.run_id = %s",
            (result["run_id"],),
        ).fetchone()["n"]
        assert member_count == sum(t["doc_count"] for t in result["themes"])


def test_second_run_marks_matched_themes_as_stable_or_growing_or_decaying():
    first = run_theme_clustering(trigger="manual")
    second = run_theme_clustering(trigger="manual")

    matched = [t for t in second["themes"] if t["taxonomy_node"] is not None]
    assert any(t["status"] != "new" for t in matched), (
        "at least one taxonomy-mapped theme should be recognised as already existing on a second run"
    )
    assert first["doc_total"] == second["doc_total"]
