#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -m venv .build-venv
./.build-venv/bin/python -m pip install --upgrade pip
./.build-venv/bin/python -m pip install -r build_tools/build-requirements.txt
./.build-venv/bin/python build_tools/release_metadata.py --write-windows-version
./.build-venv/bin/python build_tools/release_metadata.py --check
./.build-venv/bin/python build_tools/stage_ocr_runtime.py
./.build-venv/bin/python -m pytest -q

rm -rf build dist release
MSIO_ONEFILE=0 ./.build-venv/bin/pyinstaller --clean --noconfirm build_tools/MapleStoryIdleOptimizer.spec
MSIO_ONEFILE=1 ./.build-venv/bin/pyinstaller --clean --noconfirm build_tools/MapleStoryIdleOptimizer.spec
./.build-venv/bin/python build_tools/package_release_artifacts.py

echo
echo "Raw PyInstaller builds: $(pwd)/dist"
echo "Upload-ready files:      $(pwd)/release"
echo "Test the -onedir archive first, then the single-file executable."
