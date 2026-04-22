"""Floating recorder strip window."""

from __future__ import annotations

import ctypes
import sys
from html import escape
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QSizePolicy,
    QSpacerItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from audiotranscriber.app_config import AppConfig
from audiotranscriber.controllers.app_controller import AppController
from audiotranscriber.pipelines.recording import MicrophoneDevice
from audiotranscriber.resources import resource_path
from audiotranscriber.state import (
    InputSource,
    PreviewKind,
    RecorderState,
    RecorderStatus,
    TranscriptionLanguage,
)
from audiotranscriber.update_checker import UpdateInfo
from audiotranscriber.ui.widgets import (
    GREEN,
    RED,
    YELLOW,
    IconKind,
    PrimaryRecordButton,
    StripIconButton,
    WaveformWidget,
)

COLLAPSED_WIDTH = 560
EXPANDED_WIDTH = 780
SNAP_TOP_DISTANCE = 18
UNSNAP_PULL_DISTANCE = 34


class RecorderStripWindow(QMainWindow):
    """Compact always-on-top friendly recorder strip."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._controller: AppController | None = None
        self._drag_position = None
        self._snapped_to_top = False
        self._snap_screen_top = 0
        self._size_animation: QPropertyAnimation | None = None
        self._panel_animation: QPropertyAnimation | None = None
        self._audio_output = None
        self._media_player = None
        self._last_preview_render_key: tuple[PreviewKind, str] | None = None

        self.setWindowTitle("AudioTranscriber")
        self.setWindowIcon(QIcon(str(resource_path("audiotranscriber/assets/app.ico"))))
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(COLLAPSED_WIDTH)
        self.setMaximumWidth(1040)
        self.resize(COLLAPSED_WIDTH, 64)
        self.setFixedHeight(64)

        root = QWidget(self)
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.strip = QFrame(root)
        self.strip.setObjectName("strip")
        self.strip.setFixedHeight(64)
        strip_layout = QHBoxLayout(self.strip)
        strip_layout.setContentsMargins(20, 4, 18, 4)
        strip_layout.setSpacing(10)

        self.waveform = WaveformWidget(self.strip)
        self.waveform.set_compact(True)
        self.timer_label = QLabel("00:00:00", self.strip)
        self.timer_label.setObjectName("timerLabel")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setFixedWidth(84)
        self.language_button = QToolButton(self.strip)
        self.language_button.setObjectName("languageButton")
        self.language_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.language_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.language_button.setFixedWidth(64)
        self.language_menu = QMenu(self.language_button)
        self.language_menu.setObjectName("languageMenu")
        self.language_actions = QActionGroup(self.language_menu)
        self.language_actions.setExclusive(True)
        self._language_action_by_value: dict[str, QAction] = {}
        for label, language in (
            ("AUTO", TranscriptionLanguage.AUTO),
            ("NL", TranscriptionLanguage.DUTCH),
            ("EN", TranscriptionLanguage.ENGLISH),
        ):
            action = QAction(label, self.language_menu)
            action.setCheckable(True)
            action.setData(language.value)
            action.triggered.connect(self._language_changed)
            self.language_actions.addAction(action)
            self.language_menu.addAction(action)
            self._language_action_by_value[language.value] = action
        self.language_button.setMenu(self.language_menu)
        self._set_language_button_text(TranscriptionLanguage.AUTO)
        self.stop_button = StripIconButton(IconKind.STOP, self.strip)
        self.pause_button = StripIconButton(IconKind.PAUSE, self.strip)
        self.record_button = PrimaryRecordButton(self.strip)
        self.expand_button = StripIconButton(IconKind.EXPAND, self.strip)

        separator = QFrame(self.strip)
        separator.setObjectName("separator")
        separator.setFixedWidth(1)
        separator.setFixedHeight(30)

        strip_layout.addWidget(self.waveform, 1, Qt.AlignmentFlag.AlignVCenter)
        strip_layout.addWidget(self.timer_label, 0, Qt.AlignmentFlag.AlignVCenter)
        strip_layout.addWidget(self.language_button, 0, Qt.AlignmentFlag.AlignVCenter)
        strip_layout.addWidget(separator, 0, Qt.AlignmentFlag.AlignVCenter)
        strip_layout.addWidget(self.stop_button, 0, Qt.AlignmentFlag.AlignVCenter)
        strip_layout.addWidget(self.pause_button, 0, Qt.AlignmentFlag.AlignVCenter)
        strip_layout.addWidget(self.record_button, 0, Qt.AlignmentFlag.AlignVCenter)
        strip_layout.addWidget(self.expand_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.transcript_panel = QFrame(root)
        self.transcript_panel.setObjectName("transcriptPanel")
        self.transcript_panel.setMaximumHeight(0)
        self.transcript_panel.setMinimumHeight(0)
        self.panel_layout = QVBoxLayout(self.transcript_panel)
        self.panel_layout.setContentsMargins(28, 18, 28, 22)
        self.panel_layout.setSpacing(12)

        panel_header = QHBoxLayout()
        panel_header.setSpacing(10)
        self.preview_dot = QLabel(self.transcript_panel)
        self.preview_dot.setObjectName("previewDot")
        self.preview_dot.setFixedSize(11, 11)
        self.preview_status = QLabel("Verwerken...", self.transcript_panel)
        self.preview_status.setObjectName("previewStatus")
        self.preview_age = QLabel("(laatste update: 5s geleden)", self.transcript_panel)
        self.preview_age.setObjectName("previewAge")
        panel_header.addWidget(self.preview_dot)
        panel_header.addWidget(self.preview_status)
        panel_header.addWidget(self.preview_age)
        panel_header.addItem(QSpacerItem(20, 1, QSizePolicy.Policy.Expanding))

        self.progress_bar = QProgressBar(self.transcript_panel)
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.hide()

        self.transcript_text = QTextEdit(self.transcript_panel)
        self.transcript_text.setObjectName("transcriptText")
        self.transcript_text.setReadOnly(True)
        self.transcript_text.setAcceptRichText(True)
        self.transcript_text.setFrameShape(QFrame.Shape.NoFrame)
        self.transcript_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.transcript_text.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        self.panel_layout.addLayout(panel_header)
        self.panel_layout.addWidget(self.progress_bar)
        self.panel_layout.addWidget(self.transcript_text)

        layout.addWidget(self.strip)
        layout.addWidget(self.transcript_panel)
        layout.setStretch(0, 0)
        layout.setStretch(1, 1)
        self.setCentralWidget(root)

        self._apply_styles()
        self._connect_buttons()

    def bind_controller(self, controller: AppController) -> None:
        self._controller = controller
        controller.state_changed.connect(self.apply_state)
        controller.update_check_finished.connect(self._handle_update_check_finished)
        controller.update_check_failed.connect(self._handle_update_check_failed)
        controller.model_cache_refresh_finished.connect(self._handle_model_cache_refresh_finished)
        controller.model_cache_refresh_failed.connect(self._handle_model_cache_refresh_failed)
        controller.emit_current_state()

    def apply_state(self, state: RecorderState) -> None:
        self.record_button.set_status(state.status)
        self.waveform.set_status(state.status)
        self.waveform.set_level(state.audio_level)
        self.timer_label.setText(self._format_elapsed(state.elapsed_seconds))
        self.record_button.setEnabled(
            state.status
            not in {
                RecorderStatus.RECORDING,
                RecorderStatus.PROCESSING,
            }
        )
        self._apply_language_state(state)
        self._set_transcript_text(state.preview_text, state.preview_kind)
        self.expand_button.set_kind(IconKind.COLLAPSE if state.transcript_open else IconKind.EXPAND)
        self.strip.setProperty("expanded", state.transcript_open)
        self.strip.style().unpolish(self.strip)
        self.strip.style().polish(self.strip)

        panel_target = self._expanded_panel_height() if state.transcript_open else 0
        width_target = EXPANDED_WIDTH if state.transcript_open else COLLAPSED_WIDTH
        self.waveform.set_compact(not state.transcript_open)
        if self.transcript_panel.maximumHeight() != panel_target:
            self._animate_layout(panel_target, width_target)
        elif self.width() != width_target:
            self._animate_window_width(width_target)

        if state.status == RecorderStatus.RECORDING:
            self.progress_bar.hide()
            self.preview_status.setText("Opnemen...")
            source = {
                InputSource.TEST_TONE: "testtoon",
                InputSource.MICROPHONE: "microfoon",
                InputSource.DEV_SAMPLE: "dev sample",
            }[state.input_source]
            if state.transcription_total_chunks:
                live_progress = (
                    f", live chunk {state.transcription_current_chunk}/"
                    f"{state.transcription_total_chunks}"
                )
            else:
                live_progress = ""
            self.preview_age.setText(f"({source}, WAV 16 kHz mono{live_progress})")
        elif state.status == RecorderStatus.PROCESSING:
            age = state.last_update_seconds if state.last_update_seconds is not None else 0
            self.progress_bar.show()
            status_label = state.processing_label or "Transcriberen..."
            if state.transcription_total_chunks:
                progress = state.processing_progress_text or (
                    f"chunk {state.transcription_current_chunk}/"
                    f"{state.transcription_total_chunks}"
                )
                self.progress_bar.setRange(0, state.transcription_total_chunks)
                self.progress_bar.setValue(state.transcription_current_chunk)
            else:
                progress = state.processing_progress_text or "bezig"
                self.progress_bar.setRange(0, 0)
            self.preview_status.setText(status_label)
            self.preview_age.setText(f"({progress}, laatste update: {age}s geleden)")
        elif state.status == RecorderStatus.PAUSED:
            self.progress_bar.hide()
            self.preview_status.setText("Gepauzeerd")
            self.preview_age.setText("(opname tijdelijk stilgezet)")
        else:
            self.progress_bar.hide()
            self.preview_status.setText("Klaar")
            self.preview_age.setText("(wacht op opname)")

        self._set_status_color(state.status)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            screen = self.screen() or QApplication.primaryScreen()
            if screen is not None:
                self._snap_screen_top = screen.availableGeometry().top()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            target = event.globalPosition().toPoint() - self._drag_position
            screen = QApplication.screenAt(event.globalPosition().toPoint()) or self.screen()
            if screen is None:
                self.move(target)
                event.accept()
                return

            available = screen.availableGeometry()
            if self._snapped_to_top:
                if target.y() > self._snap_screen_top + UNSNAP_PULL_DISTANCE:
                    self._snapped_to_top = False
                    self.move(target)
                else:
                    self.move(target.x(), available.top())
            elif target.y() <= available.top() + SNAP_TOP_DISTANCE:
                self._snapped_to_top = True
                self._snap_screen_top = available.top()
                self.move(target.x(), available.top())
            else:
                self.move(target)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = None
            event.accept()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        _enable_windows_taskbar_minimize(self)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.setObjectName("contextMenu")

        self._add_microphone_device_actions(menu)

        if self._config.show_input_selector:
            self._add_input_source_actions(menu)

        if self._config.show_dev_samples:
            self._add_dev_sample_actions(menu)

        open_folder_action = QAction("Open recordings folder", menu)
        open_folder_action.triggered.connect(self._open_recordings_folder)
        menu.addAction(open_folder_action)

        menu.addSeparator()

        export_mp3_action = QAction("WAV to MP3 Backup", menu)
        export_mp3_action.setEnabled(
            self._controller is not None
            and self._controller.state.status
            not in {
                RecorderStatus.RECORDING,
                RecorderStatus.PAUSED,
                RecorderStatus.PROCESSING,
            }
        )
        export_mp3_action.triggered.connect(self._select_wav_for_mp3_backup)
        menu.addAction(export_mp3_action)

        high_quality_action = QAction("WAV to High Quality Transcript", menu)
        high_quality_action.setEnabled(export_mp3_action.isEnabled())
        high_quality_action.triggered.connect(self._select_wav_for_high_quality_transcript)
        menu.addAction(high_quality_action)

        menu.addSeparator()

        if self._config.enable_update_check:
            update_action = QAction("Check for updates", menu)
            update_action.triggered.connect(self._check_for_updates)
            menu.addAction(update_action)

            refresh_models_action = QAction("Refresh transcription models", menu)
            refresh_models_action.setEnabled(
                self._controller is not None
                and self._controller.state.status
                not in {
                    RecorderStatus.RECORDING,
                    RecorderStatus.PAUSED,
                    RecorderStatus.PROCESSING,
                }
            )
            refresh_models_action.triggered.connect(self._refresh_transcription_models)
            menu.addAction(refresh_models_action)
            menu.addSeparator()

        diagnostics_action = QAction("Show settings and diagnostics", menu)
        diagnostics_action.setEnabled(self._controller is not None)
        diagnostics_action.triggered.connect(self._show_microphone_diagnostics)
        menu.addAction(diagnostics_action)

        menu.addSeparator()

        minimize_action = QAction("Minimize app", menu)
        minimize_action.triggered.connect(self.showMinimized)
        menu.addAction(minimize_action)

        close_action = QAction("Close app", menu)
        close_action.triggered.connect(self.close)
        menu.addAction(close_action)

        menu.exec(event.globalPos())

    def _add_input_source_actions(self, menu: QMenu) -> None:
        if self._config.show_test_tone:
            test_tone_action = QAction("Use test tone input", menu)
            test_tone_action.setCheckable(True)
            test_tone_action.setChecked(
                self._controller is not None
                and self._controller.state.input_source == InputSource.TEST_TONE
            )
            test_tone_action.triggered.connect(
                lambda: self._controller
                and self._controller.set_input_source(InputSource.TEST_TONE)
            )
            menu.addAction(test_tone_action)

        if self._config.show_dev_samples:
            dev_sample_input_action = QAction("Use dev sample input", menu)
            dev_sample_input_action.setCheckable(True)
            dev_sample_input_action.setChecked(
                self._controller is not None
                and self._controller.state.input_source == InputSource.DEV_SAMPLE
            )
            dev_sample_input_action.setEnabled(self._controller is not None)
            dev_sample_input_action.triggered.connect(
                lambda: self._controller
                and self._controller.set_input_source(InputSource.DEV_SAMPLE)
            )
            menu.addAction(dev_sample_input_action)

        menu.addSeparator()

    def _add_microphone_device_actions(self, menu: QMenu) -> None:
        microphone_menu = QMenu("Microphone input", menu)
        microphone_menu.setObjectName("contextMenu")
        action_group = QActionGroup(microphone_menu)
        action_group.setExclusive(True)

        busy = (
            self._controller is None
            or self._controller.state.status
            in {
                RecorderStatus.RECORDING,
                RecorderStatus.PAUSED,
                RecorderStatus.PROCESSING,
            }
        )

        auto_action = QAction("Auto-detect", microphone_menu)
        auto_action.setCheckable(True)
        auto_action.setChecked(
            self._controller is not None
            and self._controller.state.input_source == InputSource.MICROPHONE
            and self._controller.state.selected_microphone_device_key is None
        )
        auto_action.setEnabled(not busy)
        auto_action.triggered.connect(
            lambda: self._controller and self._controller.set_microphone_device(None)
        )
        action_group.addAction(auto_action)
        microphone_menu.addAction(auto_action)

        devices = self._controller.microphone_devices() if self._controller is not None else []
        if devices:
            microphone_menu.addSeparator()
            for device in devices:
                device_action = QAction(device.label.replace("&", "&&"), microphone_menu)
                device_action.setCheckable(True)
                device_action.setChecked(
                    self._controller is not None
                    and self._controller.state.input_source == InputSource.MICROPHONE
                    and self._controller.state.selected_microphone_device_key == device.key
                )
                device_action.setEnabled(not busy)
                device_action.triggered.connect(
                    lambda _checked=False, key=device.key: self._controller
                    and self._controller.set_microphone_device(key)
                )
                action_group.addAction(device_action)
                microphone_menu.addAction(device_action)
        else:
            no_devices_action = QAction("No input devices found", microphone_menu)
            no_devices_action.setEnabled(False)
            microphone_menu.addAction(no_devices_action)

        menu.addMenu(microphone_menu)
        menu.addSeparator()

    def _add_dev_sample_actions(self, menu: QMenu) -> None:
        select_sample_action = QAction("Select dev sample", menu)
        select_sample_action.setEnabled(self._controller is not None)
        select_sample_action.triggered.connect(self._select_dev_sample)
        menu.addAction(select_sample_action)

        play_sample_action = QAction("Play dev sample", menu)
        play_sample_action.setEnabled(self._dev_sample_path() is not None)
        play_sample_action.triggered.connect(self._play_dev_sample)
        menu.addAction(play_sample_action)

        stop_sample_action = QAction("Stop dev sample", menu)
        stop_sample_action.setEnabled(self._dev_sample_is_playing())
        stop_sample_action.triggered.connect(self._stop_dev_sample)
        menu.addAction(stop_sample_action)
        menu.addSeparator()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._controller is not None:
            self._controller.shutdown()
        app = QApplication.instance()
        if app is not None:
            app.quit()
        super().closeEvent(event)

    def _connect_buttons(self) -> None:
        self.record_button.clicked.connect(self._record_clicked)
        self.pause_button.clicked.connect(self._pause_clicked)
        self.stop_button.clicked.connect(self._stop_clicked)
        self.expand_button.clicked.connect(lambda: self._controller and self._controller.toggle_transcript())

    def _set_status_color(self, status: RecorderStatus) -> None:
        if status == RecorderStatus.RECORDING:
            color = RED.name()
        elif status in {RecorderStatus.PROCESSING, RecorderStatus.PAUSED}:
            color = YELLOW.name()
        else:
            color = GREEN.name()

        self.preview_dot.setStyleSheet(
            "#previewDot {"
            f"background: {color};"
            "border-radius: 5px;"
            "}"
        )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#root {
                background: transparent;
                color: #f7f8f8;
                font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
            }

            QFrame#strip {
                background: #151a1d;
                border-radius: 34px;
            }

            QFrame#strip[expanded="true"] {
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom-left-radius: 0;
                border-bottom-right-radius: 0;
                margin-bottom: 0;
            }

            QFrame#separator {
                background: rgba(255, 255, 255, 0.14);
            }

            QLabel#timerLabel {
                color: #ffffff;
                font-size: 15px;
                font-weight: 500;
                min-width: 84px;
                max-width: 84px;
            }

            QToolButton#languageButton {
                background: rgba(255, 255, 255, 0.08);
                color: #f7f8f8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px 0;
                font-size: 12px;
                font-weight: 700;
            }

            QToolButton#languageButton:disabled {
                color: rgba(247, 248, 248, 0.48);
            }

            QToolButton#languageButton::menu-indicator {
                image: none;
                width: 0;
            }

            QMenu#languageMenu {
                background: #151a1d;
                color: #f7f8f8;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                padding: 6px;
            }

            QMenu#languageMenu::item {
                padding: 8px 20px;
                border-radius: 6px;
            }

            QMenu#languageMenu::item:selected {
                background: rgba(255, 255, 255, 0.12);
            }

            QFrame#transcriptPanel {
                background: #151a1d;
                border-top: none;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
                margin-top: -1px;
            }

            QLabel#previewStatus {
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
            }

            QLabel#previewAge {
                color: #c8cdd0;
                font-size: 14px;
                font-weight: 400;
            }

            QProgressBar#progressBar {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 3px;
            }

            QProgressBar#progressBar::chunk {
                background: #f7c331;
                border-radius: 3px;
            }

            QLabel#transcriptText {
                color: #ffffff;
                font-size: 17px;
                line-height: 1.45;
                font-weight: 500;
            }

            QTextEdit#transcriptText {
                background: transparent;
                color: #ffffff;
                border: none;
                font-size: 17px;
                font-weight: 500;
                selection-background-color: rgba(255, 255, 255, 0.18);
            }

            QTextEdit#transcriptText QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0;
            }

            QTextEdit#transcriptText QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.24);
                border-radius: 4px;
                min-height: 28px;
            }

            QTextEdit#transcriptText QScrollBar::add-line:vertical,
            QTextEdit#transcriptText QScrollBar::sub-line:vertical {
                height: 0;
            }

            QMenu#contextMenu {
                background: #151a1d;
                color: #f7f8f8;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                padding: 6px;
            }

            QMenu#contextMenu::item {
                padding: 8px 20px;
                border-radius: 6px;
            }

            QMenu#contextMenu::item:selected {
                background: rgba(255, 255, 255, 0.12);
            }

            QMenu#contextMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.18);
                margin: 6px 8px;
            }
            """
        )

    def _expanded_panel_height(self) -> int:
        return 380

    def _open_recordings_folder(self) -> None:
        if self._controller is None:
            return
        path = self._controller.recordings_dir
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _check_for_updates(self) -> None:
        if self._controller is None:
            return

        self._controller.check_for_updates()

    def _refresh_transcription_models(self) -> None:
        if self._controller is None:
            return

        result = QMessageBox.question(
            self,
            "Refresh transcription models",
            (
                "Clear the local Whisper model cache?\n\n"
                "The live and high-quality transcription models will be downloaded again. "
                "This can help if model files are missing or outdated."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        self._controller.refresh_transcription_models()

    def _show_microphone_diagnostics(self) -> None:
        if self._controller is None:
            return

        dialog = DiagnosticsDialog(self._controller, self)
        dialog.exec()

    def _handle_update_check_finished(self, info: UpdateInfo) -> None:
        if info.error:
            QMessageBox.warning(
                self,
                "Check for updates",
                f"{info.error}\n\n{info.model_cache_summary}",
            )
            return

        latest = info.latest_version or "unknown"
        if info.update_available:
            result = QMessageBox.question(
                self,
                "Update available",
                (
                    f"A new AudioTranscriber version is available.\n\n"
                    f"Current version: {info.current_version}\n"
                    f"Latest version: {latest}\n\n"
                    f"{info.model_cache_summary}\n\n"
                    "Open the GitHub release page?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if result == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl(info.release_url))
            return

        QMessageBox.information(
            self,
            "AudioTranscriber is up to date",
            (
                f"You are using the latest available version.\n\n"
                f"Current version: {info.current_version}\n"
                f"Latest version: {latest}\n\n"
                f"{info.model_cache_summary}"
            ),
        )

    def _handle_update_check_failed(self, error: str) -> None:
        QMessageBox.warning(self, "Check for updates", error)

    def _handle_model_cache_refresh_finished(self, message: str) -> None:
        QMessageBox.information(self, "Refresh transcription models", message)

    def _handle_model_cache_refresh_failed(self, error: str) -> None:
        QMessageBox.warning(self, "Refresh transcription models", error)

    def _select_dev_sample(self) -> None:
        if self._controller is None:
            return

        samples_dir = self._controller.dev_samples_dir
        samples_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select dev audio sample",
            str(samples_dir.resolve()),
            "Audio files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg)",
        )
        if file_path:
            self._controller.select_dev_sample(Path(file_path))

    def _select_wav_for_mp3_backup(self) -> None:
        path = self._select_recording_wav("Select WAV for MP3 Backup")
        if path is not None and self._controller is not None:
            self._controller.export_mp3_backup_for(path)

    def _select_wav_for_high_quality_transcript(self) -> None:
        path = self._select_recording_wav("Select WAV for High Quality Transcript")
        if path is not None and self._controller is not None:
            language = self._selected_transcription_language()
            if not self._confirm_high_quality_language(language):
                return
            self._controller.set_transcription_language(language)
            self._controller.create_high_quality_transcript_for(path)

    def _select_recording_wav(self, title: str) -> Path | None:
        if self._controller is None:
            return None

        recordings_dir = self._controller.recordings_dir
        recordings_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            str(recordings_dir.resolve()),
            "WAV recordings (*.wav)",
        )
        if not file_path:
            return None
        return Path(file_path)

    def _play_dev_sample(self) -> None:
        path = self._dev_sample_path()
        if path is None or not path.exists():
            return

        media_player = self._ensure_media_player()
        media_player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        media_player.play()

    def _stop_dev_sample(self) -> None:
        if self._media_player is not None:
            self._media_player.stop()

    def _dev_sample_is_playing(self) -> bool:
        if self._media_player is None:
            return False
        stopped = type(self._media_player).PlaybackState.StoppedState
        return self._media_player.playbackState() != stopped

    def _ensure_media_player(self):  # noqa: ANN202
        if self._media_player is None:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            self._audio_output = QAudioOutput(self)
            self._audio_output.setVolume(0.8)
            self._media_player = QMediaPlayer(self)
            self._media_player.setAudioOutput(self._audio_output)
        return self._media_player

    def _record_clicked(self) -> None:
        if self._controller is None:
            return

        previous_status = self._controller.state.status
        self._controller.record()
        if self._controller.state.status == RecorderStatus.RECORDING:
            if self._controller.state.input_source == InputSource.DEV_SAMPLE:
                if previous_status == RecorderStatus.PAUSED:
                    self._ensure_media_player().play()
                else:
                    self._play_dev_sample()
            else:
                self._stop_dev_sample()

    def _pause_clicked(self) -> None:
        if self._controller is None:
            return

        was_recording_dev_sample = (
            self._controller.state.status == RecorderStatus.RECORDING
            and self._controller.state.input_source == InputSource.DEV_SAMPLE
        )
        was_paused_dev_sample = (
            self._controller.state.status == RecorderStatus.PAUSED
            and self._controller.state.input_source == InputSource.DEV_SAMPLE
        )
        self._controller.pause()
        if was_recording_dev_sample:
            self._ensure_media_player().pause()
        elif was_paused_dev_sample and self._controller.state.status == RecorderStatus.RECORDING:
            self._ensure_media_player().play()

    def _stop_clicked(self) -> None:
        if self._controller is None:
            return

        was_recording_dev_sample = (
            self._controller.state.status == RecorderStatus.RECORDING
            and self._controller.state.input_source == InputSource.DEV_SAMPLE
        )
        self._controller.stop()
        if was_recording_dev_sample:
            self._stop_dev_sample()

    def _dev_sample_path(self) -> Path | None:
        if self._controller is None:
            return None

        sample_path = self._controller.state.selected_dev_sample_path
        if sample_path is None:
            return None
        return Path(sample_path)

    def _apply_language_state(self, state: RecorderState) -> None:
        self.language_button.setEnabled(
            state.status not in {
                RecorderStatus.PROCESSING,
            }
        )
        self._set_language_button_text(state.transcription_language)

    def _language_changed(self) -> None:
        if self._controller is None:
            return

        language = self._selected_transcription_language()
        self._controller.set_transcription_language(language)

    def _selected_transcription_language(self) -> TranscriptionLanguage:
        checked_action = self.language_actions.checkedAction()
        value = checked_action.data() if checked_action is not None else TranscriptionLanguage.AUTO.value
        try:
            return TranscriptionLanguage(value)
        except ValueError:
            return TranscriptionLanguage.AUTO

    def _set_language_button_text(self, language: TranscriptionLanguage) -> None:
        action = self._language_action_by_value.get(language.value)
        if action is not None and not action.isChecked():
            action.setChecked(True)
        self.language_button.setText(
            {
                TranscriptionLanguage.AUTO: "AUTO",
                TranscriptionLanguage.DUTCH: "NL",
                TranscriptionLanguage.ENGLISH: "EN",
            }[language]
        )

    def _confirm_high_quality_language(self, language: TranscriptionLanguage) -> bool:
        label = {
            TranscriptionLanguage.AUTO: "AUTO (automatic detection)",
            TranscriptionLanguage.DUTCH: "NL (Dutch)",
            TranscriptionLanguage.ENGLISH: "EN (English)",
        }[language]
        result = QMessageBox.question(
            self,
            "Confirm transcript language",
            (
                "Create a high-quality transcript with this language setting?\n\n"
                f"Language: {label}"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return result == QMessageBox.StandardButton.Yes

    def _set_transcript_text(self, text: str, kind: PreviewKind) -> None:
        render_key = (kind, text)
        if self._last_preview_render_key == render_key:
            return

        self._last_preview_render_key = render_key
        scrollbar = self.transcript_text.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        if kind == PreviewKind.TRANSCRIPT:
            self.transcript_text.setPlainText(text)
        else:
            self.transcript_text.setHtml(self._render_preview_message(text, kind))
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    @staticmethod
    def _render_preview_message(text: str, kind: PreviewKind) -> str:
        is_error = kind == PreviewKind.ERROR
        paragraphs = text.strip() or "Geen extra details."
        paragraph_html = "".join(
            "<p>"
            + escape(block.strip()).replace("\n", "<br>")
            + "</p>"
            for block in paragraphs.split("\n\n")
            if block.strip()
        )
        color = "#d5dadd" if is_error else "#aeb6ba"
        return f"""
        <div style="
            font-family: Segoe UI, Inter, Arial, sans-serif;
            color: {color};
            font-size: 16px;
            line-height: 1.45;
            font-weight: 400;
        ">
            {paragraph_html}
        </div>
        """

    def _animate_layout(self, target_height: int, target_width: int) -> None:
        self._animate_window_width(target_width)
        self._animate_panel_height(target_height)

    def _animate_window_width(self, target_width: int) -> None:
        if self.width() == target_width:
            return

        start_geometry = self.geometry()
        end_geometry = start_geometry
        end_geometry.setWidth(target_width)
        self._size_animation = QPropertyAnimation(self, b"geometry", self)
        self._size_animation.setDuration(150)
        self._size_animation.setStartValue(start_geometry)
        self._size_animation.setEndValue(end_geometry)
        self._size_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._size_animation.start()

    def _animate_panel_height(self, target_height: int) -> None:
        anchor = self.frameGeometry().topLeft()
        start_height = self.transcript_panel.maximumHeight()
        animation = QPropertyAnimation(self.transcript_panel, b"maximumHeight", self)
        animation.setDuration(150)
        animation.setStartValue(start_height)
        animation.setEndValue(target_height)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(
            lambda value: self._sync_window_height(int(value), anchor)
        )
        animation.finished.connect(lambda: self._sync_window_height(target_height, anchor))
        self._panel_animation = animation
        animation.start()

    def _sync_window_height(self, panel_height: int, anchor) -> None:  # noqa: ANN001
        overlap = 1 if panel_height > 0 else 0
        self.setFixedHeight(self.strip.height() + max(0, panel_height) - overlap)
        if self._snapped_to_top:
            screen = self.screen() or QApplication.primaryScreen()
            top = screen.availableGeometry().top() if screen is not None else self._snap_screen_top
            self.move(anchor.x(), top)
        else:
            self.move(anchor)

    @staticmethod
    def _format_elapsed(seconds: int) -> str:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02}:{minutes:02}:{secs:02}"


def _clean_device_name(name: str) -> str:
    cleaned = name.strip()
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")

    if "(" in cleaned and ")" in cleaned:
        prefix, _, suffix = cleaned.partition("(")
        inner, _, trailing = suffix.partition(")")
        if inner.strip().startswith("@") or not inner.strip():
            cleaned = prefix.strip()

    return cleaned.strip(" ;")


class DiagnosticsDialog(QDialog):
    """Dark app diagnostics dialog for audio, model, and runtime settings."""

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._diagnostics_snapshot = controller.diagnostics_snapshot()
        self._drag_position = None
        self.setWindowTitle("AudioTranscriber diagnostics")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(620, 520)
        self.resize(720, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        frame = QFrame(self)
        frame.setObjectName("diagnosticsRoot")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(24, 16, 24, 20)
        frame_layout.setSpacing(16)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        header = QLabel("Settings and diagnostics", frame)
        header.setObjectName("diagnosticsTitle")
        header_row.addWidget(header)
        header_row.addStretch(1)
        subtitle = QLabel(
            "Audio input, model settings, folders, and detected microphone devices.",
            frame,
        )
        subtitle.setObjectName("diagnosticsSubtitle")
        subtitle.setWordWrap(True)
        frame_layout.addLayout(header_row)
        frame_layout.addWidget(subtitle)

        scroll_area = QScrollArea(frame)
        scroll_area.setObjectName("diagnosticsScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget(scroll_area)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        for title, rows in self._diagnostics_snapshot.sections:
            scroll_layout.addWidget(self._section(title, rows, scroll_content))
        scroll_layout.addWidget(
            self._model_section(
                "Transcription Models",
                self._diagnostics_snapshot.model_rows,
                scroll_content,
            )
        )
        scroll_layout.addWidget(
            self._device_section(
                "Detected Input Devices",
                self._diagnostics_snapshot.devices,
                scroll_content,
            )
        )
        scroll_layout.addStretch(1)
        scroll_area.setWidget(scroll_content)
        frame_layout.addWidget(scroll_area, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        copy_button = QPushButton("Copy diagnostics", frame)
        copy_button.clicked.connect(self._copy_diagnostics)
        close_button = QPushButton("Close", frame)
        close_button.clicked.connect(self.accept)
        button_row.addWidget(copy_button)
        button_row.addWidget(close_button)
        frame_layout.addLayout(button_row)

        root.addWidget(frame)
        self._apply_styles()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 72:
            self._drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = None
        super().mouseReleaseEvent(event)

    def _section(
        self,
        title: str,
        rows: list[tuple[str, str]],
        parent: QWidget,
    ) -> QFrame:
        section = QFrame(parent)
        section.setObjectName("diagnosticsSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        heading = QLabel(title, section)
        heading.setObjectName("diagnosticsSectionTitle")
        layout.addWidget(heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        for row_index, (label, value) in enumerate(rows):
            key_label = QLabel(label, section)
            key_label.setObjectName("diagnosticsKey")
            value_label = QLabel(value, section)
            value_label.setObjectName("diagnosticsValue")
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            value_label.setWordWrap(True)
            grid.addWidget(key_label, row_index, 0)
            grid.addWidget(value_label, row_index, 1)
        layout.addLayout(grid)
        return section

    def _model_section(
        self,
        title: str,
        rows: list[tuple[str, str, str]],
        parent: QWidget,
    ) -> QFrame:
        section = QFrame(parent)
        section.setObjectName("diagnosticsSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        heading = QLabel(title, section)
        heading.setObjectName("diagnosticsSectionTitle")
        layout.addWidget(heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, 140)
        grid.setColumnMinimumWidth(1, 150)
        grid.setColumnMinimumWidth(2, 150)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)

        live_header = QLabel("Live translation", section)
        live_header.setObjectName("diagnosticsColumnHeader")
        high_quality_header = QLabel("High quality", section)
        high_quality_header.setObjectName("diagnosticsColumnHeader")
        grid.addWidget(live_header, 0, 1)
        grid.addWidget(high_quality_header, 0, 2)
        grid.addItem(
            QSpacerItem(1, 1, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum),
            0,
            3,
        )

        for row_index, (label, live_value, high_quality_value) in enumerate(rows, start=1):
            key_label = QLabel(label, section)
            key_label.setObjectName("diagnosticsKey")
            live_label = QLabel(live_value, section)
            live_label.setObjectName("diagnosticsValue")
            live_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            live_label.setWordWrap(True)
            high_quality_label = QLabel(high_quality_value, section)
            high_quality_label.setObjectName("diagnosticsValue")
            high_quality_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            high_quality_label.setWordWrap(True)
            grid.addWidget(key_label, row_index, 0)
            grid.addWidget(live_label, row_index, 1)
            grid.addWidget(high_quality_label, row_index, 2)

        layout.addLayout(grid)
        return section

    def _device_section(
        self,
        title: str,
        devices: list[MicrophoneDevice],
        parent: QWidget,
    ) -> QFrame:
        section = QFrame(parent)
        section.setObjectName("diagnosticsSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        heading = QLabel(title, section)
        heading.setObjectName("diagnosticsSectionTitle")
        layout.addWidget(heading)

        if not devices:
            empty_label = QLabel("No input devices found", section)
            empty_label.setObjectName("diagnosticsValue")
            layout.addWidget(empty_label)
            return section

        selected_key = self._controller.state.selected_microphone_device_key
        for index, device in enumerate(devices, start=1):
            marker = _device_marker(device, selected_key)
            row = QFrame(section)
            row.setObjectName("diagnosticsDeviceRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            number = QLabel(f"{index}.", row)
            number.setObjectName("diagnosticsDeviceNumber")
            number.setFixedWidth(24)
            device_label = QLabel(f"{_clean_device_name(device.name)}{marker}", row)
            device_label.setObjectName("diagnosticsValue")
            device_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            device_label.setWordWrap(True)
            row_layout.addWidget(number, 0, Qt.AlignmentFlag.AlignTop)
            row_layout.addWidget(device_label, 1)
            layout.addWidget(row)

        return section

    def _copy_diagnostics(self) -> None:
        sections = []
        for title, rows in self._diagnostics_snapshot.sections:
            sections.append(title)
            sections.extend(f"{label}: {value}" for label, value in rows)
            sections.append("")
        sections.append("Transcription Models")
        sections.append("Setting: Live translation | High quality")
        sections.extend(
            f"{label}: {live_value} | {high_quality_value}"
            for label, live_value, high_quality_value in self._diagnostics_snapshot.model_rows
        )
        sections.append("")
        sections.append("Detected Input Devices")
        selected_key = self._controller.state.selected_microphone_device_key
        if self._diagnostics_snapshot.devices:
            sections.extend(
                f"{index}. {_clean_device_name(device.name)}"
                f"{_device_marker(device, selected_key)}"
                for index, device in enumerate(self._diagnostics_snapshot.devices, start=1)
            )
        else:
            sections.append("No input devices found")
        QApplication.clipboard().setText("\n".join(sections).strip())

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#diagnosticsRoot {
                background: #151a1d;
                color: #f7f8f8;
                font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
            }

            QLabel#diagnosticsTitle {
                color: #ffffff;
                font-size: 22px;
                font-weight: 800;
            }

            QLabel#diagnosticsSubtitle {
                color: #c8cdd0;
                font-size: 13px;
            }

            QScrollArea#diagnosticsScroll {
                background: transparent;
                border: none;
            }

            QScrollArea#diagnosticsScroll QWidget {
                background: transparent;
            }

            QFrame#diagnosticsSection {
                background: rgba(255, 255, 255, 0.055);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
            }

            QLabel#diagnosticsSectionTitle {
                color: #ffffff;
                font-size: 14px;
                font-weight: 800;
            }

            QLabel#diagnosticsColumnHeader {
                color: #ffffff;
                font-size: 12px;
                font-weight: 800;
            }

            QLabel#diagnosticsKey {
                color: #9da5a9;
                font-size: 12px;
                font-weight: 700;
            }

            QLabel#diagnosticsValue {
                color: #f7f8f8;
                font-size: 12px;
            }

            QFrame#diagnosticsDeviceRow {
                background: transparent;
                border: none;
            }

            QLabel#diagnosticsDeviceNumber {
                color: #9da5a9;
                font-size: 12px;
                font-weight: 800;
            }

            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #f7f8f8;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 700;
            }

            QPushButton:hover {
                background: rgba(255, 255, 255, 0.14);
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0;
            }

            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.24);
                border-radius: 4px;
                min-height: 28px;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )


def _device_marker(device: MicrophoneDevice, selected_key: str | None) -> str:
    markers = []
    if device.is_default:
        markers.append("default")
    if device.key == selected_key:
        markers.append("selected")
    if not markers:
        return ""
    return f" ({', '.join(markers)})"


def _enable_windows_taskbar_minimize(window: QWidget) -> None:
    if sys.platform != "win32":
        return

    try:
        hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        get_window_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_window_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        get_window_long.restype = ctypes.c_ssize_t
        set_window_long.restype = ctypes.c_ssize_t

        style_index = -16  # GWL_STYLE
        system_menu = 0x00080000  # WS_SYSMENU
        minimize_box = 0x00020000  # WS_MINIMIZEBOX
        style = get_window_long(hwnd, style_index)
        set_window_long(hwnd, style_index, style | system_menu | minimize_box)
        user32.DrawMenuBar(hwnd)
    except Exception:  # noqa: BLE001
        return
