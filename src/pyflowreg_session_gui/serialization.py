from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .model_utils import model_to_dict

RELATIVE_PATH_FIELDS = {"output_root", "final_results", "center"}


def _convert_paths_to_strings(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _convert_paths_to_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_convert_paths_to_strings(v) for v in value]
    if isinstance(value, tuple):
        return [_convert_paths_to_strings(v) for v in value]
    return value


def _maybe_relative(path_value: Any, root_path: Path | None, prefer_relative: bool) -> Any:
    if not prefer_relative or root_path is None or not isinstance(path_value, str):
        return path_value

    candidate = Path(path_value)
    if not candidate.is_absolute() or not root_path.is_absolute():
        return path_value

    try:
        return str(candidate.relative_to(root_path))
    except ValueError:
        return path_value


def serialize_config_to_yaml(config: Any, path: str | Path, prefer_relative: bool = True) -> None:
    """Serialize SessionConfig-like model to YAML, preserving relative paths under root when possible."""

    output_path = Path(path)
    data = _convert_paths_to_strings(model_to_dict(config))

    root_path: Path | None = None
    root_raw = data.get("root") if isinstance(data, dict) else None
    if isinstance(root_raw, str) and root_raw:
        root_path = Path(root_raw)

    if isinstance(data, dict):
        for field_name in RELATIVE_PATH_FIELDS:
            if field_name in data:
                data[field_name] = _maybe_relative(data[field_name], root_path, prefer_relative)

        flow_options = data.get("flow_options")
        if isinstance(flow_options, str):
            data["flow_options"] = _maybe_relative(flow_options, root_path, prefer_relative)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)
