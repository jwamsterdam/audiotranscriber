"""GitHub release update checks and local model cache helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from audiotranscriber.app_config import APP_VERSION


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str | None
    release_url: str
    update_available: bool
    model_cache_summary: str
    error: str | None = None


def check_for_updates(update_repo: str, model_cache_dir: Path) -> UpdateInfo:
    import json
    import urllib.error
    import urllib.request

    model_summary = model_cache_summary(model_cache_dir)
    release_url = f"https://github.com/{update_repo}/releases"
    api_url = f"https://api.github.com/repos/{update_repo}/releases/latest"

    try:
        request = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "AudioTranscriber",
            },
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            error = (
                "No GitHub Release was found for this app yet. Create a release in "
                f"{update_repo}, then try again."
            )
        else:
            error = (
                "Could not check GitHub Releases right now. Check your internet "
                "connection and try again."
            )
        return UpdateInfo(
            current_version=APP_VERSION,
            latest_version=None,
            release_url=release_url,
            update_available=False,
            model_cache_summary=model_summary,
            error=error,
        )
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return UpdateInfo(
            current_version=APP_VERSION,
            latest_version=None,
            release_url=release_url,
            update_available=False,
            model_cache_summary=model_summary,
            error=(
                "Could not check GitHub Releases right now. Check your internet "
                "connection and try again."
            ),
        )

    latest_version = _clean_version(str(data.get("tag_name") or data.get("name") or ""))
    html_url = str(data.get("html_url") or release_url)
    update_available = _version_tuple(latest_version) > _version_tuple(APP_VERSION)
    return UpdateInfo(
        current_version=APP_VERSION,
        latest_version=latest_version or None,
        release_url=html_url,
        update_available=update_available,
        model_cache_summary=model_summary,
    )


def model_cache_summary(model_cache_dir: Path) -> str:
    if not model_cache_dir.exists():
        return f"No model cache found yet.\n{model_cache_dir}"

    files = [path for path in model_cache_dir.rglob("*") if path.is_file()]
    if not files:
        return f"Model cache folder exists but is empty.\n{model_cache_dir}"

    size_mb = sum(path.stat().st_size for path in files) / (1024 * 1024)
    return f"Model cache present: {len(files)} files, {size_mb:.1f} MB.\n{model_cache_dir}"


def refresh_model_cache(model_cache_dir: Path) -> str:
    if not model_cache_dir.exists():
        model_cache_dir.mkdir(parents=True, exist_ok=True)
        return (
            "No cached transcription models were found yet. "
            "The model will download on the next transcription."
        )

    try:
        shutil.rmtree(model_cache_dir)
        model_cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            "Could not refresh the transcription model cache. Close AudioTranscriber "
            "and try again. Windows may still be locking model files."
        ) from exc

    return "Transcription model cache cleared. The model will download on the next transcription."


def _clean_version(version: str) -> str:
    return version.strip().lstrip("vV")


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in _clean_version(version).split("."):
        digits = "".join(character for character in part if character.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts or [0])
