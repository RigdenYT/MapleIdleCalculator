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

VERSION="$(./.build-venv/bin/python build_tools/release_metadata.py --print-version)"
case "$(uname -m)" in
    arm64|aarch64) ARCH="arm64" ;;
    *) ARCH="x86_64" ;;
esac
BASE="MapleStory-Idle-Optimizer-${VERSION}-Linux-${ARCH}"
ONEDIR_EXE="dist/${BASE}-onedir/${BASE}-onedir"
ONEFILE_EXE="dist/${BASE}"

run_packaged_smoke_test() {
    local executable="$1"
    echo "Packaged startup smoke test: ${executable}"
    if command -v xvfb-run >/dev/null 2>&1; then
        xvfb-run -a "${executable}" --packaging-smoke-test
    elif [[ -n "${DISPLAY:-}" ]]; then
        "${executable}" --packaging-smoke-test
    else
        echo "No DISPLAY and xvfb-run is unavailable; cannot test the packaged GUI." >&2
        exit 1
    fi
}

run_packaged_smoke_test "${ONEDIR_EXE}"
run_packaged_smoke_test "${ONEFILE_EXE}"

./.build-venv/bin/python build_tools/package_release_artifacts.py

echo
echo "Raw PyInstaller builds: $(pwd)/dist"
echo "Upload-ready files:      $(pwd)/release"
echo "Test the -onedir archive first, then the single-file executable."
