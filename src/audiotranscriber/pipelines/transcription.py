"""Chunked faster-whisper transcription pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

import numpy as np


DEFAULT_MODEL_NAME = "base"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_CHUNK_SECONDS = 15
DEFAULT_OVERLAP_SECONDS = 0
DEFAULT_LANGUAGE: str | None = None
SAMPLE_RATE = 16_000

ProgressCallback = Callable[[int, int, str, Path], None]


@dataclass(frozen=True)
class TranscriptionConfig:
    model_name: str = DEFAULT_MODEL_NAME
    device: str = DEFAULT_DEVICE
    compute_type: str = DEFAULT_COMPUTE_TYPE
    cpu_threads: int = 0
    chunk_seconds: int = DEFAULT_CHUNK_SECONDS
    overlap_seconds: int = DEFAULT_OVERLAP_SECONDS
    language: str | None = DEFAULT_LANGUAGE
    model_cache_dir: Path | None = None
    vad_filter: bool = False


class TranscriptionPipeline:
    """Transcribe audio in small chunks and save confirmed text incrementally."""

    def __init__(self, config: TranscriptionConfig | None = None) -> None:
        self._config = config or TranscriptionConfig()
        self._model = None

    @property
    def config(self) -> TranscriptionConfig:
        return self._config

    def reset_model(self) -> None:
        self._model = None

    def set_language(self, language: str | None) -> None:
        self._config = TranscriptionConfig(
            model_name=self._config.model_name,
            device=self._config.device,
            compute_type=self._config.compute_type,
            cpu_threads=self._config.cpu_threads,
            chunk_seconds=self._config.chunk_seconds,
            overlap_seconds=self._config.overlap_seconds,
            language=language,
            model_cache_dir=self._config.model_cache_dir,
            vad_filter=self._config.vad_filter,
        )

    def transcript_path_for(self, audio_path: Path) -> Path:
        return audio_path.with_suffix(".txt")

    def transcribe(
        self,
        audio_path: Path,
        on_progress: ProgressCallback,
        cancel_event: Event,
        transcript_path: Path | None = None,
    ) -> Path:
        audio_path = audio_path.resolve()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        transcript_path = transcript_path or self.transcript_path_for(audio_path)
        transcript_path.parent.mkdir(parents=True, exist_ok=True)

        model = self._load_model()
        audio = self._decode_audio(audio_path)
        chunk_frames = self._config.chunk_seconds * SAMPLE_RATE
        overlap_frames = self._config.overlap_seconds * SAMPLE_RATE
        step_frames = max(1, chunk_frames - overlap_frames)
        total_chunks = max(1, (len(audio) + step_frames - 1) // step_frames)

        confirmed_text: list[str] = []
        transcript_path.write_text("", encoding="utf-8")
        rendered_text = ""

        for chunk_index, start in enumerate(range(0, len(audio), step_frames), start=1):
            if cancel_event.is_set():
                break

            end = min(len(audio), start + chunk_frames)
            chunk = audio[start:end]
            if len(chunk) == 0:
                continue

            segments, _info = model.transcribe(
                chunk,
                beam_size=1,
                vad_filter=self._config.vad_filter,
                language=self._config.language,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            if text:
                confirmed_text.append(text)
                with transcript_path.open("a", encoding="utf-8") as transcript_file:
                    if rendered_text:
                        transcript_file.write("\n\n")
                    transcript_file.write(text)
                rendered_text = "\n\n".join(confirmed_text)

            on_progress(chunk_index, total_chunks, rendered_text, transcript_path)

        return transcript_path

    def transcribe_pcm16_chunk(self, pcm_bytes: bytes) -> str:
        if not pcm_bytes:
            return ""

        model = self._load_model()
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = model.transcribe(
            audio,
            beam_size=1,
            vad_filter=self._config.vad_filter,
            language=self._config.language,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _load_model(self):  # noqa: ANN202
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "Transcription support is missing from this app build. "
                    "Please reinstall AudioTranscriber."
                ) from exc

            if self._config.model_cache_dir is not None:
                self._config.model_cache_dir.mkdir(parents=True, exist_ok=True)

            try:
                self._model = WhisperModel(
                    self._config.model_name,
                    device=self._config.device,
                    compute_type=self._config.compute_type,
                    cpu_threads=self._config.cpu_threads,
                    download_root=(
                        str(self._config.model_cache_dir)
                        if self._config.model_cache_dir is not None
                        else None
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(_friendly_model_error(exc, self._config)) from exc
        return self._model

    @staticmethod
    def _decode_audio(audio_path: Path):  # noqa: ANN205
        try:
            from faster_whisper.audio import decode_audio
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper audio decoding is unavailable. Run .\\run.ps1."
            ) from exc

        return decode_audio(str(audio_path), sampling_rate=SAMPLE_RATE)


def _friendly_model_error(error: Exception, config: TranscriptionConfig) -> str:
    detail = str(error).strip()
    lower_detail = detail.lower()
    cache_hint = (
        f"\n\nModel cache:\n{config.model_cache_dir}"
        if config.model_cache_dir is not None
        else ""
    )

    if any(
        word in lower_detail
        for word in {
            "connection",
            "internet",
            "network",
            "timeout",
            "timed out",
            "dns",
            "ssl",
            "certificate",
            "huggingface",
            "resolve",
        }
    ):
        return (
            "The transcription model needs to be downloaded once before first use, "
            "but the download could not complete. Connect to the internet and try "
            "the transcription again."
            f"{cache_hint}"
        )

    if any(word in lower_detail for word in {"permission", "access", "denied"}):
        return (
            "The transcription model cache could not be written. Check folder permissions "
            "or choose a writable app data location, then try again."
            f"{cache_hint}"
        )

    return (
        "The transcription model could not be loaded. On first use, AudioTranscriber "
        "downloads the model once and then reuses it locally. Connect to the internet "
        "and try again; if this keeps happening, reinstall the app."
        f"{cache_hint}"
    )
