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
    chunk_seconds: int = DEFAULT_CHUNK_SECONDS
    overlap_seconds: int = DEFAULT_OVERLAP_SECONDS
    language: str | None = DEFAULT_LANGUAGE


class TranscriptionPipeline:
    """Transcribe audio in small chunks and save confirmed text incrementally."""

    def __init__(self, config: TranscriptionConfig | None = None) -> None:
        self._config = config or TranscriptionConfig()
        self._model = None

    @property
    def config(self) -> TranscriptionConfig:
        return self._config

    def set_language(self, language: str | None) -> None:
        self._config = TranscriptionConfig(
            model_name=self._config.model_name,
            device=self._config.device,
            compute_type=self._config.compute_type,
            chunk_seconds=self._config.chunk_seconds,
            overlap_seconds=self._config.overlap_seconds,
            language=language,
        )

    def transcript_path_for(self, audio_path: Path) -> Path:
        return audio_path.with_suffix(".txt")

    def transcribe(
        self,
        audio_path: Path,
        on_progress: ProgressCallback,
        cancel_event: Event,
    ) -> Path:
        audio_path = audio_path.resolve()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        transcript_path = self.transcript_path_for(audio_path)
        transcript_path.parent.mkdir(parents=True, exist_ok=True)

        model = self._load_model()
        audio = self._decode_audio(audio_path)
        chunk_frames = self._config.chunk_seconds * SAMPLE_RATE
        overlap_frames = self._config.overlap_seconds * SAMPLE_RATE
        step_frames = max(1, chunk_frames - overlap_frames)
        total_chunks = max(1, (len(audio) + step_frames - 1) // step_frames)

        confirmed_text: list[str] = []
        transcript_path.write_text("", encoding="utf-8")

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
                vad_filter=False,
                language=self._config.language,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            if text:
                confirmed_text.append(text)

            transcript_path.write_text("\n\n".join(confirmed_text), encoding="utf-8")
            on_progress(chunk_index, total_chunks, "\n\n".join(confirmed_text), transcript_path)

        return transcript_path

    def transcribe_pcm16_chunk(self, pcm_bytes: bytes) -> str:
        if not pcm_bytes:
            return ""

        model = self._load_model()
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = model.transcribe(
            audio,
            beam_size=1,
            vad_filter=False,
            language=self._config.language,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _load_model(self):  # noqa: ANN202
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "faster-whisper is not installed. Run .\\run.ps1 to install dependencies."
                ) from exc

            self._model = WhisperModel(
                self._config.model_name,
                device=self._config.device,
                compute_type=self._config.compute_type,
            )
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
