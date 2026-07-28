"""Backend for /admin/label (§6's human-labelling UI) and the /quality
screen's metrics feed.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from aisle.db.connection import get_conn
from aisle.eval import metrics as metrics_module
from aisle.eval.golden import stratified_sample, submit_golden_label
from aisle.eval.negative_control import run_negative_control_check

router = APIRouter(tags=["admin"])


@router.get("/admin/label/sample")
def get_labelling_sample(n: int = 20) -> list[dict]:
    sample = stratified_sample(n=n)
    return [{"document_id": r["id"], "raw_text": r["raw_text"], "lang_detected": r["lang_detected"]} for r in sample]


@router.get("/admin/label/next")
def get_next_unlabelled(annotator_id: str, round: int = 1) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT d.id, d.raw_text, d.lang_detected FROM documents d
            WHERE d.dupe_of_id IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM golden_labels g
                WHERE g.document_id = d.id AND g.annotator_id = %s AND g.round = %s
              )
            ORDER BY d.id LIMIT 1
            """,
            (annotator_id, round),
        ).fetchone()
    return dict(row) if row else None


class LabelSubmission(BaseModel):
    document_id: int
    is_junk: bool
    discovery_relevance: int | None = None
    annotator_id: str
    round: int = 1


@router.post("/admin/label")
def submit_label(payload: LabelSubmission) -> dict:
    submit_golden_label(
        payload.document_id,
        {"is_junk": payload.is_junk, "discovery_relevance": payload.discovery_relevance},
        annotator_id=payload.annotator_id,
        label_round=payload.round,
    )
    return {"status": "ok"}


@router.get("/quality/metrics")
def quality_metrics(annotator_id: str = "synthetic_proxy_v1", round: int = 1, schema_version: str = "pmgate.v1") -> dict:
    # Fetched once and reused below — each of these used to independently
    # re-run the identical golden_labels/classifications join (and open its
    # own DB connection to do it), 8 round trips for one page load.
    rows = metrics_module.fetch_joined_labels(annotator_id, round)
    return {
        "stage1_junk": metrics_module.stage1_junk_metrics(annotator_id, round, rows=rows),
        "stage3_relevance": metrics_module.stage3_relevance_metrics(annotator_id, round, rows=rows),
        "classifier_vs_human_kappa": metrics_module.classifier_vs_human_kappa(annotator_id, round, rows=rows),
        "calibration": metrics_module.calibration_bins(annotator_id, round, rows=rows),
        "abstention": metrics_module.abstention_rate(schema_version),
        "acceptance_gate": metrics_module.acceptance_gate(annotator_id, round, rows=rows),
        "annotator_id_note": (
            "synthetic_proxy_v1 is NOT a real human annotator — see aisle/README.md. "
            "Real acceptance-gate numbers require labels from an actual /admin/label session."
        ) if annotator_id == "synthetic_proxy_v1" else None,
    }


@router.get("/quality/negative-control")
def negative_control(run_id: int | None = None) -> dict:
    return run_negative_control_check(run_id)
