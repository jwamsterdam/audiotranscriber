# Agent Notes

This project is a lightweight local desktop recorder and transcription strip.

## Current Phase

Phase 3.5 is in progress. The app has a PySide6 UI, local WAV recording, a test tone input
for machines without a microphone, optional microphone input through `sounddevice`, a timer,
audio level preview, a collapsible transcript panel, and chunked `faster-whisper`
transcription.

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
- The floating strip can magnetically snap to the top screen edge and release when pulled down.
- Status colors:
  - Green: idle / ready.
  - Red blinking: recording.
  - Yellow: processing / transcribing.
- Be honest about chunked transcription. Show it as preview/recent transcript, not perfect live dictation.

## Phase Plan

Phase 2:

- Current raw format is WAV, 16 kHz, mono, 16-bit PCM.
- Microphone input is the default.
- Test tone input is available from the right-click menu.
- Microphone input is available from the right-click menu where a device exists.
- Recordings are saved in `recordings/` and should not be committed.
- Development audio samples live in `dev_samples/` and should not be committed.
- The UI can select a dev sample from the right-click menu for Phase 3 transcription work.

Phase 3:

- Default config is `model=base`, `device=cpu`, `compute_type=int8`.
- Live preview chunks are currently 4 seconds for more responsive updates while recording.
- The main strip language selector supports auto-detect, Dutch (`nl`), and English (`en`),
  and can be changed while recording so future chunks use the updated language.
- Transcripts are saved incrementally as `.txt` next to the recorded audio file.
- Dev samples in `dev_samples/` can be selected from the right-click menu.
- Dev samples can be used directly as an input source for end-to-end recording/transcription tests.
- Near-real-time preview is chunk-based and updates from completed chunks while recording.
- After stop, queued live chunks are drained and saved. Do not start a second transcription pass
  for the normal recording flow.
- UI transcript updates preserve scroll position unless the user is already at the bottom.
- Post-processing is separate from live recording and starts by selecting a WAV file.
- MP3 backup uses `*.backup.mp3`.
- MP3 backup resolves ffmpeg from the system PATH first and then from `imageio-ffmpeg`,
  which is the packaging-friendly fallback.
- High-quality transcript uses the user-facing `*.high-quality.txt` filename and internally
  maps to faster-whisper `small`, `cpu`, `int8`, 15-second chunks.

Phase 4:

- Export/finalize MP3.
- Add polish, error handling, and settings cleanup.
- Prepare for packaging on Windows and macOS.

## Development

Use the one-command Windows runner when possible:

```powershell
.\run.ps1
```

`run.ps1`, `dev.ps1`, and `run.bat` set `AUDIOTRANSCRIBER_PROFILE=dev`.
Frozen/packaged builds default to `prod` unless the environment variable overrides it.
Profile behavior lives in `src/audiotranscriber/app_config.py`.

Dev profile:
- Uses project-local `recordings/`.
- Keeps input selector, test tone, and dev sample menu actions.
- Uses `.models/` for the faster-whisper cache.

Prod profile:
- Uses microphone input only.
- Hides dev sample/test input menu actions.
- Stores recordings in `Documents/AudioTranscriber/Recordings`.
- Stores models in the OS app data folder and downloads them on first use.
- Checks GitHub Releases for updates using `jwamsterdam/audiotranscriber` by default.
- `Refresh transcription models` clears the model cache so the next transcription downloads fresh files.

Use restart-on-save during UI iteration:

```powershell
.\dev.ps1
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
