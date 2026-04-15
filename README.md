# AudioTranscriber

Compact local recording and transcription strip for desktop interviews and conversations.

## Phase 1

This checkpoint implements the PySide6 visual MVP only:

- Floating compact strip with dark rounded styling.
- Collapsible transcript panel below the strip.
- Idle, recording, paused, and processing states.
- Green idle, blinking red recording, yellow processing/paused indicators.
- Timer and lightweight animated waveform preview.
- Dummy state transitions only. No real audio is recorded in Phase 1.

## Run

On Windows, the easiest review command is:

```powershell
.\run.ps1
```

If PowerShell script execution gets in the way, use:

```powershell
.\run.bat
```

Both commands create `.venv` if needed, install the local package, and start the app.

For UI iteration with automatic restart after Python file changes:

```powershell
.\dev.ps1
```

This is restart-on-save rather than true in-place hot reload. The app closes and reopens
when files under `src/` change.

Manual setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m audiotranscriber.main
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m audiotranscriber.main
```

## Phase Notes

Phase 2 should add real recording, pause/stop behavior, timestamped output paths, and a real audio level indicator.
Phase 3 should add chunking plus faster-whisper background transcription.
Phase 4 should finalize MP3 export, error handling, settings, and packaging preparation.
