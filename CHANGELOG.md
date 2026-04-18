# Changelog

All notable changes to AudioTranscriber will be documented in this file.

## Unreleased

_No unreleased changes._

## Released

## 0.1.6 - Calmer Recording Strip and Messages

- Replaced the separate strip status dot and record button with one primary status/action button: red while idle or recording, yellow while processing, with subtle pulsing during active states.
- Made the collapsed strip narrower with a compact 7-bar waveform, added quick expand/collapse animation, and reduced expanded waveform amplitude so the strip is less visually distracting.
- Prevented empty 0-second WAV/TXT artifacts when microphone startup fails before recording begins.
- Rendered system and error messages separately from live captions in the transcript panel, with Dutch user-facing microphone startup messages.
- Made the main recorder window appear as a normal running app in the Windows taskbar with the AudioTranscriber icon.
- Improved shutdown cleanup, startup-failure cleanup, version reporting, resource path handling, and privacy-safe logging.
- Added live-caption backlog protection, incremental transcript writes, and a long-WAV warning for high-quality transcription.

## 0.1.5 - High-Quality VAD Packaging Fix

- Included faster-whisper assets in the Windows build so high-quality transcription with VAD can load `silero_vad_v6.onnx` from packaged installs.

## 0.1.4 - Diagnostics and High-Quality Transcription Polish

- Added a persistent `Microphone input` context-menu submenu with auto-detect and explicit input-device choices.
- Saved the selected microphone device in user settings and used it for future microphone recordings, with auto-detect fallback when no saved device is selected.
- Replaced the plain microphone diagnostics message with a dark settings and diagnostics dialog covering app paths, microphone input, detected devices, and transcription model settings.
- Optimized high-quality `small` transcription with explicit CPU thread selection based on physical cores and VAD enabled, without changing live transcription settings.

## 0.1.2 - Microphone Detection

- Made microphone detection more robust by scanning all available input devices instead of relying only on the Windows default input.
- Added fallback behavior to use the first available input device when no valid default input is reported.
- Added `Show microphone diagnostics` to the production context menu so users can see which input devices are detected.
- Improved microphone startup errors by including the selected input device when startup fails.

## 0.1.1 - Production Packaging

- Switched the Windows installer to per-user install under `%LOCALAPPDATA%\Programs\AudioTranscriber`.
- Added the app icon to the PyInstaller executable, installer, and runtime window metadata.
- Updated app/package/installer version metadata to `0.1.1`.

## 0.1.0 - Initial MVP

- Added PySide6 project scaffold with `src/` package layout.
- Added compact floating recorder strip UI based on the supplied screenshot.
- Added collapsible transcript preview panel below the strip.
- Added dummy app state transitions for idle, recording, paused, and processing.
- Added green idle, blinking red recording, and yellow processing/paused status indicators.
- Added timer display and lightweight animated waveform preview.
- Added modular placeholders for future recording and transcription pipelines.
- Added Windows one-command launchers: `run.ps1` and `run.bat`.
- Documented initial run instructions in `README.md`.

### Fixed

- Widened the initial strip to prevent the waveform from overlapping the timer.
- Increased the expanded transcript panel height so the preview text is not clipped.
- Added a right-click context menu with a `Close app` action.
- Added `Esc` as a keyboard shortcut to close the app.
- Reduced the default strip width so the app feels more like a corner utility.
- Added right-click width presets for compact, comfortable, and wide layouts.
- Made expanded transcript height respond to wrapped text instead of using a fixed height.
- Made closing the UI explicitly quit the Qt app so PowerShell returns to the prompt.
- Increased the expanded transcript panel's measured height so wrapped preview text remains readable.
- Added a dependency-free dev watcher for restart-on-save UI iteration.

## Early Development Notes

These notes describe development milestones that happened before the numbered
`0.1.x` release line settled.

### Recording MVP

- Added timestamped raw WAV recording to `recordings/`.
- Added built-in test tone input for machines without a microphone.
- Added microphone input support through `sounddevice`.
- Added pause/resume behavior that pauses writing audio frames.
- Replaced dummy waveform behavior with level updates from incoming audio buffers.
- Added right-click input source switching between test tone and microphone.
- Ignored local recording outputs in `.gitignore`.
- Anchored transcript expansion so the strip stays fixed while the panel opens below it.
- Removed the duplicate collapse button from the transcript panel.
- Added context menu actions to open the recordings folder and last saved WAV.
- Added a write lock around WAV writes and close to make stop/shutdown safer.
- Kept the saved recording message visible after the short processing state.
- Ignored `dev_samples/` and added context menu actions for selecting development audio samples.

### Transcription MVP

- Added chunked background transcription using `faster-whisper`.
- Set default transcription config to `base`, `cpu`, and `int8`.
- Added incremental `.txt` transcript saving next to the source audio.
- Added context menu actions to transcribe recorded audio and open the transcript file.
- Automatically starts transcription after stopping a recording.
- Clarified that dev samples are transcribed from the context menu, while the record button creates a new recording.
- Added a clearer empty-transcript message when no speech is detected.
- Made Stop cancel active transcription after the current chunk completes.
- Replaced the transcript label with a scrollable read-only transcript viewport.
- Reduced transcription chunk length from 15 seconds to 8 seconds for more responsive updates.
- Added explicit chunk progress state for the transcript header.
- Added context menu playback for the selected dev sample or recorded audio.
- Added dev sample as a first-class recording input source.
- Updated the context menu with explicit dev sample select/play/stop actions.
- Removed direct selected-audio transcription and width preset menu actions.
- Simplified the context menu into input, dev sample, open, and close groups.
- Styled context menu separators so group divider lines are visible.
- Added PowerShell console logging for transcription start, chunk progress, completion, cancellation, and failures.
- Added near-real-time chunk transcription while recording.
- Removed the separate final transcription lane so the live chunks are the single source of transcript text.
- Live transcription is now written directly to the normal `.txt` file.
- Stop now drains queued live chunks and does not start a second transcription pass.
- Added a compact main-strip language selector for `AUTO`, `NL`, and `EN` faster-whisper language hints.
- Removed the experimental LocalAgreement sentence mode and transcription mode context menu.
- Allowed changing the language selector while recording so future chunks use the updated language.
- Added top-edge magnetic snapping for the floating strip with pull-down release.
- Added post-processing actions for MP3 backup export and high-quality transcript creation.
- Added `*.backup.mp3` and `*.high-quality.txt` output naming for post-recording files.
- Changed post-processing actions to prompt for a WAV file, so older recordings can be processed.
- Added an `imageio-ffmpeg` fallback so MP3 export does not require ffmpeg on the system PATH.
- Renamed post-processing menu actions and added transcript-panel progress feedback.
- Added language confirmation before high-quality transcript creation and centered the language selector labels.
- Replaced the language combo with a compact centered menu button and made transcript unfold immediate to avoid stutter.
- Removed direct open-last-recording/open-transcript menu actions and made microphone the default input.
- Added dev/prod runtime profiles, production-safe recording/model paths, and a first Windows PyInstaller build script.
- Added a production-focused context menu profile with microphone-only input and hidden dev sample/test tone actions.
- Added a Windows Inno Setup installer template and packaging script.
- Added friendlier production errors for missing/blocked microphones and first-use transcription model downloads.
- Hardened Windows build scripts so PyInstaller/Inno failures stop the script and running app locks are reported clearly.
- Wired update checking to GitHub Releases for `jwamsterdam/audiotranscriber` and added a model-cache refresh action.
