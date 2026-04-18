"""Incremental transcript file writer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriptWriter:
    """Keep the in-memory transcript and on-disk transcript in sync."""

    path: Path
    text: str = ""
    chunks_with_text: int = 0

    def reset(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")
        self.text = ""
        self.chunks_with_text = 0

    def append(self, text: str, *, clean_overlap: bool = False) -> str:
        next_text = text.strip()
        if clean_overlap:
            next_text = clean_next_text(self.text, next_text)
        if not next_text:
            return self.text

        prefix = "\n\n" if self.text else ""
        with self.path.open("a", encoding="utf-8") as transcript_file:
            transcript_file.write(f"{prefix}{next_text}")

        self.text = f"{self.text}{prefix}{next_text}"
        self.chunks_with_text += 1
        return self.text


def clean_next_text(existing_text: str, next_text: str) -> str:
    """Trim repeated leading words when adjacent chunks overlap."""

    if not existing_text or not next_text:
        return next_text

    previous_words = existing_text.rsplit("\n\n", maxsplit=1)[-1].split()
    current_words = next_text.split()
    max_overlap = min(len(previous_words), len(current_words), 8)
    for size in range(max_overlap, 0, -1):
        if previous_words[-size:] == current_words[:size]:
            return " ".join(current_words[size:])
    return next_text
