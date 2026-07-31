#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .build-venv
./.build-venv/bin/python -m pip install --upgrade pip
./.build-venv/bin/python -m pip install -r build_tools/build-requirements.txt
./.build-venv/bin/python build_tools/stage_ocr_runtime.py
./.build-venv/bin/python -m pytest -q

rm -rf build dist
MSIO_ONEFILE=0 ./.build-venv/bin/pyinstaller --clean --noconfirm build_tools/MapleStoryIdleOptimizer.spec
MSIO_ONEFILE=1 ./.build-venv/bin/pyinstaller --clean --noconfirm build_tools/MapleStoryIdleOptimizer.spec

echo
echo "Builds are in: $(pwd)/dist"
echo "Test the -onedir build first, then the single-file executable."
