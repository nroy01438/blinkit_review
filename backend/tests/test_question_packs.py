import pytest

from aisle.qa.question_packs import PACK_FUNCTIONS, list_packs, run_pack


def test_list_packs_has_all_eight():
    packs = list_packs()
    assert len(packs) == 8
    assert set(p["id"] for p in packs) == set(PACK_FUNCTIONS.keys())


@pytest.mark.parametrize("pack_id", list(PACK_FUNCTIONS.keys()))
def test_every_pack_runs_and_returns_the_common_envelope(pack_id):
    result = run_pack(pack_id)
    assert "generated_at" in result
    assert "answer_summary" in result
    assert isinstance(result["answer_summary"], str)
    assert "n" in result
    assert "top_quotes" in result


def test_run_pack_rejects_unknown_id():
    with pytest.raises(ValueError):
        run_pack("not_a_real_pack")
