"""API surface for the /upload screen (§5). Two calls: preview (parse +
suggest mapping + validate + first-20 preview, nothing persisted) and
commit (actually writes documents, idempotently).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from aisle.ingest.upload import commit as upload_commit
from aisle.ingest.upload import load_rows, preview as upload_preview
from aisle.ingest.upload import suggest_mapping, validate as upload_validate

router = APIRouter(prefix="/upload", tags=["upload"])


class PreviewResponse(BaseModel):
    suggested_mapping: dict[str, str | None]
    validation: dict
    preview_rows: list[dict]


@router.post("/preview", response_model=PreviewResponse)
async def preview_upload(file: UploadFile = File(...), source_name: str = Form(...)) -> PreviewResponse:
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        rows = load_rows(tmp_path)
        headers = list(rows[0].keys()) if rows else []
        mapping = suggest_mapping(headers)
        return PreviewResponse(
            suggested_mapping=mapping,
            validation=upload_validate(rows, mapping, source_name=source_name),
            preview_rows=upload_preview(rows, mapping),
        )
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/commit")
async def commit_upload(file: UploadFile = File(...), source_name: str = Form(...), mapping_json: str = Form(...)) -> dict:
    import json

    mapping = json.loads(mapping_json)
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        rows = load_rows(tmp_path)
        result = upload_commit(rows, mapping, source_name=source_name, file_label=file.filename)
        return result
    finally:
        tmp_path.unlink(missing_ok=True)
