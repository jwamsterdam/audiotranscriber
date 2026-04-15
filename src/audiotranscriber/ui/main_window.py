"""Floating recorder strip window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QFileDialog,
    QMainWindow,
    QMenu,
    QTextEdit,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from audiotranscriber.controllers.app_controller import AppController
from audiotranscriber.state import InputSource, RecorderState, RecorderStatus
from audiotranscriber.ui.widgets import (
    GREEN,
    RED,
    YELLOW,
    IconKind,
    StatusDot,
    StripIconButton,
    WaveformWidget,
    animate_height,
)

DEFAULT_WIDTH = 740


class RecorderStripWindow(QMainWindow):
    """Compact always-on-top friendly window for Phase 1."""

    def __init__(self) -> None:
        super().__init__()
        self._controller: AppController | None = None
        self._height_animation = None
        self._drag_position = None
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.8)
        self._media_player = QMediaPlayer(self)
        self._media_player.setAudioOutput(self._audio_output)

        self.setWindowTitle("AudioTranscriber")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(680)
        self.setMaximumWidth(1040)
        self.resize(DEFAULT_WIDTH, 64)
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
        strip_layout.setContentsMargins(22, 6, 18, 6)
        strip_layout.setSpacing(12)

        self.status_dot = StatusDot(self.strip)
        self.waveform = WaveformWidget(self.strip)
        self.timer_label = QLabel("00:00:00", self.strip)
        self.timer_label.setObjectName("timerLabel")
        self.stop_button = StripIconButton(IconKind.STOP, self.strip)
        self.pause_button = StripIconButton(IconKind.PAUSE, self.strip)
        self.record_button = StripIconButton(IconKind.RECORD, self.strip)
        self.expand_button = StripIconButton(IconKind.EXPAND, self.strip)

        separator = QFrame(self.strip)
        separator.setObjectName("separator")
        separator.setFixedWidth(1)
        separator.setFixedHeight(30)

        strip_layout.addWidget(self.status_dot)
        strip_layout.addWidget(self.waveform, 1)
        strip_layout.addWidget(self.timer_label)
        strip_layout.addWidget(separator)
        strip_layout.addWidget(self.stop_button)
        strip_layout.addWidget(self.pause_button)
        strip_layout.addWidget(self.record_button)
        strip_layout.addWidget(self.expand_button)

        self.transcript_panel = QFrame(root)
        self.transcript_panel.setObjectName("transcriptPanel")
        self.transcript_panel.setMaximumHeight(0)
        self.transcript_panel.setMinimumHeight(0)
        self.panel_layout = QVBoxLayout(self.transcript_panel)
        self.panel_layout.setContentsMargins(28, 17, 28, 22)
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

        self.transcript_text = QTextEdit(self.transcript_panel)
        self.transcript_text.setObjectName("transcriptText")
        self.transcript_text.setReadOnly(True)
        self.transcript_text.setAcceptRichText(False)
        self.transcript_text.setFrameShape(QFrame.Shape.NoFrame)
        self.transcript_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.transcript_text.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        self.panel_layout.addLayout(panel_header)
        self.panel_layout.addWidget(self.transcript_text)

        layout.addWidget(self.strip)
        layout.addWidget(self.transcript_panel)
        self.setCentralWidget(root)

        self._apply_styles()
        self._connect_buttons()

    def bind_controller(self, controller: AppController) -> None:
        self._controller = controller
        controller.state_changed.connect(self.apply_state)
        controller.emit_current_state()

    def apply_state(self, state: RecorderState) -> None:
        self.status_dot.set_status(state.status)
        self.waveform.set_status(state.status)
        self.waveform.set_level(state.audio_level)
        self.timer_label.setText(self._format_elapsed(state.elapsed_seconds))
        self._set_transcript_text(state.preview_text)
        self.expand_button.set_kind(IconKind.COLLAPSE if state.transcript_open else IconKind.EXPAND)
        self.strip.setProperty("expanded", state.transcript_open)
        self.strip.style().unpolish(self.strip)
        self.strip.style().polish(self.strip)

        panel_target = self._expanded_panel_height() if state.transcript_open else 0
        if self.transcript_panel.maximumHeight() != panel_target:
            self._animate_panel_height(panel_target)

        if state.status == RecorderStatus.RECORDING:
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
            if state.transcription_total_chunks:
                progress = (
                    f"chunk {state.transcription_current_chunk}/"
                    f"{state.transcription_total_chunks}"
                )
            else:
                progress = "model laden"
            self.preview_status.setText("Transcriberen...")
            self.preview_age.setText(f"({progress}, laatste update: {age}s geleden)")
        elif state.status == RecorderStatus.PAUSED:
            self.preview_status.setText("Gepauzeerd")
            self.preview_age.setText("(opname tijdelijk stilgezet)")
        else:
            self.preview_status.setText("Klaar")
            self.preview_age.setText("(wacht op opname)")

        self._set_status_color(state.status)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = None
            event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.setObjectName("contextMenu")

        test_tone_action = QAction("Use test tone input", menu)
        test_tone_action.setCheckable(True)
        test_tone_action.setChecked(
            self._controller is not None
            and self._controller.state.input_source == InputSource.TEST_TONE
        )
        test_tone_action.triggered.connect(
            lambda: self._controller and self._controller.set_input_source(InputSource.TEST_TONE)
        )
        menu.addAction(test_tone_action)

        microphone_action = QAction("Use microphone input", menu)
        microphone_action.setCheckable(True)
        microphone_action.setChecked(
            self._controller is not None
            and self._controller.state.input_source == InputSource.MICROPHONE
        )
        microphone_action.triggered.connect(
            lambda: self._controller and self._controller.set_input_source(InputSource.MICROPHONE)
        )
        menu.addAction(microphone_action)

        dev_sample_input_action = QAction("Use dev sample input", menu)
        dev_sample_input_action.setCheckable(True)
        dev_sample_input_action.setChecked(
            self._controller is not None
            and self._controller.state.input_source == InputSource.DEV_SAMPLE
        )
        dev_sample_input_action.setEnabled(self._controller is not None)
        dev_sample_input_action.triggered.connect(
            lambda: self._controller and self._controller.set_input_source(InputSource.DEV_SAMPLE)
        )
        menu.addAction(dev_sample_input_action)
        menu.addSeparator()

        select_sample_action = QAction("Select dev sample", menu)
        select_sample_action.setEnabled(self._controller is not None)
        select_sample_action.triggered.connect(self._select_dev_sample)
        menu.addAction(select_sample_action)

        play_sample_action = QAction("Play dev sample", menu)
        play_sample_action.setEnabled(self._dev_sample_path() is not None)
        play_sample_action.triggered.connect(self._play_dev_sample)
        menu.addAction(play_sample_action)

        stop_sample_action = QAction("Stop dev sample", menu)
        stop_sample_action.setEnabled(
            self._media_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState
        )
        stop_sample_action.triggered.connect(self._media_player.stop)
        menu.addAction(stop_sample_action)
        menu.addSeparator()

        open_folder_action = QAction("Open recordings folder", menu)
        open_folder_action.triggered.connect(self._open_recordings_folder)
        menu.addAction(open_folder_action)

        open_last_action = QAction("Open last recording", menu)
        open_last_action.setEnabled(
            self._controller is not None and self._controller.state.output_audio_path is not None
        )
        open_last_action.triggered.connect(self._open_last_recording)
        menu.addAction(open_last_action)

        open_transcript_action = QAction("Open transcript TXT", menu)
        open_transcript_action.setEnabled(
            self._controller is not None
            and self._controller.state.transcript_output_path is not None
        )
        open_transcript_action.triggered.connect(self._open_transcript)
        menu.addAction(open_transcript_action)

        menu.addSeparator()

        close_action = QAction("Close app", menu)
        close_action.triggered.connect(self.close)
        menu.addAction(close_action)

        menu.exec(event.globalPos())

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
        self.pause_button.clicked.connect(lambda: self._controller and self._controller.pause())
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
                border-bottom-left-radius: 0;
                border-bottom-right-radius: 0;
            }

            QFrame#separator {
                background: rgba(255, 255, 255, 0.14);
            }

            QLabel#timerLabel {
                color: #ffffff;
                font-size: 15px;
                font-weight: 500;
                min-width: 78px;
            }

            QFrame#transcriptPanel {
                background: #151a1d;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                border-bottom-left-radius: 24px;
                border-bottom-right-radius: 24px;
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

    def _open_last_recording(self) -> None:
        if self._controller is None or self._controller.state.output_audio_path is None:
            return
        path = Path(self._controller.state.output_audio_path)
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _open_transcript(self) -> None:
        if self._controller is None or self._controller.state.transcript_output_path is None:
            return
        path = Path(self._controller.state.transcript_output_path)
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

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

    def _play_dev_sample(self) -> None:
        path = self._dev_sample_path()
        if path is None or not path.exists():
            return

        self._media_player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self._media_player.play()

    def _record_clicked(self) -> None:
        if self._controller is None:
            return

        self._controller.record()
        if self._controller.state.status == RecorderStatus.RECORDING:
            if self._controller.state.input_source == InputSource.DEV_SAMPLE:
                self._play_dev_sample()
            else:
                self._media_player.stop()

    def _stop_clicked(self) -> None:
        if self._controller is None:
            return

        was_recording_dev_sample = (
            self._controller.state.status == RecorderStatus.RECORDING
            and self._controller.state.input_source == InputSource.DEV_SAMPLE
        )
        self._controller.stop()
        if was_recording_dev_sample:
            self._media_player.stop()

    def _dev_sample_path(self) -> Path | None:
        if self._controller is None:
            return None

        sample_path = self._controller.state.selected_dev_sample_path
        if sample_path is None:
            return None
        return Path(sample_path)

    def _set_transcript_text(self, text: str) -> None:
        if self.transcript_text.toPlainText() == text:
            return

        scrollbar = self.transcript_text.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        self.transcript_text.setPlainText(text)
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _animate_panel_height(self, target_height: int) -> None:
        anchor = self.frameGeometry().topLeft()
        self._height_animation = animate_height(self.transcript_panel, target_height)
        self._height_animation.valueChanged.connect(
            lambda value: self._sync_window_height(int(value), anchor)
        )
        self._height_animation.finished.connect(
            lambda: self._sync_window_height(target_height, anchor)
        )

    def _sync_window_height(self, panel_height: int, anchor) -> None:  # noqa: ANN001
        self.setFixedHeight(self.strip.height() + max(0, panel_height))
        self.move(anchor)

    @staticmethod
    def _format_elapsed(seconds: int) -> str:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02}:{minutes:02}:{secs:02}"
