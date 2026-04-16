"""App controller for recording state and Phase 2 audio capture."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from queue import Queue
from threading import Event, Thread

from PySide6.QtCore import QObject, QTimer, Signal

from audiotranscriber.app_config import AppConfig
from audiotranscriber.pipelines.post_processing import (
    backup_mp3_path_for,
    export_mp3_backup,
    high_quality_transcript_path_for,
    high_quality_transcription_config,
)
from audiotranscriber.pipelines.recording import LIVE_CHUNK_SECONDS, RecordingPipeline
from audiotranscriber.pipelines.transcription import TranscriptionConfig, TranscriptionPipeline
from audiotranscriber.state import (
    InputSource,
    RecorderState,
    RecorderStatus,
    TranscriptionLanguage,
)


class AppController(QObject):
    """Owns app state until real audio/transcription services arrive in later phases."""

    state_changed = Signal(object)
    level_detected = Signal(float)
    recording_failed = Signal(str)
    live_transcription_progress = Signal(int, int, str, str)
    transcription_progress = Signal(int, int, str, str)
    transcription_finished = Signal(str)
    transcription_failed = Signal(str)
    transcription_cancelled = Signal(str)
    post_processing_progress = Signal(int, int, str)
    post_processing_finished = Signal(str, str)
    post_processing_failed = Signal(str)

    def __init__(self, config: AppConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._state = RecorderState(input_source=config.default_input_source)
        self._recorder = RecordingPipeline(
            config.recordings_dir,
            self.level_detected.emit,
            self._recording_chunk_from_thread,
            self.recording_failed.emit,
        )
        self._transcriber = TranscriptionPipeline(
            TranscriptionConfig(model_cache_dir=config.model_cache_dir)
        )
        self._transcription_cancel = Event()
        self._transcription_thread: Thread | None = None
        self._live_chunk_queue: Queue[tuple[int, bytes] | None] = Queue()
        self._live_transcription_thread: Thread | None = None
        self._live_transcript_parts: dict[int, str] = {}
        self._live_transcript_path: Path | None = None
        self._live_audio_path: Path | None = None
        self._live_chunks_done = 0
        self._live_chunks_queued = 0
        self.level_detected.connect(self._set_audio_level)
        self.recording_failed.connect(self._handle_recording_failed)
        self.live_transcription_progress.connect(self._handle_live_transcription_progress)
        self.transcription_progress.connect(self._handle_transcription_progress)
        self.transcription_finished.connect(self._handle_transcription_finished)
        self.transcription_failed.connect(self._handle_transcription_failed)
        self.transcription_cancelled.connect(self._handle_transcription_cancelled)
        self.post_processing_progress.connect(self._handle_post_processing_progress)
        self.post_processing_finished.connect(self._handle_post_processing_finished)
        self.post_processing_failed.connect(self._handle_post_processing_failed)

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
        if not self._config.show_input_selector and source != InputSource.MICROPHONE:
            return

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

    def set_transcription_language(self, language: TranscriptionLanguage) -> None:
        if self._state.status in {
            RecorderStatus.PROCESSING,
        }:
            return

        whisper_language = None if language == TranscriptionLanguage.AUTO else language.value
        self._transcriber.set_language(whisper_language)
        label = {
            TranscriptionLanguage.AUTO: "auto",
            TranscriptionLanguage.DUTCH: "Nederlands",
            TranscriptionLanguage.ENGLISH: "Engels",
        }[language]
        self._set_state(
            transcription_language=language,
            error_message=None,
            preview_text=f"Taal ingesteld op {label}. Klaar voor opname.",
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
            self._set_state(
                status=RecorderStatus.RECORDING,
                error_message=None,
                processing_label=None,
            )
            return

        try:
            source_path = (
                Path(self._state.selected_dev_sample_path)
                if self._state.input_source == InputSource.DEV_SAMPLE
                and self._state.selected_dev_sample_path is not None
                else None
            )
            output_path = self._recorder.start(
                self._state.input_source,
                source_path=source_path,
            )
        except Exception as exc:  # noqa: BLE001
            self._elapsed_timer.stop()
            error = str(exc)
            self._set_state(
                status=RecorderStatus.IDLE,
                audio_level=0.0,
                error_message=error,
                preview_text=f"Opname kon niet starten:\n{error}",
                transcript_open=True,
            )
            return

        self._start_live_transcription(output_path)
        self._elapsed_timer.start()
        self._set_state(
            status=RecorderStatus.RECORDING,
            elapsed_seconds=0,
            last_update_seconds=None,
            output_audio_path=str(output_path),
            transcript_output_path=(
                str(self._live_transcript_path)
                if self._live_transcript_path is not None
                else None
            ),
            selected_dev_sample_path=(
                self._state.selected_dev_sample_path
                if self._state.input_source == InputSource.DEV_SAMPLE
                else None
            ),
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            processing_label=None,
            processing_progress_text=None,
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
            preview = f"Opname gestopt. Laatste live chunk wordt opgeslagen...\n\n{output_path}"
            print(
                "Saving transcript from queued live chunks. "
                "No second transcription pass will be started.",
                flush=True,
            )

        self._set_state(
            status=RecorderStatus.PROCESSING,
            transcript_open=True,
            last_update_seconds=0,
            audio_level=0.0,
            processing_label="Opname afronden...",
            processing_progress_text=None,
            output_audio_path=str(output_path) if output_path is not None else None,
            preview_text=preview,
        )
        if output_path is not None:
            self._finish_live_transcription()
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
            processing_label="Transcriberen...",
            processing_progress_text=None,
            preview_text=(
                "Transcriptie voorbereiden...\n"
                "Model wordt indien nodig eenmalig gedownload.\n"
                f"Model: {self._transcriber.config.model_name}, "
                f"{self._transcriber.config.device}, {self._transcriber.config.compute_type}"
            ),
        )
        print(
            "Starting transcription: "
            f"{target} "
            f"model={self._transcriber.config.model_name} "
            f"device={self._transcriber.config.device} "
            f"compute_type={self._transcriber.config.compute_type} "
            f"language={self._transcriber.config.language or 'auto'}",
            flush=True,
        )
        self._preview_age_timer.start()

        self._transcription_thread = Thread(
            target=self._run_transcription,
            args=(target,),
            name="TranscriptionPipeline",
            daemon=True,
        )
        self._transcription_thread.start()

    def export_mp3_backup_for(self, audio_path: Path) -> None:
        if self._state.status in {
            RecorderStatus.RECORDING,
            RecorderStatus.PAUSED,
            RecorderStatus.PROCESSING,
        }:
            return

        target = audio_path.resolve()
        if not target.exists():
            self._set_state(
                error_message="Geen opname beschikbaar voor MP3 export.",
                transcript_open=True,
                preview_text=f"WAV bestand niet gevonden:\n{target}",
            )
            return

        output_path = backup_mp3_path_for(target)
        self._set_state(
            status=RecorderStatus.PROCESSING,
            transcript_open=True,
            last_update_seconds=0,
            error_message=None,
            output_audio_path=str(target),
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            processing_label="MP3 exporteren...",
            processing_progress_text="0%",
            preview_text=(
                "MP3 backup maken...\n\n"
                f"Bron:\n{target}\n\n"
                f"Doel:\n{output_path}"
            ),
        )
        self._preview_age_timer.start()
        print(f"Starting MP3 backup export: {target} -> {output_path}", flush=True)

        self._transcription_thread = Thread(
            target=self._run_mp3_export,
            args=(target,),
            name="PostProcessMp3Export",
            daemon=True,
        )
        self._transcription_thread.start()

    def create_high_quality_transcript_for(self, audio_path: Path) -> None:
        if self._state.status in {
            RecorderStatus.RECORDING,
            RecorderStatus.PAUSED,
            RecorderStatus.PROCESSING,
        }:
            return

        target = audio_path.resolve()
        if not target.exists():
            self._set_state(
                error_message="Geen opname beschikbaar voor high-quality transcript.",
                transcript_open=True,
                preview_text=f"WAV bestand niet gevonden:\n{target}",
            )
            return

        output_path = high_quality_transcript_path_for(target)
        self._transcription_cancel.clear()
        self._set_state(
            status=RecorderStatus.PROCESSING,
            transcript_open=True,
            last_update_seconds=0,
            error_message=None,
            output_audio_path=str(target),
            transcript_output_path=str(output_path),
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            processing_label="High quality transcript...",
            processing_progress_text=None,
            preview_text=(
                "High-quality transcript voorbereiden...\n\n"
                "Preset: high-quality\n"
                "Model wordt indien nodig eenmalig gedownload.\n"
                f"Bron:\n{target}\n\n"
                f"Doel:\n{output_path}"
            ),
        )
        self._preview_age_timer.start()
        print(
            "Starting high-quality transcript: "
            f"{target} "
            "model=small device=cpu compute_type=int8 "
            f"language={self._transcriber.config.language or 'auto'}",
            flush=True,
        )

        self._transcription_thread = Thread(
            target=self._run_high_quality_transcription,
            args=(target,),
            name="PostProcessHighQualityTranscript",
            daemon=True,
        )
        self._transcription_thread.start()

    def cancel_transcription(self) -> None:
        standard_running = self._transcription_thread and self._transcription_thread.is_alive()
        live_running = (
            self._live_transcription_thread and self._live_transcription_thread.is_alive()
        )
        if not (standard_running or live_running):
            self._set_state(
                status=RecorderStatus.IDLE,
                last_update_seconds=None,
                audio_level=0.0,
                processing_label=None,
                processing_progress_text=None,
            )
            return

        self._transcription_cancel.set()
        if live_running:
            self._live_chunk_queue.put(None)
        self._set_state(
            status=RecorderStatus.PROCESSING,
            transcript_open=True,
            processing_label="Transcriptie stoppen...",
            processing_progress_text=None,
            preview_text=(
                f"{self._state.preview_text}\n\nTranscriptie stoppen... "
                "De huidige chunk wordt nog afgerond."
            ),
        )

    def _finish_processing(self) -> None:
        self._preview_age_timer.stop()
        self._set_state(
            status=RecorderStatus.IDLE,
            last_update_seconds=None,
            audio_level=0.0,
            processing_label=None,
            processing_progress_text=None,
        )

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
        self._finish_live_transcription()

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

    def _run_mp3_export(self, audio_path: Path) -> None:
        try:
            output_path = export_mp3_backup(
                audio_path,
                on_progress=lambda current, total: self.post_processing_progress.emit(
                    current,
                    total,
                    f"{current}%",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self.post_processing_failed.emit(str(exc))
            return

        self.post_processing_finished.emit("MP3 backup opgeslagen", str(output_path))

    def _run_high_quality_transcription(self, audio_path: Path) -> None:
        transcript_path = high_quality_transcript_path_for(audio_path)
        transcriber = TranscriptionPipeline(
            high_quality_transcription_config(
                self._transcriber.config.language,
                self._config.model_cache_dir,
            )
        )
        try:
            result_path = transcriber.transcribe(
                audio_path,
                on_progress=lambda current, total, text, path: self.transcription_progress.emit(
                    current,
                    total,
                    text,
                    str(path),
                ),
                cancel_event=self._transcription_cancel,
                transcript_path=transcript_path,
            )
        except Exception as exc:  # noqa: BLE001
            self.transcription_failed.emit(str(exc))
            return

        if self._transcription_cancel.is_set():
            self.transcription_cancelled.emit(str(result_path))
            return

        self.transcription_finished.emit(str(result_path))

    def _start_live_transcription(self, audio_path: Path) -> None:
        self._transcription_cancel.clear()
        self._live_chunk_queue = Queue()
        self._live_transcript_parts = {}
        self._live_audio_path = audio_path
        self._live_transcript_path = self._transcriber.transcript_path_for(audio_path)
        self._live_transcript_path.write_text("", encoding="utf-8")
        self._live_chunks_done = 0
        self._live_chunks_queued = 0
        self._live_transcription_thread = Thread(
            target=self._run_live_transcription,
            name="LiveTranscriptionPipeline",
            daemon=True,
        )
        self._live_transcription_thread.start()
        print(
            "Starting near-real-time transcription: "
            f"{audio_path} "
            f"chunk_seconds={LIVE_CHUNK_SECONDS} "
            f"language={self._transcriber.config.language or 'auto'}",
            flush=True,
        )

    def _recording_chunk_from_thread(self, chunk: bytes, chunk_index: int) -> None:
        if self._live_transcription_thread is None:
            return
        if self._transcription_cancel.is_set():
            return

        self._live_chunks_queued = max(self._live_chunks_queued, chunk_index)
        self._live_chunk_queue.put((chunk_index, chunk))

    def _finish_live_transcription(self) -> None:
        if self._live_transcription_thread and self._live_transcription_thread.is_alive():
            self._live_chunk_queue.put(None)
            self._preview_age_timer.start()
            return

        if self._transcription_cancel.is_set():
            return

        if self._live_transcript_path is not None:
            self.transcription_finished.emit(str(self._live_transcript_path))

    def _run_live_transcription(self) -> None:
        while not self._transcription_cancel.is_set():
            item = self._live_chunk_queue.get()
            if item is None:
                break

            chunk_index, chunk = item
            try:
                text = self._transcriber.transcribe_pcm16_chunk(chunk)
            except Exception as exc:  # noqa: BLE001
                self.transcription_failed.emit(str(exc))
                return
            if text:
                self._live_transcript_parts[chunk_index] = text
            self._live_chunks_done = chunk_index
            transcript_text = self._render_live_transcript_text()
            print(
                f"Live transcription chunk "
                f"{chunk_index}/{max(self._live_chunks_queued, chunk_index)}",
                flush=True,
            )

            if self._live_transcript_path is not None:
                self._live_transcript_path.write_text(transcript_text, encoding="utf-8")
                transcript_path = str(self._live_transcript_path)
            else:
                transcript_path = ""

            self.live_transcription_progress.emit(
                chunk_index,
                max(self._live_chunks_queued, chunk_index),
                transcript_text,
                transcript_path,
            )

        if self._transcription_cancel.is_set():
            if self._live_transcript_path is not None:
                self.transcription_cancelled.emit(str(self._live_transcript_path))
            return

        if self._live_transcript_path is not None:
            transcript_text = self._render_live_transcript_text()
            self._live_transcript_path.write_text(transcript_text, encoding="utf-8")
            print(
                f"Transcript saved from {len(self._live_transcript_parts)} live chunks.",
                flush=True,
            )
            self._live_audio_path = None
            self.transcription_finished.emit(str(self._live_transcript_path))

    def _render_live_transcript_text(self) -> str:
        parts: list[str] = []
        for index in sorted(self._live_transcript_parts):
            text = self._live_transcript_parts[index].strip()
            if text:
                parts.append(text)
        return self._clean_joined_text(parts)

    @staticmethod
    def _clean_joined_text(parts: list[str]) -> str:
        cleaned: list[str] = []
        for text in parts:
            if not text:
                continue
            if cleaned:
                previous_words = cleaned[-1].split()
                current_words = text.split()
                max_overlap = min(len(previous_words), len(current_words), 8)
                overlap = 0
                for size in range(max_overlap, 0, -1):
                    if previous_words[-size:] == current_words[:size]:
                        overlap = size
                        break
                if overlap:
                    text = " ".join(current_words[overlap:])
            if text:
                cleaned.append(text)
        return "\n\n".join(cleaned)

    def _handle_transcription_progress(
        self,
        current_chunk: int,
        total_chunks: int,
        text: str,
        transcript_path: str,
    ) -> None:
        latest_text = text.rsplit("\n\n", maxsplit=1)[-1].strip() if text.strip() else ""
        if latest_text:
            print(
                f"Transcription chunk {current_chunk}/{total_chunks}: {latest_text}",
                flush=True,
            )
        else:
            print(
                f"Transcription chunk {current_chunk}/{total_chunks}: no speech detected yet",
                flush=True,
            )
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

    def _handle_live_transcription_progress(
        self,
        current_chunk: int,
        total_chunks: int,
        text: str,
        transcript_path: str,
    ) -> None:
        status = self._state.status
        self._set_state(
            status=status,
            last_update_seconds=0,
            transcript_output_path=transcript_path,
            transcription_current_chunk=current_chunk,
            transcription_total_chunks=total_chunks,
            preview_text=(
                text
                or (
                    f"Live transcript chunk {current_chunk}/{total_chunks}...\n\n"
                    "Nog geen spraak herkend in de verwerkte audio."
                )
            ),
        )

    def _handle_recording_failed(self, error: str) -> None:
        self._elapsed_timer.stop()
        self._preview_age_timer.stop()
        self._transcription_cancel.set()
        self._live_chunk_queue.put(None)
        print(f"Recording failed: {error}", flush=True)
        self._set_state(
            status=RecorderStatus.IDLE,
            last_update_seconds=None,
            audio_level=0.0,
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            processing_label=None,
            processing_progress_text=None,
            error_message=error,
            preview_text=f"Opname kon niet starten:\n{error}",
            transcript_open=True,
        )

    def _handle_transcription_finished(self, transcript_path: str) -> None:
        self._preview_age_timer.stop()
        print(f"Transcription finished: {transcript_path}", flush=True)
        text = self._state.preview_text
        saved_text = ""
        try:
            saved_text = Path(transcript_path).read_text(encoding="utf-8").strip()
        except OSError:
            saved_text = ""

        if saved_text:
            text = saved_text

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
            processing_label=None,
            processing_progress_text=None,
            preview_text=text,
        )

    def _handle_transcription_failed(self, error: str) -> None:
        self._preview_age_timer.stop()
        print(f"Transcription failed: {error}", flush=True)
        self._set_state(
            status=RecorderStatus.IDLE,
            last_update_seconds=None,
            audio_level=0.0,
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            processing_label=None,
            processing_progress_text=None,
            error_message=error,
            preview_text=f"Transcriptie mislukt:\n{error}",
            transcript_open=True,
        )

    def _handle_transcription_cancelled(self, transcript_path: str) -> None:
        self._preview_age_timer.stop()
        print(f"Transcription cancelled. Partial transcript: {transcript_path}", flush=True)
        self._set_state(
            status=RecorderStatus.IDLE,
            last_update_seconds=None,
            audio_level=0.0,
            transcript_output_path=transcript_path,
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            processing_label=None,
            processing_progress_text=None,
            preview_text=(
                f"{self._state.preview_text}\n\nTranscriptie gestopt. "
                f"Gedeeltelijke tekst opgeslagen:\n{transcript_path}"
            ),
            transcript_open=True,
        )

    def _handle_post_processing_progress(
        self,
        current: int,
        total: int,
        progress_text: str,
    ) -> None:
        self._set_state(
            last_update_seconds=0,
            transcription_current_chunk=current,
            transcription_total_chunks=total,
            processing_progress_text=progress_text,
        )

    def _handle_post_processing_finished(self, label: str, output_path: str) -> None:
        self._preview_age_timer.stop()
        print(f"{label}: {output_path}", flush=True)
        self._set_state(
            status=RecorderStatus.IDLE,
            last_update_seconds=None,
            audio_level=0.0,
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            processing_label=None,
            processing_progress_text=None,
            error_message=None,
            preview_text=f"{label}:\n{output_path}",
            transcript_open=True,
        )

    def _handle_post_processing_failed(self, error: str) -> None:
        self._preview_age_timer.stop()
        print(f"Post-processing failed: {error}", flush=True)
        self._set_state(
            status=RecorderStatus.IDLE,
            last_update_seconds=None,
            audio_level=0.0,
            transcription_current_chunk=0,
            transcription_total_chunks=0,
            processing_label=None,
            processing_progress_text=None,
            error_message=error,
            preview_text=f"Post-processing mislukt:\n{error}",
            transcript_open=True,
        )

    def _current_transcription_audio_path(self) -> Path | None:
        if self._state.output_audio_path:
            return Path(self._state.output_audio_path)
        return None

    def _set_state(self, **changes: object) -> None:
        self._state = replace(self._state, **changes)
        self.state_changed.emit(self._state)
