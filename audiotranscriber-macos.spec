# PyInstaller spec for the macOS production app bundle build.

from PyInstaller.utils.hooks import collect_all

block_cipher = None

imageio_datas, imageio_binaries, imageio_hiddenimports = collect_all("imageio_ffmpeg")
faster_whisper_datas, faster_whisper_binaries, faster_whisper_hiddenimports = collect_all(
    "faster_whisper"
)
app_datas = [
    ("src/audiotranscriber/assets/app.ico", "audiotranscriber/assets"),
    ("src/audiotranscriber/assets/app.png", "audiotranscriber/assets"),
]

a = Analysis(
    ["src/audiotranscriber/main.py"],
    pathex=["src"],
    binaries=imageio_binaries + faster_whisper_binaries,
    datas=imageio_datas + faster_whisper_datas + app_datas,
    hiddenimports=imageio_hiddenimports + faster_whisper_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["dev_samples"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AudioTranscriber",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AudioTranscriber",
)
app = BUNDLE(
    coll,
    name="AudioTranscriber.app",
    icon="src/audiotranscriber/assets/app.icns",
    bundle_identifier="com.localtools.audiotranscriber",
    info_plist={
        "CFBundleShortVersionString": "0.1.7",
        "CFBundleVersion": "0.1.7",
        "NSMicrophoneUsageDescription": "AudioTranscriber needs microphone access to record audio for transcription.",
        "LSUIElement": False,
        "LSMultipleInstancesProhibited": True,
    },
)
