from __future__ import annotations

import contextlib
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[3]
)
LEGACY_CONFIG_PATH = PROJECT_ROOT / "config.json"


def resolve_user_config_path(environ: dict[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    local_app_data = values.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "AI Material Preprocessor" / "config.json"


USER_CONFIG_PATH = resolve_user_config_path()
CONFIG_PATH = USER_CONFIG_PATH

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "schema_version": 3,
        "onboarding_completed": False,
        "theme": "system",
        "update_check_enabled": False,
    },
    "output_folder_name": "AI素材处理结果",
    "history_directory": "",
    "tools": {
        "markitdown": "",
        "ffmpeg": "",
        "ffprobe": "",
        "exiftool": "",
        "libreoffice": "",
        "winword": "",
        "powerpoint": "",
    },
    "video": {
        "compression_crf": 23,
        "compression_preset": "medium",
        "audio_format": "mp3",
        "audio_bitrate": "192k",
        "rename_template": "{date}_{time}_{location}_{index}",
        "project_name": "",
        "organize_mode": "date_location",
        "location_dictionary": {},
        "scene_threshold": 0.30,
        "max_keyframes": 24,
        "contact_sheet_columns": 4,
    },
    "document": {
        "mode": "enhanced",
        "split_enabled": True,
        "target_tokens": 4000,
        "max_tokens": 6000,
        "ocr_enabled": False,
    },
    "task_center": {
        "state_directory": "",
        "disk_space_safety_mb": 512,
    },
    "history": {
        "retention_days": 90,
        "max_size_mb": 512,
    },
}


def coerce_int(value: object, default: int, *, minimum: int | None = None) -> int:
    try:
        converted = int(value) if isinstance(value, (int, str)) else default
    except ValueError:
        converted = default
    return max(minimum, converted) if minimum is not None else converted


def resource_path(*parts: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    return root.joinpath(*parts)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or USER_CONFIG_PATH
    should_migrate = path is None and not config_path.is_file() and LEGACY_CONFIG_PATH.is_file()
    if should_migrate:
        config_path = LEGACY_CONFIG_PATH
    if not config_path.is_file():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            user_config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(user_config, dict):
        return copy.deepcopy(DEFAULT_CONFIG)
    merged = _deep_merge(DEFAULT_CONFIG, user_config)
    if should_migrate:
        with contextlib.suppress(OSError):
            save_config(merged, USER_CONFIG_PATH)
    return merged


def save_config(config: dict[str, Any], path: Path | None = None) -> Path:
    config_path = path or USER_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, config_path)
    return config_path
