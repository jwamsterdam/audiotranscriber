"""Runtime/build profile configuration."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from audiotranscriber.state import InputSource

APP_NAME = "AudioTranscriber"
APP_VERSION = "0.1.0"
DEFAULT_UPDATE_REPO = "jwamsterdam/audiotranscriber"
PROFILE_ENV_VAR = "AUDIOTRANSCRIBER_PROFILE"
UPDATE_URL_ENV_VAR = "AUDIOTRANSCRIBER_UPDATE_URL"
UPDATE_REPO_ENV_VAR = "AUDIOTRANSCRIBER_UPDATE_REPO"


@dataclass(frozen=True)
class AppConfig:
    profile: str
    show_input_selector: bool
    show_dev_samples: bool
    show_test_tone: bool
    default_input_source: InputSource
    recordings_dir: Path
    model_cache_dir: Path
    download_models_on_first_use: bool
    enable_update_check: bool
    update_repo: str
    update_url: str | None


def load_app_config() -> AppConfig:
    default_profile = "prod" if getattr(sys, "frozen", False) else "dev"
    profile = os.environ.get(PROFILE_ENV_VAR, default_profile).strip().lower()
    if profile == "prod":
        return _prod_config()
    return _dev_config()


def _dev_config() -> AppConfig:
    root = Path.cwd()
    return AppConfig(
        profile="dev",
        show_input_selector=True,
        show_dev_samples=True,
        show_test_tone=True,
        default_input_source=InputSource.MICROPHONE,
        recordings_dir=root / "recordings",
        model_cache_dir=root / ".models",
        download_models_on_first_use=True,
        enable_update_check=True,
        update_repo=os.environ.get(UPDATE_REPO_ENV_VAR, DEFAULT_UPDATE_REPO),
        update_url=os.environ.get(UPDATE_URL_ENV_VAR),
    )


def _prod_config() -> AppConfig:
    return AppConfig(
        profile="prod",
        show_input_selector=False,
        show_dev_samples=False,
        show_test_tone=False,
        default_input_source=InputSource.MICROPHONE,
        recordings_dir=_documents_recordings_dir(),
        model_cache_dir=_app_data_dir() / "models",
        download_models_on_first_use=True,
        enable_update_check=True,
        update_repo=os.environ.get(UPDATE_REPO_ENV_VAR, DEFAULT_UPDATE_REPO),
        update_url=os.environ.get(UPDATE_URL_ENV_VAR),
    )


def _documents_recordings_dir() -> Path:
    documents = Path.home() / "Documents"
    return documents / APP_NAME / "Recordings"


def _app_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
