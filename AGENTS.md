# Agent Notes

AudioTranscriber is a lightweight local desktop recorder and transcription strip.
It is designed for interviews and sensitive conversations where recordings and
transcripts should stay on the user's machine.

## Current Product State

- PySide6 desktop app with a compact floating strip.
- Default transcript panel state is collapsed.
- Expanded transcript panel opens below the strip.
- The strip can magnetically snap to the top screen edge and release when pulled down.
- One primary record/status button:
  - red while idle or recording;
  - yellow while processing/transcribing;
  - subtle pulse during recording/processing.
- Stop and pause are separate controls.
- Collapsed mode uses a compact 7-bar waveform.
- Expanded mode uses a wider, calmer waveform.
- Live captions are white.
- System and error messages are light grey and should not use techy labels.
- Keep the app compact, calm, and utility-like.

## Privacy And Local-First Behavior

- Recordings are local.
- Transcripts are local.
- `faster-whisper` transcription runs locally.
- Do not add cloud transcription, telemetry, or upload behavior unless the user explicitly asks.
- GitHub Releases update checks are allowed in production and must not upload audio or transcript content.
- Whisper model files may be downloaded on first use or when the user refreshes the local model cache.

## Architecture

- UI lives in `src/audiotranscriber/ui/`.
- App state lives in `src/audiotranscriber/state.py`.
- Controller logic lives in `src/audiotranscriber/controllers/`.
- Recording pipeline work goes in `src/audiotranscriber/pipelines/recording.py`.
- Transcription pipeline work goes in `src/audiotranscriber/pipelines/transcription.py`.
- Post-processing work goes in `src/audiotranscriber/pipelines/post_processing.py`.
- Runtime/build profile behavior lives in `src/audiotranscriber/app_config.py`.
- Keep UI, recording, transcription, post-processing, and controller responsibilities separate.

## Recording And Transcription Behavior

- Raw recording format is WAV, 16 kHz, mono, 16-bit PCM.
- Microphone input is the production default.
- In dev profile, test tone and dev sample inputs are available from the right-click menu.
- Recordings are saved in `recordings/` in dev and should not be committed.
- Production recordings are saved in `Documents/AudioTranscriber/Recordings`.
- Development audio samples live in `dev_samples/` and should not be committed.
- Do not create empty WAV/TXT artifacts when microphone startup fails.
- The record button must not start a second recording while recording or processing.
- Pause should allow resume through the record button.
- Stop should stop recording or cancel processing.

Live transcription:

- Uses `base`, `cpu`, `int8`.
- `cpu_threads=0`.
- `vad_filter=false`.
- `beam_size=1`.
- Live preview chunks are 4 seconds.
- The language selector supports auto-detect, Dutch (`nl`), and English (`en`).
- Language can be changed while recording so future chunks use the updated language.
- Transcripts are saved incrementally as `.txt` next to the recorded audio file.
- Near-real-time preview is chunk-based and updates from completed chunks while recording.
- After stop, queued live chunks are drained and saved. Do not start a second transcription pass for the normal recording flow.
- UI transcript updates should preserve scroll position unless the user is already at the bottom.

High-quality transcription:

- Starts separately by selecting a WAV file.
- Uses user-facing `*.high-quality.txt` output.
- Uses `small`, `cpu`, `int8`, 15-second chunks.
- Uses `vad_filter=true`.
- Uses `beam_size=1`.
- Uses the physical-core CPU thread formula:
  - physical <= 2: use all physical cores;
  - physical <= 4: keep one physical core free;
  - physical > 4: cap at 4 threads.

MP3 backup:

- Starts separately by selecting a WAV file.
- Uses `*.backup.mp3`.
- Resolves ffmpeg from the system PATH first and then from `imageio-ffmpeg`.

## Microphone And Diagnostics

- Production context menu has a `Microphone input` submenu.
- The user can select `Auto-detect` or a detected input device.
- The selected microphone device is saved in user settings.
- If no explicit device is selected, auto-detect uses the Windows default input when valid, otherwise falls back to the first available input device.
- Recording uses the selected device explicitly.
- The settings and diagnostics dialog is dark, frameless, and movable.
- Diagnostics should include app paths, system CPU/memory, microphone settings, detected input devices, and live/high-quality model settings.

## Runtime Profiles

Use the one-command Windows runner when possible:

```powershell
.\run.ps1
```

`run.ps1`, `dev.ps1`, and `run.bat` set `AUDIOTRANSCRIBER_PROFILE=dev`.
Frozen/packaged builds default to `prod` unless the environment variable overrides it.

Dev profile:

- Uses project-local `recordings/`.
- Uses project-local `.models/`.
- Shows input selector, test tone, and dev sample menu actions.

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

## Build And Release

- Current release target is `0.1.6`.
- Build from `C:\Users\jwhen\Desktop\audiotranscriber`, not the old OneDrive desktop path.
- Close running `AudioTranscriber.exe` before building.
- Windows build:

```powershell
.\build-windows.ps1
.\package-windows.ps1
Compress-Archive -Path .\dist\AudioTranscriber\* -DestinationPath .\installer\AudioTranscriber-v0.1.6-windows.zip -Force
```

- Expected installer: `installer\AudioTranscriberSetup-v0.1.6.exe`.
- Expected portable zip: `installer\AudioTranscriber-v0.1.6-windows.zip`.
- Build scripts set `TEMP` and `TMP` to `.tmp\build` to avoid Windows temp-permission issues.

## Implementation Preferences

- Prefer simple, stable Python dependencies.
- Use PySide6 for GUI work.
- Use `faster-whisper` for transcription.
- Use ffmpeg where appropriate for conversion/export.
- Prefer Python-accessible audio capture through `sounddevice`.
- Avoid heavy visuals or complex spectrum analysis.
- Keep styling compact, calm, and readable.
- Keep user-facing text in Dutch where the surrounding UI is Dutch.
- Do not reintroduce phase-split documentation unless the user asks for it.
