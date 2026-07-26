import csv

from aisle.cluster.incremental import run_incremental_clustering
from aisle.cluster.themes import run_theme_clustering
from aisle.db.connection import get_conn
from aisle.ingest.upload import commit as upload_commit
from aisle.ingest.upload import load_rows, suggest_mapping
from tests.conftest import delete_documents_for_source


def _seed_new_docs(tmp_path, source_name: str, texts: list[str]) -> None:
    with get_conn() as conn:
        delete_documents_for_source(conn, source_name)
        conn.commit()
    csv_path = tmp_path / "incremental.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["review", "stars"])
        writer.writeheader()
        for t in texts:
            writer.writerow({"review": t, "stars": "3"})
    rows = load_rows(csv_path)
    mapping = suggest_mapping(list(rows[0].keys()))
    upload_commit(rows, mapping, source_name=source_name, file_label="incremental.csv")


def test_incremental_clustering_runs_after_a_full_cluster(tmp_path):
    baseline = run_theme_clustering(trigger="manual")
    assert baseline["n_themes"] > 0

    _seed_new_docs(
        tmp_path,
        "test_incremental_source",
        [
            "I always reorder my usual basket every single week from the saved list, never opening new categories.",
            "Every time I open the app I search for exactly what I need, I never browse new category pages at all.",
        ],
    )

    from aisle.classify.run import run_classification

    run_classification(limit=100, trigger="manual")

    with get_conn() as conn:
        run_row = conn.execute("INSERT INTO runs (trigger, status) VALUES ('manual', 'running') RETURNING id").fetchone()
        conn.commit()
        run_id = run_row["id"]

    result = run_incremental_clustering(run_id)

    assert result["new_docs"] >= 0
    assert result["assigned_to_existing"] + result["residual_size"] == result["new_docs"]
    for t in result["themes"]:
        assert "moved_beyond_prior_ci" in t
        assert 0.0 <= t["prevalence"] <= 1.0


def test_incremental_clustering_is_safe_to_rerun_with_no_new_activity():
    """A residual too small to clear min_cluster_size is legitimately left
    unclustered (HDBSCAN noise is a metric, not a nuisance, per §7) — it
    will keep showing up as "new_docs" on every rerun until enough similar
    documents accumulate. What must NOT happen on a rerun with no new
    ingestion/classification activity is: reassigning already-assigned
    docs, or creating duplicate new themes from the same stagnant residual.
    """
    with get_conn() as conn:
        run_row = conn.execute("INSERT INTO runs (trigger, status) VALUES ('manual', 'running') RETURNING id").fetchone()
        conn.commit()
        run_id = run_row["id"]

    first = run_incremental_clustering(run_id)

    with get_conn() as conn:
        run_row_2 = conn.execute("INSERT INTO runs (trigger, status) VALUES ('manual', 'running') RETURNING id").fetchone()
        conn.commit()
        run_id_2 = run_row_2["id"]

    second = run_incremental_clustering(run_id_2)
    assert second["new_docs"] <= first["residual_size"], "no new eligible documents arrived between the two runs"
    assert second["assigned_to_existing"] == 0, "nothing new arrived to assign"
    assert second["new_themes_created"] == 0, "the same already-tried residual must not form a new theme twice"
