import json
from pathlib import Path

from ai_material_preprocessor.services.config import DEFAULT_CONFIG, load_config, save_config


def test_load_config_deep_merges_partial_user_values(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"video": {"compression_crf": 28}}), encoding="utf-8")

    config = load_config(path)

    assert config["video"]["compression_crf"] == 28
    assert config["video"]["audio_format"] == DEFAULT_CONFIG["video"]["audio_format"]
    assert "tools" in config
    assert config["document"]["mode"] == "enhanced"
    assert config["document"]["target_tokens"] == 4000
    assert config["document"]["max_tokens"] == 6000
    assert config["document"]["ocr_enabled"] is False
    assert config["video"]["scene_threshold"] == 0.30
    assert config["video"]["max_keyframes"] == 24
    assert config["task_center"]["disk_space_safety_mb"] == 512
    assert config["history"]["retention_days"] == 90
    assert config["history"]["max_size_mb"] == 512


def test_save_config_is_utf8_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = load_config(tmp_path / "missing.json")
    config["video"]["rename_template"] = "{date}_{location}_旅行"

    save_config(config, path)

    assert load_config(path)["video"]["rename_template"] == "{date}_{location}_旅行"
