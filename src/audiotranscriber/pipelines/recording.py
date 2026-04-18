"""Local WAV recording pipeline."""

from __future__ import annotations

import math
import logging
import struct
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
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
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MicrophoneDevice:
    index: int
    name: str
    host_api: str
    max_input_channels: int
    is_default: bool = False

    @property
    def key(self) -> str:
        return f"{_normalise_device_part(self.host_api)}::{_normalise_device_part(self.name)}"

    @property
    def label(self) -> str:
        return f"{self.name} ({self.host_api})"


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
        self._microphone_device_key: str | None = None
        self._started_event = threading.Event()
        self._startup_failed: Exception | None = None

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @property
    def output_path(self) -> Path | None:
        return self._output_path

    @staticmethod
    def list_microphone_devices() -> list[MicrophoneDevice]:
        try:
            import sounddevice as sd
        except ImportError:
            return []

        try:
            return _list_input_devices(sd)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not read audio devices: %s", exc)
            return []

    @staticmethod
    def microphone_diagnostics(selected_device_key: str | None = None) -> str:
        try:
            import sounddevice as sd
        except ImportError:
            return "Microphone backend is missing from this app build."

        try:
            input_devices = _list_input_devices(sd)
        except Exception as exc:  # noqa: BLE001
            return f"Could not read audio devices:\n{exc}"

        lines = ["Detected input devices:"]
        for device in input_devices:
            marker = ""
            if device.is_default:
                marker += " (default)"
            if selected_device_key and device.key == selected_device_key:
                marker += " (selected)"
            lines.append(
                f"- {device.index}: {device.name} "
                f"({device.max_input_channels} channels, {device.host_api}){marker}"
            )

        if not input_devices:
            lines.append("- none")
        return "\n".join(lines)

    @staticmethod
    def default_microphone_device_label() -> str:
        try:
            import sounddevice as sd
        except ImportError:
            return "Microphone backend missing"

        try:
            input_devices = _list_input_devices(sd)
        except Exception:  # noqa: BLE001
            return "None / unavailable"

        for device in input_devices:
            if device.is_default:
                return device.label
        return "None / unavailable"

    def start(
        self,
        source: InputSource,
        source_path: Path | None = None,
        microphone_device_key: str | None = None,
        chunk_seconds: int = LIVE_CHUNK_SECONDS,
    ) -> Path:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Recording is already running.")

        self._source = source
        self._microphone_device_key = microphone_device_key
        if source == InputSource.MICROPHONE:
            self._check_microphone_available(microphone_device_key)
        if source == InputSource.DEV_SAMPLE and source_path is None:
            raise RuntimeError("No dev sample selected for recording.")

        self._stop_event.clear()
        self._pause_event.clear()
        self._started_event.clear()
        self._startup_failed = None
        self._chunk_buffer = bytearray()
        self._chunk_index = 0
        self._chunk_target_bytes = self._chunk_bytes_for_seconds(chunk_seconds)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._output_path = self._output_dir / self._timestamped_name()

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
        if not self._started_event.wait(timeout=2):
            self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=1)
                if not self._thread.is_alive():
                    self._thread = None
            self._close_wave()
            self._delete_empty_output()
            raise RuntimeError(
                "De opname kon niet worden gestart. Probeer het opnieuw."
            )
        if self._startup_failed is not None:
            self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=1)
                if not self._thread.is_alive():
                    self._thread = None
            self._delete_empty_output()
            raise self._startup_failed
        return self._output_path

    def _run_recording_target(self, target: Callable[..., None], *args) -> None:  # noqa: ANN002
        try:
            target(*args)
        except Exception as exc:  # noqa: BLE001
            if not self._started_event.is_set():
                self._startup_failed = exc
                self._started_event.set()
            self._on_level(0.0)
            self._close_wave()
            self._delete_empty_output()
            if self._startup_failed is not None:
                return
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
        self._open_wave_file()
        self._started_event.set()
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
        device_index, device_name = _select_input_device(sd, self._microphone_device_key)

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
                device=device_index,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                callback=callback,
                blocksize=CHUNK_FRAMES,
            ):
                self._open_wave_file()
                self._started_event.set()
                while not self._stop_event.is_set():
                    time.sleep(CHUNK_SECONDS)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(_friendly_microphone_error(exc, device_name)) from exc

    def _record_dev_sample(self, source_path: Path) -> None:
        audio = _decode_audio_file(source_path)
        self._open_wave_file()
        self._started_event.set()
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

    def _open_wave_file(self) -> None:
        with self._write_lock:
            if self._wave_file is not None:
                return
            if self._output_path is None:
                raise RuntimeError("No output path was prepared for recording.")
            self._wave_file = wave.open(str(self._output_path), "wb")
            self._wave_file.setnchannels(CHANNELS)
            self._wave_file.setsampwidth(SAMPLE_WIDTH_BYTES)
            self._wave_file.setframerate(SAMPLE_RATE)

    def _delete_empty_output(self) -> None:
        path = self._output_path
        if path is None or not path.exists():
            return
        try:
            if path.stat().st_size == 0:
                path.unlink()
        except OSError:
            pass

    @staticmethod
    def _timestamped_name() -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"recording_{timestamp}.raw.wav"

    @staticmethod
    def _chunk_bytes_for_seconds(seconds: int) -> int:
        return SAMPLE_RATE * max(1, seconds) * SAMPLE_WIDTH_BYTES

    @staticmethod
    def _check_microphone_available(microphone_device_key: str | None = None) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Microphone support is missing from this app build. "
                "Please reinstall AudioTranscriber."
            ) from exc

        _select_input_device(sd, microphone_device_key)


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


