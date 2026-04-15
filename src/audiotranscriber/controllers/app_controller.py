"""App controller for recording state and Phase 2 audio capture."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event, Thread

from PySide6.QtCore import QObject, QTimer, Signal

from audiotranscriber.pipelines.recording import RecordingPipeline
from audiotranscriber.pipelines.transcription import TranscriptionPipeline
from audiotranscriber.state import InputSource, RecorderState, RecorderStatus


class AppController(QObject):
    """Owns app state until real audio/transcription services arrive in later phases."""

    state_changed = Signal(object)
    level_detected = Signal(float)
    transcription_progress = Signal(int, int, str, str)
    transcription_finished = Signal(str)
    transcription_failed = Signal(str)
    transcription_cancelled = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = RecorderState()
        self._recorder = RecordingPipeline(Path.cwd() / "recordings", self.level_detected.emit)
        self._transcriber = TranscriptionPipeline()
        self._transcription_cancel = Event()
        self._transcription_thread: Thread | None = None
        self.level_detected.connect(self._set_audio_level)
        self.transcription_progress.connect(self._handle_transcription_progress)
        self.transcription_finished.connect(self._handle_transcription_finished)
        self.transcription_failed.connect(self._handle_transcription_failed)
        self.transcription_cancelled.connect(self._handle_transcription_cancelled)

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

    @property
    def dev_samples_dir(self) -> Path:
        return Path.cwd() / "dev_samples"

    def emit_current_state(self) -> None:
        self.state_changed.emit(self._state)

    def toggle_transcript(self) -> None:
        self._set_state(transcript_open=not self._state.transcript_open)

    def set_input_source(self, source: InputSource) -> None:
        if self._state.status in {RecorderStatus.RECORDING, RecorderStatus.PAUSED}:
            return

        if source == InputSource.DEV_SAMPLE and self._state.selected_dev_sample_path is None:
            self._set_state(
                input_source=source,
                error_message="Geen dev sample geselecteerd.",
                transcript_open=True,
                preview_text=(
                    "Dev sample input geselecteerd, maar er is nog geen bestand gekozen.\n\n"
                    "Gebruik rechtermuisknop > Select dev sample."
                ),
            )
            return

        label = {
            InputSource.TEST_TONE: "testtoon",
            InputSource.MICROPHONE: "microfoon",
            InputSource.DEV_SAMPLE: "dev sample",
        }[source]
        self._set_state(
            input_source=source,
            error_message=None,
            preview_text=f"Invoer ingesteld op {label}. Klaar voor opname.",
        )

    def select_dev_sample(self, path: Path) -> None:
        if self._state.status in {
            RecorderStatus.RECORDING,
            RecorderStatus.PAUSED,
            RecorderStatus.PROCESSING,
        }:
            return

        resolved = path.resolve()
        if not resolved.exists():
            self._set_state(
                error_message="Dev sample bestaat niet.",
                preview_text=f"Dev sample niet gevonden:\n{resolved}",
                transcript_open=True,
            )
            return

        self._set_state(
            selected_dev_sample_path=str(resolved),
            error_message=None,
            transcript_open=True,
            preview_text=(
                "Dev sample geselecteerd:\n"
                f"{resolved}\n\n"
                "Kies 'Use dev sample input' om dit bestand via de rode opnameknop "
                "op te nemen en daarna automatisch te transcriberen."
            ),
        )

    def record(self) -> None:
        if self._state.status in {RecorderStatus.RECORDING, RecorderStatus.PROCESSING}:
            return

        self._processing_timer.stop()
        self._preview_age_timer.stop()

        if self._state.status == RecorderStatus.PAUSED:
            self._recorder.resume()
            self._elapsed_timer.start()
            self._set_state(status=RecorderStatus.RECORDING, error_message=None)
            return

        try:
            source_path = (
                Path(self._state.selected_dev_sample_path)
                if self._state.input_source == InputSource.DEV_SAMPLE
                and self._state.selected_dev_sample_path is not None
                else None
            )
            output_path = self._recorder.start(self._state.input_source, source_path=source_path)
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
            transcript_output_path=None,
            selected_dev_sample_path=(
                self._state.selected_dev_sample_path
                if self._state.input_source == InputSource.DEV_SAMPLE
                else None
            ),
            transcription_current_chunk=0,
            transcription_total_chunks=0,
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
        if self._state.status == RecorderStatus.PROCESSING:
            self.cancel_transcription()
            return

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
        if output_path is not None:
            self.start_transcription(Path(output_path))
        else:
            self._preview_age_timer.start()
            self._processing_timer.setInterval(900)
            self._processing_timer.start()

    def start_transcription(self, audio_path: Path | None = None) -> None:
        if self._state.status in {RecorderStatus.RECORDING, RecorderStatus.PAUSED}:
            return
        if self._transcription_thread and self._transcription_thread.is_alive():
            return

        target = audio_path or self._current_transcription_audio_path()
        if target is None:
            self._set_state(
                error_message="Geen audio gekozen voor transcriptie.",
                transcript_open=True,
                preview_text=(
                    "Geen audio gekozen. Neem eerst iets op of selecteer een dev sample."
                ),
            )
            return

        self._transcription_cancel.clear()
        transcript_path = self._transcriber.transcript_path_for(target)
        self._set_state(
            status=RecorderStatus.PROCESSING,
            transcript_open=True,
            last_update_seconds=0,
            error_message=None,
            output_audio_path=str(target),
            transcript_output_path=str(transcript_path),
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            preview_text=(
                "Transcriptie voorbereiden...\n"
                f"Model: {self._transcriber.config.model_name}, "
                f"{self._transcriber.config.device}, {self._transcriber.config.compute_type}"
            ),
        )
        self._preview_age_timer.start()

        self._transcription_thread = Thread(
            target=self._run_transcription,
            args=(target,),
            name="TranscriptionPipeline",
            daemon=True,
        )
        self._transcription_thread.start()

    def cancel_transcription(self) -> None:
        if not (self._transcription_thread and self._transcription_thread.is_alive()):
            self._set_state(status=RecorderStatus.IDLE, last_update_seconds=None, audio_level=0.0)
            return

        self._transcription_cancel.set()
        self._set_state(
            status=RecorderStatus.PROCESSING,
            transcript_open=True,
            preview_text=(
                f"{self._state.preview_text}\n\nTranscriptie stoppen... "
                "De huidige chunk wordt nog afgerond."
            ),
        )

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
        self._transcription_cancel.set()

    def _set_audio_level(self, level: float) -> None:
        if self._state.status == RecorderStatus.RECORDING:
            self._set_state(audio_level=level)

    def _run_transcription(self, audio_path: Path) -> None:
        try:
            transcript_path = self._transcriber.transcribe(
                audio_path,
                on_progress=lambda current, total, text, path: self.transcription_progress.emit(
                    current,
                    total,
                    text,
                    str(path),
                ),
                cancel_event=self._transcription_cancel,
            )
        except Exception as exc:  # noqa: BLE001
            self.transcription_failed.emit(str(exc))
            return

        if self._transcription_cancel.is_set():
            self.transcription_cancelled.emit(str(transcript_path))
            return

        self.transcription_finished.emit(str(transcript_path))

    def _handle_transcription_progress(
        self,
        current_chunk: int,
        total_chunks: int,
        text: str,
        transcript_path: str,
    ) -> None:
        self._set_state(
            status=RecorderStatus.PROCESSING,
            last_update_seconds=0,
            transcript_output_path=transcript_path,
            transcription_current_chunk=current_chunk,
            transcription_total_chunks=total_chunks,
            preview_text=(
                text
                or (
                    f"Transcriberen chunk {current_chunk}/{total_chunks}...\n\n"
                    "Nog geen spraak herkend in de verwerkte audio."
                )
            ),
        )

    def _handle_transcription_finished(self, transcript_path: str) -> None:
        self._preview_age_timer.stop()
        text = self._state.preview_text
        if not text.strip() or "Nog geen spraak herkend" in text:
            text = (
                "Transcriptie voltooid, maar er is geen spraak herkend in deze audio.\n\n"
                f"Transcript opgeslagen:\n{transcript_path}"
            )
        elif text.strip():
            text = f"{text}\n\nTranscript opgeslagen:\n{transcript_path}"
        else:
            text = f"Transcript opgeslagen:\n{transcript_path}"
        self._set_state(
            status=RecorderStatus.IDLE,
            last_update_seconds=None,
            audio_level=0.0,
            transcript_output_path=transcript_path,
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            preview_text=text,
        )

    def _handle_transcription_failed(self, error: str) -> None:
        self._preview_age_timer.stop()
        self._set_state(
            status=RecorderStatus.IDLE,
            last_update_seconds=None,
            audio_level=0.0,
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            error_message=error,
            preview_text=f"Transcriptie mislukt:\n{error}",
            transcript_open=True,
        )

    def _handle_transcription_cancelled(self, transcript_path: str) -> None:
        self._preview_age_timer.stop()
        self._set_state(
            status=RecorderStatus.IDLE,
            last_update_seconds=None,
            audio_level=0.0,
            transcript_output_path=transcript_path,
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            preview_text=(
                f"{self._state.preview_text}\n\nTranscriptie gestopt. "
                f"Gedeeltelijke tekst opgeslagen:\n{transcript_path}"
            ),
            transcript_open=True,
        )

    def _current_transcription_audio_path(self) -> Path | None:
        if self._state.output_audio_path:
            return Path(self._state.output_audio_path)
        return None

    def _set_state(self, **changes: object) -> None:
        self._state = replace(self._state, **changes)
        self.state_changed.emit(self._state)
