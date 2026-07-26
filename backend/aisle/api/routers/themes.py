from __future__ import annotations

from fastapi import APIRouter

from aisle.db.connection import get_conn

router = APIRouter(prefix="/themes", tags=["themes"])


def _latest_run_id(conn) -> int | None:
    row = conn.execute("SELECT run_id FROM themes ORDER BY run_id DESC LIMIT 1").fetchone()
    return row["run_id"] if row else None


@router.get("")
def list_themes(run_id: int | None = None) -> list[dict]:
    with get_conn() as conn:
        rid = run_id or _latest_run_id(conn)
        if rid is None:
            return []
        rows = conn.execute(
            """
            SELECT id, label, description, taxonomy_node, doc_count, doc_total, prevalence, ci_low, ci_high,
                   source_spread_json, status, delta_vs_prev_run, noise_pct, stability_ari, first_seen_run
            FROM themes WHERE run_id = %s ORDER BY prevalence DESC
            """,
            (rid,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{theme_id}")
def get_theme(theme_id: int) -> dict | None:
    with get_conn() as conn:
        theme = conn.execute("SELECT * FROM themes WHERE id = %s", (theme_id,)).fetchone()
        if theme is None:
            return None
        members = conn.execute(
            """
            SELECT d.id AS document_id, d.raw_text, d.posted_at, s.name AS source_name, s.brand,
                   td.is_exemplar, c.segment_label, c.sentiment
            FROM theme_documents td JOIN documents d ON d.id = td.document_id JOIN sources s ON s.id = d.source_id
            JOIN classifications c ON c.document_id = d.id
            WHERE td.theme_id = %s ORDER BY td.is_exemplar DESC, d.id
            """,
            (theme_id,),
        ).fetchall()
        sparkline = conn.execute(
            "SELECT run_id, prevalence FROM themes WHERE taxonomy_node = %s ORDER BY run_id",
            (theme["taxonomy_node"],),
        ).fetchall() if theme["taxonomy_node"] else []
    result = dict(theme)
    result.pop("centroid", None)  # a raw 384-dim vector — not JSON-serialisable and not needed by the UI
    result["members"] = [dict(m) for m in members]
    result["sparkline"] = [dict(s) for s in sparkline]
    return result
