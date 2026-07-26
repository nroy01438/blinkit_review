"""The upload utility (§5) — one code path shared by the CLI and the
`/upload` API/UI. Handles CSV / XLSX / JSON / JSONL / TXT, auto-suggests a
column mapping onto the canonical schema, validates before committing,
previews the first 20 normalised rows, and on commit is idempotent (re-
uploading the same file changes nothing) with partial-success semantics —
bad rows are collected with a reason, never fail the whole batch.

CLI: python -m aisle.ingest.upload --file data.csv --source-name "Instagram export" [--mapping mapping.yaml] [--commit]
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
from datetime import datetime
from pathlib import Path

import yaml
from langdetect import LangDetectException, detect

from aisle.db.connection import get_conn
from aisle.ingest.dedupe import content_hash
from aisle.ingest.pipeline import persist_docs
from aisle.ingest.schema import RawDoc

CANONICAL_SYNONYMS: dict[str, list[str]] = {
    "text": ["text", "review", "review_text", "content", "body", "comment", "message", "caption", "tweet"],
    "rating": ["rating", "stars", "score", "star_rating"],
    "posted_at": ["posted_at", "date", "created_at", "timestamp", "review_date", "time"],
    "author": ["author", "user", "username", "reviewer", "name", "handle"],
    "url": ["url", "link", "permalink"],
    "source": ["source", "platform", "app"],
    "lang": ["lang", "language"],
}
REQUIRED_FIELDS = {"text"}


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {}
    normalised = {h: h.strip().lower().replace(" ", "_") for h in headers}
    for canonical, synonyms in CANONICAL_SYNONYMS.items():
        match = None
        for header, norm in normalised.items():
            if norm in synonyms:
                match = header
                break
        if match is None:
            close = difflib.get_close_matches(canonical, list(normalised.values()), n=1, cutoff=0.7)
            if close:
                match = next(h for h, n in normalised.items() if n == close[0])
        mapping[canonical] = match
    return mapping


def load_rows(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv"):
        delimiter = "\t" if suffix == ".tsv" else ","
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f, delimiter=delimiter))
    if suffix == ".xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(next(rows_iter))]
        return [dict(zip(headers, row)) for row in rows_iter]
    if suffix == ".jsonl":
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
    if suffix == ".json":
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    if suffix == ".txt":
        with open(path) as f:
            return [{"text": line.strip()} for line in f if line.strip()]
    raise ValueError(f"Unsupported file type: {suffix}")


def _normalise_row(row: dict, mapping: dict[str, str | None]) -> dict:
    out = {}
    for canonical, header in mapping.items():
        if header is None:
            continue
        val = row.get(header)
        out[canonical] = val.strip() if isinstance(val, str) else val
    return out


def _parse_posted_at(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def validate(rows: list[dict], mapping: dict[str, str | None], *, source_name: str) -> dict:
    missing_required = [c for c in REQUIRED_FIELDS if mapping.get(c) is None]
    n = len(rows)
    missing_text = 0
    langs: dict[str, int] = {}
    dates = []
    seen_hashes: set[str] = set()
    dupes_within_file = 0

    with get_conn() as conn:
        existing_hashes = {
            r["content_hash"]
            for r in conn.execute(
                """
                SELECT d.content_hash FROM documents d JOIN sources s ON s.id = d.source_id
                WHERE s.name = %s
                """,
                (source_name,),
            ).fetchall()
        }

    dupes_against_corpus = 0
    for row in rows:
        norm = _normalise_row(row, mapping)
        text = norm.get("text")
        if not text:
            missing_text += 1
            continue
        h = content_hash(str(text))
        if h in seen_hashes:
            dupes_within_file += 1
        seen_hashes.add(h)
        if h in existing_hashes:
            dupes_against_corpus += 1
        try:
            lang = detect(str(text))
            langs[lang] = langs.get(lang, 0) + 1
        except LangDetectException:
            pass
        dt = _parse_posted_at(norm.get("posted_at"))
        if dt is not None:
            dates.append(dt)

    return {
        "row_count": n,
        "missing_required_fields": missing_required,
        "pct_missing_text": round(100 * missing_text / n, 1) if n else 0.0,
        "languages_detected": langs,
        "dupes_within_file": dupes_within_file,
        "dupes_against_existing_corpus": dupes_against_corpus,
        "date_range": {
            "min": min(dates).isoformat() if dates else None,
            "max": max(dates).isoformat() if dates else None,
        },
    }


def preview(rows: list[dict], mapping: dict[str, str | None], n: int = 20) -> list[dict]:
    return [_normalise_row(row, mapping) for row in rows[:n]]


def _get_or_create_source(source_name: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM sources WHERE name = %s", (source_name,)).fetchone()
        if row is not None:
            return row["id"]
        row = conn.execute(
            """
            INSERT INTO sources (name, kind, brand, config_json, is_active)
            VALUES (%s, 'manual_upload', 'mixed', '{}'::jsonb, true)
            RETURNING id
            """,
            (source_name,),
        ).fetchone()
        conn.commit()
        return row["id"]


def commit(
    rows: list[dict], mapping: dict[str, str | None], *, source_name: str, file_label: str
) -> dict:
    """Idempotent: external_id defaults to content_hash of the text when the
    file has no natural id column, so re-uploading the identical file maps
    every row back onto the same (source_id, external_id) and the
    ON CONFLICT DO NOTHING in persist_docs makes the re-upload a no-op.
    """
    source_id = _get_or_create_source(source_name)
    with get_conn() as conn:
        run_row = conn.execute(
            "INSERT INTO runs (trigger, status, config_snapshot_json) VALUES ('upload', 'running', %s) RETURNING id",
            (json.dumps({"file_label": file_label, "source_name": source_name}),),
        ).fetchone()
        conn.commit()
        run_id = run_row["id"]

    docs: list[RawDoc] = []
    rejected: list[dict] = []
    for i, row in enumerate(rows):
        norm = _normalise_row(row, mapping)
        text = norm.get("text")
        if not text or not str(text).strip():
            rejected.append({"row_index": i, "reason": "missing required field: text", "raw": row})
            continue
        rating = norm.get("rating")
        try:
            rating = int(float(rating)) if rating not in (None, "") else None
        except (ValueError, TypeError):
            rejected.append({"row_index": i, "reason": f"invalid rating value: {rating!r}", "raw": row})
            continue
        docs.append(
            RawDoc(
                external_id=content_hash(str(text)),
                raw_text=str(text),
                author=str(norm.get("author") or "unknown"),
                source_name=source_name,
                rating=rating,
                posted_at=_parse_posted_at(norm.get("posted_at")),
                url=norm.get("url"),
                lang_hint=norm.get("lang"),
                meta={"upload_file": file_label, "row_index": i},
            )
        )

    counts = persist_docs(docs, source_id) if docs else {"fetched": 0, "exact_dupe_skipped": 0, "near_dupe_flagged": 0, "inserted": 0}
    status = "completed" if not rejected else "partial"

    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = now(), status = %s, stage_stats_json = %s WHERE id = %s",
            (status, json.dumps({**counts, "rejected_count": len(rejected)}), run_id),
        )
        conn.commit()

    return {"run_id": run_id, "source_id": source_id, **counts, "rejected_rows": rejected}


def write_rejected_rows_csv(rejected: list[dict], out_path: Path) -> None:
    if not rejected:
        return
    fieldnames = sorted({k for r in rejected for k in ({"row_index", "reason"} | set(r.get("raw", {}).keys()))})
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rejected:
            writer.writerow({"row_index": r["row_index"], "reason": r["reason"], **(r.get("raw") or {})})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--mapping", default=None, help="optional YAML file overriding the auto-suggested column mapping")
    parser.add_argument("--commit", action="store_true", help="without this flag, only preview+validate is printed")
    args = parser.parse_args()

    path = Path(args.file)
    rows = load_rows(path)
    headers = list(rows[0].keys()) if rows else []
    mapping = suggest_mapping(headers)
    if args.mapping:
        with open(args.mapping) as f:
            mapping.update(yaml.safe_load(f))

    print("Suggested/overridden mapping:", json.dumps(mapping, indent=2))
    print("Validation:", json.dumps(validate(rows, mapping, source_name=args.source_name), indent=2, default=str))
    print("Preview (first 5 of up to 20):", json.dumps(preview(rows, mapping)[:5], indent=2, default=str))

    if args.commit:
        result = commit(rows, mapping, source_name=args.source_name, file_label=path.name)
        print("Committed:", json.dumps({k: v for k, v in result.items() if k != "rejected_rows"}, indent=2))
        if result["rejected_rows"]:
            out = path.with_name("rejected_rows.csv")
            write_rejected_rows_csv(result["rejected_rows"], out)
            print(f"{len(result['rejected_rows'])} row(s) rejected — see {out}")


if __name__ == "__main__":
    main()
