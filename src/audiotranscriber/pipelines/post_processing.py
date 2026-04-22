"""Post-recording export and high-quality transcript helpers."""

from __future__ import annotations

import shutil
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path

from audiotranscriber.pipelines.transcription import (
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    TranscriptionConfig,
)
from audiotranscriber.system_info import logical_cpu_threads, physical_cpu_cores

HIGH_QUALITY_MODEL_NAME = "small"
HIGH_QUALITY_MODEL_LABEL = "small"
MP3_BITRATE = "96k"
ProgressCallback = Callable[[int, int], None]


def backup_mp3_path_for(audio_path: Path) -> Path:
    return audio_path.with_name(f"{audio_path.stem}.backup.mp3")


def high_quality_transcript_path_for(audio_path: Path) -> Path:
    return audio_path.with_name(f"{audio_path.stem}.high-quality.txt")


def high_quality_transcription_config(
    language: str | None,
    model_cache_dir: Path | None = None,
) -> TranscriptionConfig:
    return TranscriptionConfig(
        model_name=HIGH_QUALITY_MODEL_NAME,
        device=DEFAULT_DEVICE,
        compute_type=DEFAULT_COMPUTE_TYPE,
        cpu_threads=high_quality_cpu_threads(),
        chunk_seconds=None,
        language=language,
        model_cache_dir=model_cache_dir,
        vad_filter=False,
        full_audio_defaults=True,
    )


def high_quality_cpu_threads() -> int:
    physical = _physical_cpu_cores()
    if physical <= 2:
        return max(1, physical)
    if physical <= 4:
        return physical - 1
    return 4


def _physical_cpu_cores() -> int:
    physical = physical_cpu_cores()
    if physical is not None:
        return physical
    logical = logical_cpu_threads()
    if logical is None:
        return 1
    return max(1, logical // 2)


def export_mp3_backup(audio_path: Path, on_progress: ProgressCallback | None = None) -> Path:
    ffmpeg = _ffmpeg_executable()

    audio_path = audio_path.resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    output_path = backup_mp3_path_for(audio_path)
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        MP3_BITRATE,
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]

    duration_seconds = wav_duration_seconds(audio_path)
    if on_progress is not None:
        on_progress(0, 100)

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=_creation_flags(),
    )
    assert process.stdout is not None
    for line in process.stdout:
        if duration_seconds is None:
            continue
        key, _, value = line.strip().partition("=")
        if key != "out_time_ms":
            continue
        try:
            seconds_done = int(value) / 1_000_000
        except ValueError:
            continue
        progress = min(99, max(0, round((seconds_done / duration_seconds) * 100)))
        if on_progress is not None:
            on_progress(progress, 100)

    _, stderr = process.communicate()
    if process.returncode != 0:
        detail = (stderr or "unknown ffmpeg error").strip()
        raise RuntimeError(f"MP3 export failed: {detail}")
    if on_progress is not None:
        on_progress(100, 100)
    return output_path


def _ffmpeg_executable() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg is not None:
        return system_ffmpeg

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError(
            "ffmpeg is not available yet. Run .\\run.ps1 once to install the bundled "
            "ffmpeg helper, then try the MP3 export again."
        ) from exc

    return imageio_ffmpeg.get_ffmpeg_exe()


def _creation_flags() -> int:
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


def wav_duration_seconds(audio_path: Path) -> float | None:
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
    except (wave.Error, OSError):
        return None
    if sample_rate <= 0:
        return None
    return frames / sample_rate
