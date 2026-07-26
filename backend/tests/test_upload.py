import csv
from pathlib import Path

from aisle.db.connection import get_conn
from aisle.ingest.upload import commit, load_rows, suggest_mapping, validate
from tests.conftest import delete_documents_for_source


def _write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_suggest_mapping_matches_common_header_variants():
    mapping = suggest_mapping(["Review Text", "Stars", "Posted On", "Username", "Link"])
    assert mapping["text"] == "Review Text"
    assert mapping["rating"] == "Stars"
    assert mapping["author"] == "Username"
    assert mapping["url"] == "Link"


def test_upload_round_trip_is_idempotent(tmp_path):
    source_name = "test_upload_idempotent"
    with get_conn() as conn:
        delete_documents_for_source(conn, source_name)
        conn.commit()

    csv_path = tmp_path / "export.csv"
    _write_csv(
        csv_path,
        [
            {"review": "I only ever reorder my usual basket, never browse new categories", "stars": "4", "user": "u1"},
            {"review": "app crashed on checkout", "stars": "1", "user": "u2"},
        ],
    )
    rows = load_rows(csv_path)
    mapping = suggest_mapping(list(rows[0].keys()))
    assert mapping["text"] is not None

    val = validate(rows, mapping, source_name=source_name)
    assert val["row_count"] == 2
    assert val["pct_missing_text"] == 0.0

    first = commit(rows, mapping, source_name=source_name, file_label="export.csv")
    second = commit(rows, mapping, source_name=source_name, file_label="export.csv")

    assert first["inserted"] == 2
    assert second["inserted"] == 0, "re-uploading the identical file must be a no-op"
    assert first["rejected_rows"] == []


def test_upload_rejects_bad_rows_without_failing_whole_batch(tmp_path):
    source_name = "test_upload_partial"
    with get_conn() as conn:
        delete_documents_for_source(conn, source_name)
        conn.commit()

    csv_path = tmp_path / "export.csv"
    _write_csv(
        csv_path,
        [
            {"review": "good specific review about produce freshness concerns", "stars": "3", "user": "u1"},
            {"review": "", "stars": "2", "user": "u2"},  # missing text -> rejected
            {"review": "another valid review about search habits", "stars": "not-a-number", "user": "u3"},  # bad rating -> rejected
        ],
    )
    rows = load_rows(csv_path)
    mapping = suggest_mapping(list(rows[0].keys()))
    result = commit(rows, mapping, source_name=source_name, file_label="export.csv")

    assert result["inserted"] == 1
    assert len(result["rejected_rows"]) == 2
    reasons = {r["reason"].split(":")[0] for r in result["rejected_rows"]}
    assert any("missing required field" in r["reason"] for r in result["rejected_rows"])
    assert any("invalid rating" in r["reason"] for r in result["rejected_rows"])
