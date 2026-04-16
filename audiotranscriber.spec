# PyInstaller spec for the Windows production folder build.

from PyInstaller.utils.hooks import collect_all

block_cipher = None

imageio_datas, imageio_binaries, imageio_hiddenimports = collect_all("imageio_ffmpeg")

a = Analysis(
    ["src/audiotranscriber/main.py"],
    pathex=["src"],
    binaries=imageio_binaries,
    datas=imageio_datas,
    hiddenimports=imageio_hiddenimports,
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
