"""Application entry point."""

from __future__ import annotations

import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from audiotranscriber.app_config import load_app_config
from audiotranscriber.controllers.app_controller import AppController
from audiotranscriber.resources import resource_path
from audiotranscriber.ui.main_window import RecorderStripWindow


def main() -> int:
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("AudioTranscriber")
    app.setApplicationDisplayName("AudioTranscriber")
    app.setOrganizationName("LocalTools")
    app.setWindowIcon(QIcon(str(resource_path("audiotranscriber/assets/app.ico"))))

    config = load_app_config()
    _configure_logging(config)
    window = RecorderStripWindow(config)
    controller = AppController(config, window)
    window.bind_controller(controller)
    window.show()

    return app.exec()


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p("LocalTools.AudioTranscriber")
        )
    except Exception:  # noqa: BLE001
        pass


def _configure_logging(config) -> None:  # noqa: ANN001
    log_dir = (
        Path.cwd() / ".tmp" / "logs"
        if config.profile == "dev"
        else config.model_cache_dir.parent / "logs"
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(
                log_dir / "AudioTranscriber.log",
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            ),
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
