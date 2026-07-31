#!/usr/bin/env python3
"""Package PyInstaller outputs into upload-ready release assets."""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

from release_metadata import app_version

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASE = ROOT / "release"


def architecture() -> str:
    machine = platform.machine().casefold()
    return "arm64" if machine in {"arm64", "aarch64"} else "x86_64"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def zip_directory(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source.parent))


def tar_directory(source: Path, destination: Path) -> None:
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(source, arcname=source.name)


def main() -> int:
    version = app_version()
    arch = architecture()
    system = "Windows" if os.name == "nt" else "Linux"
    base = f"MapleStory-Idle-Optimizer-{version}-{system}-{arch}"
    onefile = DIST / (base + (".exe" if os.name == "nt" else ""))
    onedir = DIST / f"{base}-onedir"

    if not onefile.is_file():
        raise FileNotFoundError(f"Missing single-file build: {onefile}")
    if not onedir.is_dir():
        raise FileNotFoundError(f"Missing one-folder build: {onedir}")

    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    RELEASE.mkdir(parents=True)

    copied_onefile = RELEASE / onefile.name
    shutil.copy2(onefile, copied_onefile)

    if os.name == "nt":
        onedir_archive = RELEASE / f"{base}-onedir.zip"
        zip_directory(onedir, onedir_archive)
    else:
        onedir_archive = RELEASE / f"{base}-onedir.tar.gz"
        tar_directory(onedir, onedir_archive)

    readme_target = RELEASE / f"README-{version}-{system}-{arch}.txt"
    shutil.copy2(ROOT / "README.txt", readme_target)

    checksummed = [copied_onefile, onedir_archive, readme_target]
    checksums = RELEASE / f"SHA256SUMS-{system}-{arch}.txt"
    checksums.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in checksummed),
        encoding="utf-8",
    )

    print(f"Packaged release assets in {RELEASE}")
    for path in sorted(RELEASE.iterdir()):
        print(f"- {path.name} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
