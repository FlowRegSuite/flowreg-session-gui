from __future__ import annotations

from pathlib import Path
from typing import Any

from .pyflowreg_api import get_session_config_class
from .serialization import serialize_config_to_yaml


def load_config_from_file(path: str | Path, session_config_cls: type[Any] | None = None) -> Any:
    cls = session_config_cls or get_session_config_class()
    return cls.from_file(str(path))


def save_config_to_yaml(config: Any, path: str | Path, prefer_relative: bool = True) -> None:
    serialize_config_to_yaml(config, path, prefer_relative=prefer_relative)
