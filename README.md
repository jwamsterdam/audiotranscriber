# AudioTranscriber

Compact local recording and transcription strip for desktop interviews and conversations.

## Phase 1 / 2 / 3.5

This checkpoint implements the PySide6 visual MVP, local recording basics, and
chunked transcription:

- Floating compact strip with dark rounded styling.
- Collapsible transcript panel below the strip.
- Idle, recording, paused, and processing states.
- Green idle, blinking red recording, yellow processing/paused indicators.
- Timer and lightweight waveform preview.
- Timestamped raw WAV recording. Dev uses `recordings/`; production uses
  `Documents/AudioTranscriber/Recordings`.
- Microphone input is the default input source.
- Test tone input for machines without a microphone in the development profile.
- Right-click action to open the recordings folder.
- Dev sample selection from ignored `dev_samples/` for Phase 3 transcription work in
  the development profile.
- Chunked background transcription with `faster-whisper` defaults: `base`, `cpu`, `int8`.
- Incremental `.txt` transcript saving next to the recorded audio source.
- Stop button cancels active transcription after the current chunk completes.
- Transcript panel uses a scrollable viewport during long transcripts.
- Floating strip can snap magnetically to the top of the screen and releases when pulled down.
- Right-click playback for the selected dev sample.
- Dev samples can be used as a recording input source for end-to-end testing.
- Near-real-time transcript preview updates from short completed chunks while recording.
- Main strip language selector: `AUTO`, `NL`, or `EN`.
- Language can be changed during recording; new chunks use the updated selection.
- Stop only drains/merges queued live chunks instead of starting a second transcription pass.
- Post-processing actions for any saved WAV recording:
  - `WAV to MP3 Backup` lets you pick a WAV and creates `*.backup.mp3`.
  - `WAV to High Quality Transcript` lets you pick a WAV and creates
    `*.high-quality.txt` using the high-quality preset.
  - High-quality transcription confirms the selected language before starting.
  - The transcript panel shows a progress bar while post-processing runs.
- Production profile keeps the context menu focused on microphone recording,
  recordings folder, post-processing, update check, and close.

Phase 2 raw audio format:

```text
WAV, 16 kHz, mono, 16-bit PCM
Default input: microphone
```

Development audio samples can be placed in `dev_samples/`. That folder is ignored by git.
Use the app's right-click menu to select a sample. Choose `Use dev sample input` when you
want the red record button to record that sample into a new WAV and then run the normal
stop/transcription flow.

Phase 3 transcription defaults:

```text
model=base
device=cpu
compute_type=int8
live_chunk_seconds=4
language=auto | nl | en
```

Post-processing presets:

```text
mp3_backup=ffmpeg via system PATH or bundled imageio-ffmpeg, libmp3lame, 96k
high_quality_transcript=faster-whisper small, cpu, int8, 15s chunks
```

Build/runtime profiles:

```text
AUDIOTRANSCRIBER_PROFILE=dev
  project recordings folder
  input selector, test tone, and dev sample menu actions
  model cache in .models/

AUDIOTRANSCRIBER_PROFILE=prod
  Documents/AudioTranscriber/Recordings
  microphone-only production menu
  model cache in the OS app data folder
  models download on first use
```

Optional update URL:

```text
AUDIOTRANSCRIBER_UPDATE_URL=https://your-release-page
```

If no update URL is configured, the production menu still shows `Check for updates`,
but it displays a friendly "not configured yet" message.

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
They explicitly run the `dev` profile.

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

Production folder build on Windows:

```powershell
.\build-windows.ps1
```

This creates a PyInstaller folder build at `dist/AudioTranscriber/AudioTranscriber.exe`.
Packaged/frozen builds default to the `prod` profile.

Windows installer build:

```powershell
.\package-windows.ps1
```

This runs the production folder build and then uses Inno Setup 6, when installed, to
create `installer/AudioTranscriberSetup.exe`.

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
Phase 3.5 now uses one chunk-based live transcription pass written directly to `.txt`.
Post-processing can create smaller MP3 backups and high-quality transcript files.
Phase 4 should finalize MP3 export, error handling, settings, and packaging preparation.
