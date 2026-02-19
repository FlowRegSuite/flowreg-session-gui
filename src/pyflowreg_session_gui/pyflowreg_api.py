from __future__ import annotations

from pathlib import Path
from typing import Any


def get_session_config_class() -> type[Any]:
    from pyflowreg.session.config import SessionConfig

    return SessionConfig


def load_session_config(path: str | Path) -> Any:
    session_config_cls = get_session_config_class()
    return session_config_cls.from_file(str(path))


def discover_input_files_for_config(config: Any) -> list[Path]:
    from pyflowreg.session.stage1_compensate import discover_input_files

    return list(discover_input_files(config))
