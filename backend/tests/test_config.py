from aisle.settings import codes_taxonomy, get_settings, question_packs_config, scoring_config, sources_config


def test_settings_defaults_to_mock_mode():
    settings = get_settings()
    assert settings.mock_mode is True
    assert settings.mock_llm is True


def test_scoring_config_has_pm_utility_weights_summing_to_one():
    cfg = scoring_config()
    weights = cfg["pm_utility"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_iqs_weights_sum_to_100():
    cfg = scoring_config()
    weights = cfg["iqs"]["weights"]
    assert sum(weights.values()) == 100


def test_sources_config_has_manual_upload():
    cfg = sources_config()
    names = {s["name"] for s in cfg["sources"]}
    assert "manual_upload" in names


def test_question_packs_has_all_eight():
    cfg = question_packs_config()
    assert len(cfg["packs"]) == 8


def test_codes_taxonomy_has_seed_segments():
    cfg = codes_taxonomy()
    assert "habitual_replenisher" in cfg["segments"]
    assert "explorer" in cfg["segments"]
