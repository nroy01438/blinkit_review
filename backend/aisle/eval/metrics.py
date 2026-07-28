"""Classifier accountability metrics (§6): per-stage precision/recall/F1
against the golden set, Cohen's κ (classifier-vs-human and human-vs-human),
a calibration curve, abstention rate, and the §6 acceptance gate.
"""
from __future__ import annotations

from sklearn.metrics import cohen_kappa_score, precision_recall_fscore_support

from aisle.db.connection import get_conn

ACCEPTANCE_THRESHOLDS = {
    "stage1_junk_recall": 0.90,
    "stage3_relevance_f1": 0.80,
    "kappa": 0.65,
}


def fetch_joined_labels(annotator_id: str, label_round: int = 1) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT g.document_id, g.human_label_json, c.is_junk AS clf_is_junk,
                   c.discovery_relevance AS clf_discovery_relevance, c.confidence AS clf_confidence
            FROM golden_labels g
            LEFT JOIN classifications c ON c.document_id = g.document_id
            WHERE g.annotator_id = %s AND g.round = %s
            """,
            (annotator_id, label_round),
        ).fetchall()


def stage1_junk_metrics(annotator_id: str, label_round: int = 1, *, rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else fetch_joined_labels(annotator_id, label_round)
    rows = [r for r in rows if r["clf_is_junk"] is not None]
    if not rows:
        return {"precision": None, "recall": None, "f1": None, "n": 0}
    y_true = [bool(r["human_label_json"]["is_junk"]) for r in rows]
    y_pred = [bool(r["clf_is_junk"]) for r in rows]
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {
        "precision": round(float(precision), 4), "recall": round(float(recall), 4),
        "f1": round(float(f1), 4), "n": len(rows),
    }


def stage3_relevance_metrics(
    annotator_id: str, label_round: int = 1, relevance_floor: int = 2, *, rows: list[dict] | None = None
) -> dict:
    rows = rows if rows is not None else fetch_joined_labels(annotator_id, label_round)
    rows = [r for r in rows if r["clf_discovery_relevance"] is not None]
    if not rows:
        return {"precision": None, "recall": None, "f1": None, "n": 0}
    y_true = [int(r["human_label_json"].get("discovery_relevance", 0)) >= relevance_floor for r in rows]
    y_pred = [r["clf_discovery_relevance"] >= relevance_floor for r in rows]
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {
        "precision": round(float(precision), 4), "recall": round(float(recall), 4),
        "f1": round(float(f1), 4), "n": len(rows),
    }


def classifier_vs_human_kappa(
    annotator_id: str, label_round: int = 1, field: str = "is_junk", *, rows: list[dict] | None = None
) -> dict:
    rows = rows if rows is not None else fetch_joined_labels(annotator_id, label_round)
    rows = [r for r in rows if r["clf_is_junk"] is not None]
    if len(rows) < 2:
        return {"kappa": None, "n": len(rows)}
    y_human = [bool(r["human_label_json"].get(field)) for r in rows]
    y_model = [bool(r["clf_is_junk"]) for r in rows]
    return {"kappa": round(float(cohen_kappa_score(y_human, y_model)), 4), "n": len(rows)}


def human_vs_human_kappa(annotator_a: str, annotator_b: str, field: str, label_round: int = 1) -> dict:
    """Requires >=100 overlapping docs labelled by two independent
    annotators (§6). If this comes back < 0.6, the rubric is the problem —
    sharpen the anchors and re-label, don't touch the model.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT a.document_id, a.human_label_json AS label_a, b.human_label_json AS label_b
            FROM golden_labels a
            JOIN golden_labels b ON b.document_id = a.document_id AND b.round = a.round
            WHERE a.annotator_id = %s AND b.annotator_id = %s AND a.round = %s
            """,
            (annotator_a, annotator_b, label_round),
        ).fetchall()
    if len(rows) < 2:
        return {"kappa": None, "n": len(rows)}
    y_a = [bool(r["label_a"].get(field)) for r in rows]
    y_b = [bool(r["label_b"].get(field)) for r in rows]
    return {"kappa": round(float(cohen_kappa_score(y_a, y_b)), 4), "n": len(rows)}


def calibration_bins(
    annotator_id: str, label_round: int = 1, n_bins: int = 5, *, rows: list[dict] | None = None
) -> list[dict]:
    """Predicted confidence vs actual accuracy (is_junk agreement), bucketed
    into `n_bins` equal-width confidence bins. A well-calibrated classifier
    has actual_accuracy ~= mean_predicted_confidence in every bin.
    """
    rows = rows if rows is not None else fetch_joined_labels(annotator_id, label_round)
    rows = [r for r in rows if r["clf_is_junk"] is not None and r["clf_confidence"] is not None]
    bins = [{"bin_low": i / n_bins, "bin_high": (i + 1) / n_bins, "n": 0, "correct": 0, "confidence_sum": 0.0} for i in range(n_bins)]
    for r in rows:
        conf = r["clf_confidence"]
        idx = min(n_bins - 1, int(conf * n_bins))
        correct = bool(r["human_label_json"]["is_junk"]) == bool(r["clf_is_junk"])
        bins[idx]["n"] += 1
        bins[idx]["correct"] += int(correct)
        bins[idx]["confidence_sum"] += conf
    out = []
    for b in bins:
        if b["n"] == 0:
            out.append({**b, "actual_accuracy": None, "avg_predicted_confidence": None})
        else:
            out.append(
                {
                    **b,
                    "actual_accuracy": round(b["correct"] / b["n"], 4),
                    "avg_predicted_confidence": round(b["confidence_sum"] / b["n"], 4),
                }
            )
    return out


def abstention_rate(schema_version: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count(*) AS n, sum(abstained::int) AS abstained FROM classifications WHERE schema_version = %s",
            (schema_version,),
        ).fetchone()
    n = row["n"] or 0
    abstained = row["abstained"] or 0
    return {"n": n, "abstained": abstained, "rate": round(abstained / n, 4) if n else 0.0}


def acceptance_gate(annotator_id: str, label_round: int = 1, *, rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else fetch_joined_labels(annotator_id, label_round)
    junk = stage1_junk_metrics(annotator_id, label_round, rows=rows)
    relevance = stage3_relevance_metrics(annotator_id, label_round, rows=rows)
    kappa = classifier_vs_human_kappa(annotator_id, label_round, rows=rows)

    checks = {
        "stage1_junk_recall": {
            "value": junk["recall"], "threshold": ACCEPTANCE_THRESHOLDS["stage1_junk_recall"],
            "passed": bool(junk["recall"] is not None and junk["recall"] >= ACCEPTANCE_THRESHOLDS["stage1_junk_recall"]),
        },
        "stage3_relevance_f1": {
            "value": relevance["f1"], "threshold": ACCEPTANCE_THRESHOLDS["stage3_relevance_f1"],
            "passed": bool(relevance["f1"] is not None and relevance["f1"] >= ACCEPTANCE_THRESHOLDS["stage3_relevance_f1"]),
        },
        "kappa": {
            "value": kappa["kappa"], "threshold": ACCEPTANCE_THRESHOLDS["kappa"],
            "passed": bool(kappa["kappa"] is not None and kappa["kappa"] >= ACCEPTANCE_THRESHOLDS["kappa"]),
        },
    }
    return {"checks": checks, "all_passed": bool(all(c["passed"] for c in checks.values()))}
