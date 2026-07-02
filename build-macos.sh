#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
DIST_APP="$PROJECT_ROOT/dist/AudioTranscriber.app"
BUILD_TEMP="$PROJECT_ROOT/.tmp/build"

export AUDIOTRANSCRIBER_PROFILE=prod

mkdir -p "$BUILD_TEMP"

if pgrep -x "AudioTranscriber" > /dev/null 2>&1; then
    echo "AudioTranscriber is still running. Close it before building."
    echo "Run: pkill -x AudioTranscriber"
    exit 1
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_ROOT/.venv"
fi

echo "Installing/updating build dependencies..."
"$VENV_PYTHON" -m pip install -e "$PROJECT_ROOT"
"$VENV_PYTHON" -m pip install pyinstaller

echo "Building production app..."
"$VENV_PYTHON" -m PyInstaller "$PROJECT_ROOT/audiotranscriber-macos.spec" --noconfirm --clean \
    --workpath "$BUILD_TEMP" \
    --distpath "$PROJECT_ROOT/dist"

echo ""
echo "Build complete:"
echo "$DIST_APP"
