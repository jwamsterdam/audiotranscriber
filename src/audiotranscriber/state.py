"""Shared app state for the recorder strip."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecorderStatus(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    PROCESSING = "processing"


@dataclass(frozen=True)
class RecorderState:
    status: RecorderStatus = RecorderStatus.IDLE
    elapsed_seconds: int = 0
    transcript_open: bool = False
    last_update_seconds: int | None = None
    preview_text: str = (
        "Dus ja, dat was voor mij echt een keerpunt. Ik dacht altijd: ik doe mijn "
        "werk gewoon goed, dan komt het vanzelf wel. Maar op een gegeven moment "
        "merk je dat het niet alleen gaat om wat je doet, maar ook om hoe je het "
        "brengt en met wie je werkt."
    )

