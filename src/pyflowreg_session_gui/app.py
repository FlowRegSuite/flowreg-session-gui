from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .main_window import MainWindow
from .state import AppState


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    try:
        window = MainWindow(AppState())
    except Exception as exc:
        QMessageBox.critical(None, "Startup Error", str(exc))
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
