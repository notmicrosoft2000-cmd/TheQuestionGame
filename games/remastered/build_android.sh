#!/usr/bin/env bash
# One-shot Android build for The Question Game Remastered.
#
#   ./build_android.sh                 # debug APK  (default)
#   ./build_android.sh android release # release build
#
# Applies the local p4a patches first (p4a lives in the gitignored .buildozer/
# clone), then runs buildozer from the project virtualenv (~/.myenv).
set -euo pipefail
cd "$(dirname "$0")"

PY=~/.myenv/bin/python
BOZER=~/.myenv/bin/buildozer

if [ ! -x "$BOZER" ]; then
    echo "buildozer not found in ~/.myenv — install it there first" >&2
    exit 1
fi

# Activate the venv: buildozer only skips `pip install --user` when VIRTUAL_ENV
# is set, and pip refuses --user inside a venv.
export VIRTUAL_ENV=~/.myenv
export PATH="$VIRTUAL_ENV/bin:$PATH"

# p4a pins Gradle 8.14, which cannot run on the system's Java 27
# ("Unsupported class file major version 71"). Use the local Temurin 21.
if [ -d "$HOME/android/jdk21" ]; then
    export JAVA_HOME="$HOME/android/jdk21"
    export PATH="$JAVA_HOME/bin:$PATH"
fi

"$PY" apply_p4a_patches.py

# Guard: an interrupted `pip install -U pip` inside p4a's build venv leaves a
# mixed-pip venv (multiple pip-*.dist-info) that fails with ImportError.
VENV_DIR=".buildozer/android/platform/build-arm64-v8a/build/venv"
if [ -d "$VENV_DIR" ] && [ "$(ls "$VENV_DIR"/lib/*/site-packages/ 2>/dev/null | grep -c '^pip-.*\.dist-info$')" -gt 1 ]; then
    echo "corrupt p4a build venv detected (mixed pip versions) — removing $VENV_DIR"
    rm -rf "$VENV_DIR"
fi

if [ "$#" -eq 0 ]; then
    set -- android debug
fi

exec "$BOZER" "$@"
