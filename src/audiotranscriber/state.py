"""Shared app state for the recorder strip."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecorderStatus(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    PROCESSING = "processing"


class InputSource(str, Enum):
    TEST_TONE = "test_tone"
    MICROPHONE = "microphone"
    DEV_SAMPLE = "dev_sample"


class TranscriptionLanguage(str, Enum):
    AUTO = "auto"
    DUTCH = "nl"
    ENGLISH = "en"


@dataclass(frozen=True)
class RecorderState:
    status: RecorderStatus = RecorderStatus.IDLE
    elapsed_seconds: int = 0
    transcript_open: bool = False
    last_update_seconds: int | None = None
    input_source: InputSource = InputSource.TEST_TONE
    transcription_language: TranscriptionLanguage = TranscriptionLanguage.AUTO
    audio_level: float = 0.0
    output_audio_path: str | None = None
    transcript_output_path: str | None = None
    selected_dev_sample_path: str | None = None
    transcription_current_chunk: int = 0
    transcription_total_chunks: int = 0
    error_message: str | None = None
    preview_text: str = (
        "Nog geen opname opgeslagen. Gebruik voor testen zonder microfoon de "
        "ingebouwde testtoon via de rechtermuisknop."
    )
