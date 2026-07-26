from aisle.qa.agent import answer_question


def test_agent_refuses_on_nonsense_query_with_too_little_evidence():
    result = answer_question("xqzflorptronium banana zylophone quantum kettle 999")
    assert result["refused"] is True
    assert "don't have enough evidence" in result["answer"]


def test_agent_answers_with_citations_on_a_real_question():
    result = answer_question("Why do users reorder their usual basket every week?")
    assert result["refused"] is False
    assert len(result["citations"]) > 0
    for c in result["citations"]:
        assert "document_id" in c and "quote" in c


def test_agent_triggers_segment_comparison_tool_on_comparison_question():
    result = answer_question("Compare habitual_replenisher vs explorer — which segment is more likely to try new categories?")
    assert result["refused"] is False
    assert "run_segment_comparison" in result.get("tool_outputs", {})


def test_agent_triggers_prevalence_tool_on_how_many_question():
    result = answer_question("How many documents mention freshness concerns?")
    assert result["refused"] is False
    assert "compute_prevalence" in result.get("tool_outputs", {})
