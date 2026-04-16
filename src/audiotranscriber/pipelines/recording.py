"""Local WAV recording pipeline for Phase 2."""

from __future__ import annotations

import math
import struct
import threading
import time
import wave
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from audiotranscriber.state import InputSource

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
CHUNK_SECONDS = 0.05
CHUNK_FRAMES = int(SAMPLE_RATE * CHUNK_SECONDS)
MAX_INT16 = 32767

LevelCallback = Callable[[float], None]
ChunkCallback = Callable[[bytes, int], None]
ErrorCallback = Callable[[str], None]
LIVE_CHUNK_SECONDS = 4


class RecordingPipeline:
    """Record microphone or generated test audio to a timestamped WAV file."""

    def __init__(
        self,
        output_dir: Path,
        on_level: LevelCallback,
        on_chunk: ChunkCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._on_level = on_level
        self._on_chunk = on_chunk
        self._on_error = on_error
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._write_lock = threading.Lock()
        self._chunk_buffer = bytearray()
        self._chunk_index = 0
        self._chunk_target_bytes = self._chunk_bytes_for_seconds(LIVE_CHUNK_SECONDS)
        self._wave_file: wave.Wave_write | None = None
        self._output_path: Path | None = None
        self._source = InputSource.TEST_TONE

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @property
    def output_path(self) -> Path | None:
        return self._output_path

    def start(
        self,
        source: InputSource,
        source_path: Path | None = None,
        chunk_seconds: int = LIVE_CHUNK_SECONDS,
    ) -> Path:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Recording is already running.")

        self._source = source
        if source == InputSource.MICROPHONE:
            self._check_microphone_available()
        if source == InputSource.DEV_SAMPLE and source_path is None:
            raise RuntimeError("No dev sample selected for recording.")

        self._stop_event.clear()
        self._pause_event.clear()
        self._chunk_buffer = bytearray()
        self._chunk_index = 0
        self._chunk_target_bytes = self._chunk_bytes_for_seconds(chunk_seconds)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._output_path = self._output_dir / self._timestamped_name()

        self._wave_file = wave.open(str(self._output_path), "wb")
        self._wave_file.setnchannels(CHANNELS)
        self._wave_file.setsampwidth(SAMPLE_WIDTH_BYTES)
        self._wave_file.setframerate(SAMPLE_RATE)

        if source == InputSource.TEST_TONE:
            target = self._record_test_tone
            args = ()
        elif source == InputSource.MICROPHONE:
            target = self._record_microphone
            args = ()
        else:
            target = self._record_dev_sample
            args = (source_path,)

        self._thread = threading.Thread(
            target=self._run_recording_target,
            args=(target, *args),
            name="RecordingPipeline",
            daemon=True,
        )
        self._thread.start()
        return self._output_path

    def _run_recording_target(self, target: Callable[..., None], *args) -> None:  # noqa: ANN002
        try:
            target(*args)
        except Exception as exc:  # noqa: BLE001
            self._on_level(0.0)
            self._close_wave()
            if self._on_error is not None:
                if self._source == InputSource.MICROPHONE:
                    self._on_error(_friendly_microphone_error(exc))
                else:
                    self._on_error(str(exc))

    def pause(self) -> None:
        self._pause_event.set()
        self._on_level(0.0)

    def resume(self) -> None:
        self._pause_event.clear()

    def stop(self) -> Path | None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._flush_live_chunk()
        self._close_wave()
        self._on_level(0.0)
        return self._output_path

    def _record_test_tone(self) -> None:
        frame_index = 0
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(CHUNK_SECONDS)
                continue

            chunk = bytearray()
            level_sum = 0.0
            for index in range(CHUNK_FRAMES):
                t = (frame_index + index) / SAMPLE_RATE
                envelope = 0.45 + 0.35 * math.sin(2 * math.pi * 1.8 * t)
                sample = 0.28 * envelope * math.sin(2 * math.pi * 220 * t)
                sample += 0.08 * envelope * math.sin(2 * math.pi * 440 * t)
                value = int(max(-1.0, min(1.0, sample)) * MAX_INT16)
                level_sum += abs(value) / MAX_INT16
                chunk.extend(struct.pack("<h", value))

            self._write_frames(bytes(chunk))
            self._on_level(min(1.0, level_sum / CHUNK_FRAMES * 4.0))
            frame_index += CHUNK_FRAMES
            time.sleep(CHUNK_SECONDS)

    def _record_microphone(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Microphone support is missing from this app build. "
                "Please reinstall AudioTranscriber."
            ) from exc

        def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
            del frames, time_info, status
            if self._pause_event.is_set() or self._stop_event.is_set():
                self._on_level(0.0)
                return

            raw = bytes(indata)
            self._write_frames(raw)
            self._on_level(_level_from_int16(raw))

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                callback=callback,
                blocksize=CHUNK_FRAMES,
            ):
                while not self._stop_event.is_set():
                    time.sleep(CHUNK_SECONDS)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(_friendly_microphone_error(exc)) from exc

    def _record_dev_sample(self, source_path: Path) -> None:
        audio = _decode_audio_file(source_path)
        cursor = 0
        while not self._stop_event.is_set() and cursor < len(audio):
            if self._pause_event.is_set():
                time.sleep(CHUNK_SECONDS)
                continue

            chunk = audio[cursor : cursor + CHUNK_FRAMES]
            raw = _float_audio_to_int16_bytes(chunk)
            self._write_frames(raw)
            self._on_level(_level_from_int16(raw))
            cursor += CHUNK_FRAMES
            time.sleep(CHUNK_SECONDS)

        self._on_level(0.0)

    def _write_frames(self, frames: bytes) -> None:
        chunks_to_emit: list[tuple[bytes, int]] = []
        with self._write_lock:
            if self._wave_file is not None:
                self._wave_file.writeframes(frames)
            if self._on_chunk is not None:
                self._chunk_buffer.extend(frames)
                while len(self._chunk_buffer) >= self._chunk_target_bytes:
                    self._chunk_index += 1
                    chunk = bytes(self._chunk_buffer[: self._chunk_target_bytes])
                    del self._chunk_buffer[: self._chunk_target_bytes]
                    chunks_to_emit.append((chunk, self._chunk_index))

        for chunk, chunk_index in chunks_to_emit:
            self._on_chunk(chunk, chunk_index)

    def _flush_live_chunk(self) -> None:
        if self._on_chunk is None:
            return

        chunk = None
        chunk_index = 0
        with self._write_lock:
            if self._chunk_buffer:
                self._chunk_index += 1
                chunk_index = self._chunk_index
                chunk = bytes(self._chunk_buffer)
                self._chunk_buffer.clear()

        if chunk:
            self._on_chunk(chunk, chunk_index)

    def _close_wave(self) -> None:
        with self._write_lock:
            if self._wave_file is not None:
                self._wave_file.close()
                self._wave_file = None

    @staticmethod
    def _timestamped_name() -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"recording_{timestamp}.raw.wav"

    @staticmethod
    def _chunk_bytes_for_seconds(seconds: int) -> int:
        return SAMPLE_RATE * max(1, seconds) * SAMPLE_WIDTH_BYTES

    @staticmethod
    def _check_microphone_available() -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Microphone support is missing from this app build. "
                "Please reinstall AudioTranscriber."
            ) from exc

        try:
            sd.query_devices(kind="input")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(_friendly_microphone_error(exc)) from exc


