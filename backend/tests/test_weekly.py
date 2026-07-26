from aisle.jobs.weekly import run_weekly_job


def test_weekly_job_runs_end_to_end_and_produces_a_digest(tmp_path):
    digest_path = tmp_path / "digest.md"
    result = run_weekly_job(digest_path=str(digest_path))

    assert result["status"] in ("completed", "partial")
    assert "digest" in result
    assert result["digest"].startswith("# AISLE weekly digest")
    assert isinstance(result["alerts"], list)
    assert digest_path.exists()
    assert digest_path.read_text() == result["digest"]


def test_weekly_job_is_resumable_on_a_second_run():
    first = run_weekly_job()
    second = run_weekly_job()
    assert second["run_id"] > first["run_id"]
    assert second["status"] in ("completed", "partial")
