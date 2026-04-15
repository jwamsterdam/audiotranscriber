# Agent Notes

This project is a lightweight local desktop recorder and transcription strip.

## Current Phase

Phase 1 is implemented only. The app has a PySide6 UI, dummy state transitions, a timer,
animated waveform preview, and a collapsible transcript panel. It does not record audio yet.

## Architecture

- UI lives in `src/audiotranscriber/ui/`.
- App state lives in `src/audiotranscriber/state.py`.
- Controller logic lives in `src/audiotranscriber/controllers/`.
- Recording pipeline work should go in `src/audiotranscriber/pipelines/recording.py`.
- Transcription pipeline work should go in `src/audiotranscriber/pipelines/transcription.py`.

Keep the UI, recording pipeline, transcription pipeline, and controller responsibilities separate.

## Product Direction

- Keep the app compact, calm, and utility-like.
- Match the supplied screenshot as the primary visual reference.
- Default transcript state should stay collapsed.
- Expanded transcript should open below the strip.
- Status colors:
  - Green: idle / ready.
  - Red blinking: recording.
  - Yellow: processing / transcribing.
- Be honest about chunked transcription. Show it as preview/recent transcript, not perfect live dictation.

## Phase Plan

Phase 2:

- Add real microphone recording.
- Add record, pause, and stop behavior.
- Add timestamp-based filenames.
- Save raw audio safely.
- Replace dummy waveform activity with real audio level activity.

Phase 3:

- Add chunking pipeline.
- Add background faster-whisper transcription.
- Append confirmed transcript chunks.
- Save draft/final transcript text.

Phase 4:

- Export/finalize MP3.
- Add polish, error handling, and settings cleanup.
- Prepare for packaging on Windows and macOS.

## Development

Use the one-command Windows runner when possible:

```powershell
.\run.ps1
```

Fallback:

```powershell
.\run.bat
```

Manual run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m audiotranscriber.main
```

## Implementation Preferences

- Prefer simple, stable Python dependencies.
- Use PySide6 for GUI work.
- Use faster-whisper for transcription in Phase 3.
- Use ffmpeg where appropriate for conversion/export.
- For Phase 2 capture, prefer a Python-accessible recording backend first if it is simpler and more reliable cross-platform than controlling ffmpeg directly.
- Avoid heavy visuals or complex spectrum analysis.
- Keep code modular enough for later packaging.