def _level_from_int16(raw: bytes) -> float:
    if not raw:
        return 0.0

    sample_count = len(raw) // SAMPLE_WIDTH_BYTES
    if sample_count == 0:
        return 0.0

    total = 0
    for (sample,) in struct.iter_unpack("<h", raw[: sample_count * SAMPLE_WIDTH_BYTES]):
        total += abs(sample)
    return min(1.0, (total / sample_count) / MAX_INT16 * 4.0)


def _friendly_microphone_error(error: Exception) -> str:
    detail = str(error).strip()
    lower_detail = detail.lower()
    if any(word in lower_detail for word in {"permission", "access", "denied", "privacy"}):
        return (
            "Microphone access was blocked. Allow AudioTranscriber to use the microphone "
            "in Windows privacy settings, then restart the app and try again."
        )

    if any(word in lower_detail for word in {"device", "input", "invalid", "unavailable"}):
        return (
            "No microphone input was found. Connect a microphone, check that Windows sees "
            "an input device, then restart AudioTranscriber."
        )

    return (
        "The microphone could not be started. Check that a microphone is connected, that "
        "Windows microphone permissions are enabled, and that no other app is blocking it."
    )


def _decode_audio_file(path: Path):
    try:
        from faster_whisper.audio import decode_audio
    except ImportError as exc:
        raise RuntimeError("faster-whisper is required for dev sample input.") from exc

    return decode_audio(str(path), sampling_rate=SAMPLE_RATE)


def _float_audio_to_int16_bytes(audio) -> bytes:  # noqa: ANN001
    chunk = bytearray()
    for sample in audio:
        value = int(max(-1.0, min(1.0, float(sample))) * MAX_INT16)
        chunk.extend(struct.pack("<h", value))
    return bytes(chunk)
