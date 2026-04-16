# Changelog

All notable changes to AudioTranscriber will be documented in this file.

## 0.1.0 - Phase 1 MVP

- Added PySide6 project scaffold with `src/` package layout.
- Added compact floating recorder strip UI based on the supplied screenshot.
- Added collapsible transcript preview panel below the strip.
- Added dummy app state transitions for idle, recording, paused, and processing.
- Added green idle, blinking red recording, and yellow processing/paused status indicators.
- Added timer display and lightweight animated waveform preview.
- Added modular placeholders for future recording and transcription pipelines.
- Added Windows one-command launchers: `run.ps1` and `run.bat`.
- Documented Phase 1 run instructions in `README.md`.

### Fixed

- Widened the Phase 1 strip to prevent the waveform from overlapping the timer.
- Increased the expanded transcript panel height so the preview text is not clipped.
- Added a right-click context menu with a `Close app` action.
- Added `Esc` as a keyboard shortcut to close the app.
- Reduced the default strip width so the app feels more like a corner utility.
- Added right-click width presets for compact, comfortable, and wide layouts.
- Made expanded transcript height respond to wrapped text instead of using a fixed height.
- Made closing the UI explicitly quit the Qt app so PowerShell returns to the prompt.
- Increased the expanded transcript panel's measured height so wrapped preview text remains readable.
- Added a dependency-free dev watcher for restart-on-save UI iteration.

## 0.2.0 - Phase 2 Recording MVP

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

## 0.3.0 - Phase 3 Transcription MVP

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
