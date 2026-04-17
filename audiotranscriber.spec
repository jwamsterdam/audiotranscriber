# PyInstaller spec for the Windows production folder build.

from PyInstaller.utils.hooks import collect_all

block_cipher = None

imageio_datas, imageio_binaries, imageio_hiddenimports = collect_all("imageio_ffmpeg")
faster_whisper_datas, faster_whisper_binaries, faster_whisper_hiddenimports = collect_all(
    "faster_whisper"
)
app_datas = [
    ("src/audiotranscriber/assets/app.ico", "audiotranscriber/assets"),
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
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon="src/audiotranscriber/assets/app.ico",
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
    upx=True,
    upx_exclude=[],
    name="AudioTranscriber",
)
