"""Phase 1 controller with honest dummy state transitions."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QObject, QTimer, Signal

from audiotranscriber.state import RecorderState, RecorderStatus


class AppController(QObject):
    """Owns app state until real audio/transcription services arrive in later phases."""

    state_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = RecorderState()

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

    def emit_current_state(self) -> None:
        self.state_changed.emit(self._state)

    def toggle_transcript(self) -> None:
        self._set_state(transcript_open=not self._state.transcript_open)

    def record(self) -> None:
        if self._state.status == RecorderStatus.RECORDING:
            return

        if self._state.status == RecorderStatus.IDLE:
            self._set_state(elapsed_seconds=0, last_update_seconds=None)

        self._processing_timer.stop()
        self._preview_age_timer.stop()
        self._elapsed_timer.start()
        self._set_state(status=RecorderStatus.RECORDING)

    def pause(self) -> None:
        if self._state.status == RecorderStatus.RECORDING:
            self._elapsed_timer.stop()
            self._set_state(status=RecorderStatus.PAUSED)
        elif self._state.status == RecorderStatus.PAUSED:
            self._elapsed_timer.start()
            self._set_state(status=RecorderStatus.RECORDING)

    def stop(self) -> None:
        if self._state.status not in {RecorderStatus.RECORDING, RecorderStatus.PAUSED}:
            return

        self._elapsed_timer.stop()
        self._set_state(
            status=RecorderStatus.PROCESSING,
            transcript_open=True,
            last_update_seconds=0,
        )
        self._preview_age_timer.start()
        self._processing_timer.start()

    def _finish_processing(self) -> None:
        self._preview_age_timer.stop()
        self._set_state(status=RecorderStatus.IDLE, last_update_seconds=None)

    def _tick_elapsed(self) -> None:
        self._set_state(elapsed_seconds=self._state.elapsed_seconds + 1)

    def _tick_preview_age(self) -> None:
        current = self._state.last_update_seconds
        if current is not None:
            self._set_state(last_update_seconds=current + 1)

    def _set_state(self, **changes: object) -> None:
        self._state = replace(self._state, **changes)
        self.state_changed.emit(self._state)
