#!/usr/bin/env python3
"""Read and validate release metadata derived from the application source.

The application version has one source of truth: APP_VERSION in
maplestory_idle_companion_optimizer.py. Build scripts and GitHub Actions use
this helper so executable names and Windows metadata cannot silently drift.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "maplestory_idle_companion_optimizer.py"
README = ROOT / "README.txt"
BUILD_NOTES = ROOT / "build_tools" / "BUILDING_RELEASES.txt"
WINDOWS_VERSION_FILE = ROOT / "build_tools" / "windows_version_info.txt"

_VERSION_PATTERN = re.compile(
    r'^APP_VERSION\s*=\s*["\'](?P<version>\d+\.\d+\.\d+)["\']\s*$',
    re.MULTILINE,
)


def app_version() -> str:
    text = SOURCE.read_text(encoding="utf-8")
    match = _VERSION_PATTERN.search(text)
    if not match:
        raise RuntimeError(f"Could not find APP_VERSION in {SOURCE}")
    return match.group("version")


def version_tuple(version: str) -> tuple[int, int, int, int]:
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch, 0


def windows_version_text(version: str) -> str:
    numeric = version_tuple(version)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric},
    prodvers={numeric},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Community project'),
         StringStruct(u'FileDescription', u'MapleStory Idle Companion Optimizer'),
         StringStruct(u'FileVersion', u'{version}'),
         StringStruct(u'InternalName', u'MapleStoryIdleOptimizer'),
         StringStruct(u'OriginalFilename', u'MapleStory-Idle-Optimizer-{version}-Windows-x86_64.exe'),
         StringStruct(u'ProductName', u'MapleStory Idle Companion Optimizer'),
         StringStruct(u'ProductVersion', u'{version}')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def write_windows_version_file(version: str) -> None:
    WINDOWS_VERSION_FILE.write_text(windows_version_text(version), encoding="utf-8")


def check_tag(tag: str, version: str) -> None:
    expected = f"v{version}"
    if tag != expected:
        raise RuntimeError(
            f"Release tag {tag!r} does not match APP_VERSION {version!r}. "
            f"Use the tag {expected!r}, or update APP_VERSION before tagging."
        )


def validate(version: str) -> None:
    problems: list[str] = []

    readme_text = README.read_text(encoding="utf-8")
    if f"OPTIMIZER {version}" not in readme_text.splitlines()[0]:
        problems.append(
            f"README.txt title does not identify version {version}."
        )
    if f"WHAT CHANGED IN {version}" not in readme_text:
        problems.append(
            f"README.txt has no 'WHAT CHANGED IN {version}' section."
        )

    notes_text = BUILD_NOTES.read_text(encoding="utf-8")
    if version not in notes_text.splitlines()[0]:
        problems.append(
            f"build_tools/BUILDING_RELEASES.txt title does not identify version {version}."
        )

    expected_windows = windows_version_text(version)
    if not WINDOWS_VERSION_FILE.is_file() or WINDOWS_VERSION_FILE.read_text(
        encoding="utf-8"
    ) != expected_windows:
        problems.append(
            "build_tools/windows_version_info.txt is stale. Run "
            "'python build_tools/release_metadata.py --write-windows-version'."
        )

    if problems:
        raise RuntimeError("Release metadata validation failed:\n- " + "\n- ".join(problems))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-version", action="store_true")
    parser.add_argument("--write-windows-version", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-tag", metavar="TAG")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = app_version()

    if args.write_windows_version:
        write_windows_version_file(version)
        print(f"Updated {WINDOWS_VERSION_FILE.relative_to(ROOT)} for {version}")
    if args.check_tag:
        check_tag(args.check_tag, version)
        print(f"Tag {args.check_tag} matches APP_VERSION {version}")
    if args.check:
        validate(version)
        print(f"Release metadata is consistent for {version}")
    if args.print_version or not any(
        (args.write_windows_version, args.check, args.check_tag)
    ):
        print(version)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
