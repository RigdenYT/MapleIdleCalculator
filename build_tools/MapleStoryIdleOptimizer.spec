# PyInstaller specification for MapleStory Idle Companion Optimizer.
from __future__ import annotations

import os
import platform
import re
from pathlib import Path

ROOT = Path(SPEC).resolve().parent.parent
ENTRY = ROOT / "maplestory_idle_companion_optimizer.py"
source_text = ENTRY.read_text(encoding="utf-8")
version_match = re.search(
    r'^APP_VERSION\s*=\s*["\'](?P<version>\d+\.\d+\.\d+)["\']\s*$',
    source_text,
    re.MULTILINE,
)
if not version_match:
    raise SystemExit(f"Could not read APP_VERSION from {ENTRY}")
VERSION = version_match.group("version")
ONEFILE = os.environ.get("MSIO_ONEFILE", "0") == "1"
SYSTEM = "Windows" if os.name == "nt" else "Linux"
MACHINE = platform.machine().casefold()
ARCH = "arm64" if MACHINE in {"arm64", "aarch64"} else "x86_64"
PLATFORM_TAG = f"{'windows' if os.name == 'nt' else 'linux'}-{ARCH}"
BASE_NAME = f"MapleStory-Idle-Optimizer-{VERSION}-{SYSTEM}-{ARCH}"
NAME = BASE_NAME if ONEFILE else f"{BASE_NAME}-onedir"

assets = ROOT / "assets"
vendor_ocr = ROOT / "vendor" / "ocr" / PLATFORM_TAG
if not vendor_ocr.is_dir():
    raise SystemExit(
        f"Missing staged OCR runtime: {vendor_ocr}\n"
        "Run: python build_tools/stage_ocr_runtime.py"
    )

datas = [
    (str(ROOT / "README.txt"), "."),
    (str(ROOT / "example_account.json"), "."),
    (str(ROOT / "legacy_example_profile.json"), "."),
    (str(ROOT / "new_companion_skill_reference.txt"), "."),
    (str(ROOT / "additional_companion_equip_reference.txt"), "."),
]
for source in assets.rglob("*"):
    if source.is_file():
        destination = str(source.parent.relative_to(ROOT))
        datas.append((str(source), destination))

binaries = []
for source in vendor_ocr.rglob("*"):
    if not source.is_file():
        continue
    relative_parent = source.parent.relative_to(vendor_ocr)
    destination = Path("assets") / "ocr" / PLATFORM_TAG / relative_parent
    lowered = source.name.casefold()
    if (
        lowered in {"tesseract", "tesseract.exe"}
        or lowered.endswith(".dll")
        or ".so" in lowered
        or lowered.endswith(".dylib")
    ):
        binaries.append((str(source), str(destination)))
    else:
        datas.append((str(source), str(destination)))

icon = ROOT / "assets" / "ui" / ("app_icon.ico" if os.name == "nt" else "app_icon.png")
version_file = ROOT / "build_tools" / "windows_version_info.txt"

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

common_exe = dict(
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon),
)
if os.name == "nt" and version_file.is_file():
    common_exe["version"] = str(version_file)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        **common_exe,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        **common_exe,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name=NAME,
    )
