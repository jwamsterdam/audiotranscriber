"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from audiotranscriber.controllers.app_controller import AppController
from audiotranscriber.ui.main_window import RecorderStripWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AudioTranscriber")
    app.setOrganizationName("LocalTools")

    window = RecorderStripWindow()
    controller = AppController(window)
    window.bind_controller(controller)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

