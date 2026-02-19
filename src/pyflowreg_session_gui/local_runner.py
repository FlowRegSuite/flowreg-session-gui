from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, Signal

from .serialization import serialize_config_to_yaml

RUNNER_SCRIPT = r"""
import sys

from pyflowreg.session.config import SessionConfig
from pyflowreg.session.stage1_compensate import run_stage1
from pyflowreg.session.stage2_between_avgs import run_stage2
from pyflowreg.session.stage3_valid_mask import run_stage3


def main() -> None:
    cfg_path = sys.argv[1]
    mode = sys.argv[2]
    config = SessionConfig.from_file(cfg_path)
    print(f"Loaded config: {cfg_path}", flush=True)

    if mode == "all":
        print("Running Stage1", flush=True)
        run_stage1(config)
        print("Running Stage2", flush=True)
        middle_idx, avg, displacements = run_stage2(config)
        del avg
        print(f"Running Stage3 (middle_idx={middle_idx})", flush=True)
        run_stage3(config, middle_idx, displacements)
        print("Completed Stage1 -> Stage2 -> Stage3", flush=True)
        return

    if mode == "stage1":
        run_stage1(config)
        print("Completed Stage1", flush=True)
        return

    if mode == "stage2":
        middle_idx, avg, displacements = run_stage2(config)
        del avg, displacements
        print(f"Completed Stage2 (middle_idx={middle_idx})", flush=True)
        return

    if mode == "stage3":
        middle_idx, avg, displacements = run_stage2(config)
        del avg
        run_stage3(config, middle_idx, displacements)
        print("Completed Stage3 (after Stage2 preload)", flush=True)
        return

    raise ValueError(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
"""


class LocalRunner(QObject):
    log_emitted = Signal(str)
    run_started = Signal()
    run_finished = Signal(int)
    run_failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None

    def is_running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.NotRunning

    def terminate(self) -> None:
        if self._process is not None:
            self._process.kill()

    def start(self, config: Any, mode: str) -> None:
        if self.is_running():
            raise RuntimeError("A local run is already in progress.")

        self._tmpdir = tempfile.TemporaryDirectory(prefix="pyflowreg_session_gui_")
        config_path = Path(self._tmpdir.name) / "session_config.yaml"
        serialize_config_to_yaml(config, config_path, prefer_relative=True)

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(["-u", "-c", RUNNER_SCRIPT, str(config_path), mode])

        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        process.finished.connect(self._on_finished)

        self._process = process
        process.start()

        if not process.waitForStarted(5000):
            self._cleanup()
            raise RuntimeError("Failed to start local worker subprocess.")

        self.run_started.emit()

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.log_emitted.emit(data.rstrip("\n"))

    def _on_stderr(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        if data:
            self.log_emitted.emit(f"[stderr] {data.rstrip()}")

    def _on_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        if exit_code != 0:
            self.run_failed.emit(f"Local run failed with exit code {exit_code}.")
        self.run_finished.emit(exit_code)
        self._cleanup()

    def _cleanup(self) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
        self._tmpdir = None
        self._process = None
