# AudioTranscriber

Compact local recording and transcription strip for desktop interviews and conversations.

## Phase 1 / 2

This checkpoint implements the PySide6 visual MVP plus Phase 2 recording basics:

- Floating compact strip with dark rounded styling.
- Collapsible transcript panel below the strip.
- Idle, recording, paused, and processing states.
- Green idle, blinking red recording, yellow processing/paused indicators.
- Timer and lightweight waveform preview.
- Timestamped raw WAV recording to `recordings/`.
- Test tone input for machines without a microphone.
- Microphone input option for machines with a local input device.
- Right-click actions to open the recordings folder, selected audio, or transcript.
- Dev sample selection from ignored `dev_samples/` for Phase 3 transcription work.
- Chunked background transcription with `faster-whisper` defaults: `base`, `cpu`, `int8`.
- Incremental `.txt` transcript saving next to the selected audio source.
- Stop button cancels active transcription after the current chunk completes.
- Transcript panel uses a scrollable viewport during long transcripts.

Phase 2 raw audio format:

```text
WAV, 16 kHz, mono, 16-bit PCM
```

Development audio samples can be placed in `dev_samples/`. That folder is ignored by git.
Use the app's right-click menu to select a sample or use the latest sample, then choose
`Transcribe selected audio`. The red record button always creates a new recording.

Phase 3 transcription defaults:

```text
model=base
device=cpu
compute_type=int8
chunk_seconds=15
```

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

Phase 2 now has raw WAV recording, pause/stop behavior, timestamped output paths, test tone input, microphone input, and a real audio level indicator.
Phase 3 adds chunking plus faster-whisper background transcription.
Phase 4 should finalize MP3 export, error handling, settings, and packaging preparation.
