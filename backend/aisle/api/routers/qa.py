from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from aisle.qa.agent import answer_question
from aisle.qa.question_packs import list_packs, run_pack

router = APIRouter(tags=["qa"])


class AskRequest(BaseModel):
    question: str


@router.post("/ask")
def ask(payload: AskRequest) -> dict:
    return answer_question(payload.question)


@router.get("/question-packs")
def get_question_packs() -> list[dict]:
    return list_packs()


@router.get("/question-packs/{pack_id}/run")
def run_question_pack(pack_id: str) -> dict:
    try:
        return run_pack(pack_id)
    except ValueError as e:
        return {"error": str(e)}
