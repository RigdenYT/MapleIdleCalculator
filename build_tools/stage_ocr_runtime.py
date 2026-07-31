#!/usr/bin/env python3
"""Stage a redistributable Tesseract runtime for the current build platform.

Run this on the same operating system that will build the application. The
result is copied into vendor/ocr/<platform>-<arch>, then included by the
PyInstaller specification. Testers do not need Tesseract installed.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = PROJECT_ROOT / "vendor" / "ocr"


def platform_tag() -> str:
    machine = platform.machine().casefold()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x86_64"
    system = "windows" if os.name == "nt" else "linux"
    return f"{system}-{arch}"


def clean_destination() -> Path:
    destination = VENDOR_ROOT / platform_tag()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    return destination


def find_tessdata(home: Path) -> Path:
    override = os.environ.get("TESSDATA_PREFIX", "").strip()
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    candidates.extend(
        [
            home / "tessdata",
            home / "share" / "tessdata",
            home / "share" / "tesseract-ocr" / "5" / "tessdata",
            home.parent / "share" / "tesseract-ocr" / "5" / "tessdata",
            Path("/usr/share/tesseract-ocr/5/tessdata"),
            Path("/usr/share/tessdata"),
        ]
    )
    for candidate in candidates:
        if (candidate / "eng.traineddata").is_file():
            return candidate
    raise RuntimeError(
        "Could not find eng.traineddata. Install the English Tesseract language data "
        "or set TESSDATA_PREFIX to its tessdata directory."
    )


def copy_tessdata(source: Path, destination: Path) -> None:
    target = destination / "tessdata"
    (target / "configs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "eng.traineddata", target / "eng.traineddata")
    osd = source / "osd.traineddata"
    if osd.is_file():
        shutil.copy2(osd, target / "osd.traineddata")
    tsv_config = source / "configs" / "tsv"
    if not tsv_config.is_file():
        raise RuntimeError(f"Missing required Tesseract TSV config: {tsv_config}")
    shutil.copy2(tsv_config, target / "configs" / "tsv")


def stage_windows(destination: Path) -> None:
    override = os.environ.get("TESSERACT_HOME", "").strip()
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    executable = shutil.which("tesseract.exe") or shutil.which("tesseract")
    if executable:
        candidates.append(Path(executable).resolve().parent)
    for key in ("ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(key)
        if root:
            candidates.extend(
                [
                    Path(root) / "Tesseract-OCR",
                    Path(root) / "Programs" / "Tesseract-OCR",
                ]
            )
    home = next((path for path in candidates if (path / "tesseract.exe").is_file()), None)
    if home is None:
        raise RuntimeError(
            "Tesseract was not found. Install a 64-bit Windows Tesseract build, or set "
            "TESSERACT_HOME to the folder containing tesseract.exe."
        )
    shutil.copy2(home / "tesseract.exe", destination / "tesseract.exe")
    for pattern in ("*.dll", "*.config"):
        for source in home.glob(pattern):
            shutil.copy2(source, destination / source.name)
    copy_tessdata(find_tessdata(home), destination)


def parse_ldd(executable: Path) -> list[Path]:
    process = subprocess.run(
        ["ldd", str(executable)], capture_output=True, text=True, check=True
    )
    paths: list[Path] = []
    for line in process.stdout.splitlines():
        match = re.search(r"=>\s+(/\S+)", line)
        if not match:
            match = re.match(r"\s*(/\S+)\s+\(", line)
        if match:
            path = Path(match.group(1))
            if path.is_file():
                paths.append(path)
    return paths


def stage_linux(destination: Path) -> None:
    executable_text = os.environ.get("MAPLE_IDLE_TESSERACT", "").strip() or shutil.which("tesseract")
    if not executable_text:
        raise RuntimeError("Tesseract was not found. Install it before building the Linux release.")
    executable = Path(executable_text).resolve()
    target_executable = destination / "tesseract"
    shutil.copy2(executable, target_executable)
    target_executable.chmod(target_executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    library_dir = destination / "lib"
    library_dir.mkdir()
    # Do not bundle glibc or the dynamic loader. They must match the target host;
    # everything else needed by Tesseract is staged beside the executable.
    skip_prefixes = (
        "libc.so", "libm.so", "libpthread.so", "libdl.so", "librt.so",
        "libresolv.so", "libnss_", "ld-linux", "libgcc_s.so",
    )
    copied = set()
    for source in parse_ldd(executable):
        if source.name.startswith(skip_prefixes):
            continue
        if source.name in copied:
            continue
        copied.add(source.name)
        shutil.copy2(source, library_dir / source.name)
    copy_tessdata(find_tessdata(executable.parent), destination)


def verify(destination: Path) -> None:
    executable = destination / ("tesseract.exe" if os.name == "nt" else "tesseract")
    if not executable.is_file() or not (destination / "tessdata" / "eng.traineddata").is_file():
        raise RuntimeError("The staged OCR runtime is incomplete.")
    env = dict(os.environ)
    env["TESSDATA_PREFIX"] = str(destination / "tessdata")
    if os.name != "nt":
        env["LD_LIBRARY_PATH"] = str(destination / "lib")
    process = subprocess.run(
        [str(executable), "--list-langs"], capture_output=True, text=True, env=env, timeout=30
    )
    if process.returncode != 0 or "eng" not in process.stdout.split():
        raise RuntimeError(
            "Staged Tesseract failed its English-language check:\n" + (process.stderr or process.stdout)
        )


def main() -> int:
    destination = clean_destination()
    if os.name == "nt":
        stage_windows(destination)
    elif sys.platform.startswith("linux"):
        stage_linux(destination)
    else:
        raise RuntimeError("Only Windows and Linux release staging is supported.")
    verify(destination)
    print(f"Staged OCR runtime: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
