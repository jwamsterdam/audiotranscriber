"""App controller for recording state and Phase 2 audio capture."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from audiotranscriber.pipelines.recording import RecordingPipeline
from audiotranscriber.state import InputSource, RecorderState, RecorderStatus


class AppController(QObject):
    """Owns app state until real audio/transcription services arrive in later phases."""

    state_changed = Signal(object)
    level_detected = Signal(float)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = RecorderState()
        self._recorder = RecordingPipeline(Path.cwd() / "recordings", self.level_detected.emit)
        self.level_detected.connect(self._set_audio_level)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        self._processing_timer = QTimer(self)
        self._processing_timer.setSingleShot(True)
        self._processing_timer.setInterval(4200)
        self._processing_timer.timeout.connect(self._finish_processing)

        self._preview_age_timer = QTimer(self)
        self._preview_age_timer.setInterval(1000)
        self._preview_age_timer.timeout.connect(self._tick_preview_age)

    @property
    def state(self) -> RecorderState:
        return self._state

    @property
    def recordings_dir(self) -> Path:
        return self._recorder.output_dir

    def emit_current_state(self) -> None:
        self.state_changed.emit(self._state)

    def toggle_transcript(self) -> None:
        self._set_state(transcript_open=not self._state.transcript_open)

    def set_input_source(self, source: InputSource) -> None:
        if self._state.status in {RecorderStatus.RECORDING, RecorderStatus.PAUSED}:
            return
        label = "testtoon" if source == InputSource.TEST_TONE else "microfoon"
        self._set_state(
            input_source=source,
            error_message=None,
            preview_text=f"Invoer ingesteld op {label}. Klaar voor opname.",
        )

    def record(self) -> None:
        if self._state.status == RecorderStatus.RECORDING:
            return

        self._processing_timer.stop()
        self._preview_age_timer.stop()

        if self._state.status == RecorderStatus.PAUSED:
            self._recorder.resume()
            self._elapsed_timer.start()
            self._set_state(status=RecorderStatus.RECORDING, error_message=None)
            return

        try:
            output_path = self._recorder.start(self._state.input_source)
        except Exception as exc:  # noqa: BLE001
            self._elapsed_timer.stop()
            self._set_state(
                status=RecorderStatus.IDLE,
                audio_level=0.0,
                error_message=str(exc),
                preview_text=f"Opname kon niet starten: {exc}",
                transcript_open=True,
            )
            return

        self._elapsed_timer.start()
        self._set_state(
            status=RecorderStatus.RECORDING,
            elapsed_seconds=0,
            last_update_seconds=None,
            output_audio_path=str(output_path),
            error_message=None,
            preview_text=f"Opname loopt. Ruwe audio wordt opgeslagen als:\n{output_path}",
        )

    def pause(self) -> None:
        if self._state.status == RecorderStatus.RECORDING:
            self._recorder.pause()
            self._elapsed_timer.stop()
            self._set_state(status=RecorderStatus.PAUSED, audio_level=0.0)
        elif self._state.status == RecorderStatus.PAUSED:
            self._recorder.resume()
            self._elapsed_timer.start()
            self._set_state(status=RecorderStatus.RECORDING)

    def stop(self) -> None:
        if self._state.status not in {RecorderStatus.RECORDING, RecorderStatus.PAUSED}:
            return

        self._elapsed_timer.stop()
        output_path = self._recorder.stop()
        preview = "Opname gestopt."
        if output_path is not None:
            preview = f"Ruwe audio opgeslagen:\n{output_path}"

        self._set_state(
            status=RecorderStatus.PROCESSING,
            transcript_open=True,
            last_update_seconds=0,
            audio_level=0.0,
            output_audio_path=str(output_path) if output_path is not None else None,
            preview_text=preview,
        )
        self._preview_age_timer.start()
        self._processing_timer.setInterval(900)
        self._processing_timer.start()

    def _finish_processing(self) -> None:
        self._preview_age_timer.stop()
        self._set_state(status=RecorderStatus.IDLE, last_update_seconds=None, audio_level=0.0)

    def _tick_elapsed(self) -> None:
        self._set_state(elapsed_seconds=self._state.elapsed_seconds + 1)

    def _tick_preview_age(self) -> None:
        current = self._state.last_update_seconds
        if current is not None:
            self._set_state(last_update_seconds=current + 1)

    def shutdown(self) -> None:
        if self._state.status in {RecorderStatus.RECORDING, RecorderStatus.PAUSED}:
            self._recorder.stop()

    def _set_audio_level(self, level: float) -> None:
        if self._state.status == RecorderStatus.RECORDING:
            self._set_state(audio_level=level)

    def _set_state(self, **changes: object) -> None:
        self._state = replace(self._state, **changes)
        self.state_changed.emit(self._state)