def _list_input_devices(sd) -> list[MicrophoneDevice]:  # noqa: ANN001
    try:
        devices = sd.query_devices()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(_friendly_microphone_error(exc)) from exc

    try:
        host_apis = sd.query_hostapis()
    except Exception:  # noqa: BLE001
        host_apis = []

    try:
        default_input = sd.default.device[0]
    except Exception:  # noqa: BLE001
        default_input = None

    input_devices: list[MicrophoneDevice] = []
    for index, device in enumerate(devices):
        channels = int(device.get("max_input_channels", 0))
        if channels <= 0:
            continue

        host_api_name = "Unknown"
        try:
            host_api_index = int(device.get("hostapi", -1))
            host_api_name = str(host_apis[host_api_index].get("name", host_api_name))
        except Exception:  # noqa: BLE001
            host_api_name = "Unknown"

        input_devices.append(
            MicrophoneDevice(
                index=index,
                name=str(device.get("name", f"Input device {index}")),
                host_api=host_api_name,
                max_input_channels=channels,
                is_default=isinstance(default_input, int) and index == default_input,
            )
        )

    return input_devices


def _select_input_device(
    sd,  # noqa: ANN001
    preferred_device_key: str | None = None,
) -> tuple[int, str]:
    input_devices = _list_input_devices(sd)

    if not input_devices:
        raise RuntimeError(
            "Geen microfooningang gevonden. Sluit een microfoon of lijningang aan, "
            "controleer of Windows de ingang ziet en probeer het daarna opnieuw."
        )

    if preferred_device_key:
        for device in input_devices:
            if device.key == preferred_device_key:
                return device.index, device.label

    try:
        default_input = sd.default.device[0]
    except Exception:  # noqa: BLE001
        default_input = None

    if isinstance(default_input, int) and default_input >= 0:
        for device in input_devices:
            if device.index == default_input:
                return device.index, device.label

    fallback = input_devices[0]
    return fallback.index, fallback.label


def _normalise_device_part(value: str) -> str:
    return " ".join(value.casefold().split())


def _friendly_microphone_error(error: Exception, device_name: str | None = None) -> str:
    detail = str(error).strip()
    lower_detail = detail.lower()
    device_hint = f"\n\nGeselecteerde ingang: {device_name}" if device_name else ""
    if any(word in lower_detail for word in {"permission", "access", "denied", "privacy"}):
        return (
            "Microfoontoegang is geblokkeerd. Geef AudioTranscriber toegang tot de "
            "microfoon in de Windows privacy-instellingen en probeer het daarna opnieuw."
            f"{device_hint}"
        )

    if any(word in lower_detail for word in {"device", "input", "invalid", "unavailable"}):
        return (
            "Geen microfooningang gevonden. Sluit een microfoon of lijningang aan, "
            "controleer of Windows de ingang ziet en probeer het daarna opnieuw."
            f"{device_hint}"
        )

    return (
        "De microfoon kon niet worden gestart. Controleer of de ingang is aangesloten, "
        "of Windows microfoontoegang toestaat en of geen andere app de ingang blokkeert."
        f"{device_hint}"
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
