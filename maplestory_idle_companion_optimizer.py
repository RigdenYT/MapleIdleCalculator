#!/usr/bin/env python3
"""
MapleStory: Idle RPG Companion Optimizer — first public-data version

A Tkinter desktop application that optimizes companion equip combinations from
the character stats currently displayed in-game. The core optimizer has no
third-party Python dependency; optional screenshot import uses local Pillow and
Tesseract OCR. The GUI uses a fixed roster so owned pages can be enabled directly
instead of entered one by one. When those
stats include the equipped team, the app mathematically removes that team's
equip effects before testing replacements.

The exact optimizer covers companion equip effects. Main-companion active skill
contributions can be supplied as an optional, time-averaged manual percentage
because current public data does not fully specify every animation, cooldown,
proc, target-count, and class interaction.
"""

from __future__ import annotations

import copy
import csv
import difflib
import heapq
import io
import itertools
import json
import math
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError as exc:  # pragma: no cover - depends on local Python install
    raise SystemExit(
        "Tkinter is not available. On Arch/CachyOS, install it with: sudo pacman -S tk"
    ) from exc

try:  # optional; used for themed background rendering and screenshot import
    from PIL import Image, ImageDraw, ImageGrab, ImageTk  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageGrab = None  # type: ignore[assignment]
    ImageTk = None  # type: ignore[assignment]


APP_NAME = "MapleStory Idle Companion Optimizer"
APP_VERSION = "2.6.6"
APP_SLUG = "maplestory-idle-optimizer"
PROFILE_VERSION = 3

# ---------------------------------------------------------------------------
# Companion data
# ---------------------------------------------------------------------------

RARITIES = ("Common", "Rare", "Epic", "Unique", "Legendary")
RARITY_ORDER = {name: idx for idx, name in enumerate(RARITIES)}
EQUIPPED_ROLES = ("Not equipped", "Main", "Sub")

ORIGINAL_COMPANIONS = (
    "Hero",
    "Dark Knight",
    "Ice/Lightning",
    "Fire/Poison",
    "Bowmaster",
    "Marksman",
    "Night Lord",
    "Shadower",
)

# Later companion additions whose equip-effect families and level checkpoints
# were verified from official patch notes plus player-provided in-game panels.
# Their observed values follow the same linear level families used by the
# original companion tables.
ADDITIONAL_FORMULA_COMPANIONS = (
    "Bishop",
    "Paladin",
    "Buccaneer",
    "Corsair",
    "Night Walker",
    "Wind Archer",
)

FORMULA_COMPANIONS = ORIGINAL_COMPANIONS + ADDITIONAL_FORMULA_COMPANIONS
MANUAL_COMPANIONS: Tuple[str, ...] = ()
KNOWN_COMPANIONS = FORMULA_COMPANIONS

# Match the order used by the in-game companion browser. This changes only
# presentation; stable page IDs and calculations remain unchanged.
COMPANION_DISPLAY_ORDER = (
    "Hero", "Paladin", "Dark Knight",
    "Ice/Lightning", "Fire/Poison", "Bishop",
    "Bowmaster", "Marksman",
    "Night Lord", "Shadower",
    "Buccaneer", "Corsair",
    "Night Walker", "Wind Archer",
)

COMMON_AVAILABLE = {"Hero", "Ice/Lightning", "Bowmaster", "Shadower", "Buccaneer"}

EFFECT_LABELS: Dict[str, str] = {
    "attack": "Flat Attack",
    "max_damage": "Max Damage Multiplier",
    "accuracy": "Accuracy",
    "normal_damage": "Normal Monster Damage",
    "crit_rate": "Critical Rate",
    "attack_speed": "Attack Speed",
    "status_damage": "Status Damage",
    "boss_damage": "Boss Damage",
    "min_damage": "Min Damage Multiplier",
    "skill_damage": "Skill Damage",
    "basic_attack_damage": "Basic Attack Damage",
    "main_stat_pct": "Main Stat %",
    "damage": "Damage",
    "crit_damage": "Critical Damage",
    "damage_amp": "Damage Amplification",
    "final_damage": "Final Damage",
    "defense_pen": "Defense Penetration",
}
LABEL_TO_EFFECT = {label: key for key, label in EFFECT_LABELS.items()}

# Retained for backward-compatible profile loading. All currently known roster
# companions are formula-backed in this version.
MANUAL_EFFECT_HINTS = {
    "Bishop": "skill_damage",
    "Paladin": "basic_attack_damage",
    "Buccaneer": "main_stat_pct",
    "Corsair": "crit_damage",
}

# Epic+ on-equip effect by companion.
EPIC_EFFECTS = {
    "Hero": "max_damage",
    "Dark Knight": "accuracy",
    "Ice/Lightning": "normal_damage",
    "Fire/Poison": "crit_rate",
    "Bowmaster": "attack_speed",
    "Marksman": "status_damage",
    "Night Lord": "boss_damage",
    "Shadower": "min_damage",
    "Night Walker": "accuracy",
    "Wind Archer": "boss_damage",
    "Bishop": "skill_damage",
    "Paladin": "basic_attack_damage",
    "Buccaneer": "main_stat_pct",
    "Corsair": "crit_damage",
}

# Level-1 value and per-level increment for Epic/Unique/Legendary effects.
# The sequence is linear through level 300 in the public companion data.
EFFECT_SCALING = {
    "standard": {
        "Epic": (5.0, 0.5),
        "Unique": (10.0, 1.0),
        "Legendary": (20.0, 2.0),
    },
    "accuracy": {
        "Epic": (6.0, 0.6),
        "Unique": (12.0, 1.2),
        "Legendary": (24.0, 2.4),
    },
    "crit_rate": {
        "Epic": (3.0, 0.3),
        "Unique": (6.0, 0.6),
        "Legendary": (12.0, 1.2),
    },
    "reduced_standard": {
        "Epic": (2.0, 0.2),
        "Unique": (4.0, 0.4),
        "Legendary": (8.0, 0.8),
    },
    "status_damage": {
        "Epic": (8.0, 0.8),
        "Unique": (16.0, 1.6),
        "Legendary": (32.0, 3.2),
    },
}

CONTENT_MODES = (
    "Normal farming",
    "Boss",
    "Mixed stage",
    "Arena / neither",
)

CLASS_NAMES = (
    "Hero",
    "Paladin",
    "Dark Knight",
    "Ice/Lightning Arch Mage",
    "Fire/Poison Arch Mage",
    "Bishop",
    "Bowmaster",
    "Marksman",
    "Night Lord",
    "Shadower",
    "Buccaneer",
    "Corsair",
    "Night Walker",
    "Wind Archer",
    "Other / future class",
)

# Used only to designate a main companion when no measured main-active bonus is
# supplied. It does not change the optimizer score.
MAIN_TIEBREAK = {
    "Normal farming": (
        "Ice/Lightning", "Wind Archer", "Bishop", "Fire/Poison",
        "Buccaneer", "Bowmaster", "Night Walker", "Corsair",
        "Night Lord", "Marksman", "Hero", "Paladin", "Dark Knight", "Shadower",
    ),
    "Boss": (
        "Wind Archer", "Bowmaster", "Night Walker", "Night Lord",
        "Bishop", "Buccaneer", "Fire/Poison", "Marksman",
        "Paladin", "Corsair", "Hero", "Shadower", "Dark Knight", "Ice/Lightning",
    ),
    "Mixed stage": (
        "Wind Archer", "Bishop", "Ice/Lightning", "Night Walker",
        "Bowmaster", "Buccaneer", "Night Lord", "Fire/Poison",
        "Corsair", "Marksman", "Hero", "Paladin", "Dark Knight", "Shadower",
    ),
    "Arena / neither": (
        "Night Walker", "Hero", "Dark Knight", "Shadower", "Bishop",
        "Paladin", "Buccaneer", "Corsair", "Wind Archer", "Bowmaster",
        "Night Lord", "Fire/Poison", "Ice/Lightning", "Marksman",
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NUMBER_SUFFIXES = {
    "k": 1e3,
    "m": 1e6,
    "b": 1e9,
    "t": 1e12,
    "q": 1e15,
}


def parse_number(value: object, *, field_name: str = "value") -> float:
    """Parse commas and k/m/b/t/q suffixes without external packages."""
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text = str(value).strip().lower().replace(",", "").replace(" ", "")
        if not text:
            return 0.0
        match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))(?:([kmbtq]))?%?", text)
        if not match:
            raise ValueError(f"{field_name} must be a number (examples: 1250, 1.25m, 18.5).")
        result = float(match.group(1))
        suffix = match.group(2)
        if suffix:
            result *= NUMBER_SUFFIXES[suffix]
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite.")
    return result


def fmt_number(value: float, decimals: int = 2) -> str:
    abs_value = abs(value)
    for suffix, scale in (("q", 1e15), ("t", 1e12), ("b", 1e9), ("m", 1e6), ("k", 1e3)):
        if abs_value >= scale:
            return f"{value / scale:.{decimals}f}{suffix}"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:,.{decimals}f}"


def fmt_pct(value: float, decimals: int = 2, signed: bool = False) -> str:
    prefix = "+" if signed and value >= 0 else ""
    return f"{prefix}{value:.{decimals}f}%"


def entry_number_text(value: float) -> str:
    """Preserve an OCR number exactly enough for editable entry fields."""
    if math.isclose(value, round(value), rel_tol=0.0, abs_tol=1e-10):
        return str(int(round(value)))
    return f"{value:.10f}".rstrip("0").rstrip(".")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def combine_diminishing(current: float, additions: Iterable[float], cap: float) -> float:
    """Combine percentage sources by multiplying their remaining distance to cap."""
    current = clamp(current, 0.0, cap)
    remaining = 1.0 - current / cap
    for addition in additions:
        addition = clamp(float(addition), 0.0, cap)
        remaining *= 1.0 - addition / cap
    return cap * (1.0 - remaining)


def combine_final_damage(current: float, additions: Iterable[float]) -> float:
    factor = max(0.0, 1.0 + current / 100.0)
    for addition in additions:
        factor *= max(0.0, 1.0 + float(addition) / 100.0)
    return (factor - 1.0) * 100.0


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    return cleaned or "maplestory_idle_profile"


def application_resource_directory() -> Path:
    """Return the read-only application resource root in source and frozen builds."""
    # PyInstaller sets __file__ to the bundled entry point. Keeping all packaged
    # assets relative to this file makes the same paths work from source,
    # one-folder builds, and one-file extraction directories.
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    return application_resource_directory().joinpath(*parts)


def is_frozen_build() -> bool:
    return bool(getattr(sys, "frozen", False))


def user_config_directory() -> Path:
    """Return the per-user configuration directory used by local app state."""
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home()))
        return root / "MapleStoryIdleOptimizer"
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "maplestory-idle-optimizer"


def default_autosave_path() -> Path:
    """Return a per-user autosave path that survives program updates."""
    return user_config_directory() / "last_session.json"


def default_preferences_path() -> Path:
    """Return the local UI-preference path, separate from account/build saves."""
    return user_config_directory() / "ui_preferences.json"


def crash_log_directory() -> Path:
    return user_config_directory() / "crash_logs"


def _exception_text(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback,
    *,
    context: str,
) -> str:
    header = [
        f"{APP_NAME} {APP_VERSION} CRASH REPORT",
        f"Created UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Context: {context}",
        f"Frozen build: {is_frozen_build()}",
        f"Python: {platform.python_version()}",
        f"Executable: {sys.executable}",
        f"Platform: {platform.platform()}",
        "",
        "TRACEBACK",
    ]
    return "\n".join(header) + "\n" + "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    )


def write_crash_log(
    context: str,
    exc_type: Optional[type[BaseException]] = None,
    exc_value: Optional[BaseException] = None,
    exc_traceback=None,
) -> Optional[Path]:
    """Persist an exception report without allowing logging itself to crash the app."""
    try:
        if exc_type is None or exc_value is None:
            current_type, current_value, current_traceback = sys.exc_info()
            if current_type is None or current_value is None:
                current_value = RuntimeError("No active exception was available.")
                current_type = type(current_value)
                current_traceback = current_value.__traceback__
            exc_type, exc_value, exc_traceback = current_type, current_value, current_traceback
        directory = crash_log_directory()
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = directory / f"crash_{stamp}.txt"
        path.write_text(
            _exception_text(exc_type, exc_value, exc_traceback, context=context),
            encoding="utf-8",
        )
        # Keep the folder useful without letting first-beta callback failures
        # accumulate indefinitely.
        logs = sorted(directory.glob("crash_*.txt"), key=lambda item: item.stat().st_mtime, reverse=True)
        for old_path in logs[20:]:
            try:
                old_path.unlink()
            except OSError:
                pass
        return path
    except Exception:
        return None


def recent_crash_logs(limit: int = 3) -> List[Path]:
    try:
        return sorted(
            crash_log_directory().glob("crash_*.txt"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[: max(0, limit)]
    except Exception:
        return []


def write_json_atomic(path: Path, payload: object) -> None:
    """Write JSON without exposing a partially written save file.

    The temporary file is created beside the destination so os.replace() stays
    atomic on normal local filesystems. This is used for both manual saves and
    autosaves; a failed write leaves the previous valid file untouched.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def companion_effect(name: str, rarity: str, level: int) -> Tuple[str, float]:
    """Return a verified formula-backed equip effect and level-scaled value."""
    if name not in FORMULA_COMPANIONS:
        raise ValueError(f"{name} does not have a built-in equip-effect formula in this version.")
    if rarity not in RARITIES:
        raise ValueError(f"Unknown rarity: {rarity}")
    if not 1 <= int(level) <= 300:
        raise ValueError("Companion level must be from 1 to 300.")
    level = int(level)

    if rarity == "Common":
        if name not in COMMON_AVAILABLE:
            raise ValueError(f"{name} has no Common/base companion page in the current roster.")
        return "attack", 60.0 + 6.0 * (level - 1)

    if rarity == "Rare":
        return "attack", 200.0 + 20.0 * (level - 1)

    effect = EPIC_EFFECTS[name]
    if effect == "accuracy":
        family = "accuracy"
    elif effect in {"crit_rate", "crit_damage", "main_stat_pct"}:
        family = "crit_rate"
    elif effect in {"skill_damage", "basic_attack_damage"}:
        family = "reduced_standard"
    elif effect == "status_damage":
        family = "status_damage"
    else:
        family = "standard"
    base, per_level = EFFECT_SCALING[family][rarity]
    return effect, base + per_level * (level - 1)


def companion_key(name: str, rarity: str) -> str:
    return f"{name.strip().casefold()}::{rarity.casefold()}"


# ---------------------------------------------------------------------------
# Local screenshot OCR
# ---------------------------------------------------------------------------

# The stat panel hides rows whose value is zero. A complete scrolling capture
# therefore lets the importer distinguish a visible value from an inferred
# zero, while values that are not part of the panel remain explicitly marked
# for manual review.
OCR_IMPORT_FIELDS: Tuple[str, ...] = (
    "attack",
    "total_main_stat",
    "damage",
    "stat_prop_damage",
    "crit_rate",
    "crit_damage",
    "attack_speed",
    "min_damage",
    "max_damage",
    "normal_damage",
    "boss_damage",
    "basic_attack_damage",
    "skill_damage",
    "status_damage",
    "damage_amp",
    "final_damage",
    "defense_pen",
    "accuracy",
)

OCR_MANUAL_FIELDS: Tuple[str, ...] = (
    "current_main_stat_pct",
    "flat_attack_scaling_pct",
    "basic_attack_share",
    "status_uptime",
)

OCR_ZERO_HIDDEN_FIELDS = {
    "normal_damage",
    "boss_damage",
    "basic_attack_damage",
    "skill_damage",
    "status_damage",
    "damage_amp",
    "final_damage",
    "defense_pen",
}

OCR_FIELD_DISPLAY = {
    "attack": "Attack",
    "total_main_stat": "Total Main Stat",
    "damage": "Damage %",
    "stat_prop_damage": "Stat Prop Damage %",
    "crit_rate": "Critical Rate %",
    "crit_damage": "Critical Damage %",
    "attack_speed": "Attack Speed %",
    "min_damage": "Min Damage Multiplier %",
    "max_damage": "Max Damage Multiplier %",
    "normal_damage": "Normal Monster Damage %",
    "boss_damage": "Boss Monster Damage %",
    "basic_attack_damage": "Basic Attack Damage %",
    "skill_damage": "Skill Damage %",
    "status_damage": "Status Damage %",
    "damage_amp": "Damage Amplification %",
    "final_damage": "Final Damage %",
    "defense_pen": "Defense Penetration %",
    "accuracy": "Accuracy",
    "current_main_stat_pct": "Current Main Stat %",
    "flat_attack_scaling_pct": "Flat Attack scaling %",
    "basic_attack_share": "Basic Attack share %",
    "status_uptime": "Status uptime %",
}

CLASS_MAIN_STAT = {
    "Hero": "STR",
    "Paladin": "STR",
    "Dark Knight": "STR",
    "Ice/Lightning Arch Mage": "INT",
    "Fire/Poison Arch Mage": "INT",
    "Bishop": "INT",
    "Bowmaster": "DEX",
    "Marksman": "DEX",
    "Night Lord": "LUK",
    "Shadower": "LUK",
    "Buccaneer": "STR",
    "Corsair": "DEX",
    "Night Walker": "LUK",
    "Wind Archer": "DEX",
}

OCR_LABEL_ALIASES: Dict[str, Tuple[str, ...]] = {
    "attack": ("Attack",),
    "damage": ("Damage",),
    "stat_prop_damage": ("Stat Prop Damage", "Stat Proportional Damage"),
    "crit_rate": ("Critical Rate",),
    "crit_damage": ("Critical Damage",),
    "attack_speed": ("Attack Speed",),
    "min_damage": ("Min Damage Multiplier", "Minimum Damage Multiplier"),
    "max_damage": ("Max Damage Multiplier", "Maximum Damage Multiplier"),
    "normal_damage": ("Normal Monster Damage",),
    "boss_damage": ("Boss Monster Damage",),
    "basic_attack_damage": ("Basic Attack Damage",),
    "skill_damage": ("Skill Damage",),
    "status_damage": ("Status Damage", "Status Effect Damage"),
    "damage_amp": ("Damage Amplification",),
    "final_damage": ("Final Damage",),
    "defense_pen": ("Defense Penetration",),
    "accuracy": ("Accuracy",),
    "STR": ("STR",),
    "DEX": ("DEX",),
    "INT": ("INT",),
    "LUK": ("LUK",),
    "anchor_job": (
        "1st Job Skill Lv",
        "2nd Job Skill Lv",
        "3rd Job Skill Lv",
        "4th Job Skill Lv",
        "All Skill Levels",
    ),
}


@dataclass
class OCRObservation:
    key: str
    value: float
    confidence: float
    label_text: str
    raw_value: str
    source_path: str


@dataclass
class OCRImportResult:
    values: Dict[str, float]
    statuses: Dict[str, str]
    notes: Dict[str, str]
    complete_coverage: bool
    screenshot_count: int
    observed_labels: Tuple[str, ...] = ()


def _normalize_ocr_label(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    # Tesseract commonly interprets the circular information icon as one of
    # these isolated tokens. They are never part of a real stat name.
    ignored = {"i", "l", "u", "gi", "d", "1"}
    return " ".join(token for token in normalized.split() if token not in ignored)


def _ocr_alias_table() -> List[Tuple[str, str]]:
    return [
        (key, _normalize_ocr_label(alias))
        for key, aliases in OCR_LABEL_ALIASES.items()
        for alias in aliases
    ]


OCR_ALIAS_TABLE = _ocr_alias_table()


def _match_ocr_label(text: str) -> Tuple[Optional[str], float, str]:
    normalized = _normalize_ocr_label(text)
    if not normalized:
        return None, 0.0, normalized
    for key, alias in OCR_ALIAS_TABLE:
        if normalized == alias:
            return key, 1.0, normalized

    best_key: Optional[str] = None
    best_score = 0.0
    for key, alias in OCR_ALIAS_TABLE:
        score = difflib.SequenceMatcher(None, normalized, alias).ratio()
        # Preserve the semantic head/tail when OCR reverses or wraps a label.
        n_tokens = set(normalized.split())
        a_tokens = set(alias.split())
        if len(a_tokens) >= 2 and n_tokens == a_tokens:
            score = max(score, 0.98)
        elif len(a_tokens) >= 2 and a_tokens.issubset(n_tokens):
            score = max(score, 0.94)
        if score > best_score:
            best_key, best_score = key, score
    return best_key, best_score, normalized


@dataclass(frozen=True)
class OCRRuntime:
    executable: Path
    tessdata: Optional[Path]
    bundled: bool


def _ocr_platform_tag() -> str:
    machine = platform.machine().casefold()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x86_64"
    system = "windows" if os.name == "nt" else "linux"
    return f"{system}-{arch}"


def _tessdata_for_executable(executable: Path) -> Optional[Path]:
    candidates = [
        executable.parent / "tessdata",
        executable.parent / "share" / "tessdata",
        executable.parent / "share" / "tesseract-ocr" / "5" / "tessdata",
        executable.parent / "share" / "tesseract-ocr" / "tessdata",
        executable.parent.parent / "share" / "tesseract-ocr" / "5" / "tessdata",
        executable.parent.parent / "share" / "tesseract-ocr" / "tessdata",
    ]
    for candidate in candidates:
        if (candidate / "eng.traineddata").is_file():
            return candidate
    return None


def resolve_tesseract_runtime() -> Optional[OCRRuntime]:
    """Find the packaged OCR runtime first, then a system installation."""
    executable_name = "tesseract.exe" if os.name == "nt" else "tesseract"
    platform_tag = _ocr_platform_tag()
    candidates: List[Tuple[Path, bool]] = []

    override = os.environ.get("MAPLE_IDLE_TESSERACT", "").strip()
    if override:
        override_path = Path(override).expanduser()
        if override_path.is_dir():
            override_path = override_path / executable_name
        candidates.append((override_path, False))

    candidates.extend(
        [
            (resource_path("assets", "ocr", platform_tag, executable_name), True),
            (resource_path("vendor", "ocr", platform_tag, executable_name), True),
            (Path(sys.executable).resolve().parent / "ocr" / platform_tag / executable_name, True),
        ]
    )

    system_path = shutil.which("tesseract")
    if system_path:
        candidates.append((Path(system_path), False))

    seen: set[str] = set()
    for executable, bundled in candidates:
        try:
            key = str(executable.resolve())
        except OSError:
            key = str(executable)
        if key in seen:
            continue
        seen.add(key)
        if not executable.is_file():
            continue
        tessdata_override = os.environ.get("TESSDATA_PREFIX", "").strip()
        tessdata = Path(tessdata_override).expanduser() if tessdata_override else None
        if tessdata is not None and not (tessdata / "eng.traineddata").is_file():
            tessdata = None
        if tessdata is None:
            tessdata = _tessdata_for_executable(executable)
        # A packaged runtime must carry English data; a system installation may
        # use its compiled-in search paths when no nearby folder is discoverable.
        if bundled and tessdata is None:
            continue
        return OCRRuntime(executable=executable, tessdata=tessdata, bundled=bundled)
    return None


def _ocr_subprocess_environment(runtime: OCRRuntime) -> Dict[str, str]:
    env = dict(os.environ)
    if runtime.tessdata is not None:
        env["TESSDATA_PREFIX"] = str(runtime.tessdata)

    if os.name != "nt":
        if runtime.bundled:
            library_paths = [runtime.executable.parent / "lib", runtime.executable.parent]
            existing = env.get("LD_LIBRARY_PATH", "")
            parts = [str(path) for path in library_paths if path.is_dir()]
            if existing:
                parts.append(existing)
            if parts:
                env["LD_LIBRARY_PATH"] = os.pathsep.join(parts)
        elif is_frozen_build():
            # PyInstaller adjusts LD_LIBRARY_PATH for its own shared objects. A
            # system Tesseract should instead use the host's normal libraries.
            original = env.get("LD_LIBRARY_PATH_ORIG")
            if original is not None:
                env["LD_LIBRARY_PATH"] = original
            else:
                env.pop("LD_LIBRARY_PATH", None)
    return env


def _require_ocr_dependencies() -> Tuple[object, OCRRuntime]:
    try:
        from PIL import Image, ImageEnhance, ImageOps  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Screenshot import is unavailable because Pillow was not packaged correctly. "
            "Please create a diagnostic bug report."
        ) from exc
    runtime = resolve_tesseract_runtime()
    if runtime is None:
        message = (
            "Screenshot import could not find its OCR runtime.\n\n"
            "Packaged releases should include Tesseract automatically. If this is a development copy, "
            "install Tesseract or set MAPLE_IDLE_TESSERACT to its executable.\n\n"
            "Use Report Bug if this happened in a packaged release."
        )
        raise RuntimeError(message)
    return (Image, ImageEnhance, ImageOps), runtime


def _detect_stat_panel_box(image) -> Tuple[int, int, int, int]:
    """Find the centered white Stat Info panel, with a relative-layout fallback."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    y_start = int(0.12 * height)
    y_end = int(0.90 * height)
    sample_step = max(1, height // 500)
    bright_columns: List[int] = []
    for x in range(int(0.25 * width), int(0.75 * width)):
        bright = 0
        sampled = 0
        for y in range(y_start, y_end, sample_step):
            red, green, blue = pixels[x, y]
            sampled += 1
            if (
                red > 205
                and green > 205
                and blue > 205
                and max(red, green, blue) - min(red, green, blue) < 45
            ):
                bright += 1
        if sampled and bright / sampled > 0.25:
            bright_columns.append(x)

    intervals: List[Tuple[int, int]] = []
    if bright_columns:
        start = previous = bright_columns[0]
        for x in bright_columns[1:]:
            if x > previous + 1:
                intervals.append((start, previous))
                start = x
            previous = x
        intervals.append((start, previous))

    plausible = [interval for interval in intervals if interval[1] - interval[0] >= 0.12 * width]
    if plausible:
        x0, x1 = max(plausible, key=lambda interval: interval[1] - interval[0])
        margin = max(6, int(0.007 * width))
        x0 -= margin
        x1 += margin
    else:
        x0, x1 = int(0.371 * width), int(0.630 * width)

    # The popup's vertical position scales consistently with the game window.
    # This includes the CP header and every visible row while excluding most of
    # the dark game UI that otherwise confuses OCR.
    y0 = int(0.210 * height)
    y1 = int(0.825 * height)
    return max(0, x0), max(0, y0), min(width, x1 + 1), min(height, y1)


def _prepare_stat_panel_image(source_path: Path, output_path: Path) -> Tuple[int, int]:
    dependencies, _ = _require_ocr_dependencies()
    Image, ImageEnhance, ImageOps = dependencies
    image = Image.open(source_path).convert("RGB")
    box = _detect_stat_panel_box(image)
    panel = image.crop(box)
    if panel.width < 250 or panel.height < 400:
        raise RuntimeError(f"Could not locate a usable Stat Info panel in {source_path.name}.")
    panel = panel.resize(
        (panel.width * 2, panel.height * 2),
        Image.Resampling.LANCZOS,
    )
    # A mild contrast increase improves decimal points without destroying the
    # light gray row labels.
    panel = ImageEnhance.Contrast(panel).enhance(1.08)
    panel.save(output_path)
    return panel.size


def _ordered_ocr_label(words: List[Dict[str, object]]) -> str:
    """Order a wrapped label by visual rows rather than Tesseract block order."""
    if not words:
        return ""
    ordered = sorted(words, key=lambda word: float(word["center_y"]))
    rows: List[List[Dict[str, object]]] = []
    for word in ordered:
        center_y = float(word["center_y"])
        if not rows:
            rows.append([word])
            continue
        current_center = sum(float(item["center_y"]) for item in rows[-1]) / len(rows[-1])
        if abs(center_y - current_center) <= 24:
            rows[-1].append(word)
        else:
            rows.append([word])
    fragments: List[str] = []
    for row in rows:
        row.sort(key=lambda word: int(word["left"]))
        fragments.extend(str(word["text"]) for word in row)
    return " ".join(fragments)


def _parse_ocr_number(raw_text: str) -> Optional[float]:
    cleaned = raw_text.strip().replace("O", "0").replace("o", "0")
    match = re.fullmatch(
        r"([+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+))(?:%|sec)?",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def ocr_stat_screenshot(source_path: Path) -> Tuple[List[OCRObservation], Tuple[str, ...]]:
    """Read one screenshot and return known stat/value observations."""
    _, runtime = _require_ocr_dependencies()
    with tempfile.TemporaryDirectory(prefix="maplestory-stat-ocr-") as temporary_dir:
        panel_path = Path(temporary_dir) / "stat_panel.png"
        panel_width, panel_height = _prepare_stat_panel_image(source_path, panel_path)
        subprocess_options: Dict[str, object] = {}
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            subprocess_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        process = subprocess.run(
            [str(runtime.executable), str(panel_path), "stdout", "-l", "eng", "--psm", "11", "tsv"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
            env=_ocr_subprocess_environment(runtime),
            **subprocess_options,
        )
        if process.returncode != 0:
            detail = process.stderr.strip() or "Tesseract returned an unknown error."
            raise RuntimeError(f"OCR failed for {source_path.name}: {detail}")

        words: List[Dict[str, object]] = []
        reader = csv.DictReader(io.StringIO(process.stdout), delimiter="\t")
        for row in reader:
            text = str(row.get("text", "")).strip()
            if not text:
                continue
            try:
                confidence = float(row.get("conf", "-1"))
                left = int(row.get("left", "0"))
                top = int(row.get("top", "0"))
                width = int(row.get("width", "0"))
                height = int(row.get("height", "0"))
            except (TypeError, ValueError):
                continue
            if confidence < 0:
                continue
            words.append(
                {
                    "text": text,
                    "confidence": confidence,
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                    "center_x": left + width / 2.0,
                    "center_y": top + height / 2.0,
                }
            )

        observations: List[OCRObservation] = []
        labels_seen: set[str] = set()
        for value_word in words:
            center_x = float(value_word["center_x"])
            center_y = float(value_word["center_y"])
            if center_x < panel_width * 0.68:
                continue
            value = _parse_ocr_number(str(value_word["text"]))
            if value is None:
                continue

            label_words = [
                word
                for word in words
                if float(word["center_x"]) < panel_width * 0.68
                and abs(float(word["center_y"]) - center_y) <= 58
            ]
            label_text = _ordered_ocr_label(label_words)
            key, match_score, _ = _match_ocr_label(label_text)
            if key is None or match_score < 0.62:
                continue
            labels_seen.add(key)
            label_confidences = [float(word["confidence"]) for word in label_words]
            average_confidence = (
                (float(value_word["confidence"]) + sum(label_confidences))
                / (1 + len(label_confidences))
                if label_confidences
                else float(value_word["confidence"])
            )
            observations.append(
                OCRObservation(
                    key=key,
                    value=value,
                    confidence=max(0.0, min(100.0, average_confidence * match_score)),
                    label_text=label_text,
                    raw_value=str(value_word["text"]),
                    source_path=str(source_path),
                )
            )
        return observations, tuple(sorted(labels_seen))


def merge_stat_screenshots(
    screenshot_paths: Sequence[Path],
    character_class: str,
) -> OCRImportResult:
    if not screenshot_paths:
        raise ValueError("Choose at least one Stat Info screenshot.")

    all_observations: List[OCRObservation] = []
    observed_labels: set[str] = set()
    for path in screenshot_paths:
        observations, labels = ocr_stat_screenshot(Path(path))
        all_observations.extend(observations)
        observed_labels.update(labels)

    by_key: Dict[str, List[OCRObservation]] = {}
    for observation in all_observations:
        by_key.setdefault(observation.key, []).append(observation)

    main_stat_key = CLASS_MAIN_STAT.get(character_class)
    if main_stat_key and main_stat_key in by_key:
        by_key["total_main_stat"] = list(by_key[main_stat_key])
        observed_labels.add("total_main_stat")

    complete_coverage = (
        "attack" in by_key
        and "damage" in by_key
        and "final_damage" in by_key
        and "anchor_job" in observed_labels
    )

    values: Dict[str, float] = {}
    statuses: Dict[str, str] = {}
    notes: Dict[str, str] = {}
    for key in OCR_IMPORT_FIELDS:
        observations = by_key.get(key, [])
        if observations:
            observed_values = [observation.value for observation in observations]
            first = observed_values[0]
            tolerance = max(0.05, abs(first) * 0.001)
            conflict = any(abs(value - first) > tolerance for value in observed_values[1:])
            if conflict:
                # Keep the highest-confidence reading visible in the review
                # dialog, but require the user to resolve the red conflict.
                selected = max(observations, key=lambda observation: observation.confidence)
                values[key] = selected.value
                statuses[key] = "conflict"
                detail = ", ".join(
                    f"{Path(observation.source_path).name}: {observation.raw_value}"
                    for observation in observations
                )
                notes[key] = f"Screenshots disagree ({detail}). Check this value manually."
            else:
                selected = max(observations, key=lambda observation: observation.confidence)
                values[key] = selected.value
                statuses[key] = "screenshot"
                notes[key] = (
                    f"Read from {len(observations)} screenshot(s); "
                    f"OCR confidence {selected.confidence:.0f}%."
                )
        elif complete_coverage and key in OCR_ZERO_HIDDEN_FIELDS:
            values[key] = 0.0
            statuses[key] = "inferred_zero"
            notes[key] = "The full Stat Info list was covered and this zero-valued row was absent."
        else:
            statuses[key] = "uncovered"
            if key == "total_main_stat" and not main_stat_key:
                notes[key] = "Select a supported class so the importer knows whether STR, DEX, INT, or LUK is the main stat."
            else:
                notes[key] = "Not established by these screenshots; keep or enter it manually."

    for key in OCR_MANUAL_FIELDS:
        statuses[key] = "uncovered"
        notes[key] = "This value is not shown in the scrolling Stat Info panel and must be checked manually."

    return OCRImportResult(
        values=values,
        statuses=statuses,
        notes=notes,
        complete_coverage=complete_coverage,
        screenshot_count=len(screenshot_paths),
        observed_labels=tuple(sorted(observed_labels)),
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CharacterStats:
    character_class: str = "Other / future class"
    character_level: int = 1
    attack: float = 100000.0
    total_main_stat: float = 0.0
    current_main_stat_pct: float = 0.0
    flat_attack_scaling_pct: float = 0.0
    damage: float = 0.0
    stat_prop_damage: float = 0.0
    crit_rate: float = 0.0
    crit_damage: float = 0.0
    attack_speed: float = 0.0
    min_damage: float = 100.0
    max_damage: float = 100.0
    normal_damage: float = 0.0
    boss_damage: float = 0.0
    basic_attack_damage: float = 0.0
    skill_damage: float = 0.0
    basic_attack_share: float = 30.0
    status_damage: float = 0.0
    status_uptime: float = 0.0
    damage_amp: float = 0.0
    final_damage: float = 0.0
    defense_pen: float = 0.0
    accuracy: float = 0.0


@dataclass
class TargetProfile:
    content_mode: str = "Boss"
    normal_weight: float = 50.0
    target_defense: float = 0.0
    target_evasion: float = 0.0
    use_accuracy_approximation: bool = False


@dataclass
class Companion:
    uid: str
    name: str
    rarity: str
    level: int
    effect_type: str
    effect_value: float
    main_bonus: float = 0.0
    equipped_role: str = "Not equipped"
    source: str = "manual"
    notes: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.name} — {self.rarity} Lv. {self.level}"

    @property
    def effect_text(self) -> str:
        label = EFFECT_LABELS.get(self.effect_type, self.effect_type)
        suffix = "" if self.effect_type in {"attack", "accuracy"} else "%"
        return f"{label}: {fmt_number(self.effect_value)}{suffix}"


@dataclass
class EffectiveState:
    attack: float
    total_main_stat: float
    damage: float
    stat_prop_damage: float
    crit_rate: float
    crit_damage: float
    attack_speed: float
    min_damage: float
    max_damage: float
    normal_damage: float
    boss_damage: float
    basic_attack_damage: float
    skill_damage: float
    status_damage: float
    damage_amp: float
    final_damage: float
    defense_pen: float
    accuracy: float
    hit_rate: float
    defense_multiplier: float
    score_normal: float
    score_boss: float
    score_arena: float
    score_selected: float
    main_stat_gain: float = 0.0
    warnings: List[str] = field(default_factory=list)


@dataclass
class OptimizationResult:
    score: float
    gain_pct: float
    main: Companion
    subs: Tuple[Companion, ...]
    team: Tuple[Companion, ...]
    state: EffectiveState
    effect_totals: Dict[str, float]
    reference_score: float = 0.0
    reference_label: str = "Unequipped baseline"


# ---------------------------------------------------------------------------
# Damage model
# ---------------------------------------------------------------------------

ADDITIVE_EFFECTS = {
    "attack",
    "max_damage",
    "accuracy",
    "normal_damage",
    "crit_rate",
    "status_damage",
    "boss_damage",
    "min_damage",
    "skill_damage",
    "basic_attack_damage",
    "main_stat_pct",
    "damage",
    "crit_damage",
    "damage_amp",
}


def aggregate_effects(team: Sequence[Companion]) -> Dict[str, object]:
    totals: Dict[str, object] = {key: 0.0 for key in ADDITIVE_EFFECTS}
    totals["attack_speed_sources"] = []
    totals["defense_pen_sources"] = []
    totals["final_damage_sources"] = []

    for companion in team:
        key = companion.effect_type
        value = companion.effect_value
        if key == "attack_speed":
            totals["attack_speed_sources"].append(value)  # type: ignore[index]
        elif key == "defense_pen":
            totals["defense_pen_sources"].append(value)  # type: ignore[index]
        elif key == "final_damage":
            totals["final_damage_sources"].append(value)  # type: ignore[index]
        else:
            totals[key] = float(totals.get(key, 0.0)) + value
    return totals


def _hit_rate(accuracy: float, target: TargetProfile) -> float:
    if not target.use_accuracy_approximation:
        return 1.0
    difference = max(0.0, target.target_evasion - accuracy)
    # Clearly exposed as an approximation in the GUI: a 100-point deficit maps
    # to the documented 70% maximum miss chance.
    miss_rate = min(0.70, difference * 0.007)
    return 1.0 - miss_rate


def _score_from_state(
    *,
    attack: float,
    damage: float,
    stat_prop_damage: float,
    crit_rate: float,
    crit_damage: float,
    attack_speed: float,
    min_damage: float,
    max_damage: float,
    normal_damage: float,
    boss_damage: float,
    basic_attack_damage: float,
    skill_damage: float,
    basic_attack_share: float,
    status_damage: float,
    status_uptime: float,
    damage_amp: float,
    final_damage: float,
    defense_pen: float,
    accuracy: float,
    target: TargetProfile,
) -> Tuple[float, float, float, float, float]:
    attack = max(0.0, attack)
    crit_rate_capped = clamp(crit_rate, 0.0, 100.0)
    attack_speed_capped = clamp(attack_speed, 0.0, 150.0)

    effective_max = max(0.0, max_damage)
    effective_min = clamp(min_damage, 0.0, effective_max)
    range_multiplier = (effective_min + effective_max) / 200.0

    crit_multiplier = 1.0 + (crit_rate_capped / 100.0) * max(0.0, crit_damage) / 100.0
    speed_multiplier = 1.0 + attack_speed_capped / 100.0
    stat_multiplier = max(0.0, 1.0 + stat_prop_damage / 100.0)
    damage_multiplier = max(0.0, 1.0 + damage / 100.0)
    amp_multiplier = max(0.0, 1.0 + damage_amp / 100.0)
    final_multiplier = max(0.0, 1.0 + final_damage / 100.0)

    basic_share = clamp(basic_attack_share, 0.0, 100.0) / 100.0
    skill_share = 1.0 - basic_share
    attack_type_multiplier = (
        basic_share * max(0.0, 1.0 + basic_attack_damage / 100.0)
        + skill_share * max(0.0, 1.0 + skill_damage / 100.0)
    )

    uptime = clamp(status_uptime, 0.0, 100.0) / 100.0
    status_multiplier = 1.0 + uptime * status_damage / 100.0

    effective_defense = max(0.0, target.target_defense) * (1.0 - clamp(defense_pen, 0.0, 100.0) / 100.0)
    defense_multiplier = 6000.0 / (6000.0 + effective_defense)
    hit_rate = _hit_rate(accuracy, target)

    common = (
        attack
        * range_multiplier
        * crit_multiplier
        * speed_multiplier
        * stat_multiplier
        * damage_multiplier
        * amp_multiplier
        * final_multiplier
        * attack_type_multiplier
        * status_multiplier
        * defense_multiplier
        * hit_rate
    )
    normal_score = common * max(0.0, 1.0 + normal_damage / 100.0)
    boss_score = common * max(0.0, 1.0 + boss_damage / 100.0)
    arena_score = common

    if target.content_mode == "Normal farming":
        selected = normal_score
    elif target.content_mode == "Boss":
        selected = boss_score
    elif target.content_mode == "Mixed stage":
        normal_weight = clamp(target.normal_weight, 0.0, 100.0) / 100.0
        selected = normal_weight * normal_score + (1.0 - normal_weight) * boss_score
    else:
        selected = arena_score

    return normal_score, boss_score, arena_score, selected, defense_multiplier


def evaluate_team(
    stats: CharacterStats,
    target: TargetProfile,
    team: Sequence[Companion],
    main: Optional[Companion] = None,
) -> Tuple[EffectiveState, Dict[str, float]]:
    raw = aggregate_effects(team)
    warnings: List[str] = []

    attack = stats.attack + float(raw.get("attack", 0.0)) * (1.0 + stats.flat_attack_scaling_pct / 100.0)
    total_main_stat = stats.total_main_stat
    main_stat_gain = 0.0

    added_main_stat_pct = float(raw.get("main_stat_pct", 0.0))
    if abs(added_main_stat_pct) > 1e-12:
        if stats.total_main_stat > 0.0:
            denominator = 1.0 + stats.current_main_stat_pct / 100.0
            if denominator <= 0.0:
                warnings.append("Main Stat % could not be modeled because Current Main Stat % is invalid.")
            else:
                base_main_stat = stats.total_main_stat / denominator
                total_main_stat = base_main_stat * (
                    1.0 + (stats.current_main_stat_pct + added_main_stat_pct) / 100.0
                )
                main_stat_gain = total_main_stat - stats.total_main_stat
                attack += main_stat_gain * (1.0 + stats.flat_attack_scaling_pct / 100.0)
        else:
            warnings.append(
                "Main Stat % companion effect was ignored: enter Total Main Stat and Current Main Stat % for accurate scoring."
            )

    stat_prop_damage = stats.stat_prop_damage + main_stat_gain / 100.0
    damage = stats.damage + float(raw.get("damage", 0.0))
    crit_rate = stats.crit_rate + float(raw.get("crit_rate", 0.0))
    crit_damage = stats.crit_damage + float(raw.get("crit_damage", 0.0))
    min_damage = stats.min_damage + float(raw.get("min_damage", 0.0))
    max_damage = stats.max_damage + float(raw.get("max_damage", 0.0))
    normal_damage = stats.normal_damage + float(raw.get("normal_damage", 0.0))
    boss_damage = stats.boss_damage + float(raw.get("boss_damage", 0.0))
    basic_attack_damage = stats.basic_attack_damage + float(raw.get("basic_attack_damage", 0.0))
    skill_damage = stats.skill_damage + float(raw.get("skill_damage", 0.0))
    status_damage = stats.status_damage + float(raw.get("status_damage", 0.0))
    damage_amp = stats.damage_amp + float(raw.get("damage_amp", 0.0))
    accuracy = stats.accuracy + float(raw.get("accuracy", 0.0))

    attack_speed = combine_diminishing(
        stats.attack_speed,
        raw.get("attack_speed_sources", []),  # type: ignore[arg-type]
        150.0,
    )
    defense_pen = combine_diminishing(
        stats.defense_pen,
        raw.get("defense_pen_sources", []),  # type: ignore[arg-type]
        100.0,
    )
    final_damage = combine_final_damage(
        stats.final_damage,
        raw.get("final_damage_sources", []),  # type: ignore[arg-type]
    )

    normal_score, boss_score, arena_score, selected, defense_multiplier = _score_from_state(
        attack=attack,
        damage=damage,
        stat_prop_damage=stat_prop_damage,
        crit_rate=crit_rate,
        crit_damage=crit_damage,
        attack_speed=attack_speed,
        min_damage=min_damage,
        max_damage=max_damage,
        normal_damage=normal_damage,
        boss_damage=boss_damage,
        basic_attack_damage=basic_attack_damage,
        skill_damage=skill_damage,
        basic_attack_share=stats.basic_attack_share,
        status_damage=status_damage,
        status_uptime=stats.status_uptime,
        damage_amp=damage_amp,
        final_damage=final_damage,
        defense_pen=defense_pen,
        accuracy=accuracy,
        target=target,
    )

    if main is not None and main.main_bonus:
        selected *= max(0.0, 1.0 + main.main_bonus / 100.0)
        normal_score *= max(0.0, 1.0 + main.main_bonus / 100.0)
        boss_score *= max(0.0, 1.0 + main.main_bonus / 100.0)
        arena_score *= max(0.0, 1.0 + main.main_bonus / 100.0)

    if crit_rate > 100.0:
        warnings.append(f"Critical Rate is {crit_rate - 100.0:.2f}% above the modeled 100% cap.")
    if min_damage > max_damage:
        warnings.append(
            f"Min Damage exceeds Max Damage by {min_damage - max_damage:.2f}%; the modeled minimum is capped at maximum."
        )
    if attack_speed >= 149.999:
        warnings.append("Attack Speed reaches the modeled 150% cap.")
    if target.use_accuracy_approximation:
        warnings.append("Accuracy impact uses the optional linear tooltip approximation, not a verified internal formula.")
    if main is not None and main.main_bonus:
        warnings.append(
            f"Main active contribution includes the manually supplied {main.main_bonus:.2f}% time-averaged bonus for {main.name}."
        )

    effect_totals: Dict[str, float] = {}
    for key in ADDITIVE_EFFECTS:
        value = float(raw.get(key, 0.0))
        if abs(value) > 1e-12:
            effect_totals[key] = value
    for key, label in (
        ("attack_speed_sources", "attack_speed"),
        ("defense_pen_sources", "defense_pen"),
        ("final_damage_sources", "final_damage"),
    ):
        values = raw.get(key, [])
        if values:
            effect_totals[label] = sum(float(x) for x in values)  # display total, not effective stacked value

    state = EffectiveState(
        attack=attack,
        total_main_stat=total_main_stat,
        damage=damage,
        stat_prop_damage=stat_prop_damage,
        crit_rate=crit_rate,
        crit_damage=crit_damage,
        attack_speed=attack_speed,
        min_damage=min_damage,
        max_damage=max_damage,
        normal_damage=normal_damage,
        boss_damage=boss_damage,
        basic_attack_damage=basic_attack_damage,
        skill_damage=skill_damage,
        status_damage=status_damage,
        damage_amp=damage_amp,
        final_damage=final_damage,
        defense_pen=defense_pen,
        accuracy=accuracy,
        hit_rate=_hit_rate(accuracy, target),
        defense_multiplier=defense_multiplier,
        score_normal=normal_score,
        score_boss=boss_score,
        score_arena=arena_score,
        score_selected=selected,
        main_stat_gain=main_stat_gain,
        warnings=warnings,
    )
    return state, effect_totals


def _reverse_diminishing(
    effective_value: float,
    sources: Sequence[float],
    cap: float,
    label: str,
) -> Tuple[float, Optional[str]]:
    """Undo multiplicative stacking against the remaining distance to a cap."""
    source_factor = 1.0
    for source in sources:
        source_factor *= 1.0 - clamp(float(source), 0.0, cap) / cap
    if source_factor <= 1e-12:
        raise ValueError(
            f"Cannot reconstruct unequipped {label}: a marked current companion contributes the full modeled cap."
        )

    effective_capped = clamp(effective_value, 0.0, cap)
    remaining_after = 1.0 - effective_capped / cap
    remaining_before = remaining_after / source_factor
    baseline = cap * (1.0 - remaining_before)
    tolerance = 0.05
    if baseline < -tolerance or baseline > cap + tolerance:
        total = sum(float(value) for value in sources)
        raise ValueError(
            f"The displayed {label} ({effective_value:g}%) is inconsistent with the marked current "
            f"companion effects ({total:g}% listed). Check the current-team marks and entered stat."
        )
    warning = None
    if effective_capped >= cap - 1e-9 and sources:
        warning = (
            f"Displayed {label} is at the modeled {cap:g}% cap, so its unequipped value cannot be "
            "recovered uniquely from a rounded capped display. The optimizer uses the capped inverse."
        )
    return clamp(baseline, 0.0, cap), warning


def reconstruct_unequipped_stats(
    displayed_stats: CharacterStats,
    equipped_team: Sequence[Companion],
) -> Tuple[CharacterStats, List[str]]:
    """Remove the marked current team's equip effects from displayed stats.

    The returned CharacterStats can be passed back through evaluate_team() with
    the current team to reproduce the displayed state (subject to in-game UI
    rounding and capped-stat information loss).
    """
    raw = aggregate_effects(equipped_team)
    baseline = copy.deepcopy(displayed_stats)
    warnings: List[str] = []
    scaling = 1.0 + displayed_stats.flat_attack_scaling_pct / 100.0
    if scaling < 0.0:
        raise ValueError("Flat Attack scaling % cannot make gained Attack negative.")

    # Main Stat % affects three entered fields in the forward model: total Main
    # Stat, Attack, and Stat Proportional Damage. Undo it before flat Attack.
    main_stat_gain = 0.0
    added_main_stat_pct = float(raw.get("main_stat_pct", 0.0))
    if abs(added_main_stat_pct) > 1e-12:
        if displayed_stats.total_main_stat <= 0.0:
            raise ValueError(
                "A currently equipped companion grants Main Stat %, so Total Main Stat must be entered "
                "to reconstruct the unequipped baseline."
            )
        displayed_pct_factor = 1.0 + displayed_stats.current_main_stat_pct / 100.0
        baseline.current_main_stat_pct = displayed_stats.current_main_stat_pct - added_main_stat_pct
        baseline_pct_factor = 1.0 + baseline.current_main_stat_pct / 100.0
        if displayed_pct_factor <= 0.0 or baseline_pct_factor < 0.0:
            raise ValueError(
                "Current Main Stat % is inconsistent with the marked Main Stat % companion effect."
            )
        raw_main_stat = displayed_stats.total_main_stat / displayed_pct_factor
        baseline.total_main_stat = raw_main_stat * baseline_pct_factor
        main_stat_gain = displayed_stats.total_main_stat - baseline.total_main_stat

    flat_attack_gain = float(raw.get("attack", 0.0)) * scaling
    baseline.attack = displayed_stats.attack - flat_attack_gain - main_stat_gain * scaling
    baseline.stat_prop_damage = displayed_stats.stat_prop_damage - main_stat_gain / 100.0

    additive_fields = {
        "damage": "damage",
        "crit_rate": "crit_rate",
        "crit_damage": "crit_damage",
        "min_damage": "min_damage",
        "max_damage": "max_damage",
        "normal_damage": "normal_damage",
        "boss_damage": "boss_damage",
        "basic_attack_damage": "basic_attack_damage",
        "skill_damage": "skill_damage",
        "status_damage": "status_damage",
        "damage_amp": "damage_amp",
        "accuracy": "accuracy",
    }
    for effect_key, stat_key in additive_fields.items():
        setattr(
            baseline,
            stat_key,
            float(getattr(displayed_stats, stat_key)) - float(raw.get(effect_key, 0.0)),
        )

    baseline.attack_speed, speed_warning = _reverse_diminishing(
        displayed_stats.attack_speed,
        raw.get("attack_speed_sources", []),  # type: ignore[arg-type]
        150.0,
        "Attack Speed",
    )
    if speed_warning:
        warnings.append(speed_warning)

    baseline.defense_pen, pen_warning = _reverse_diminishing(
        displayed_stats.defense_pen,
        raw.get("defense_pen_sources", []),  # type: ignore[arg-type]
        100.0,
        "Defense Penetration",
    )
    if pen_warning:
        warnings.append(pen_warning)

    final_source_factor = 1.0
    for source in raw.get("final_damage_sources", []):  # type: ignore[union-attr]
        final_source_factor *= max(0.0, 1.0 + float(source) / 100.0)
    if final_source_factor <= 0.0:
        raise ValueError("Cannot reconstruct unequipped Final Damage from the marked current team.")
    baseline_final_factor = (1.0 + displayed_stats.final_damage / 100.0) / final_source_factor
    if baseline_final_factor < -1e-9:
        raise ValueError("Displayed Final Damage is inconsistent with the marked current companion effects.")
    baseline.final_damage = max(-100.0, (baseline_final_factor - 1.0) * 100.0)

    if baseline.attack <= 0.0:
        raise ValueError(
            "Removing the marked current companion effects produces non-positive Attack. "
            "Check the displayed Attack, companion values, and current-team marks."
        )

    # Small negative values can arise from a stat page rounded to fewer decimal
    # places than the companion tooltip. Clamp only tiny discrepancies; larger
    # ones are actionable input errors.
    nonnegative_fields = (
        "total_main_stat",
        "stat_prop_damage",
        "crit_rate",
        "crit_damage",
        "min_damage",
        "max_damage",
        "normal_damage",
        "boss_damage",
        "basic_attack_damage",
        "skill_damage",
        "status_damage",
        "damage_amp",
        "accuracy",
    )
    for key in nonnegative_fields:
        value = float(getattr(baseline, key))
        if -0.05 <= value < 0.0:
            setattr(baseline, key, 0.0)
        elif value < -0.05:
            raise ValueError(
                f"Removing the current team produces negative {key.replace('_', ' ').title()} "
                f"({value:.3f}). Check the displayed stat and equipped-role marks."
            )

    return baseline, warnings


def validate_current_team(
    companions: Sequence[Companion],
    total_slots: int,
) -> Tuple[Tuple[Companion, ...], Companion]:
    invalid = [c for c in companions if c.equipped_role not in EQUIPPED_ROLES]
    if invalid:
        raise ValueError(f"Invalid current-slot value on {invalid[0].display_name}.")
    current = tuple(c for c in companions if c.equipped_role in {"Main", "Sub"})
    mains = tuple(c for c in current if c.equipped_role == "Main")
    subs = tuple(c for c in current if c.equipped_role == "Sub")
    if len(current) != total_slots:
        raise ValueError(
            f"Mark exactly {total_slots} currently equipped page(s): one Main and "
            f"{max(0, total_slots - 1)} Sub. Currently marked: {len(current)}."
        )
    if len(mains) != 1:
        raise ValueError(f"Mark exactly one currently equipped Main companion; currently marked: {len(mains)}.")
    if len(subs) != total_slots - 1:
        raise ValueError(
            f"Mark exactly {max(0, total_slots - 1)} currently equipped Sub companion(s); "
            f"currently marked: {len(subs)}."
        )
    return current, mains[0]


def prepare_optimization_context(
    stats: CharacterStats,
    target: TargetProfile,
    companions: Sequence[Companion],
    total_slots: int,
    stats_include_equipped_companions: bool,
) -> Tuple[
    CharacterStats,
    EffectiveState,
    Tuple[Companion, ...],
    Optional[Companion],
    List[str],
    str,
]:
    """Resolve the true baseline and the score used for gain comparisons."""
    if stats_include_equipped_companions:
        current_team, current_main = validate_current_team(companions, total_slots)
        model_stats, warnings = reconstruct_unequipped_stats(stats, current_team)
        reference_state, _ = evaluate_team(model_stats, target, current_team, current_main)
        return (
            model_stats,
            reference_state,
            current_team,
            current_main,
            warnings,
            "Current equipped team",
        )

    model_stats = copy.deepcopy(stats)
    reference_state, _ = evaluate_team(model_stats, target, ())
    return model_stats, reference_state, (), None, [], "Unequipped baseline"


def fast_team_score(
    stats: CharacterStats,
    target: TargetProfile,
    team: Sequence[Companion],
    main: Companion,
    *,
    apply_main_bonus: bool = True,
) -> float:
    """Allocation-light score used inside exhaustive search.

    This mirrors evaluate_team(), but returns only the selected-content score.
    Detailed state/warnings are calculated only for retained top teams.
    """
    flat_attack = max_damage_add = accuracy_add = normal_add = crit_rate_add = 0.0
    status_add = boss_add = min_damage_add = skill_add = basic_add = 0.0
    main_stat_pct_add = damage_add = crit_damage_add = amp_add = 0.0
    speed_remaining = 1.0 - clamp(stats.attack_speed, 0.0, 150.0) / 150.0
    pen_remaining = 1.0 - clamp(stats.defense_pen, 0.0, 100.0) / 100.0
    final_factor = max(0.0, 1.0 + stats.final_damage / 100.0)

    for companion in team:
        key = companion.effect_type
        value = companion.effect_value
        if key == "attack":
            flat_attack += value
        elif key == "max_damage":
            max_damage_add += value
        elif key == "accuracy":
            accuracy_add += value
        elif key == "normal_damage":
            normal_add += value
        elif key == "crit_rate":
            crit_rate_add += value
        elif key == "attack_speed":
            speed_remaining *= 1.0 - clamp(value, 0.0, 150.0) / 150.0
        elif key == "status_damage":
            status_add += value
        elif key == "boss_damage":
            boss_add += value
        elif key == "min_damage":
            min_damage_add += value
        elif key == "skill_damage":
            skill_add += value
        elif key == "basic_attack_damage":
            basic_add += value
        elif key == "main_stat_pct":
            main_stat_pct_add += value
        elif key == "damage":
            damage_add += value
        elif key == "crit_damage":
            crit_damage_add += value
        elif key == "damage_amp":
            amp_add += value
        elif key == "defense_pen":
            pen_remaining *= 1.0 - clamp(value, 0.0, 100.0) / 100.0
        elif key == "final_damage":
            final_factor *= max(0.0, 1.0 + value / 100.0)

    scaling = 1.0 + stats.flat_attack_scaling_pct / 100.0
    attack = stats.attack + flat_attack * scaling
    stat_prop = stats.stat_prop_damage
    if main_stat_pct_add and stats.total_main_stat > 0.0:
        denominator = 1.0 + stats.current_main_stat_pct / 100.0
        if denominator > 0.0:
            base_main_stat = stats.total_main_stat / denominator
            new_main_stat = base_main_stat * (
                1.0 + (stats.current_main_stat_pct + main_stat_pct_add) / 100.0
            )
            gain = new_main_stat - stats.total_main_stat
            attack += gain * scaling
            stat_prop += gain / 100.0

    attack_speed = 150.0 * (1.0 - speed_remaining)
    defense_pen = 100.0 * (1.0 - pen_remaining)
    final_damage = (final_factor - 1.0) * 100.0

    _, _, _, selected, _ = _score_from_state(
        attack=attack,
        damage=stats.damage + damage_add,
        stat_prop_damage=stat_prop,
        crit_rate=stats.crit_rate + crit_rate_add,
        crit_damage=stats.crit_damage + crit_damage_add,
        attack_speed=attack_speed,
        min_damage=stats.min_damage + min_damage_add,
        max_damage=stats.max_damage + max_damage_add,
        normal_damage=stats.normal_damage + normal_add,
        boss_damage=stats.boss_damage + boss_add,
        basic_attack_damage=stats.basic_attack_damage + basic_add,
        skill_damage=stats.skill_damage + skill_add,
        basic_attack_share=stats.basic_attack_share,
        status_damage=stats.status_damage + status_add,
        status_uptime=stats.status_uptime,
        damage_amp=stats.damage_amp + amp_add,
        final_damage=final_damage,
        defense_pen=defense_pen,
        accuracy=stats.accuracy + accuracy_add,
        target=target,
    )
    if apply_main_bonus and main.main_bonus:
        selected *= max(0.0, 1.0 + main.main_bonus / 100.0)
    return selected


def choose_main(team: Sequence[Companion], content_mode: str) -> Companion:
    """Use measured main bonuses first; otherwise use a non-scoring heuristic."""
    priorities = MAIN_TIEBREAK.get(content_mode, MAIN_TIEBREAK["Boss"])
    rank = _main_priority_rank(priorities)
    return min(
        team,
        key=lambda c: (
            -c.main_bonus,
            rank.get(c.name, len(priorities)),
            -RARITY_ORDER.get(c.rarity, -1),
            -c.level,
            c.name.casefold(),
        ),
    )


def optimize_companions(
    stats: CharacterStats,
    target: TargetProfile,
    companions: Sequence[Companion],
    total_slots: int,
    top_n: int,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    stats_include_equipped_companions: bool = False,
) -> Tuple[List[OptimizationResult], int, float]:
    if total_slots < 1 or total_slots > 7:
        raise ValueError("Total companion slots must be from 1 to 7 (one main plus up to six subs).")
    if len(companions) < total_slots:
        raise ValueError(
            f"You entered {len(companions)} owned companion pages, but selected {total_slots} total slots."
        )
    if top_n < 1:
        raise ValueError("Number of results must be at least 1.")

    seen: set[str] = set()
    for companion in companions:
        key = companion_key(companion.name, companion.rarity)
        if key in seen:
            raise ValueError(
                f"Duplicate page detected: {companion.name} {companion.rarity}. Exact same pages cannot be equipped twice."
            )
        seen.add(key)

    (
        model_stats,
        reference_state,
        _current_team,
        _current_main,
        reconstruction_warnings,
        reference_label,
    ) = prepare_optimization_context(
        stats,
        target,
        companions,
        total_slots,
        stats_include_equipped_companions,
    )
    reference = reference_state.score_selected

    if reference <= 0.0:
        raise ValueError("Reference score is zero. Enter a positive displayed Attack value and valid multipliers.")

    total_combinations = math.comb(len(companions), total_slots)
    start = time.perf_counter()
    heap: List[Tuple[float, int, Tuple[Companion, ...], Companion]] = []
    serial = 0

    for index, team in enumerate(itertools.combinations(companions, total_slots), start=1):
        if cancel_event is not None and cancel_event.is_set():
            break
        main = choose_main(team, target.content_mode)
        score = fast_team_score(model_stats, target, team, main)
        item = (score, serial, team, main)
        serial += 1
        if len(heap) < top_n:
            heapq.heappush(heap, item)
        elif score > heap[0][0]:
            heapq.heapreplace(heap, item)

        if progress is not None and (index == total_combinations or index % 5000 == 0):
            progress(index, total_combinations)

    elapsed = time.perf_counter() - start
    results: List[OptimizationResult] = []
    for score, _, team, main in sorted(heap, key=lambda x: x[0], reverse=True):
        state, totals = evaluate_team(model_stats, target, team, main)
        if reconstruction_warnings:
            state.warnings = list(reconstruction_warnings) + state.warnings
        subs = tuple(companion for companion in team if companion.uid != main.uid)
        gain_pct = (score / reference - 1.0) * 100.0
        results.append(
            OptimizationResult(
                score=score,
                gain_pct=gain_pct,
                main=main,
                subs=subs,
                team=team,
                state=state,
                effect_totals=totals,
                reference_score=reference,
                reference_label=reference_label,
            )
        )
    return results, total_combinations, elapsed


# ---------------------------------------------------------------------------
# Profile serialization
# ---------------------------------------------------------------------------

@dataclass
class Profile:
    stats: CharacterStats = field(default_factory=CharacterStats)
    target: TargetProfile = field(default_factory=TargetProfile)
    companions: List[Companion] = field(default_factory=list)
    total_slots: int = 7
    top_results: int = 20
    stats_include_equipped_companions: bool = True
    stat_sources: Dict[str, str] = field(default_factory=dict)


def profile_to_dict(profile: Profile) -> Dict[str, object]:
    return {
        "profile_version": PROFILE_VERSION,
        "app_version": APP_VERSION,
        "stats": asdict(profile.stats),
        "target": asdict(profile.target),
        "companions": [asdict(c) for c in profile.companions],
        "total_slots": profile.total_slots,
        "top_results": profile.top_results,
        "stats_include_equipped_companions": profile.stats_include_equipped_companions,
        "stat_sources": dict(profile.stat_sources),
    }


def _construct_dataclass(cls, payload: Dict[str, object]):
    allowed = {f.name for f in fields(cls)}
    return cls(**{key: value for key, value in payload.items() if key in allowed})


def profile_from_dict(payload: Dict[str, object]) -> Profile:
    version = int(payload.get("profile_version", 1))
    if version > PROFILE_VERSION:
        raise ValueError(
            f"This profile uses version {version}, but this app supports up to version {PROFILE_VERSION}."
        )
    stats = _construct_dataclass(CharacterStats, dict(payload.get("stats", {})))
    target = _construct_dataclass(TargetProfile, dict(payload.get("target", {})))
    companions = [
        _construct_dataclass(Companion, dict(item))
        for item in list(payload.get("companions", []))
    ]
    return Profile(
        stats=stats,
        target=target,
        companions=companions,
        total_slots=int(payload.get("total_slots", 7)),
        top_results=int(payload.get("top_results", 20)),
        # Version-1 profiles were explicitly built from unequipped stats.
        stats_include_equipped_companions=bool(
            payload.get("stats_include_equipped_companions", version >= 2)
        ),
        stat_sources={
            str(key): str(value)
            for key, value in dict(payload.get("stat_sources", {})).items()
        },
    )


# ---------------------------------------------------------------------------
# Tkinter utilities
# ---------------------------------------------------------------------------

COLORS = {
    "bg": "#edf4fa",
    "panel": "#fbfdff",
    "panel_alt": "#eef4fa",
    "surface": "#ffffff",
    "text": "#24364a",
    "muted": "#64778b",
    "accent": "#4ebfd4",
    "accent_hover": "#74d3e3",
    "warning": "#d99334",
    "danger": "#ca6167",
    "border": "#97aabd",
    "selection": "#7ad04f",
    "field_label": "#acd81c",
    "field_label_text": "#354600",
    "field_border": "#76818e",
}

RARITY_TILE_COLORS = {
    "Common": "#d9dde5",
    "Rare": "#4c9dff",
    "Epic": "#9d6cff",
    "Unique": "#f0a43a",
    "Legendary": "#39c994",
}


def companion_asset_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")


def companion_asset_directory() -> Path:
    return resource_path("assets", "companions")


def ui_asset_directory() -> Path:
    return resource_path("assets", "ui")


def help_asset_directory() -> Path:
    return resource_path("assets", "help")


def apply_window_icon(window: tk.Misc) -> None:
    """Apply the Fire/Poison Legendary companion portrait as the app icon."""
    try:
        icon_png = ui_asset_directory() / "app_icon.png"
        if icon_png.is_file():
            photo = tk.PhotoImage(master=window, file=str(icon_png))
            window.wm_iconphoto(True, photo)
            # Tk requires a live Python reference to the image.
            setattr(window, "_maple_app_icon_photo", photo)
        if os.name == "nt":
            icon_ico = ui_asset_directory() / "app_icon.ico"
            if icon_ico.is_file():
                window.wm_iconbitmap(default=str(icon_ico))
    except Exception:
        # An icon failure must never prevent the optimizer from opening.
        pass


def install_runtime_exception_logging(app: tk.Tk) -> None:
    """Capture otherwise invisible GUI/thread errors in packaged builds."""
    def callback_exception(exc_type, exc_value, exc_traceback):
        path = write_crash_log(
            "Tkinter callback", exc_type, exc_value, exc_traceback
        )
        location = f"\n\nA diagnostic log was saved to:\n{path}" if path else ""
        try:
            messagebox.showerror(
                "Unexpected application error",
                f"An unexpected interface error occurred:\n\n{exc_value}{location}\n\n"
                "The program may continue, but please use Report Bug if the problem repeats.",
                parent=app,
            )
        except Exception:
            pass

    def unhandled_exception(exc_type, exc_value, exc_traceback):
        path = write_crash_log(
            "Unhandled main-thread exception", exc_type, exc_value, exc_traceback
        )
        try:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        except Exception:
            if path:
                print(f"Unhandled exception log: {path}", file=sys.stderr)

    def thread_exception(args):
        write_crash_log(
            f"Unhandled thread exception ({getattr(args.thread, 'name', 'unknown')})",
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
        )

    app.report_callback_exception = callback_exception
    sys.excepthook = unhandled_exception
    if hasattr(threading, "excepthook"):
        threading.excepthook = thread_exception


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tip,
            text=self.text,
            justify="left",
            background="#f8f3df",
            foreground="#18202a",
            relief="ridge",
            borderwidth=1,
            padx=8,
            pady=6,
            wraplength=420,
            font=("TkDefaultFont", 9),
        )
        label.pack()

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None

class ScreenshotImportWarningDialog(tk.Toplevel):
    """Mandatory preparation warning shown before selecting Stat Info images."""

    def __init__(self, app: "OptimizerApp"):
        super().__init__(app)
        apply_window_icon(self)
        self.app = app
        self.proceed = False
        self.dont_show_again_var = tk.BooleanVar(value=False)

        # Build the dialog while hidden so it never flashes at the old default size.
        self.withdraw()
        self.title("Before importing Stat Info screenshots")
        self.resizable(True, True)
        self.configure(background="#efe8d7")
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _event: self.cancel())
        self.bind("<Return>", lambda _event: self.continue_import())

        outer = tk.Frame(self, background="#efe8d7", padx=24, pady=22)
        outer.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        # Only the explanatory details area is allowed to shrink. The checkbox
        # and action buttons always keep their requested height.
        outer.rowconfigure(3, weight=1)

        tk.Label(
            outer,
            text="Prepare the game before taking screenshots",
            background="#efe8d7",
            foreground="#26364b",
            font=("TkDefaultFont", 18, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            outer,
            text=(
                "Incorrect screenshot conditions change the reconstructed baseline and can make "
                "the optimizer recommend the wrong team."
            ),
            background="#efe8d7",
            foreground="#5b6670",
            font=("TkDefaultFont", 10),
            justify="left",
            wraplength=700,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(5, 16))

        warning = tk.Frame(
            outer,
            background="#fff0b8",
            highlightbackground="#c58a22",
            highlightthickness=2,
            padx=18,
            pady=16,
        )
        warning.grid(row=2, column=0, sticky="ew")
        warning.columnconfigure(0, weight=1)
        tk.Label(
            warning,
            text="REQUIRED SCREENSHOT CONDITIONS",
            background="#fff0b8",
            foreground="#7a2b16",
            font=("TkDefaultFont", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 9))
        tk.Label(
            warning,
            text=(
                "1. Set combat to MANUAL.\n"
                "2. Wait until every temporary buff and effect has fully worn off.\n"
                "3. Keep the character on Manual while taking every screenshot."
            ),
            background="#fff0b8",
            foreground="#562313",
            font=("TkDefaultFont", 12, "bold"),
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew")

        details = tk.Frame(
            outer,
            background="#fffdf7",
            highlightbackground="#b6bdc2",
            highlightthickness=1,
            padx=16,
            pady=13,
        )
        details.grid(row=3, column=0, sticky="nsew", pady=(14, 12))
        details.rowconfigure(0, weight=1)
        details.columnconfigure(0, weight=1)
        tk.Label(
            details,
            text=(
                "Then open Preset Settings → Stat Info / Expected Stats and capture overlapping images. "
                "The Main and Subs marked in this program must match the companions equipped in the captured preset.\n\n"
                "A different preset is acceptable when its only difference is the companion team. If equipment, "
                "skills, stat allocation, or other non-companion bonuses differ, capture the preset you actually want evaluated."
            ),
            background="#fffdf7",
            foreground="#26364b",
            font=("TkDefaultFont", 10),
            justify="left",
            wraplength=690,
            anchor="nw",
        ).grid(row=0, column=0, sticky="nsew")

        tk.Checkbutton(
            outer,
            text="Don't show this preparation warning again",
            variable=self.dont_show_again_var,
            background="#efe8d7",
            activebackground="#efe8d7",
            foreground="#26364b",
            selectcolor="#fffdf7",
            font=("TkDefaultFont", 10),
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", pady=(0, 14))

        buttons = tk.Frame(outer, background="#efe8d7")
        buttons.grid(row=5, column=0, sticky="ew")
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right")
        continue_button = ttk.Button(
            buttons,
            text="Continue to screenshot selection",
            command=self.continue_import,
        )
        continue_button.pack(side="right", padx=(0, 10))

        self.update_idletasks()

        # Use a comfortably large default size, but remain usable on short or
        # heavily scaled displays. Grid row 3 absorbs any necessary shrinking,
        # so the checkbox and Continue/Cancel controls cannot be pushed offscreen.
        screen_width = max(1, self.winfo_screenwidth())
        screen_height = max(1, self.winfo_screenheight())
        max_width = max(680, screen_width - 80)
        max_height = max(520, screen_height - 100)
        requested_width = max(780, self.winfo_reqwidth() + 12)
        requested_height = max(650, self.winfo_reqheight() + 12)
        width = min(requested_width, max_width)
        height = min(requested_height, max_height)

        self.minsize(min(700, width), min(540, height))
        x = max(0, app.winfo_rootx() + (app.winfo_width() - width) // 2)
        y = max(0, app.winfo_rooty() + (app.winfo_height() - height) // 2)
        # Keep the window inside the active screen even if the main window is
        # partly offscreen.
        x = min(x, max(0, screen_width - width))
        y = min(y, max(0, screen_height - height))
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        continue_button.focus_set()

    def continue_import(self):
        self.proceed = True
        self.destroy()

    def cancel(self):
        self.proceed = False
        self.destroy()


class HelpBook(tk.Toplevel):
    """Page-based in-app guide with quick navigation and screenshot examples."""

    PAGES = (
        {
            "id": "start",
            "icon": "★",
            "nav": "Quick start",
            "title": "Quick Start",
            "body": (
                "The optimizer uses the stats shown by one in-game preset, your owned companion pages, "
                "and the companions currently equipped in that preset.\n\n"
                "1. Create or select a build for the content you want to optimize.\n"
                "2. Import the preset's Expected Stats screenshots, or enter the displayed values manually.\n"
                "3. Mark every owned companion page and enter its current level.\n"
                "4. Use each portrait's role badge to mark the Main and Sub companions currently equipped.\n"
                "5. Choose the Optimization Target and press Optimize Team.\n\n"
                "Ownership and levels are shared by the account. Displayed stats, current team, target, "
                "and robustness ranges are saved separately for each build."
            ),
        },
        {
            "id": "screenshots",
            "icon": "▣",
            "nav": "Screenshots",
            "title": "Importing Expected Stats",
            "body": (
                "Open Preset Settings, then open Stat Info / Expected Stats. You do not have to capture the "
                "preset you ultimately plan to use. The screenshot supplies the non-companion baseline. If two "
                "presets differ only in their equipped companions, either preset is fine—as long as you mark the "
                "exact Main and Subs equipped in the captured preset. The app removes those modeled equip effects "
                "before testing every owned combination. The recommended best team will be the same; the displayed "
                "gain is simply measured against the team shown in the captured preset."
            ),
            "warning": (
                "IMPORTANT — SCREENSHOT CONDITIONS: Set combat to Manual, then wait until every temporary buff "
                "has fully worn off before taking the screenshots. Remaining on Auto can re-trigger skills or "
                "companion effects and contaminate the baseline."
            ),
            "body_after": (
                "Use three overlapping screenshots when possible:\n"
                "• First image: start at Attack and the top of the list.\n"
                "• Second image: overlap several rows from the first image.\n"
                "• Third image: include the bottom rows and job-skill levels.\n\n"
                "Keep the game window size and display scaling unchanged between screenshots. Click AUTO-ASSIGN, "
                "select the captures together, review the recognized values, and correct any orange or conflicting fields manually.\n\n"
                "If presets also change equipment, skills, stat allocations, or other non-companion bonuses, use the "
                "preset that matches the build you actually want evaluated. The Optimization Target determines whether "
                "the imported build is scored for Boss, Normal, Mixed, or Arena content.\n\n"
                "The example below shows the correct Preset Settings → Stat Info screen."
            ),
            "image": "preset_expected_stats_example.png",
        },
        {
            "id": "stats",
            "icon": "Σ",
            "nav": "Stats",
            "title": "Character and Combat Stats",
            "body": (
                "Enter values exactly as they appear for the active preset. Normally, leave “Displayed stats include equipped companions” checked; "
                "the optimizer then removes the current team's equip effects before testing replacements.\n\n"
                "For stable measurements, set combat to Manual and wait until all temporary buffs have worn off before capturing the values. "
                "Auto can re-trigger temporary effects while you are waiting. Boss Damage may be hidden when it is genuinely 0%, "
                "and appears once a boss-oriented preset adds it.\n\n"
                "Content-Specific Damage controls Basic Attack, Skill, Boss, Normal, and Status weighting. "
                "Advanced Multipliers are optional but improve accuracy when known. Fields not covered by screenshot import remain highlighted for manual review."
            ),
        },
        {
            "id": "companions",
            "icon": "♟",
            "nav": "Companions",
            "title": "Companion Collection",
            "body": (
                "Each portrait represents one rarity page of a companion.\n\n"
                "• Click the portrait to toggle ownership.\n"
                "• Click the level chip to type the page's current level.\n"
                "• Click the circular role badge and choose Not equipped, Main, or Sub from the menu.\n\n"
                "Only mark the team currently equipped in the selected build. The role menu does not change the existing Main until you deliberately choose Main. "
                "The app allows one Main and the number of total slots entered under Character Stat.\n\n"
                "Sub numbering is only visual; the order of Sub companions does not affect the calculation."
            ),
        },
        {
            "id": "optimization",
            "icon": "⚙",
            "nav": "Optimization",
            "title": "Optimization and Robustness",
            "body": (
                "Optimization Target selects the content model: Boss, Normal, Mixed, or Arena. Main handling can be Automatic, Equip effects only, "
                "or Lock selected Main. The normal search exhaustively checks every valid team from the owned pages entered.\n\n"
                "Robustness ranges are optional. Enter both a minimum and maximum for any uncertain value you want tested, such as Basic Attack share, "
                "Status uptime, target Defense, or target Evasion. Leave both boxes blank to skip that range.\n\n"
                "Pressing Optimize Team runs the normal search first and then automatically evaluates any completed ranges. Wider ranges take longer, "
                "but show whether the recommendation remains stable when your estimates are imperfect."
            ),
        },
        {
            "id": "results",
            "icon": "✓",
            "nav": "Results",
            "title": "Reading the Results",
            "body": (
                "The first result is the highest-scoring legal team for the active build and target. Gain is measured against the current team reconstructed "
                "from the roles you marked. Select any result to see its Main, Subs, combined effects, estimated swap costs, and model notes.\n\n"
                "Robustness output reports how often the nominal recommendation remains best across the entered ranges. Compare Mains tests the strongest Sub team "
                "for each possible Main. Plan Upgrades estimates the next companion level with the largest modeled equip-effect gain.\n\n"
                "The model is exact for the implemented equip effects, but companion AI, animations, healing, crowd control, and unmeasured active skills are not fully simulated."
            ),
        },
    )

    def __init__(self, app: tk.Tk, start_page: str = "start"):
        super().__init__(app)
        apply_window_icon(self)
        self.app = app
        self.title(f"{APP_NAME} — Help")
        self.geometry("1020x720")
        self.minsize(820, 580)
        self.configure(background="#efe8d7")
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<Left>", lambda _e: self.previous_page())
        self.bind("<Right>", lambda _e: self.next_page())
        self._page_photo = None
        self._nav_buttons: List[tk.Button] = []
        self.page_index = next(
            (index for index, page in enumerate(self.PAGES) if page["id"] == start_page),
            0,
        )

        sidebar = tk.Frame(self, background="#172536", width=188, padx=10, pady=12)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(
            sidebar,
            text="HELP GUIDE",
            background="#172536",
            foreground="#f1d54b",
            font=("TkDefaultFont", 13, "bold"),
        ).pack(anchor="w", padx=7, pady=(2, 14))
        for index, page in enumerate(self.PAGES):
            button = tk.Button(
                sidebar,
                text=f"{page['icon']}   {page['nav']}",
                command=lambda i=index: self.show_page(i),
                anchor="w",
                relief="flat",
                borderwidth=0,
                padx=10,
                pady=9,
                font=("TkDefaultFont", 10, "bold"),
                cursor="hand2",
            )
            button.pack(fill="x", pady=2)
            self._nav_buttons.append(button)

        book = tk.Frame(self, background="#efe8d7", padx=24, pady=20)
        book.pack(side="left", fill="both", expand=True)
        self.page_title = tk.Label(
            book,
            background="#efe8d7",
            foreground="#26364b",
            font=("TkDefaultFont", 19, "bold"),
            anchor="w",
        )
        self.page_title.pack(fill="x", pady=(0, 10))
        rule = tk.Frame(book, height=2, background="#a9b3bb")
        rule.pack(fill="x", pady=(0, 12))

        body_frame = tk.Frame(book, background="#fffdf7", highlightbackground="#aeb6bc", highlightthickness=1)
        body_frame.pack(fill="both", expand=True)
        body_scroll = ttk.Scrollbar(body_frame, orient="vertical")
        body_scroll.pack(side="right", fill="y")
        self.page_body = tk.Text(
            body_frame,
            wrap="word",
            background="#fffdf7",
            foreground="#26364b",
            relief="flat",
            borderwidth=0,
            padx=22,
            pady=18,
            spacing1=2,
            spacing3=5,
            font=("TkDefaultFont", 11),
            yscrollcommand=body_scroll.set,
        )
        self.page_body.pack(side="left", fill="both", expand=True)
        self.page_body.tag_configure(
            "warning",
            font=("TkDefaultFont", 11, "bold"),
            foreground="#7a2b16",
            background="#fff0b8",
            lmargin1=10,
            lmargin2=10,
            rmargin=10,
            spacing1=8,
            spacing3=8,
        )
        body_scroll.configure(command=self.page_body.yview)

        footer = tk.Frame(book, background="#efe8d7")
        footer.pack(fill="x", pady=(12, 0))
        self.previous_button = ttk.Button(footer, text="◀  Previous", command=self.previous_page)
        self.previous_button.pack(side="left")
        self.restore_warning_button = ttk.Button(
            footer,
            text="Restore screenshot warning",
            command=self.restore_screenshot_warning,
        )
        self.page_indicator = tk.Label(
            footer,
            background="#efe8d7",
            foreground="#5d6b78",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.page_indicator.pack(side="left", expand=True)
        self.next_button = ttk.Button(footer, text="Next  ▶", command=self.next_page)
        self.next_button.pack(side="right")
        self.show_page(self.page_index)

    def close(self):
        if getattr(self.app, "_help_window", None) is self:
            self.app._help_window = None
        self.destroy()

    def show_page(self, index: int):
        self.page_index = max(0, min(len(self.PAGES) - 1, index))
        page = self.PAGES[self.page_index]
        self.page_title.configure(text=page["title"])
        for button_index, button in enumerate(self._nav_buttons):
            active = button_index == self.page_index
            button.configure(
                background="#54bfd2" if active else "#22354b",
                foreground="#10232b" if active else "#eef4f8",
                activebackground="#74d3e3",
                activeforeground="#10232b",
            )
        self.page_body.configure(state="normal")
        self.page_body.delete("1.0", "end")
        self.page_body.insert("end", page["body"])
        warning = page.get("warning")
        if warning:
            self.page_body.insert("end", "\n\n")
            self.page_body.insert("end", str(warning), "warning")
        body_after = page.get("body_after")
        if body_after:
            self.page_body.insert("end", "\n\n")
            self.page_body.insert("end", str(body_after))
        self._page_photo = None
        image_name = page.get("image")
        if image_name:
            image_path = help_asset_directory() / str(image_name)
            if Image is not None and ImageTk is not None and image_path.exists():
                try:
                    image = Image.open(image_path).convert("RGB")
                    max_width = max(560, self.page_body.winfo_width() - 60)
                    image.thumbnail((min(760, max_width), 430), Image.Resampling.LANCZOS)
                    self._page_photo = ImageTk.PhotoImage(image)
                    self.page_body.insert("end", "\n\n")
                    self.page_body.image_create("end", image=self._page_photo)
                    self.page_body.insert(
                        "end",
                        "\nExample: Preset Settings with the Expected Stats / Stat Info panel open.",
                    )
                except Exception as exc:
                    self.page_body.insert("end", f"\n\nExample image could not be loaded: {exc}")
        self.page_body.configure(state="disabled")
        self.page_body.yview_moveto(0)
        self.page_indicator.configure(text=f"Page {self.page_index + 1} of {len(self.PAGES)}")
        self.previous_button.configure(state="normal" if self.page_index > 0 else "disabled")
        self.next_button.configure(state="normal" if self.page_index + 1 < len(self.PAGES) else "disabled")
        if page.get("id") == "screenshots" and self.app.is_screenshot_warning_hidden():
            self.restore_warning_button.pack(side="left", padx=(10, 0))
        else:
            self.restore_warning_button.pack_forget()

    def restore_screenshot_warning(self):
        self.app.set_screenshot_warning_hidden(False)
        self.restore_warning_button.pack_forget()
        messagebox.showinfo(
            "Screenshot warning restored",
            "The preparation warning will appear the next time you click the screenshot import button.",
            parent=self,
        )

    def previous_page(self):
        if self.page_index > 0:
            self.show_page(self.page_index - 1)

    def next_page(self):
        if self.page_index + 1 < len(self.PAGES):
            self.show_page(self.page_index + 1)


class BugReportDialog(tk.Toplevel):
    """Collect reproduction details and export a self-contained diagnostic ZIP."""

    AREAS = (
        "Layout / resizing",
        "Companion ownership, level, or role",
        "Screenshot import",
        "Saving, loading, or builds",
        "Optimization or results",
        "Robustness / planning",
        "Startup or packaging",
        "Other",
    )

    def __init__(self, app: "AdvancedOptimizerApp"):
        super().__init__(app)
        apply_window_icon(self)
        self.app = app
        self.title(f"{APP_NAME} — Report Bug")
        # The original 850×700 dialog could hide the report options/footer once
        # window decorations and display scaling were applied.  Use a larger,
        # screen-aware default and center it while still respecting smaller
        # displays.
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(960, max(680, screen_width - 100))
        height = min(840, max(560, screen_height - 120))
        width = min(width, max(640, screen_width - 20))
        height = min(height, max(500, screen_height - 60))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(760, width), min(640, height))
        # Keep the three narrative fields comfortable on normal displays while
        # allowing the footer to remain reachable on short laptop screens.
        self._report_text_height = 4 if screen_height >= 900 else (3 if screen_height >= 700 else 1)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.configure(background=COLORS["bg"])
        self.summary_var = tk.StringVar()
        self.area_var = tk.StringVar(value=self.AREAS[0])
        self.include_profile_var = tk.BooleanVar(value=True)
        self.include_screenshot_var = tk.BooleanVar(value=True)
        self._build()

    def _build(self):
        header = tk.Frame(self, background="#050505", padx=16, pady=11)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Create a Diagnostic Bug Report",
            background="#050505",
            foreground="#f1d54b",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Nothing is uploaded automatically. Save the ZIP and send it with any useful video or extra screenshots.",
            background="#050505",
            foreground="#d8e4ee",
        ).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(self, background=COLORS["bg"], padx=16, pady=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(3, weight=1)
        body.rowconfigure(5, weight=1)
        body.rowconfigure(7, weight=1)

        tk.Label(body, text="Short summary", background=COLORS["bg"], foreground=COLORS["text"], font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(body, textvariable=self.summary_var).grid(row=0, column=1, sticky="ew", pady=4)
        tk.Label(body, text="Area", background=COLORS["bg"], foreground=COLORS["text"], font=("TkDefaultFont", 10, "bold")).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Combobox(body, textvariable=self.area_var, values=self.AREAS, state="readonly").grid(row=1, column=1, sticky="ew", pady=4)

        self.steps_text = self._text_field(body, 2, "Steps to reproduce", "List the exact clicks/actions, including whether the window was resized or a profile was loaded.")
        self.expected_text = self._text_field(body, 4, "Expected behavior", "What should have happened?")
        self.actual_text = self._text_field(body, 6, "Actual behavior", "What happened instead? Include any visible error message.")

        options = tk.Frame(body, background=COLORS["bg"])
        options.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        ttk.Checkbutton(
            options,
            text="Include a snapshot of the current account/build data (recommended)",
            variable=self.include_profile_var,
        ).pack(anchor="w")
        ttk.Checkbutton(
            options,
            text="Include a screenshot of the application window when supported",
            variable=self.include_screenshot_var,
        ).pack(anchor="w", pady=(4, 0))

        footer = tk.Frame(self, background=COLORS["panel"], padx=16, pady=12)
        footer.pack(fill="x")
        ttk.Button(footer, text="Cancel", command=self.close).pack(side="right")
        ttk.Button(footer, text="Copy report text", command=self.copy_report_text).pack(side="right", padx=8)
        ttk.Button(footer, text="Save Diagnostic ZIP", style="Accent.TButton", command=self.save_report).pack(side="right")

    def _text_field(self, parent, row: int, label: str, hint: str) -> tk.Text:
        tk.Label(parent, text=label, background=COLORS["bg"], foreground=COLORS["text"], font=("TkDefaultFont", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 3))
        frame = tk.Frame(parent, background="#ffffff", highlightbackground=COLORS["border"], highlightthickness=1)
        frame.grid(row=row + 1, column=0, columnspan=2, sticky="nsew")
        widget = tk.Text(frame, height=self._report_text_height, wrap="word", relief="flat", borderwidth=0, padx=8, pady=7, background="#ffffff", foreground=COLORS["text"])
        widget.pack(fill="both", expand=True)
        widget.insert("1.0", "")
        ToolTip(widget, hint)
        return widget

    def close(self):
        if getattr(self.app, "_bug_report_window", None) is self:
            self.app._bug_report_window = None
        self.destroy()

    @staticmethod
    def _text(widget: tk.Text) -> str:
        return widget.get("1.0", "end-1c").strip()

    def _system_info(self) -> Dict[str, object]:
        app = self.app
        try:
            tk_patchlevel = str(app.tk.call("info", "patchlevel"))
        except Exception:
            tk_patchlevel = "unknown"
        try:
            tk_scaling = float(app.tk.call("tk", "scaling"))
        except Exception:
            tk_scaling = None
        try:
            scroll = app.workspace_canvas.yview() if hasattr(app, "workspace_canvas") else ()
        except Exception:
            scroll = ()
        runtime = resolve_tesseract_runtime()
        owned = 0
        equipped = 0
        for row in getattr(app, "roster_vars", {}).values():
            try:
                owned += int(bool(row["owned"].get()))
                equipped += int(str(row["role"].get()) in {"Main", "Sub"})
            except Exception:
                continue
        return {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "profile_format_version": PROFILE_VERSION,
            "python_version": platform.python_version(),
            "python_executable": Path(sys.executable).name,
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "tk_patchlevel": tk_patchlevel,
            "tk_scaling": tk_scaling,
            "pillow_available": Image is not None,
            "frozen_build": is_frozen_build(),
            "application_resource_directory": str(application_resource_directory()),
            "tesseract_path": str(runtime.executable) if runtime else "",
            "tesseract_bundled": bool(runtime and runtime.bundled),
            "tessdata_path": str(runtime.tessdata) if runtime and runtime.tessdata else "",
            "crash_log_directory": str(crash_log_directory()),
            "screen_size": [app.winfo_screenwidth(), app.winfo_screenheight()],
            "window_geometry": app.geometry(),
            "window_state": app.state(),
            "workspace_scroll_fraction": list(scroll),
            "active_build": getattr(app, "active_build_name", ""),
            "profile_saved": bool(getattr(app, "profile_path", None)),
            "profile_filename": getattr(getattr(app, "profile_path", None), "name", ""),
            "selected_companion": getattr(app, "selected_roster_key", ""),
            "owned_companion_pages": owned,
            "equipped_companion_pages": equipped,
            "results_in_memory": len(getattr(app, "results", [])),
            "current_job_kind": getattr(app, "current_job_kind", ""),
            "status_bar": getattr(getattr(app, "status_var", None), "get", lambda: "")(),
        }

    def _report_text(self) -> str:
        return (
            f"{APP_NAME} {APP_VERSION} BUG REPORT\n"
            f"Created: {datetime.now().astimezone().isoformat()}\n"
            f"Area: {self.area_var.get()}\n"
            f"Summary: {self.summary_var.get().strip()}\n\n"
            f"STEPS TO REPRODUCE\n{self._text(self.steps_text) or '[not provided]'}\n\n"
            f"EXPECTED BEHAVIOR\n{self._text(self.expected_text) or '[not provided]'}\n\n"
            f"ACTUAL BEHAVIOR\n{self._text(self.actual_text) or '[not provided]'}\n"
        )

    def copy_report_text(self):
        report = self._report_text()
        self.app.clipboard_clear()
        self.app.clipboard_append(report)
        self.app.update_idletasks()
        messagebox.showinfo("Bug report", "Report text copied to the clipboard.", parent=self)

    def _capture_window(self) -> Tuple[Optional[bytes], str]:
        if not bool(self.include_screenshot_var.get()):
            return None, "Screenshot was not requested."
        if ImageGrab is None:
            return None, "Pillow ImageGrab is unavailable."
        hidden = False
        try:
            # Hide the report form so the captured image shows the application
            # state that the tester is reporting rather than this dialog itself.
            self.withdraw()
            hidden = True
            self.app.lift()
            self.app.update_idletasks()
            self.app.update()
            x = self.app.winfo_rootx()
            y = self.app.winfo_rooty()
            width = self.app.winfo_width()
            height = self.app.winfo_height()
            image = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue(), "Application screenshot captured."
        except Exception as exc:
            return None, f"Automatic screenshot failed: {exc}"
        finally:
            if hidden and self.winfo_exists():
                self.deiconify()
                self.lift()

    def save_report(self):
        summary = self.summary_var.get().strip()
        actual = self._text(self.actual_text)
        if not summary:
            messagebox.showerror("Bug report", "Enter a short summary before saving the report.", parent=self)
            return
        if not actual:
            messagebox.showerror("Bug report", "Describe the actual behavior before saving the report.", parent=self)
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path_text = filedialog.asksaveasfilename(
            parent=self,
            title="Save diagnostic bug report",
            defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip")],
            initialfile=f"maplestory_idle_bug_{stamp}.zip",
        )
        if not path_text:
            return
        path = Path(path_text)
        if path.suffix.casefold() != ".zip":
            path = path.with_suffix(".zip")
        screenshot_bytes, screenshot_note = self._capture_window()
        system_info = self._system_info()
        try:
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("bug_report.txt", self._report_text())
                archive.writestr("system_info.json", json.dumps(system_info, indent=2))
                archive.writestr(
                    "README.txt",
                    "Send this ZIP to the developer together with any additional screenshot or short video that makes the issue clearer.\n"
                    "The report is created locally; the application does not upload it.\n\n"
                    f"{screenshot_note}\n",
                )
                if bool(self.include_profile_var.get()):
                    try:
                        account = self.app.collect_account()
                        archive.writestr("profile_snapshot.json", json.dumps(account_to_dict(account), indent=2))
                    except Exception as exc:
                        archive.writestr("profile_snapshot_error.txt", traceback.format_exc())
                if screenshot_bytes is not None:
                    archive.writestr("app_screenshot.png", screenshot_bytes)
                for index, log_path in enumerate(recent_crash_logs(limit=3), start=1):
                    try:
                        archive.write(log_path, f"crash_logs/{index}_{log_path.name}")
                    except OSError:
                        pass
            messagebox.showinfo(
                "Bug report saved",
                f"Diagnostic package saved to:\n{path}\n\nSend this ZIP with any useful video or extra screenshot.",
                parent=self,
            )
            self.close()
        except Exception as exc:
            messagebox.showerror("Bug report", f"Could not create the report package:\n\n{exc}", parent=self)


class CompanionTile(tk.Frame):
    """Compact image-backed companion page card with direct controls."""

    # Only one inline level editor may be active at a time.  Keeping this at
    # the widget class level prevents a second tile from opening an editor
    # while the first tile is still in its FocusOut/commit cycle.
    _active_level_tile: Optional["CompanionTile"] = None

    # Roughly 30% smaller than the original 124×148 card.  Keeping the
    # proportions rather than merely shrinking the portrait makes the class
    # panels substantially denser without changing the interaction model.
    WIDTH = 88
    HEIGHT = 105
    IMAGE_SIZE = 70

    def __init__(
        self,
        parent,
        *,
        key: str,
        name: str,
        rarity: str,
        color_image: Optional[tk.PhotoImage],
        gray_image: Optional[tk.PhotoImage],
        placeholder: bool,
        on_select: Callable[[str], None],
        on_toggle: Callable[[str], None],
        on_role: Callable[[str, tk.Widget, int, int], None],
        on_level: Callable[[str, str], bool],
    ):
        super().__init__(parent, background=COLORS["panel"], width=self.WIDTH, height=self.HEIGHT)
        self.grid_propagate(False)
        self.key = key
        self.name = name
        self.rarity = rarity
        self.color_image = color_image
        self.gray_image = gray_image
        self.placeholder = placeholder
        self.on_select = on_select
        self.on_toggle = on_toggle
        self.on_role = on_role
        self.on_level = on_level
        self.owned = False
        self.level = 1
        self.role_badge = "—"
        self.selected = False
        self.effect_text = ""
        self._level_window: Optional[int] = None
        self._level_entry: Optional[tk.Entry] = None
        self._level_focus_after: Optional[str] = None

        self.canvas = tk.Canvas(
            self,
            width=self.WIDTH,
            height=self.HEIGHT,
            background=COLORS["panel"],
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._handle_click)
        self.tooltip = ToolTip(self.canvas, "")
        self.redraw()

    @staticmethod
    def _initials(name: str) -> str:
        special = {
            "Ice/Lightning": "I/L",
            "Fire/Poison": "F/P",
            "Dark Knight": "DK",
            "Night Lord": "NL",
            "Night Walker": "NW",
            "Wind Archer": "WA",
        }
        if name in special:
            return special[name]
        parts = re.findall(r"[A-Za-z]+", name)
        return "".join(part[0] for part in parts[:2]).upper() or "?"

    def refresh(
        self,
        *,
        owned: bool,
        level: int,
        role_badge: str,
        selected: bool,
        effect_text: str,
    ):
        self.owned = owned
        self.level = level
        self.role_badge = role_badge
        self.selected = selected
        self.effect_text = effect_text
        source_note = "placeholder portrait" if self.placeholder else "game portrait"
        state = "owned" if owned else "not owned"
        role = {"—": "not equipped"}.get(role_badge, role_badge)
        self.tooltip.text = (
            f"{self.name} — {self.rarity}\n"
            f"Lv. {level} • {state} • {role}\n"
            f"{effect_text}\n"
            f"Portrait: {source_note}\n\n"
            "Click portrait: toggle ownership\n"
            "Click level: edit level\n"
            "Click role badge: choose current slot"
        )
        self.redraw()

    def redraw(self):
        # Refreshing selection/ownership redraws every tile.  Deleting all
        # Canvas items while this tile owns an inline Entry removes the Canvas
        # window but leaves the Entry reference alive, which is what made all
        # later level chips appear permanently unclickable.  Let the editor
        # finish first; _finish_level_editor() performs the final redraw.
        if self._level_entry is not None and self._level_entry.winfo_exists():
            return
        c = self.canvas
        c.delete("all")
        rarity_color = RARITY_TILE_COLORS[self.rarity]
        selection_color = COLORS["accent"] if self.selected else COLORS["panel"]

        c.create_rectangle(1, 1, self.WIDTH - 1, self.HEIGHT - 1, outline=selection_color, width=2)
        c.create_rectangle(
            4,
            4,
            self.WIDTH - 4,
            self.HEIGHT - 4,
            outline=rarity_color,
            width=3,
            fill=COLORS["surface"],
        )
        c.create_rectangle(7, 7, 77, 77, fill="#111821", outline="")

        image = self.color_image if self.owned else self.gray_image
        if image is not None:
            c.create_image(42, 42, image=image, anchor="center")
        else:
            c.create_text(
                42,
                38,
                text=self._initials(self.name),
                fill="#e8eef5" if self.owned else "#738091",
                font=("TkDefaultFont", 15, "bold"),
            )
            c.create_text(42, 56, text="portrait", fill=COLORS["muted"], font=("TkDefaultFont", 6))

        chip_fill = "#17202d" if self.owned else "#202733"
        c.create_rectangle(35, 6, 79, 21, fill=chip_fill, outline=rarity_color, width=1)
        c.create_text(
            77,
            13,
            text=f"Lv. {self.level}",
            anchor="e",
            fill="#ffffff",
            font=("TkDefaultFont", 7, "bold"),
        )

        band_fill = rarity_color if self.owned else "#2a3340"
        band_text = "#101621" if self.owned and self.rarity in {"Common", "Rare", "Unique"} else "#ffffff"
        c.create_rectangle(5, 80, self.WIDTH - 5, self.HEIGHT - 5, fill=band_fill, outline="")
        c.create_text(8, 92, text=self.rarity, anchor="w", fill=band_text, font=("TkDefaultFont", 7, "bold"))

        role_active = self.role_badge != "—"
        role_fill = COLORS["accent"] if role_active else "#111821"
        role_text = "#0e171b" if role_active else COLORS["muted"]
        c.create_oval(
            64,
            82,
            84,
            102,
            fill=role_fill,
            outline="#ffffff" if role_active else COLORS["border"],
            width=1,
        )
        c.create_text(74, 92, text=self.role_badge, fill=role_text, font=("TkDefaultFont", 7, "bold"))

        if not self.owned:
            c.create_text(9, 73, text="OFF", anchor="w", fill="#d7dee7", font=("TkDefaultFont", 6, "bold"))

    def _handle_click(self, event):
        level_click = 31 <= event.x <= 88 and 2 <= event.y <= 28

        # Commit the previous tile before any selection callback redraws the
        # roster.  Previously, clicking tile B caused on_select() to redraw
        # tile A first, orphaning A's Entry.  A's delayed FocusOut then redrew
        # tile B and orphaned its new Entry as well.
        active = CompanionTile._active_level_tile
        if active is not None and active is not self:
            if not active._finish_level_editor(True):
                return

        if level_click:
            self.on_select(self.key)
            self.start_level_editor()
        elif 59 <= event.x <= 88 and 78 <= event.y <= 105:
            if self._level_entry is not None and not self._finish_level_editor(True):
                return
            self.on_select(self.key)
            menu_x = self.canvas.winfo_rootx() + self.WIDTH + 4
            menu_y = self.canvas.winfo_rooty() + max(0, min(event.y - 20, self.HEIGHT - 52))
            self.on_role(self.key, self.canvas, menu_x, menu_y)
        else:
            if self._level_entry is not None and not self._finish_level_editor(True):
                return
            self.on_select(self.key)
            self.on_toggle(self.key)

    def start_level_editor(self):
        if self._level_entry is not None:
            if self._level_entry.winfo_exists():
                self._level_entry.focus_force()
                self._level_entry.selection_range(0, "end")
            return

        active = CompanionTile._active_level_tile
        if active is not None and active is not self:
            if not active._finish_level_editor(True):
                return
        entry = tk.Entry(
            self.canvas,
            justify="center",
            relief="ridge",
            borderwidth=1,
            background="#f7fafc",
            foreground="#111821",
            font=("TkDefaultFont", 8, "bold"),
        )
        entry.insert(0, str(self.level))
        window = self.canvas.create_window(57, 14, window=entry, width=43, height=20)
        self._level_entry = entry
        self._level_window = window
        CompanionTile._active_level_tile = self
        entry.bind("<Return>", lambda _e: self._finish_level_editor(True))
        entry.bind("<KP_Enter>", lambda _e: self._finish_level_editor(True))
        entry.bind("<Escape>", lambda _e: self._finish_level_editor(False))

        # The editor is created from the Canvas' ButtonPress handler.  On some
        # Linux/Tk builds, the remainder of that same mouse click can reclaim
        # focus immediately after focus_set(), which used to fire FocusOut and
        # close the editor almost instantly.  Focus it after the click has fully
        # completed, then arm click-away committing only after focus is stable.
        def activate_editor():
            self._level_focus_after = None
            if self._level_entry is not entry or not entry.winfo_exists():
                return
            entry.focus_force()
            entry.selection_range(0, "end")
            self.after(90, lambda: self._arm_level_focusout(entry))

        self._level_focus_after = self.after_idle(activate_editor)

    def _arm_level_focusout(self, entry: tk.Entry):
        if self._level_entry is not entry or not entry.winfo_exists():
            return
        entry.bind("<FocusOut>", lambda _e, target=entry: self._defer_level_focusout(target))

    def _defer_level_focusout(self, entry: tk.Entry):
        # Focus can briefly bounce during Canvas/window remapping.  Check again
        # on the idle queue before deciding that the user really clicked away.
        def commit_if_still_unfocused():
            if self._level_entry is not entry or not entry.winfo_exists():
                return
            if entry.focus_get() is entry:
                return
            self._finish_level_editor(True)

        self.after_idle(commit_if_still_unfocused)

    def _finish_level_editor(self, commit: bool) -> bool:
        entry = self._level_entry
        if entry is None:
            if CompanionTile._active_level_tile is self:
                CompanionTile._active_level_tile = None
            return True
        value = entry.get().strip()
        if commit and not self.on_level(self.key, value):
            entry.focus_force()
            entry.selection_range(0, "end")
            return False

        if self._level_focus_after is not None:
            try:
                self.after_cancel(self._level_focus_after)
            except tk.TclError:
                pass
            self._level_focus_after = None

        # Clear references before destroying the Entry so a destruction-triggered
        # FocusOut cannot recursively commit the editor a second time.
        window = self._level_window
        self._level_entry = None
        self._level_window = None
        if CompanionTile._active_level_tile is self:
            CompanionTile._active_level_tile = None
        if window is not None:
            self.canvas.delete(window)
        if entry.winfo_exists():
            entry.destroy()
        self.redraw()
        return True


class RoundedTranslucentFrame(tk.Frame):
    """Rounded panel that composites the current app background beneath a soft tint."""

    def __init__(self, parent, app: "OptimizerApp", *, radius: int = 18, alpha: int = 236, **kwargs):
        super().__init__(
            parent,
            background=COLORS["bg"],
            borderwidth=0,
            highlightthickness=0,
            padx=28,
            pady=22,
            **kwargs,
        )
        self.app = app
        self.radius = radius
        self.alpha = alpha
        self._photo = None
        self._render_after: Optional[str] = None
        self._background_label = tk.Label(self, borderwidth=0, highlightthickness=0, background=COLORS["bg"])
        self._background_label.place(x=0, y=0, relwidth=1, relheight=1)
        # Created before the controls, so it naturally remains behind them.
        # Calling lower() can place it beneath the parent surface on some Linux/Tk builds.
        self.bind("<Configure>", self._schedule_render, add="+")
        self.app._translucent_panels.append(self)

    def _schedule_render(self, _event=None):
        if self._render_after is not None:
            try:
                self.after_cancel(self._render_after)
            except tk.TclError:
                pass
        self._render_after = self.after(35, self.render_background)

    def render_background(self):
        self._render_after = None
        if Image is None or ImageDraw is None or ImageTk is None:
            return
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 4 or height < 4:
            return
        try:
            root_x = self.winfo_rootx() - self.app.winfo_rootx()
            root_y = self.winfo_rooty() - self.app.winfo_rooty()
            bg = self.app._scaled_background_pil
            source = Image.new("RGBA", (width, height), (245, 249, 253, 255))
            if bg is not None:
                src_left = max(0, root_x)
                src_top = max(0, root_y)
                src_right = min(bg.width, root_x + width)
                src_bottom = min(bg.height, root_y + height)
                if src_right > src_left and src_bottom > src_top:
                    crop = bg.crop((src_left, src_top, src_right, src_bottom))
                    dst_x = max(0, -root_x)
                    dst_y = max(0, -root_y)
                    source.alpha_composite(crop, (dst_x, dst_y))
                    # Make the panel itself notably more opaque than the background
                    # around it while preserving a faint MapleStory hint beneath.
                    source = Image.blend(source, Image.new("RGBA", (width, height), (252, 253, 255, 255)), 0.84)

            # First create the actual rounded panel silhouette. Previous versions
            # only rounded the tint/border while leaving the image rectangular.
            shape_mask = Image.new("L", (width, height), 0)
            shape_draw = ImageDraw.Draw(shape_mask)
            shape_draw.rounded_rectangle(
                (1, 1, width - 2, height - 2), radius=self.radius, fill=255
            )
            canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            canvas.paste(source, (0, 0), shape_mask)

            # Add a stronger white veil so the panels read as solid UI panels
            # rather than fully transparent windows.
            veil = Image.new("RGBA", (width, height), (252, 254, 255, 0))
            veil_alpha = shape_mask.point(lambda value: int(value * self.alpha / 255))
            veil.putalpha(veil_alpha)
            canvas = Image.alpha_composite(canvas, veil)
            draw = ImageDraw.Draw(canvas)
            draw.rounded_rectangle(
                (1, 1, width - 2, height - 2),
                radius=self.radius,
                outline=(126, 151, 174, 238),
                width=2,
            )
            photo = ImageTk.PhotoImage(canvas)
            self._photo = photo
            self._background_label.configure(image=photo, background=COLORS["bg"])
        except (tk.TclError, ValueError):
            return

    def destroy(self):
        try:
            self.app._translucent_panels.remove(self)
        except ValueError:
            pass
        super().destroy()


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, *args, on_scroll: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.on_scroll = on_scroll
        self.canvas = tk.Canvas(
            self,
            background=COLORS["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._yview)
        self.inner = ttk.Frame(self.canvas, style="App.TFrame")
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-4>", lambda event: self._on_linux_wheel(event, -1), add="+")
        self.canvas.bind_all("<Button-5>", lambda event: self._on_linux_wheel(event, 1), add="+")

    def _notify_scroll(self):
        if self.on_scroll is not None:
            self.after_idle(self.on_scroll)

    def _yview(self, *args):
        self.canvas.yview(*args)
        self._notify_scroll()

    def _scroll_units(self, amount: int):
        self.canvas.yview_scroll(amount, "units")
        self._notify_scroll()

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        self._notify_scroll()

    def _pointer_is_inside(self, event) -> bool:
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
            while widget is not None:
                if widget is self:
                    return True
                widget = widget.master
        except Exception:
            return False
        return False

    def _on_linux_wheel(self, event, amount: int):
        if self._pointer_is_inside(event):
            self._scroll_units(amount)

    def _on_mousewheel(self, event):
        if event.delta and self._pointer_is_inside(event):
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
            self._notify_scroll()


class OCRReviewDialog(tk.Toplevel):
    """Modal review step before screenshot values modify the active profile."""

    STATUS_TEXT = {
        "screenshot": "Read from screenshot",
        "inferred_zero": "Inferred zero",
        "uncovered": "Not covered — check manually",
        "conflict": "Conflict — review required",
        "manual": "Manual",
    }
    STATUS_STYLE = {
        "screenshot": "Imported.App.TLabel",
        "inferred_zero": "Zero.App.TLabel",
        "uncovered": "Uncovered.App.TLabel",
        "conflict": "Conflict.App.TLabel",
        "manual": "Muted.TLabel",
    }

    def __init__(
        self,
        parent,
        import_result: OCRImportResult,
        current_values: Dict[str, str],
    ):
        super().__init__(parent)
        self.title("Review imported Stat Info")
        self.geometry("980x760")
        self.minsize(780, 620)
        self.configure(background=COLORS["bg"])
        self.transient(parent)
        self.grab_set()
        self.import_result = import_result
        self.current_values = current_values
        self.value_vars: Dict[str, tk.StringVar] = {}
        self.applied_values: Optional[Dict[str, float]] = None
        self.applied_statuses: Optional[Dict[str, str]] = None

        outer = ttk.Frame(self, style="App.TFrame", padding=16)
        outer.pack(fill="both", expand=True)
        coverage_text = (
            f"Read {import_result.screenshot_count} screenshot(s). "
            + (
                "Top-to-bottom coverage was detected; absent zero-valued rows can be inferred."
                if import_result.complete_coverage
                else "Full top-to-bottom coverage was not confirmed; absent rows remain marked for manual checking."
            )
        )
        ttk.Label(outer, text="Review screenshot import", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text=coverage_text,
            style="Muted.TLabel",
            wraplength=900,
        ).pack(anchor="w", pady=(4, 12))

        legend = ttk.Frame(outer, style="App.TFrame")
        legend.pack(fill="x", pady=(0, 10))
        for status in ("screenshot", "inferred_zero", "uncovered", "conflict"):
            ttk.Label(
                legend,
                text=self.STATUS_TEXT[status],
                style=self.STATUS_STYLE[status],
            ).pack(side="left", padx=(0, 18))

        scroll = ScrollableFrame(outer)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner
        for column, weight in enumerate((2, 1, 1, 2, 4)):
            body.columnconfigure(column, weight=weight)
        headings = ("Optimizer field", "Current", "Reviewed value", "Import status", "Notes")
        for column, heading in enumerate(headings):
            ttk.Label(body, text=heading, style="Value.TLabel").grid(
                row=0, column=column, sticky="w", padx=6, pady=(2, 8)
            )

        row_number = 1
        field_order = list(OCR_IMPORT_FIELDS) + list(OCR_MANUAL_FIELDS)
        for key in field_order:
            status = import_result.statuses.get(key, "uncovered")
            current_text = current_values.get(key, "0")
            if key in import_result.values:
                proposed = import_result.values[key]
                initial_text = entry_number_text(proposed)
            else:
                initial_text = current_text
            variable = tk.StringVar(value=initial_text)
            self.value_vars[key] = variable
            ttk.Label(
                body,
                text=OCR_FIELD_DISPLAY.get(key, key),
                style=self.STATUS_STYLE.get(status, "Panel.TLabel"),
            ).grid(row=row_number, column=0, sticky="w", padx=6, pady=4)
            entry_style = {
                "screenshot": "Imported.TEntry",
                "inferred_zero": "Zero.TEntry",
                "uncovered": "Uncovered.TEntry",
                "conflict": "Conflict.TEntry",
            }.get(status, "TEntry")
            ttk.Label(
                body,
                text=current_text,
                style="PanelMuted.TLabel",
            ).grid(row=row_number, column=1, sticky="w", padx=6, pady=4)
            ttk.Entry(body, textvariable=variable, style=entry_style).grid(
                row=row_number, column=2, sticky="ew", padx=6, pady=4
            )
            ttk.Label(
                body,
                text=self.STATUS_TEXT.get(status, status),
                style=self.STATUS_STYLE.get(status, "PanelMuted.TLabel"),
            ).grid(row=row_number, column=3, sticky="w", padx=6, pady=4)
            ttk.Label(
                body,
                text=import_result.notes.get(key, ""),
                style="PanelMuted.TLabel",
                wraplength=360,
            ).grid(row=row_number, column=4, sticky="w", padx=6, pady=4)
            row_number += 1

        ttk.Label(
            outer,
            text=(
                "Green and blue values will be imported. Amber values keep their current number unless you edit them here, "
                "and remain highlighted in the main form until checked. Red conflicts should be corrected before optimizing."
            ),
            style="Muted.TLabel",
            wraplength=920,
        ).pack(anchor="w", pady=(10, 8))
        buttons = ttk.Frame(outer, style="App.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(
            buttons,
            text="Apply reviewed values",
            style="Accent.TButton",
            command=self._apply,
        ).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _apply(self):
        values: Dict[str, float] = {}
        statuses = dict(self.import_result.statuses)
        try:
            for key, variable in self.value_vars.items():
                entered = parse_number(variable.get(), field_name=OCR_FIELD_DISPLAY.get(key, key))
                current = parse_number(self.current_values.get(key, "0"), field_name=key)
                original = self.import_result.values.get(key)
                status = statuses.get(key, "uncovered")
                if status == "uncovered":
                    if not math.isclose(entered, current, rel_tol=1e-12, abs_tol=1e-12):
                        values[key] = entered
                        statuses[key] = "manual"
                else:
                    values[key] = entered
                    if original is None or not math.isclose(
                        entered, original, rel_tol=1e-12, abs_tol=1e-12
                    ):
                        statuses[key] = "manual"
        except ValueError as exc:
            messagebox.showerror("Invalid reviewed value", str(exc), parent=self)
            return
        self.applied_values = values
        self.applied_statuses = statuses
        self.destroy()

# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class OptimizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        apply_window_icon(self)
        install_runtime_exception_logging(self)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        initial_width = min(1600, max(1180, screen_width - 80))
        initial_height = min(920, max(740, screen_height - 120))
        self.geometry(f"{initial_width}x{initial_height}")
        self.minsize(1120, 720)
        self.configure(background=COLORS["bg"])

        self.profile_path: Optional[Path] = None
        self.companions: List[Companion] = []
        self.results: List[OptimizationResult] = []
        self.last_optimized_profile: Optional[Profile] = None
        self.roster_vars: Dict[str, Dict[str, object]] = {}
        self.roster_widgets: Dict[str, Dict[str, tk.Widget]] = {}
        self.roster_tiles: Dict[str, CompanionTile] = {}
        self.roster_image_cache: Dict[str, Optional[tk.PhotoImage]] = {}
        self.roster_asset_manifest: Dict[str, Dict[str, object]] = {}
        self.selected_roster_key: Optional[str] = None
        self.extra_companions: List[Companion] = []
        self.stat_entries: Dict[str, ttk.Entry] = {}
        self.stat_labels: Dict[str, ttk.Label] = {}
        self.stat_sources: Dict[str, str] = {}
        self._applying_ocr = False
        self._roster_syncing = False
        self._loading_profile = True
        self._autosave_after_id: Optional[str] = None
        self.autosave_path = default_autosave_path()
        self.preferences_path = default_preferences_path()
        self.ui_preferences = self._load_ui_preferences()
        self.worker: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.worker_queue: queue.Queue = queue.Queue()
        self._background_asset_path: Optional[Path] = None
        self._background_original = None
        self._scaled_background_pil = None
        self._background_photo = None
        self._background_label = None
        self._background_resize_after: Optional[str] = None
        self._last_background_size: Tuple[int, int] = (0, 0)
        self._translucent_panels: List[RoundedTranslucentFrame] = []
        self._background_matched_frames: List[BackgroundMatchedFrame] = []
        self._ui_gradient_cache: Dict[tuple, tk.PhotoImage] = {}
        self._character_bg_last_size: Tuple[int, int] = (0, 0)
        self._character_content_bg_photo = None
        self._character_bg_after: Optional[str] = None
        self._character_resize_after: Optional[str] = None
        self._character_last_built_root_size: Tuple[int, int] = (0, 0)
        self._character_pending_root_size: Tuple[int, int] = (0, 0)
        self._character_rebuild_in_progress = False
        self._character_rebuild_pending = False
        self._character_lower_remap_after: Optional[str] = None
        self._character_lower_remap_second_after: Optional[str] = None

        self._load_theme_assets()
        self._configure_styles()
        self._create_variables()
        self._build_ui()
        self.bind("<Configure>", self._on_root_resize_for_character_tab, add="+")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed_for_character_tab, add="+")
        self.after(180, self._initialize_character_resize_tracking)
        self._bind_shortcuts()
        self._update_content_fields()
        self._install_autosave_traces()
        restored = self._restore_autosave()
        self._loading_profile = False
        if not restored:
            self._refresh_roster_count()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----- resize recovery --------------------------------------------------

    def _initialize_character_resize_tracking(self):
        self._character_last_built_root_size = (
            max(1, self.winfo_width()),
            max(1, self.winfo_height()),
        )

    def _on_root_resize_for_character_tab(self, event):
        # Tk on KDE/Wayland can corrupt image-backed child windows when a live
        # canvas hierarchy is resized. Do not repaint that hierarchy in place.
        # Once the window geometry settles, rebuild only the Character tab from
        # its existing variables; the resulting render is identical to startup.
        if event.widget is not self or self._character_rebuild_in_progress:
            return
        size = (max(1, int(event.width)), max(1, int(event.height)))
        if size == self._character_pending_root_size:
            return
        self._character_pending_root_size = size
        if self._character_resize_after is not None:
            try:
                self.after_cancel(self._character_resize_after)
            except tk.TclError:
                pass
        self._character_resize_after = self.after(420, self._finish_character_resize)

    def _on_notebook_tab_changed_for_character_tab(self, _event=None):
        if self._character_rebuild_pending and self.notebook.select() == str(self.character_tab):
            self._character_rebuild_pending = False
            self.after_idle(self._rebuild_character_tab_after_resize)

    def _finish_character_resize(self):
        self._character_resize_after = None
        current = (max(1, self.winfo_width()), max(1, self.winfo_height()))
        # A Configure event may have arrived just before the timer fired.
        if current != self._character_pending_root_size:
            self._character_pending_root_size = current
            self._character_resize_after = self.after(260, self._finish_character_resize)
            return
        previous = self._character_last_built_root_size
        if previous != (0, 0) and abs(current[0] - previous[0]) < 3 and abs(current[1] - previous[1]) < 3:
            return
        if self.notebook.select() != str(self.character_tab):
            self._character_rebuild_pending = True
            return
        self._rebuild_character_tab_after_resize()

    def _cancel_character_canvas_callbacks(self):
        for attr in (
            "_character_canvas_layout_after",
            "_character_canvas_bg_after",
            "_character_lower_remap_after",
            "_character_lower_remap_second_after",
        ):
            after_id = getattr(self, attr, None)
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    def _schedule_lower_character_panel_remap(self):
        """Remap the two lower canvas windows after fullscreen geometry settles.

        On some KDE/Tk combinations, canvas child windows that are initially below
        the visible viewport keep stale backing pixels after maximize/restore. The
        upper panels repaint normally because they are mapped immediately. Detaching
        and reattaching only Advanced Multipliers and Optimization Target gives those
        widgets a fresh native window without changing their appearance or data.
        """
        if self._character_lower_remap_after is not None:
            try:
                self.after_cancel(self._character_lower_remap_after)
            except tk.TclError:
                pass
        if self._character_lower_remap_second_after is not None:
            try:
                self.after_cancel(self._character_lower_remap_second_after)
            except tk.TclError:
                pass
        self._character_lower_remap_after = self.after(190, self._remap_lower_character_panels)
        self._character_lower_remap_second_after = self.after(520, self._remap_lower_character_panels)

    def _remap_lower_character_panels(self):
        if not self.character_tab.winfo_exists():
            return
        canvas = getattr(self, "_character_canvas", None)
        items = getattr(self, "_character_canvas_items", {})
        widgets = getattr(self, "_character_canvas_widgets", {})
        if canvas is None or not canvas.winfo_exists():
            return
        targets = []
        for name in ("right_bottom", "target"):
            item = items.get(name)
            widget = widgets.get(name)
            if item is not None and widget is not None and widget.winfo_exists():
                targets.append((item, widget))
        if not targets:
            return
        try:
            # Detach the native child windows from the canvas. This is stronger
            # than hide/show and forces Tk to allocate fresh backing surfaces.
            for item, _widget in targets:
                canvas.itemconfigure(item, window="")
            canvas.update_idletasks()
            for item, widget in targets:
                canvas.itemconfigure(item, window=widget)
            self._layout_character_canvas()
            canvas.tag_lower(self._character_canvas_bg_item)
            for item, widget in targets:
                canvas.tag_raise(item)
                widget.update_idletasks()
                widget.event_generate("<Expose>", when="tail")
                for child in widget.winfo_children():
                    try:
                        child.event_generate("<Expose>", when="tail")
                    except tk.TclError:
                        pass
            canvas.update_idletasks()
        except tk.TclError:
            return

    def _rebuild_character_tab_after_resize(self):
        if self._character_rebuild_in_progress or not self.character_tab.winfo_exists():
            return
        self._character_rebuild_in_progress = True
        old_view = 0.0
        old_canvas = getattr(self, "_character_canvas", None)
        if old_canvas is not None:
            try:
                old_view = float(old_canvas.yview()[0])
            except (tk.TclError, IndexError, TypeError, ValueError):
                old_view = 0.0
        try:
            self._cancel_character_canvas_callbacks()
            for child in tuple(self.character_tab.winfo_children()):
                child.destroy()
            self.stat_entries.clear()
            self.stat_labels.clear()
            self._build_character_tab()
            self._character_last_built_root_size = (
                max(1, self.winfo_width()),
                max(1, self.winfo_height()),
            )
            self._character_pending_root_size = self._character_last_built_root_size
            self._refresh_stat_source_styles()

            def restore_view():
                canvas = getattr(self, "_character_canvas", None)
                if canvas is None or not canvas.winfo_exists():
                    return
                try:
                    self._layout_character_canvas()
                    canvas.yview_moveto(old_view)
                    canvas.update_idletasks()
                    self._schedule_lower_character_panel_remap()
                except tk.TclError:
                    pass

            self.after(90, restore_view)
        finally:
            self._character_rebuild_in_progress = False

    # ----- style and layout -------------------------------------------------

    def _load_theme_assets(self):
        asset_path = ui_asset_directory() / "maple_airship_bg.png"
        self._background_asset_path = asset_path if asset_path.exists() else None
        self._background_original = None
        if self._background_asset_path is not None and Image is not None:
            try:
                self._background_original = Image.open(self._background_asset_path).convert("RGBA")
            except Exception:
                self._background_original = None

    def _create_background_layer(self):
        if self._background_original is None or ImageTk is None:
            return
        label = tk.Label(
            self,
            background=COLORS["bg"],
            borderwidth=0,
            highlightthickness=0,
        )
        label.place(x=0, y=0, relwidth=1, relheight=1)
        label.lower()
        self._background_label = label
        self.bind("<Configure>", self._schedule_background_refresh, add="+")
        self.after(25, self._refresh_background_image)

    def _schedule_background_refresh(self, event=None):
        if event is not None and event.widget is not self:
            return
        size = (max(1, self.winfo_width()), max(1, self.winfo_height()))
        if size == self._last_background_size:
            return
        if self._background_resize_after is not None:
            try:
                self.after_cancel(self._background_resize_after)
            except tk.TclError:
                pass
        self._background_resize_after = self.after(280, self._refresh_background_image)

    def _refresh_background_image(self, _event=None):
        self._background_resize_after = None
        if self._background_original is None or self._background_label is None or ImageTk is None:
            return
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        if (width, height) == self._last_background_size and self._scaled_background_pil is not None:
            self._refresh_translucent_panels()
            return
        try:
            source = self._background_original
            scale = max(width / source.width, height / source.height)
            resized = source.resize(
                (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
                Image.LANCZOS,
            )
            left = max(0, (resized.width - width) // 2)
            top = max(0, (resized.height - height) // 2)
            fitted = resized.crop((left, top, left + width, top + height))
            self._scaled_background_pil = fitted
            photo = ImageTk.PhotoImage(fitted)
            self._background_photo = photo
            self._background_label.configure(image=photo)
            self._background_label.lower()
            self._last_background_size = (width, height)
            self._refresh_translucent_panels()
        except (tk.TclError, ValueError):
            return

    def _schedule_character_content_background(self, _event=None):
        if getattr(self, "_character_bg_after", None) is not None:
            try:
                self.after_cancel(self._character_bg_after)
            except tk.TclError:
                pass
        self._character_bg_after = self.after(260, self._refresh_character_content_background)

    def _refresh_character_content_background(self):
        self._character_bg_after = None
        label = getattr(self, "_character_content_bg_label", None)
        if label is None or self._background_original is None or Image is None or ImageTk is None:
            return
        parent = label.master
        width = max(1, parent.winfo_width())
        height = max(1, parent.winfo_height())
        if width < 10 or height < 10:
            return
        if (width, height) == self._character_bg_last_size and self._character_content_bg_photo is not None:
            label.lower()
            return
        try:
            source = self._background_original
            scale = max(width / source.width, height / source.height)
            resized = source.resize((max(1, round(source.width * scale)), max(1, round(source.height * scale))), Image.LANCZOS)
            left = max(0, (resized.width - width) // 2)
            top = max(0, (resized.height - height) // 2)
            fitted = resized.crop((left, top, left + width, top + height))
            # Keep the around-panel background clearly visible but gentle.
            faded = Image.blend(fitted, Image.new("RGBA", fitted.size, (248, 252, 255, 255)), 0.58)
            photo = ImageTk.PhotoImage(faded)
            self._character_content_bg_photo = photo
            label.configure(image=photo)
            label.lower()
            self._character_bg_last_size = (width, height)
            for child in parent.winfo_children():
                if child is not label:
                    child.lift()
            for frame in tuple(self._background_matched_frames):
                if frame.winfo_exists():
                    frame._schedule_render()
            parent.update_idletasks()
        except Exception:
            return

    def _gradient_photo(self, width: int, height: int, top_color, bottom_color, *, radius: int = 0, border_color=None, border_width: int = 1, matte_color=None):
        width = max(1, int(width))
        height = max(1, int(height))
        key = (width, height, tuple(top_color), tuple(bottom_color), radius, tuple(border_color) if border_color else None, border_width, tuple(matte_color) if matte_color else None)
        cached = self._ui_gradient_cache.get(key)
        if cached is not None:
            return cached
        if Image is None or ImageDraw is None or ImageTk is None:
            raise RuntimeError("Gradient assets require Pillow")
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for y in range(height):
            ratio = y / max(1, height - 1)
            color = tuple(int(top_color[i] + (bottom_color[i] - top_color[i]) * ratio) for i in range(4))
            draw.line((0, y, width, y), fill=color)
        if radius > 0:
            mask = Image.new("L", (width, height), 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
            if matte_color is not None:
                flattened = Image.new("RGBA", (width, height), matte_color)
                flattened.paste(img, (0, 0), mask)
                img = flattened
            else:
                img.putalpha(mask)
        if border_color is not None and border_width > 0:
            draw = ImageDraw.Draw(img)
            if radius > 0:
                draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, outline=border_color, width=border_width)
            else:
                draw.rectangle((0, 0, width - 1, height - 1), outline=border_color, width=border_width)
        photo = ImageTk.PhotoImage(img)
        self._ui_gradient_cache[key] = photo
        return photo

    def _make_gradient_label(self, parent, text: str, *, width: int, height: int, top_color, bottom_color, fg: str, font, radius: int = 0, border_color=None, padx: int = 8, pady: int = 0, anchor: str = "w", bg: Optional[str] = None):
        label_bg = bg or parent.cget("background")
        matte = None
        if isinstance(label_bg, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", label_bg):
            matte = tuple(int(label_bg[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
        photo = self._gradient_photo(width, height, top_color, bottom_color, radius=radius, border_color=border_color, matte_color=matte)
        lbl = tk.Label(
            parent,
            image=photo,
            text=text,
            compound="center",
            foreground=fg,
            background=label_bg,
            borderwidth=0,
            highlightthickness=0,
            font=font,
            anchor=anchor,
            padx=padx,
            pady=pady,
        )
        lbl.image = photo
        return lbl

    def _build_autoassign_strip(self, parent):
        strip = tk.Canvas(parent, width=320, height=42, highlightthickness=0, borderwidth=0, background=COLORS["bg"])
        bg = self._gradient_photo(320, 42, (179, 221, 255, 255), (114, 172, 231, 255), radius=10, border_color=(122, 162, 204, 255))
        pill = self._gradient_photo(96, 28, (212, 239, 84, 255), (155, 202, 32, 255), radius=8, border_color=(136, 168, 32, 255))
        strip.create_image(0, 0, image=bg, anchor="nw", tags=("strip",))
        strip.create_image(10, 7, image=pill, anchor="nw", tags=("button",))
        strip.create_text(58, 21, text="AUTO-ASSIGN", fill="#1b3151", font=("TkDefaultFont", 9, "bold"), tags=("button",))
        strip.create_text(118, 15, text="Import Stat Screenshots", anchor="w", fill="#1b4870", font=("TkDefaultFont", 9, "bold"), tags=("strip",))
        strip.create_text(118, 28, text="Read displayed stats from overlapping captures.", anchor="w", fill="#4e6b86", font=("TkDefaultFont", 8), tags=("strip",))
        strip.image = bg
        strip.pill_image = pill
        strip.configure(cursor="hand2")
        for tag in ("strip", "button"):
            strip.tag_bind(tag, "<Button-1>", lambda _e: self.import_stat_screenshots())
        ToolTip(strip, "Select the overlapping Stat Info screenshots. Values are read locally with Tesseract and shown for review before anything is changed. Shortcut: Ctrl+I.")
        return strip

    def _refresh_translucent_panels(self):
        self._schedule_character_content_background()
        for panel in tuple(self._translucent_panels):
            if panel.winfo_exists():
                panel._schedule_render()
        for frame in tuple(self._background_matched_frames):
            if frame.winfo_exists():
                frame._schedule_render()

    def _make_compact_maple_section(self, parent, title: str):
        """Smaller Maple-style panel used only by companion class rows."""
        outer = tk.Frame(parent, background="#050505", borderwidth=0, highlightthickness=0)
        top_bar = tk.Frame(outer, background="#050505", height=23, borderwidth=0, highlightthickness=0)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)
        tk.Label(
            top_bar,
            text=title,
            foreground="#f1d54b",
            background="#050505",
            borderwidth=0,
            highlightthickness=0,
            font=("TkDefaultFont", 8, "bold"),
        ).pack(expand=True)
        panel = tk.Frame(outer, background="#ffffff", borderwidth=0, highlightthickness=0, padx=5, pady=5)
        panel.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        return outer, panel

    def _make_maple_section(self, parent, title: str):
        outer = tk.Frame(parent, background="#050505", borderwidth=0, highlightthickness=0)
        top_bar = tk.Frame(outer, background="#050505", height=34, borderwidth=0, highlightthickness=0)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)
        title_label = tk.Label(
            top_bar,
            text=title,
            foreground="#f1d54b",
            background="#050505",
            borderwidth=0,
            highlightthickness=0,
            font=("TkDefaultFont", 10, "bold"),
        )
        title_label.pack(expand=True)
        panel = tk.Frame(outer, background="#ffffff", borderwidth=0, highlightthickness=0, padx=14, pady=12)
        panel.pack(fill="both", expand=True, padx=2, pady=(0, 2))
        return outer, panel

    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Header.TFrame", background=COLORS["panel"])
        style.configure("Status.TFrame", background=COLORS["panel"])

        style.configure(
            "Title.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("TkDefaultFont", 18, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            font=("TkDefaultFont", 10),
        )
        style.configure(
            "App.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["text"],
        )
        style.configure(
            "WhitePanel.TLabel",
            background="#ffffff",
            foreground=COLORS["text"],
        )
        style.configure(
            "DarkHeader.TLabel",
            background="#050505",
            foreground="#d8e4ee",
        )
        style.configure(
            "Panel.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["text"],
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "PanelMuted.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "Warning.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["warning"],
        )
        style.configure(
            "Value.TLabel",
            background=COLORS["panel"],
            foreground="#3f8bb7",
            font=("TkDefaultFont", 10, "bold"),
        )
        rarity_colors = {
            "Common": COLORS["muted"],
            "Rare": "#7bb8ff",
            "Epic": "#c89cff",
            "Unique": "#f3b66f",
            "Legendary": "#67d8b0",
        }
        for rarity, color in rarity_colors.items():
            style.configure(
                f"{rarity}.Roster.TLabel",
                background=COLORS["panel"],
                foreground=color,
                font=("TkDefaultFont", 9, "bold"),
            )

        style.configure(
            "TNotebook",
            background=COLORS["bg"],
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            background=COLORS["panel_alt"],
            foreground=COLORS["muted"],
            padding=(18, 10),
            font=("TkDefaultFont", 10, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["surface"]), ("active", COLORS["surface"])],
            foreground=[("selected", COLORS["accent"]), ("active", COLORS["text"])],
        )

        style.configure(
            "TLabelframe",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            relief="ridge",
            borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label",
            background=COLORS["panel"],
            foreground="#3f8bb7",
            font=("TkDefaultFont", 10, "bold"),
        )

        style.configure(
            "TEntry",
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            insertcolor=COLORS["text"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=7,
        )
        style.map("TEntry", bordercolor=[("focus", COLORS["accent"])])
        import_entry_styles = {
            "Imported.TEntry": ("#ecfff1", "#5de0a6"),
            "Zero.TEntry": ("#eef7ff", "#6bc3ff"),
            "Uncovered.TEntry": ("#fff6e8", COLORS["warning"]),
            "Conflict.TEntry": ("#fff0f2", COLORS["danger"]),
        }
        for style_name, (background, border) in import_entry_styles.items():
            style.configure(
                style_name,
                fieldbackground=background,
                foreground=COLORS["text"],
                insertcolor=COLORS["text"],
                bordercolor=border,
                lightcolor=border,
                darkcolor=border,
                padding=6,
            )
            style.map(style_name, bordercolor=[("focus", COLORS["accent"])])
        import_label_styles = {
            "Imported.Panel.TLabel": "#65dfaa",
            "Zero.Panel.TLabel": "#73c5ff",
            "Uncovered.Panel.TLabel": COLORS["warning"],
            "Conflict.Panel.TLabel": COLORS["danger"],
        }
        for style_name, foreground in import_label_styles.items():
            style.configure(
                style_name,
                background=COLORS["panel"],
                foreground=foreground,
            )
        style.configure(
            "Imported.App.TLabel", background=COLORS["bg"], foreground="#65dfaa"
        )
        style.configure(
            "Zero.App.TLabel", background=COLORS["bg"], foreground="#73c5ff"
        )
        style.configure(
            "Uncovered.App.TLabel", background=COLORS["bg"], foreground=COLORS["warning"]
        )
        style.configure(
            "Conflict.App.TLabel", background=COLORS["bg"], foreground=COLORS["danger"]
        )
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["surface"],
            background=COLORS["surface"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["text"],
            bordercolor=COLORS["border"],
            padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["surface"])],
            foreground=[("readonly", COLORS["text"])],
            bordercolor=[("focus", COLORS["accent"])],
        )
        style.configure(
            "TSpinbox",
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["text"],
            bordercolor=COLORS["border"],
            padding=5,
        )

        style.configure(
            "TButton",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            padding=(12, 7),
            font=("TkDefaultFont", 9, "bold"),
        )
        style.map(
            "TButton",
            background=[("active", "#f6fbff"), ("pressed", COLORS["selection"])],
            bordercolor=[("focus", COLORS["accent"])],
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground="#10323a",
            bordercolor=COLORS["accent"],
            padding=(18, 9),
            font=("TkDefaultFont", 10, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLORS["accent_hover"]), ("disabled", COLORS["border"])],
            foreground=[("disabled", COLORS["muted"])],
        )
        style.configure(
            "Danger.TButton",
            background=COLORS["panel_alt"],
            foreground=COLORS["danger"],
            bordercolor=COLORS["danger"],
        )

        style.configure(
            "Treeview",
            background=COLORS["panel"],
            fieldbackground=COLORS["panel"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            rowheight=28,
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["selection"])],
            foreground=[("selected", COLORS["text"])],
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            padding=(8, 7),
            font=("TkDefaultFont", 9, "bold"),
        )
        style.map("Treeview.Heading", background=[("active", COLORS["panel_alt"])])

        style.configure(
            "TCheckbutton",
            background=COLORS["panel"],
            foreground=COLORS["text"],
        )
        style.map("TCheckbutton", background=[("active", COLORS["panel"])])
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=COLORS["surface"],
            background=COLORS["accent"],
            bordercolor=COLORS["border"],
        )

        self.option_add("*TCombobox*Listbox.background", COLORS["surface"])
        self.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", COLORS["selection"])
        self.option_add("*TCombobox*Listbox.selectForeground", COLORS["text"])

    def _create_variables(self):
        # Character and target
        defaults = CharacterStats()
        self.stat_vars: Dict[str, tk.StringVar] = {
            "character_class": tk.StringVar(value=defaults.character_class),
            "character_level": tk.StringVar(value=str(defaults.character_level)),
        }
        for field_info in fields(CharacterStats):
            if field_info.name in {"character_class", "character_level"}:
                continue
            self.stat_vars[field_info.name] = tk.StringVar(value=str(getattr(defaults, field_info.name)))

        target = TargetProfile()
        self.target_vars: Dict[str, object] = {
            "content_mode": tk.StringVar(value=target.content_mode),
            "normal_weight": tk.StringVar(value=str(target.normal_weight)),
            "target_defense": tk.StringVar(value=str(target.target_defense)),
            "target_evasion": tk.StringVar(value=str(target.target_evasion)),
            "use_accuracy_approximation": tk.BooleanVar(value=target.use_accuracy_approximation),
        }
        self.total_slots_var = tk.StringVar(value="7")
        self.top_results_var = tk.StringVar(value="20")
        self.stats_include_equipped_var = tk.BooleanVar(value=True)

        self.roster_count_var = tk.StringVar(value="0 owned pages")
        self.status_var = tk.StringVar(value="Enter the displayed stats, then check owned pages and mark the current Main/Sub slots.")
        self.progress_text_var = tk.StringVar(value="Ready")
        self.profile_title_var = tk.StringVar(value="Unsaved profile")

        self.target_vars["content_mode"].trace_add("write", lambda *_: self._update_content_fields())  # type: ignore[union-attr]

    def _build_ui(self):
        # The themed artwork is rendered inside the Character canvas. Keeping it
        # out of a root-level Label avoids Linux/Tk stacking corruption during
        # maximize/fullscreen transitions.
        self._build_header()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(12, 8))

        self.character_tab = ttk.Frame(self.notebook, style="App.TFrame")
        self.companion_tab = ttk.Frame(self.notebook, style="App.TFrame")
        self.results_tab = ttk.Frame(self.notebook, style="App.TFrame")
        self.notebook.add(self.character_tab, text="1  Character & Target")
        self.notebook.add(self.companion_tab, text="2  Owned Companions")
        self.notebook.add(self.results_tab, text="3  Results")

        self._build_character_tab()
        self._build_companion_tab()
        self._build_results_tab()
        self._build_status_bar()

    def _build_header(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 14))
        header.pack(fill="x")
        text_frame = ttk.Frame(header, style="Header.TFrame")
        text_frame.pack(side="left", fill="x", expand=True)
        ttk.Label(text_frame, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            text_frame,
            text="Fixed companion roster • local screenshot stat import • exact equip-effect search",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        controls = ttk.Frame(header, style="Header.TFrame")
        controls.pack(side="right")
        ttk.Label(controls, textvariable=self.profile_title_var, style="PanelMuted.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="e", pady=(0, 4)
        )
        ttk.Button(controls, text="New", command=self.new_profile).grid(row=1, column=0, padx=3)
        ttk.Button(controls, text="Load", command=self.load_profile).grid(row=1, column=1, padx=3)
        ttk.Button(controls, text="Save", command=self.save_profile).grid(row=1, column=2, padx=3)
        ttk.Button(
            controls,
            text="Save As…",
            command=lambda: self.save_profile(save_as=True),
        ).grid(row=1, column=3, padx=3)
        ttk.Button(controls, text="Help", command=self.show_help).grid(row=1, column=4, padx=3)
        ttk.Button(controls, text="Report Bug", command=self.show_bug_report).grid(row=1, column=5, padx=3)
        self.optimize_button = ttk.Button(
            controls,
            text="Optimize Team",
            style="Accent.TButton",
            command=self.start_optimization,
        )
        self.optimize_button.grid(row=0, column=6, rowspan=2, padx=(14, 0), sticky="ns")

    def _build_character_tab(self):
        self._cancel_character_canvas_callbacks()
        canvas_host = tk.Frame(self.character_tab, background=COLORS["bg"], borderwidth=0, highlightthickness=0)
        canvas_host.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            canvas_host,
            background=COLORS["bg"],
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(canvas_host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._character_canvas = canvas
        self._character_canvas_bg_item = canvas.create_image(0, 0, anchor="nw")
        self._character_canvas_bg_photo = None
        self._character_canvas_bg_after = None
        self._character_canvas_last_size = (0, 0)
        self._character_canvas_content_height = 900
        self._character_canvas_items = {}
        self._character_canvas_widgets = {}

        note = ttk.Frame(canvas, style="Panel.TFrame", padding=(14, 10))
        ttk.Label(note, text="Measurement rule", style="Value.TLabel").pack(side="left", padx=(0, 12))
        ttk.Label(
            note,
            text=(
                "Enter the stats exactly as currently displayed in-game. In Owned Companions, "
                "mark the page in the Main slot and every page in a Sub slot; the app reverses "
                "those equip effects before testing replacements."
            ),
            style="Panel.TLabel",
            wraplength=900,
        ).pack(side="left", fill="x", expand=True)
        include_check = ttk.Checkbutton(
            note,
            text="Displayed stats include current companions",
            variable=self.stats_include_equipped_var,
        )
        include_check.pack(side="right", padx=(14, 0))
        ToolTip(
            include_check,
            "Leave checked for normal use. Uncheck only for a legacy profile or a measurement genuinely taken with every companion effect absent.",
        )

        legend = tk.Frame(canvas, background=COLORS["bg"], borderwidth=0, highlightthickness=0)
        ttk.Label(legend, text="After screenshot import:", style="Muted.TLabel").pack(side="left", padx=(2, 12))
        ttk.Label(legend, text="Read from screenshot", style="Imported.App.TLabel").pack(side="left", padx=(0, 18))
        ttk.Label(legend, text="Inferred zero", style="Zero.App.TLabel").pack(side="left", padx=(0, 18))
        ttk.Label(legend, text="Not covered — check manually", style="Uncovered.App.TLabel").pack(side="left", padx=(0, 18))
        ttk.Label(legend, text="Conflict", style="Conflict.App.TLabel").pack(side="left")

        left_outer, left_panel = self._make_maple_section(canvas, "Character Stat")
        left_panel.columnconfigure(0, minsize=170)
        left_panel.columnconfigure(1, weight=0)
        self._form_combo(
            left_panel,
            0,
            "Class",
            self.stat_vars["character_class"],
            CLASS_NAMES,
            "The baseline stats already contain most class conversion. Class is retained for profile context and future active-skill modeling.",
        )
        self._form_entry(
            left_panel,
            1,
            "Character level",
            self.stat_vars["character_level"],
            "Stored for profile completeness. Current equip-effect scoring uses the measured stats directly.",
        )
        self._form_entry(
            left_panel,
            2,
            "Total companion slots",
            self.total_slots_var,
            "One main plus 0–6 sub companions; valid total is 1–7.",
        )
        self._form_entry(
            left_panel,
            3,
            "Results to keep",
            self.top_results_var,
            "How many top combinations to retain after exhaustive search.",
        )

        auto_strip = self._build_autoassign_strip(canvas)

        left_bottom_outer, left_bottom_panel = self._make_maple_section(canvas, "Content-specific Damage")
        left_bottom_panel.columnconfigure(0, minsize=170)
        left_bottom_panel.columnconfigure(1, weight=0)
        content_fields = [
            ("Normal Monster Damage %", "normal_damage", "Applied only to Normal farming and the normal portion of Mixed stage."),
            ("Boss Damage %", "boss_damage", "Applied only to Boss and the boss portion of Mixed stage; ignored in Arena / neither."),
            ("Basic Attack Damage %", "basic_attack_damage", "Weighted by the Basic Attack share entered below."),
            ("Skill Damage %", "skill_damage", "Weighted by the Skill share, which is 100% minus Basic Attack share."),
            ("Basic Attack share %", "basic_attack_share", "Estimated share of sustained damage that comes from basic attacks. This controls the relative value of Basic Attack vs Skill Damage."),
            ("Status Damage %", "status_damage", "Applied only during the status uptime below."),
            ("Status uptime %", "status_uptime", "Estimated fraction of the fight in which a qualifying status effect is active."),
        ]
        for idx, (label, key, tip) in enumerate(content_fields):
            self._form_entry(left_bottom_panel, idx, label, self.stat_vars[key], tip, field_key=key)

        right_outer, right_panel = self._make_maple_section(canvas, "Combat Stat")
        right_panel.columnconfigure(0, minsize=170)
        right_panel.columnconfigure(1, weight=0)
        core_fields = [
            ("Attack", "attack", "Currently displayed Attack. The marked current team will be removed automatically. Supports commas and suffixes such as 1.2m."),
            ("Damage %", "damage", "General additive Damage stat."),
            ("Stat Prop Damage %", "stat_prop_damage", "Displayed Stat Prop Damage. Added Main Stat effects also increase this by 1% per 100 gained Main Stat."),
            ("Critical Rate %", "crit_rate", "Expected-value model caps effective Critical Rate at 100%."),
            ("Critical Damage %", "crit_damage", "Extra multiplier applied to critical hits."),
            ("Attack Speed %", "attack_speed", "Effective Attack Speed before companions; modeled cap is 150%."),
            ("Min Damage Multiplier %", "min_damage", "Enter the displayed multiplier. The model caps minimum at maximum."),
            ("Max Damage Multiplier %", "max_damage", "Enter the displayed multiplier; 100 means 1.00×."),
        ]
        for row, (label, key, tip) in enumerate(core_fields):
            self._form_entry(right_panel, row, label, self.stat_vars[key], tip, field_key=key)

        right_bottom_outer, right_bottom_panel = self._make_maple_section(canvas, "Advanced Multipliers")
        right_bottom_panel.columnconfigure(0, minsize=170)
        right_bottom_panel.columnconfigure(1, weight=0)
        advanced_fields = [
            ("Damage Amplification %", "damage_amp", "General multiplicative bucket used by the public calculator model."),
            ("Final Damage %", "final_damage", "Existing effective Final Damage. Added Final Damage sources stack multiplicatively."),
            ("Defense Penetration %", "defense_pen", "Existing effective penetration. Added sources stack against the remaining defense percentage."),
            ("Accuracy", "accuracy", "Only changes score when the optional Accuracy approximation is enabled."),
            ("Total Main Stat", "total_main_stat", "Required to score Main Stat % companion effects, including Buccaneer."),
            ("Current Main Stat %", "current_main_stat_pct", "Your Main Stat % before companions. Used with Total Main Stat to reconstruct the additive percent bucket."),
            ("Flat Attack scaling %", "flat_attack_scaling_pct", "Optional multiplier affecting gained flat Attack/Main Stat, such as account systems that scale flat attack. Leave 0 when unknown."),
        ]
        for idx, (label, key, tip) in enumerate(advanced_fields):
            self._form_entry(right_bottom_panel, idx, label, self.stat_vars[key], tip, field_key=key)

        target_outer, target = self._make_maple_section(canvas, "Optimization target")
        for col in range(4):
            target.columnconfigure(col, weight=1 if col in (1, 3) else 0)
        target_label_style = "WhitePanel.TLabel"
        ttk.Label(target, text="Content", style=target_label_style).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
        mode_combo = ttk.Combobox(
            target,
            textvariable=self.target_vars["content_mode"],
            values=CONTENT_MODES,
            state="readonly",
            width=24,
        )
        mode_combo.grid(row=0, column=1, sticky="w", padx=(0, 18), pady=5)
        ToolTip(mode_combo, "Normal and Boss use their matching damage buckets. Mixed uses the chosen normal/boss weighting. Arena uses neither.")

        ttk.Label(target, text="Normal share in Mixed %", style=target_label_style).grid(row=0, column=2, sticky="w", padx=(0, 8), pady=5)
        self.normal_weight_entry = ttk.Entry(target, textvariable=self.target_vars["normal_weight"], width=20)
        self.normal_weight_entry.grid(row=0, column=3, sticky="w", pady=5)
        ToolTip(self.normal_weight_entry, "For example, 70 means 70% normal-mob score and 30% boss score.")

        ttk.Label(target, text="Target Defense", style=target_label_style).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
        defense_entry = ttk.Entry(target, textvariable=self.target_vars["target_defense"], width=24)
        defense_entry.grid(row=1, column=1, sticky="w", padx=(0, 18), pady=5)
        ToolTip(defense_entry, "Uses the public calculator's 6000 / (6000 + effective defense) reduction model. Leave 0 when unknown.")

        ttk.Label(target, text="Target Evasion", style=target_label_style).grid(row=1, column=2, sticky="w", padx=(0, 8), pady=5)
        evasion_entry = ttk.Entry(target, textvariable=self.target_vars["target_evasion"], width=20)
        evasion_entry.grid(row=1, column=3, sticky="w", pady=5)
        ToolTip(evasion_entry, "Used only by the optional approximation below.")

        self.accuracy_check = ttk.Checkbutton(
            target,
            text="Include approximate Accuracy/Evasion miss-rate effect",
            variable=self.target_vars["use_accuracy_approximation"],
        )
        self.accuracy_check.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 2))
        ToolTip(
            self.accuracy_check,
            "Off by default. The game tooltip relationship is approximated linearly: a 100-point Accuracy deficit reaches a 70% miss chance. This is not treated as an exact internal formula.",
        )

        widgets = {
            "note": note,
            "legend": legend,
            "left_top": left_outer,
            "auto": auto_strip,
            "left_bottom": left_bottom_outer,
            "right_top": right_outer,
            "right_bottom": right_bottom_outer,
            "target": target_outer,
        }
        self._character_canvas_widgets = widgets
        for name, widget in widgets.items():
            self._character_canvas_items[name] = canvas.create_window(0, 0, window=widget, anchor="nw")

        canvas.tag_lower(self._character_canvas_bg_item)
        # Deliberately avoid resizing the image-backed hierarchy in place.
        # A settled root resize rebuilds this tab cleanly instead.
        self._bind_character_canvas_wheel(canvas)
        for widget in widgets.values():
            self._bind_character_canvas_wheel(widget)
        self.after(50, self._layout_character_canvas)

    def _bind_character_canvas_wheel(self, widget):
        canvas = self._character_canvas
        widget.bind("<MouseWheel>", lambda event: self._scroll_character_canvas(event), add="+")
        widget.bind("<Button-4>", lambda _event: canvas.yview_scroll(-1, "units"), add="+")
        widget.bind("<Button-5>", lambda _event: canvas.yview_scroll(1, "units"), add="+")
        for child in widget.winfo_children():
            self._bind_character_canvas_wheel(child)

    def _scroll_character_canvas(self, event):
        if event.delta:
            self._character_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _schedule_character_canvas_layout(self, _event=None):
        after_id = getattr(self, "_character_canvas_layout_after", None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        self._character_canvas_layout_after = self.after(80, self._layout_character_canvas)

    def _layout_character_canvas(self):
        self._character_canvas_layout_after = None
        canvas = self._character_canvas
        if not canvas.winfo_exists():
            return
        canvas.update_idletasks()
        width = max(760, canvas.winfo_width())
        margin = 16
        note_item = self._character_canvas_items["note"]
        canvas.itemconfigure(note_item, width=max(500, width - margin * 2))
        canvas.update_idletasks()

        note = self._character_canvas_widgets["note"]
        legend = self._character_canvas_widgets["legend"]
        left_top = self._character_canvas_widgets["left_top"]
        auto = self._character_canvas_widgets["auto"]
        left_bottom = self._character_canvas_widgets["left_bottom"]
        right_top = self._character_canvas_widgets["right_top"]
        right_bottom = self._character_canvas_widgets["right_bottom"]
        target = self._character_canvas_widgets["target"]

        y = 10
        canvas.coords(note_item, margin, y)
        y += note.winfo_reqheight() + 6
        canvas.coords(self._character_canvas_items["legend"], margin, y)
        y += legend.winfo_reqheight() + 10

        left_width = max(left_top.winfo_reqwidth(), auto.winfo_reqwidth(), left_bottom.winfo_reqwidth())
        right_width = max(right_top.winfo_reqwidth(), right_bottom.winfo_reqwidth())
        gap = 20
        group_width = left_width + gap + right_width
        left_x = max(margin, (width - group_width) // 2)
        right_x = left_x + left_width + gap
        panel_top = y

        canvas.coords(self._character_canvas_items["left_top"], left_x, panel_top)
        auto_y = panel_top + left_top.winfo_reqheight() + 8
        canvas.coords(self._character_canvas_items["auto"], left_x + 6, auto_y)
        left_bottom_y = auto_y + auto.winfo_reqheight() + 8
        canvas.coords(self._character_canvas_items["left_bottom"], left_x, left_bottom_y)

        canvas.coords(self._character_canvas_items["right_top"], right_x, panel_top)
        right_bottom_y = panel_top + right_top.winfo_reqheight() + 8
        canvas.coords(self._character_canvas_items["right_bottom"], right_x, right_bottom_y)

        left_end = left_bottom_y + left_bottom.winfo_reqheight()
        right_end = right_bottom_y + right_bottom.winfo_reqheight()
        target_y = max(left_end, right_end) + 10
        target_x = max(margin, (width - target.winfo_reqwidth()) // 2)
        canvas.coords(self._character_canvas_items["target"], target_x, target_y)
        content_height = target_y + target.winfo_reqheight() + 20
        self._character_canvas_content_height = max(content_height, canvas.winfo_height())
        canvas.configure(scrollregion=(0, 0, width, self._character_canvas_content_height))
        canvas.tag_lower(self._character_canvas_bg_item)
        self._schedule_character_canvas_background()

    def _schedule_character_canvas_background(self):
        after_id = getattr(self, "_character_canvas_bg_after", None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        self._character_canvas_bg_after = self.after(140, self._refresh_character_canvas_background)

    def _refresh_character_canvas_background(self):
        self._character_canvas_bg_after = None
        if self._background_original is None or Image is None or ImageTk is None:
            return
        canvas = self._character_canvas
        width = max(1, canvas.winfo_width())
        height = max(canvas.winfo_height(), int(self._character_canvas_content_height))
        size = (width, height)
        if size == self._character_canvas_last_size and self._character_canvas_bg_photo is not None:
            canvas.tag_lower(self._character_canvas_bg_item)
            return
        try:
            source = self._background_original
            scale = max(width / source.width, height / source.height)
            resized = source.resize(
                (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
                Image.LANCZOS,
            )
            left = max(0, (resized.width - width) // 2)
            top = max(0, (resized.height - height) // 2)
            fitted = resized.crop((left, top, left + width, top + height))
            faded = Image.blend(fitted, Image.new("RGBA", fitted.size, (248, 252, 255, 255)), 0.42)
            photo = ImageTk.PhotoImage(faded)
            self._character_canvas_bg_photo = photo
            canvas.itemconfigure(self._character_canvas_bg_item, image=photo)
            canvas.coords(self._character_canvas_bg_item, 0, 0)
            canvas.tag_lower(self._character_canvas_bg_item)
            self._character_canvas_last_size = size
        except (tk.TclError, ValueError):
            return

    def _panel_subheading(self, parent, row: int, text: str):
        label = self._make_gradient_label(
            parent,
            text,
            width=250,
            height=24,
            top_color=(210, 236, 255, 255),
            bottom_color=(167, 203, 240, 255),
            fg="#2c86b9",
            font=("TkDefaultFont", 10, "bold"),
            radius=6,
            border_color=(157, 188, 225, 255),
            padx=8,
            anchor="w",
            bg="#ffffff",
        )
        label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6), padx=(10,0))
        return label

    def _field_label_width(self, label: str) -> int:
        extra_wide = {
            "Total companion slots",
            "Normal Monster Damage %",
            "Basic Attack Damage %",
            "Basic Attack share %",
            "Basic Attack Share %",
            "Stat Prop Damage %",
            "Min Damage Multiplier %",
            "Max Damage Multiplier %",
            "Damage Amplification %",
            "Defense Penetration %",
            "Current Main Stat %",
            "Flat Attack scaling %",
            "Flat Attack Scaling %",
        }
        if label in extra_wide:
            return 158
        if len(label) >= 18:
            return 132
        return 112

    def _form_entry(
        self,
        parent,
        row: int,
        label: str,
        variable: tk.StringVar,
        tooltip: str = "",
        field_key: Optional[str] = None,
    ):
        label_width = self._field_label_width(label)
        lbl = self._make_gradient_label(
            parent,
            label,
            width=label_width,
            height=24,
            top_color=(202, 232, 76, 255),
            bottom_color=(166, 207, 24, 255),
            fg=COLORS["field_label_text"],
            font=("TkDefaultFont", 8, "bold"),
            radius=8,
            border_color=(146, 175, 35, 255),
            padx=8,
            anchor="w",
            bg="#ffffff",
        )
        lbl.grid(row=row, column=0, sticky="w", padx=(10, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=variable, style="TEntry", width=14)
        entry.grid(row=row, column=1, sticky="w", pady=4)
        if field_key:
            self.stat_entries[field_key] = entry
            self.stat_labels[field_key] = lbl
        if tooltip:
            ToolTip(lbl, tooltip)
            ToolTip(entry, tooltip)
        return entry

    def _form_combo(self, parent, row: int, label: str, variable: tk.StringVar, values: Sequence[str], tooltip: str = ""):
        label_width = self._field_label_width(label)
        lbl = self._make_gradient_label(
            parent,
            label,
            width=label_width,
            height=24,
            top_color=(202, 232, 76, 255),
            bottom_color=(166, 207, 24, 255),
            fg=COLORS["field_label_text"],
            font=("TkDefaultFont", 8, "bold"),
            radius=8,
            border_color=(146, 175, 35, 255),
            padx=8,
            anchor="w",
            bg="#ffffff",
        )
        lbl.grid(row=row, column=0, sticky="w", padx=(10, 8), pady=4)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=14)
        combo.grid(row=row, column=1, sticky="w", pady=4)
        if tooltip:
            ToolTip(lbl, tooltip)
            ToolTip(combo, tooltip)
        return combo


    def _refresh_stat_source_styles(self):
        entry_styles = {
            "screenshot": "Imported.TEntry",
            "inferred_zero": "Zero.TEntry",
            "uncovered": "Uncovered.TEntry",
            "conflict": "Conflict.TEntry",
        }
        label_styles = {
            "screenshot": "Imported.Panel.TLabel",
            "inferred_zero": "Zero.Panel.TLabel",
            "uncovered": "Uncovered.Panel.TLabel",
            "conflict": "Conflict.Panel.TLabel",
        }
        label_palette = {
            "manual": (COLORS["field_label"], COLORS["field_label_text"]),
            "screenshot": ("#b4efc8", "#184b30"),
            "inferred_zero": ("#b9dcff", "#18456c"),
            "uncovered": ("#ffe3b4", "#6f4511"),
            "conflict": ("#ffc0c7", "#6d1823"),
        }
        for key, entry in self.stat_entries.items():
            status = self.stat_sources.get(key, "manual")
            entry.configure(style=entry_styles.get(status, "TEntry"))
            label = self.stat_labels.get(key)
            if label is not None:
                if isinstance(label, tk.Label):
                    _bg, fg = label_palette.get(status, label_palette["manual"])
                    label.configure(background="#ffffff", foreground=fg)
                else:
                    label.configure(style=label_styles.get(status, "Panel.TLabel"))

    def _load_ui_preferences(self) -> Dict[str, object]:
        try:
            if self.preferences_path.exists():
                payload = json.loads(self.preferences_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
        except Exception:
            pass
        return {}

    def _save_ui_preferences(self) -> None:
        try:
            write_json_atomic(self.preferences_path, self.ui_preferences)
        except Exception:
            # A preference write failure must never block screenshot import.
            pass

    def is_screenshot_warning_hidden(self) -> bool:
        return bool(self.ui_preferences.get("hide_screenshot_import_warning", False))

    def set_screenshot_warning_hidden(self, hidden: bool) -> None:
        self.ui_preferences["hide_screenshot_import_warning"] = bool(hidden)
        self._save_ui_preferences()

    def _confirm_screenshot_import_conditions(self) -> bool:
        if self.is_screenshot_warning_hidden():
            return True
        dialog = ScreenshotImportWarningDialog(self)
        self.wait_window(dialog)
        if dialog.proceed and bool(dialog.dont_show_again_var.get()):
            self.set_screenshot_warning_hidden(True)
        return bool(dialog.proceed)

    def _on_stat_value_edited(self, key: str):
        if self._loading_profile or self._applying_ocr:
            return
        if key in self.stat_sources and self.stat_sources.get(key) != "manual":
            self.stat_sources[key] = "manual"
            self._refresh_stat_source_styles()
        self._schedule_autosave()

    def import_stat_screenshots(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(
                "Search active",
                "Wait for the current optimization search to finish before importing screenshots.",
                parent=self,
            )
            return
        if not self._confirm_screenshot_import_conditions():
            return
        selected = filedialog.askopenfilenames(
            parent=self,
            title="Select overlapping Stat Info screenshots",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.webp"),
                ("PNG screenshots", "*.png"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        try:
            _require_ocr_dependencies()
        except RuntimeError as exc:
            messagebox.showerror("Screenshot OCR is not installed", str(exc), parent=self)
            return

        progress = tk.Toplevel(self)
        progress.title("Reading Stat Info")
        progress.transient(self)
        progress.resizable(False, False)
        progress.configure(background=COLORS["panel"])
        frame = ttk.Frame(progress, style="Panel.TFrame", padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=f"Reading {len(selected)} screenshot(s) locally with Tesseract…",
            style="Panel.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text="The imported values will be shown for review before the profile changes.",
            style="PanelMuted.TLabel",
        ).pack(anchor="w", pady=(4, 12))
        bar = ttk.Progressbar(frame, mode="indeterminate", length=420)
        bar.pack(fill="x")
        bar.start(12)
        progress.update_idletasks()
        try:
            result = merge_stat_screenshots(
                [Path(path) for path in selected],
                self.stat_vars["character_class"].get(),
            )
        except Exception as exc:
            progress.destroy()
            messagebox.showerror("Screenshot import failed", str(exc), parent=self)
            return
        finally:
            try:
                bar.stop()
            except tk.TclError:
                pass
        progress.destroy()

        current_values = {
            key: self.stat_vars[key].get()
            for key in set(OCR_IMPORT_FIELDS) | set(OCR_MANUAL_FIELDS)
            if key in self.stat_vars
        }
        dialog = OCRReviewDialog(self, result, current_values)
        self.wait_window(dialog)
        if dialog.applied_values is None or dialog.applied_statuses is None:
            self.status_var.set("Screenshot import cancelled; no values were changed.")
            return

        self._applying_ocr = True
        try:
            for key, value in dialog.applied_values.items():
                if key in self.stat_vars:
                    self.stat_vars[key].set(entry_number_text(value))
            self.stat_sources = {
                key: status
                for key, status in dialog.applied_statuses.items()
                if key in self.stat_entries
            }
        finally:
            self._applying_ocr = False
        self._refresh_stat_source_styles()
        self._schedule_autosave()
        uncovered = sum(1 for status in self.stat_sources.values() if status == "uncovered")
        conflicts = sum(1 for status in self.stat_sources.values() if status == "conflict")
        if conflicts:
            self.status_var.set(
                f"Imported screenshots with {conflicts} unresolved conflict(s) and {uncovered} manually checked field(s) remaining."
            )
        else:
            self.status_var.set(
                f"Imported {len(selected)} Stat Info screenshots. {uncovered} amber field(s) still need manual checking."
            )

    def _load_roster_asset_manifest(self):
        path = companion_asset_directory() / "manifest.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.roster_asset_manifest = payload if isinstance(payload, dict) else {}
        except Exception:
            self.roster_asset_manifest = {}

    def _load_roster_photo(self, name: str, rarity: str, gray: bool = False) -> Optional[tk.PhotoImage]:
        # Version 2.1+ intentionally reuses one consistently framed portrait
        # across every rarity page. Cache by companion rather than rarity so
        # startup decodes 28 images instead of as many as 122.
        cache_key = f"{name}::{gray}::compact{CompanionTile.IMAGE_SIZE}"
        if cache_key in self.roster_image_cache:
            return self.roster_image_cache[cache_key]
        suffix = "__gray" if gray else ""
        slug = companion_asset_slug(name)
        candidates = [rarity, "Rare", "Common", "Epic", "Unique", "Legendary"]
        photo: Optional[tk.PhotoImage] = None
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            candidate_path = companion_asset_directory() / f"{slug}__{candidate.casefold()}{suffix}.png"
            if not candidate_path.exists():
                continue
            try:
                if Image is not None and ImageTk is not None:
                    portrait = Image.open(candidate_path).convert("RGBA")
                    portrait = portrait.resize(
                        (CompanionTile.IMAGE_SIZE, CompanionTile.IMAGE_SIZE),
                        Image.LANCZOS,
                    )
                    photo = ImageTk.PhotoImage(portrait)
                else:
                    raw = tk.PhotoImage(file=str(candidate_path))
                    # Integer fallback gives a close approximation when Pillow
                    # is unavailable; normal packaged builds use the exact size.
                    photo = raw.zoom(2, 2).subsample(3, 3)
                break
            except Exception:
                continue
        self.roster_image_cache[cache_key] = photo
        return photo

    def _asset_is_placeholder(self, name: str, rarity: str) -> bool:
        entry = self.roster_asset_manifest.get(f"{name}::{rarity}", {})
        return bool(entry.get("placeholder", True))

    def _build_companion_tab(self):
        self.companion_tab.columnconfigure(0, weight=1)
        self.companion_tab.rowconfigure(1, weight=1)
        self._load_roster_asset_manifest()

        intro = ttk.Frame(self.companion_tab, style="Panel.TFrame", padding=(14, 11))
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        intro.columnconfigure(1, weight=1)
        ttk.Label(intro, text="Companion collection", style="Value.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 14)
        )
        ttk.Label(
            intro,
            text=(
                "Click a portrait to toggle ownership. Click its level chip to type a level. "
                "Click the small role badge and choose Main, Sub, or not equipped for the active build."
            ),
            style="Panel.TLabel",
            wraplength=820,
        ).grid(row=0, column=1, sticky="ew")
        actions = ttk.Frame(intro, style="Panel.TFrame")
        actions.grid(row=0, column=2, sticky="e", padx=(16, 0))
        ttk.Button(actions, text="Clear current slots", command=self._clear_current_slots).pack(side="left", padx=3)
        ttk.Button(actions, text="Clear ownership", style="Danger.TButton", command=self._clear_roster).pack(
            side="left", padx=3
        )
        ttk.Label(actions, textvariable=self.roster_count_var, style="PanelMuted.TLabel").pack(
            side="left", padx=(12, 0)
        )

        body = ttk.Panedwindow(self.companion_tab, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew")
        grid_holder = ttk.Frame(body, style="App.TFrame")
        detail_holder = ttk.Frame(body, style="App.TFrame", width=330)
        body.add(grid_holder, weight=4)
        body.add(detail_holder, weight=1)

        scroll = ScrollableFrame(grid_holder)
        scroll.pack(fill="both", expand=True)
        container = scroll.inner
        container.columnconfigure(0, weight=1)

        for group_index, name in enumerate(COMPANION_DISPLAY_ORDER):
            group = ttk.Frame(container, style="Panel.TFrame", padding=(12, 9))
            group.grid(row=group_index, column=0, sticky="ew", pady=(0, 9), padx=(0, 6))
            ttk.Label(group, text=name, style="Value.TLabel").grid(
                row=0, column=0, columnspan=5, sticky="w", pady=(0, 7)
            )

            rarities = RARITIES if name in COMMON_AVAILABLE else RARITIES[1:]
            for page_index, rarity in enumerate(rarities):
                key = companion_key(name, rarity)
                try:
                    default_effect, default_value = companion_effect(name, rarity, 1)
                except ValueError:
                    continue

                owned_var = tk.BooleanVar(value=False)
                level_var = tk.StringVar(value="1")
                role_var = tk.StringVar(value="Not equipped")
                effect_label_var = tk.StringVar(value=EFFECT_LABELS[default_effect])
                effect_value_var = tk.StringVar(value=f"{default_value:g}")
                main_bonus_var = tk.StringVar(value="0")
                self.roster_vars[key] = {
                    "name": name,
                    "rarity": rarity,
                    "formula": True,
                    "owned": owned_var,
                    "level": level_var,
                    "role": role_var,
                    "effect_label": effect_label_var,
                    "effect_value": effect_value_var,
                    "main_bonus": main_bonus_var,
                }

                tile = CompanionTile(
                    group,
                    key=key,
                    name=name,
                    rarity=rarity,
                    color_image=self._load_roster_photo(name, rarity, False),
                    gray_image=self._load_roster_photo(name, rarity, True),
                    placeholder=self._asset_is_placeholder(name, rarity),
                    on_select=self._select_roster_tile,
                    on_toggle=self._toggle_roster_owned_from_tile,
                    on_role=self._show_roster_role_menu,
                    on_level=self._commit_roster_level_from_tile,
                )
                tile.grid(row=1, column=page_index, padx=(0, 9), pady=(0, 2), sticky="nw")
                self.roster_tiles[key] = tile
                self.roster_widgets[key] = {"tile": tile}

                level_var.trace_add("write", lambda *_args, k=key: self._on_roster_level_changed(k))
                role_var.trace_add("write", lambda *_args, k=key: self._on_roster_role_changed(k))
                effect_label_var.trace_add("write", lambda *_args: self._schedule_autosave())
                effect_value_var.trace_add("write", lambda *_args: self._schedule_autosave())
                main_bonus_var.trace_add("write", lambda *_args, k=key: self._on_roster_detail_value_changed(k))

        detail = ttk.LabelFrame(detail_holder, text="Selected companion page", padding=14)
        detail.pack(fill="both", expand=True, padx=(8, 0))
        detail.columnconfigure(1, weight=1)
        self.companion_detail_title_var = tk.StringVar(value="Select a portrait")
        self.companion_detail_state_var = tk.StringVar(value="")
        self.companion_detail_level_var = tk.StringVar(value="")
        self.companion_detail_role_var = tk.StringVar(value="")
        self.companion_detail_effect_var = tk.StringVar(value="")
        self.companion_detail_value_var = tk.StringVar(value="")
        self.companion_detail_asset_var = tk.StringVar(value="")
        ttk.Label(
            detail,
            textvariable=self.companion_detail_title_var,
            style="Value.TLabel",
            wraplength=280,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        fields_to_show = (
            ("Collection", self.companion_detail_state_var),
            ("Level", self.companion_detail_level_var),
            ("Current slot", self.companion_detail_role_var),
            ("On-equip effect", self.companion_detail_effect_var),
            ("Effect value", self.companion_detail_value_var),
            ("Portrait", self.companion_detail_asset_var),
        )
        for row_index, (label, variable) in enumerate(fields_to_show, start=1):
            ttk.Label(detail, text=label, style="PanelMuted.TLabel").grid(
                row=row_index, column=0, sticky="nw", padx=(0, 12), pady=5
            )
            ttk.Label(detail, textvariable=variable, style="Panel.TLabel", wraplength=190).grid(
                row=row_index, column=1, sticky="nw", pady=5
            )

        ttk.Separator(detail).grid(row=8, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(detail, text="Measured Main adjustment %", style="PanelMuted.TLabel").grid(
            row=9, column=0, columnspan=2, sticky="w"
        )
        self.companion_detail_main_bonus_entry = ttk.Entry(detail, width=14, state="disabled")
        self.companion_detail_main_bonus_entry.grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=(5, 4)
        )
        ToolTip(
            self.companion_detail_main_bonus_entry,
            "Optional measured, time-averaged whole-build gain when this page is Main. Leave 0 when unknown.",
        )

        role_buttons = ttk.Frame(detail, style="Panel.TFrame")
        role_buttons.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        ttk.Button(role_buttons, text="Set Main", command=lambda: self._set_selected_roster_role("Main")).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(role_buttons, text="Set Sub", command=lambda: self._set_selected_roster_role("Sub")).pack(
            side="left", padx=4
        )
        ttk.Button(
            role_buttons,
            text="Clear",
            command=lambda: self._set_selected_roster_role("Not equipped"),
        ).pack(side="left", padx=4)

        ttk.Label(
            detail,
            text=(
                "M and S1–S6 are current-build slot markers. Sub numbers are visual only; "
                "Sub order does not change the optimizer calculation."
            ),
            style="PanelMuted.TLabel",
            wraplength=280,
        ).grid(row=12, column=0, columnspan=2, sticky="sw", pady=(18, 0))
        detail.rowconfigure(12, weight=1)

        footer = ttk.Frame(self.companion_tab, style="Panel.TFrame", padding=(12, 9))
        footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            footer,
            text=(
                "Portraits from your supplied game capture are framed consistently and reused across rarity pages. "
                "Rarity is shown by each card frame; portrait artwork does not affect data or calculations."
            ),
            style="PanelMuted.TLabel",
            wraplength=1120,
        ).pack(side="left", fill="x", expand=True)

        if self.roster_vars:
            self._select_roster_tile(next(iter(self.roster_vars)))
        self._refresh_all_roster_tiles()

    def _select_roster_tile(self, key: str):
        if key not in self.roster_vars:
            return
        self.selected_roster_key = key
        self._refresh_all_roster_tiles()
        self._update_companion_detail()

    def _toggle_roster_owned_from_tile(self, key: str):
        row = self.roster_vars[key]
        row["owned"].set(not bool(row["owned"].get()))
        self._select_roster_tile(key)

    def _commit_roster_level_from_tile(self, key: str, value: str) -> bool:
        try:
            level = int(parse_number(value, field_name="Companion level"))
            if not 1 <= level <= 300:
                raise ValueError("Companion level must be from 1 to 300.")
        except Exception as exc:
            messagebox.showerror("Companion level", str(exc), parent=self)
            return False
        row = self.roster_vars[key]
        row["level"].set(str(level))
        if not bool(row["owned"].get()):
            row["owned"].set(True)
        self._select_roster_tile(key)
        return True

    def _cycle_roster_role_from_tile(self, key: str):
        row = self.roster_vars[key]
        current = str(row["role"].get())
        next_role = {
            "Not equipped": "Main",
            "Main": "Sub",
            "Sub": "Not equipped",
        }.get(current, "Not equipped")
        self._set_roster_role(key, next_role)
        self._select_roster_tile(key)

    def _show_roster_role_menu(
        self,
        key: str,
        anchor_widget: tk.Widget,
        x_root: int,
        y_root: int,
    ):
        """Show an explicit role chooser without changing the current Main first."""
        if key not in self.roster_vars:
            return
        active = CompanionTile._active_level_tile
        if active is not None and not active._finish_level_editor(True):
            return
        previous = getattr(self, "_roster_role_menu", None)
        if previous is not None:
            try:
                previous.unpost()
                previous.destroy()
            except tk.TclError:
                pass
        current = str(self.roster_vars[key]["role"].get())
        menu = tk.Menu(
            self,
            tearoff=False,
            background="#ffffff",
            foreground=COLORS["text"],
            activebackground=COLORS["accent"],
            activeforeground="#10232b",
            borderwidth=1,
            relief="solid",
            font=("TkDefaultFont", 10),
        )
        self._roster_role_menu = menu

        def choose(role: str):
            self._set_roster_role(key, role)
            self._select_roster_tile(key)

        for role in EQUIPPED_ROLES:
            check = "✓  " if role == current else "    "
            label = "Not equipped" if role == "Not equipped" else role
            menu.add_command(label=f"{check}{label}", command=lambda selected=role: choose(selected))
        try:
            menu.tk_popup(int(x_root), int(y_root))
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass
            try:
                menu.destroy()
            except tk.TclError:
                pass
            if getattr(self, "_roster_role_menu", None) is menu:
                self._roster_role_menu = None

    def _set_selected_roster_role(self, role: str):
        if self.selected_roster_key:
            self._set_roster_role(self.selected_roster_key, role)

    def _set_roster_role(self, key: str, role: str):
        if role not in EQUIPPED_ROLES:
            return
        row = self.roster_vars[key]
        current = str(row["role"].get())
        try:
            total_slots = int(parse_number(self.total_slots_var.get(), field_name="Total companion slots"))
        except Exception:
            total_slots = 7
        equipped_other = sum(
            str(other["role"].get()) in {"Main", "Sub"}
            for other_key, other in self.roster_vars.items()
            if other_key != key
        )
        if role in {"Main", "Sub"} and current == "Not equipped" and equipped_other >= total_slots:
            messagebox.showinfo(
                "Current team full",
                f"This build has {total_slots} companion slot(s). Clear another current slot first.",
                parent=self,
            )
            return
        if role != "Not equipped" and not bool(row["owned"].get()):
            row["owned"].set(True)
        row["role"].set(role)
        self._select_roster_tile(key)

    def _on_roster_detail_value_changed(self, key: str):
        self._schedule_autosave()
        if key == self.selected_roster_key:
            self._update_companion_detail()

    def _role_badges(self) -> Dict[str, str]:
        badges: Dict[str, str] = {}
        sub_index = 1
        for name in COMPANION_DISPLAY_ORDER:
            rarities = RARITIES if name in COMMON_AVAILABLE else RARITIES[1:]
            for rarity in rarities:
                key = companion_key(name, rarity)
                row = self.roster_vars.get(key)
                if not row:
                    continue
                role = str(row["role"].get())
                if role == "Main":
                    badges[key] = "M"
                elif role == "Sub":
                    badges[key] = f"S{sub_index}"
                    sub_index += 1
                else:
                    badges[key] = "—"
        return badges

    def _refresh_all_roster_tiles(self):
        if not self.roster_tiles:
            return
        badges = self._role_badges()
        for key, tile in self.roster_tiles.items():
            row = self.roster_vars[key]
            try:
                level = int(parse_number(row["level"].get(), field_name="Companion level"))
            except Exception:
                level = 1
            effect = str(row["effect_label"].get())
            value = str(row["effect_value"].get())
            suffix = "" if effect in {"Flat Attack", "Accuracy"} else "%"
            tile.refresh(
                owned=bool(row["owned"].get()),
                level=level,
                role_badge=badges.get(key, "—"),
                selected=(key == self.selected_roster_key),
                effect_text=f"{effect}: +{value}{suffix}",
            )

    def _update_companion_detail(self):
        key = self.selected_roster_key
        if not key or key not in self.roster_vars or not hasattr(self, "companion_detail_title_var"):
            return
        row = self.roster_vars[key]
        name, rarity = str(row["name"]), str(row["rarity"])
        owned = bool(row["owned"].get())
        level = str(row["level"].get())
        role = str(row["role"].get())
        effect = str(row["effect_label"].get())
        value = str(row["effect_value"].get())
        suffix = "" if effect in {"Flat Attack", "Accuracy"} else "%"
        placeholder = self._asset_is_placeholder(name, rarity)
        self.companion_detail_title_var.set(f"{name} — {rarity}")
        self.companion_detail_state_var.set("Owned" if owned else "Not owned")
        self.companion_detail_level_var.set(f"Lv. {level}")
        self.companion_detail_role_var.set(role)
        self.companion_detail_effect_var.set(effect)
        self.companion_detail_value_var.set(f"+{value}{suffix}")
        self.companion_detail_asset_var.set("Placeholder portrait" if placeholder else "Game portrait")
        self.companion_detail_main_bonus_entry.configure(
            textvariable=row["main_bonus"],
            state="normal" if owned else "disabled",
        )

    def _build_results_tab(self):
        self.results_tab.columnconfigure(0, weight=3)
        self.results_tab.columnconfigure(1, weight=2)
        self.results_tab.rowconfigure(1, weight=1)

        controls = ttk.Frame(self.results_tab, style="Panel.TFrame", padding=(12, 10))
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.results_summary_label = ttk.Label(
            controls,
            text="Run the optimizer to compare every valid team.",
            style="Panel.TLabel",
        )
        self.results_summary_label.pack(side="left")
        self.cancel_button = ttk.Button(controls, text="Cancel", style="Danger.TButton", command=self.cancel_optimization, state="disabled")
        self.cancel_button.pack(side="right")
        ttk.Button(controls, text="Copy selected report", command=self.copy_selected_report).pack(side="right", padx=6)
        ttk.Button(controls, text="Export results CSV", command=self.export_results_csv).pack(side="right", padx=6)

        left = ttk.Frame(self.results_tab, style="Panel.TFrame")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        columns = ("rank", "gain", "main", "subs", "score")
        self.results_tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        result_headings = {"rank": "#", "gain": "Gain", "main": "Main", "subs": "Sub companions", "score": "Relative score"}
        result_widths = {"rank": 42, "gain": 82, "main": 160, "subs": 420, "score": 110}
        for col in columns:
            self.results_tree.heading(col, text=result_headings[col])
            self.results_tree.column(col, width=result_widths[col], minwidth=40, anchor="w")
        self.results_tree.column("rank", anchor="center")
        self.results_tree.column("gain", anchor="e")
        self.results_tree.column("score", anchor="e")
        result_scroll = ttk.Scrollbar(left, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=result_scroll.set)
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        result_scroll.grid(row=0, column=1, sticky="ns")
        self.results_tree.bind("<<TreeviewSelect>>", self._show_selected_result)

        right = ttk.LabelFrame(self.results_tab, text="Selected team analysis", padding=10)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.result_detail = tk.Text(
            right,
            wrap="word",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["selection"],
            relief="flat",
            borderwidth=0,
            padx=8,
            pady=8,
            font=("TkFixedFont", 10),
        )
        detail_scroll = ttk.Scrollbar(right, orient="vertical", command=self.result_detail.yview)
        self.result_detail.configure(yscrollcommand=detail_scroll.set)
        self.result_detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll.grid(row=0, column=1, sticky="ns")
        self.result_detail.insert("1.0", self._empty_result_text())
        self.result_detail.configure(state="disabled")

    def _build_status_bar(self):
        status = ttk.Frame(self, style="Status.TFrame", padding=(14, 8))
        status.pack(fill="x", side="bottom")
        ttk.Label(status, textvariable=self.status_var, style="PanelMuted.TLabel").pack(side="left")
        self.progressbar = ttk.Progressbar(status, mode="determinate", length=210)
        self.progressbar.pack(side="right", padx=(10, 0))
        ttk.Label(status, textvariable=self.progress_text_var, style="PanelMuted.TLabel").pack(side="right")

    def _bind_shortcuts(self):
        self.bind_all("<Control-s>", lambda _e: self.save_profile())
        self.bind_all("<Control-Shift-S>", lambda _e: self.save_profile(save_as=True))
        self.bind_all("<Control-o>", lambda _e: self.load_profile())
        self.bind_all("<Control-n>", lambda _e: self.new_profile())
        self.bind_all("<Control-i>", lambda _e: self.import_stat_screenshots())
        self.bind_all("<F5>", lambda _e: self.start_optimization())
        self.bind_all("<Escape>", lambda _e: self.cancel_optimization())

    # ----- state parsing ----------------------------------------------------

    def collect_stats(self) -> CharacterStats:
        numeric: Dict[str, float] = {}
        for field_info in fields(CharacterStats):
            key = field_info.name
            if key == "character_class":
                continue
            if key == "character_level":
                level = int(parse_number(self.stat_vars[key].get(), field_name="Character level"))
                if level < 1:
                    raise ValueError("Character level must be at least 1.")
                numeric[key] = level
            else:
                numeric[key] = parse_number(self.stat_vars[key].get(), field_name=key.replace("_", " ").title())

        if numeric["attack"] <= 0:
            raise ValueError("Attack must be greater than zero.")
        for key in ("basic_attack_share", "status_uptime", "crit_rate"):
            if numeric[key] < 0:
                raise ValueError(f"{key.replace('_', ' ').title()} cannot be negative.")
        if numeric["basic_attack_share"] > 100:
            raise ValueError("Basic Attack share must be from 0 to 100%.")
        if numeric["status_uptime"] > 100:
            raise ValueError("Status uptime must be from 0 to 100%.")
        if numeric["min_damage"] < 0 or numeric["max_damage"] <= 0:
            raise ValueError("Damage multipliers must be positive (normally around 100 or higher).")

        return CharacterStats(
            character_class=self.stat_vars["character_class"].get().strip() or "Other / future class",
            **numeric,
        )

    def collect_target(self) -> TargetProfile:
        mode = self.target_vars["content_mode"].get()  # type: ignore[union-attr]
        if mode not in CONTENT_MODES:
            raise ValueError("Select a valid content mode.")
        normal_weight = parse_number(self.target_vars["normal_weight"].get(), field_name="Normal share")  # type: ignore[union-attr]
        if not 0 <= normal_weight <= 100:
            raise ValueError("Normal share must be from 0 to 100%.")
        defense = parse_number(self.target_vars["target_defense"].get(), field_name="Target Defense")  # type: ignore[union-attr]
        evasion = parse_number(self.target_vars["target_evasion"].get(), field_name="Target Evasion")  # type: ignore[union-attr]
        if defense < 0 or evasion < 0:
            raise ValueError("Target Defense and Evasion cannot be negative.")
        return TargetProfile(
            content_mode=mode,
            normal_weight=normal_weight,
            target_defense=defense,
            target_evasion=evasion,
            use_accuracy_approximation=bool(self.target_vars["use_accuracy_approximation"].get()),  # type: ignore[union-attr]
        )

    def collect_profile(self) -> Profile:
        total_slots = int(parse_number(self.total_slots_var.get(), field_name="Total companion slots"))
        top_results = int(parse_number(self.top_results_var.get(), field_name="Results to keep"))
        if not 1 <= total_slots <= 7:
            raise ValueError("Total companion slots must be from 1 to 7.")
        if not 1 <= top_results <= 100:
            raise ValueError("Results to keep must be from 1 to 100.")
        companions = self._collect_roster_companions()
        self.companions = copy.deepcopy(companions)
        return Profile(
            stats=self.collect_stats(),
            target=self.collect_target(),
            companions=companions,
            total_slots=total_slots,
            top_results=top_results,
            stats_include_equipped_companions=bool(self.stats_include_equipped_var.get()),
            stat_sources=dict(self.stat_sources),
        )

    def apply_profile(self, profile: Profile):
        previous_loading = self._loading_profile
        self._loading_profile = True
        try:
            for field_info in fields(CharacterStats):
                key = field_info.name
                self.stat_vars[key].set(str(getattr(profile.stats, key)))
            for field_info in fields(TargetProfile):
                key = field_info.name
                var = self.target_vars[key]
                var.set(getattr(profile.target, key))  # type: ignore[union-attr]
            self.total_slots_var.set(str(profile.total_slots))
            self.top_results_var.set(str(profile.top_results))
            self.stats_include_equipped_var.set(profile.stats_include_equipped_companions)
            self.stat_sources = dict(profile.stat_sources)
            self._refresh_stat_source_styles()
            self._load_companions_into_roster(profile.companions)
            self.companions = copy.deepcopy(profile.companions)
            self.results = []
            self.last_optimized_profile = None
            self.refresh_results_tree()

        finally:
            self._loading_profile = previous_loading
    # ----- fixed companion roster -------------------------------------------

    def _stable_roster_uid(self, name: str, rarity: str) -> str:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"maplestory-idle:{name}:{rarity}").hex

    def _on_roster_owned_changed(self, key: str):
        if self._roster_syncing:
            return
        row = self.roster_vars[key]
        if not bool(row["owned"].get()):  # type: ignore[union-attr]
            self._roster_syncing = True
            row["role"].set("Not equipped")  # type: ignore[union-attr]
            self._roster_syncing = False
        self._set_roster_row_state(key)
        self._refresh_roster_count()
        self._schedule_autosave()

    def _on_roster_level_changed(self, key: str):
        if self._roster_syncing:
            return
        self._refresh_roster_formula(key)
        self._refresh_all_roster_tiles()
        if key == self.selected_roster_key:
            self._update_companion_detail()
        self._schedule_autosave()

    def _on_roster_role_changed(self, key: str):
        if self._roster_syncing:
            return
        row = self.roster_vars[key]
        role = str(row["role"].get())  # type: ignore[union-attr]
        if role not in EQUIPPED_ROLES:
            return
        self._roster_syncing = True
        try:
            if role != "Not equipped":
                row["owned"].set(True)  # type: ignore[union-attr]
            if role == "Main":
                for other_key, other in self.roster_vars.items():
                    if other_key != key and str(other["role"].get()) == "Main":  # type: ignore[union-attr]
                        other["role"].set("Not equipped")  # type: ignore[union-attr]
        finally:
            self._roster_syncing = False
        self._set_roster_row_state(key)
        self._refresh_roster_count()
        self._schedule_autosave()

    def _set_roster_row_state(self, key: str):
        row = self.roster_vars[key]
        widgets = self.roster_widgets.get(key, {})
        owned = bool(row["owned"].get())  # type: ignore[union-attr]
        if "level" in widgets:
            widgets["level"].configure(state="normal")
        if "role" in widgets:
            widgets["role"].configure(state="readonly" if owned else "disabled")
        if "main_bonus" in widgets:
            widgets["main_bonus"].configure(state="normal" if owned else "disabled")
        if not bool(row["formula"]):
            if "effect" in widgets:
                widgets["effect"].configure(state="readonly" if owned else "disabled")
            if "value" in widgets:
                widgets["value"].configure(state="normal" if owned else "disabled")
        if hasattr(self, "roster_tiles") and key in self.roster_tiles:
            self._refresh_all_roster_tiles()
            if key == self.selected_roster_key:
                self._update_companion_detail()

    def _refresh_roster_formula(self, key: str):
        row = self.roster_vars[key]
        if not bool(row["formula"]):
            return
        try:
            level = int(parse_number(row["level"].get(), field_name="Companion level"))  # type: ignore[union-attr]
            effect_type, value = companion_effect(str(row["name"]), str(row["rarity"]), level)
        except Exception:
            return
        self._roster_syncing = True
        try:
            row["effect_label"].set(EFFECT_LABELS[effect_type])  # type: ignore[union-attr]
            row["effect_value"].set(f"{value:g}")  # type: ignore[union-attr]
        finally:
            self._roster_syncing = False

    def _collect_roster_companions(self) -> List[Companion]:
        companions: List[Companion] = []
        for key, row in self.roster_vars.items():
            if not bool(row["owned"].get()):  # type: ignore[union-attr]
                continue
            name = str(row["name"])
            rarity = str(row["rarity"])
            level = int(parse_number(row["level"].get(), field_name=f"{name} {rarity} level"))  # type: ignore[union-attr]
            if not 1 <= level <= 300:
                raise ValueError(f"{name} {rarity} level must be from 1 to 300.")
            if bool(row["formula"]):
                effect_type, effect_value = companion_effect(name, rarity, level)
                source = "formula"
            else:
                label = str(row["effect_label"].get())  # type: ignore[union-attr]
                if label not in LABEL_TO_EFFECT:
                    raise ValueError(f"Select an equip effect for {name} {rarity}.")
                effect_type = LABEL_TO_EFFECT[label]
                effect_value = parse_number(
                    row["effect_value"].get(),  # type: ignore[union-attr]
                    field_name=f"{name} {rarity} equip value",
                )
                source = "manual"
            if effect_value < 0:
                raise ValueError(f"{name} {rarity} equip value cannot be negative.")
            main_bonus = parse_number(
                row["main_bonus"].get(),  # type: ignore[union-attr]
                field_name=f"{name} {rarity} Main adjustment",
            )
            role = str(row["role"].get())  # type: ignore[union-attr]
            if role not in EQUIPPED_ROLES:
                raise ValueError(f"Select a valid current slot for {name} {rarity}.")
            companions.append(
                Companion(
                    uid=self._stable_roster_uid(name, rarity),
                    name=name,
                    rarity=rarity,
                    level=level,
                    effect_type=effect_type,
                    effect_value=effect_value,
                    main_bonus=main_bonus,
                    equipped_role=role,
                    source=source,
                    notes="Player-entered exact value" if source == "manual" else "Built-in level formula",
                )
            )
        companions.extend(copy.deepcopy(self.extra_companions))
        companions.sort(key=lambda c: (KNOWN_COMPANIONS.index(c.name) if c.name in KNOWN_COMPANIONS else 999, RARITY_ORDER.get(c.rarity, 99)))
        return companions

    def _load_companions_into_roster(self, companions: Sequence[Companion]):
        self._roster_syncing = True
        self._loading_profile = True
        try:
            for key, row in self.roster_vars.items():
                row["owned"].set(False)  # type: ignore[union-attr]
                row["level"].set("1")  # type: ignore[union-attr]
                row["role"].set("Not equipped")  # type: ignore[union-attr]
                row["main_bonus"].set("0")  # type: ignore[union-attr]
                if not bool(row["formula"]):
                    default_effect = MANUAL_EFFECT_HINTS.get(str(row["name"]), "damage")
                    row["effect_label"].set(EFFECT_LABELS[default_effect])  # type: ignore[union-attr]
                    row["effect_value"].set("0")  # type: ignore[union-attr]
                self._refresh_roster_formula(key)
            self.extra_companions = []
            for companion in companions:
                key = companion_key(companion.name, companion.rarity)
                row = self.roster_vars.get(key)
                if row is None:
                    self.extra_companions.append(copy.deepcopy(companion))
                    continue
                row["owned"].set(True)  # type: ignore[union-attr]
                row["level"].set(str(companion.level))  # type: ignore[union-attr]
                row["role"].set(companion.equipped_role)  # type: ignore[union-attr]
                row["main_bonus"].set(f"{companion.main_bonus:g}")  # type: ignore[union-attr]
                if bool(row["formula"]):
                    self._refresh_roster_formula(key)
                else:
                    row["effect_label"].set(EFFECT_LABELS.get(companion.effect_type, companion.effect_type))  # type: ignore[union-attr]
                    row["effect_value"].set(f"{companion.effect_value:g}")  # type: ignore[union-attr]
        finally:
            self._roster_syncing = False
            self._loading_profile = False
        for key in self.roster_vars:
            self._set_roster_row_state(key)
        self._refresh_roster_count()
        if self.extra_companions:
            self.status_var.set(
                f"Loaded {len(self.extra_companions)} custom/future page(s) in addition to the fixed roster. They are preserved but not editable in this build."
            )

    def _clear_current_slots(self):
        self._roster_syncing = True
        try:
            for row in self.roster_vars.values():
                row["role"].set("Not equipped")  # type: ignore[union-attr]
        finally:
            self._roster_syncing = False
        self._refresh_roster_count()
        self._schedule_autosave()

    def _clear_roster(self):
        if not messagebox.askyesno("Clear ownership", "Uncheck every companion page and clear current slots?", parent=self):
            return
        self._roster_syncing = True
        try:
            for row in self.roster_vars.values():
                row["owned"].set(False)  # type: ignore[union-attr]
                row["role"].set("Not equipped")  # type: ignore[union-attr]
            self.extra_companions = []
        finally:
            self._roster_syncing = False
        for key in self.roster_vars:
            self._set_roster_row_state(key)
        self._refresh_roster_count()
        self._schedule_autosave()

    def _refresh_roster_count(self):
        owned = sum(bool(row["owned"].get()) for row in self.roster_vars.values())  # type: ignore[union-attr]
        equipped = sum(str(row["role"].get()) in {"Main", "Sub"} for row in self.roster_vars.values())  # type: ignore[union-attr]
        extra = len(self.extra_companions)
        suffix = f" • {extra} custom" if extra else ""
        self.roster_count_var.set(f"{owned + extra} owned • {equipped} equipped{suffix}")
        if hasattr(self, "roster_tiles"):
            self._refresh_all_roster_tiles()
            self._update_companion_detail()

    # ----- optimization -----------------------------------------------------

    def start_optimization(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            profile = self.collect_profile()
            if len(profile.companions) < profile.total_slots:
                raise ValueError(
                    f"Add at least {profile.total_slots} owned companion pages; currently there are {len(profile.companions)}."
                )
            prepare_optimization_context(
                profile.stats,
                profile.target,
                profile.companions,
                profile.total_slots,
                profile.stats_include_equipped_companions,
            )
            combination_count = math.comb(len(profile.companions), profile.total_slots)
            if combination_count > 25_000_000:
                proceed = messagebox.askyesno(
                    "Large exact search",
                    f"This exact search contains {combination_count:,} teams. It will run in the background and may be CPU-intensive. Continue?",
                    parent=self,
                )
                if not proceed:
                    return
        except Exception as exc:
            messagebox.showerror("Cannot optimize", str(exc), parent=self)
            return

        self.cancel_event.clear()
        self.last_optimized_profile = copy.deepcopy(profile)
        self.results = []
        self.refresh_results_tree()
        self.optimize_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progressbar.configure(value=0, maximum=max(1, combination_count))
        self.progress_text_var.set(f"0 / {combination_count:,}")
        self.status_var.set("Searching every valid team…")
        self.notebook.select(self.results_tab)

        def progress(done: int, total: int):
            self.worker_queue.put(("progress", done, total))

        def run():
            try:
                results, total, elapsed = optimize_companions(
                    profile.stats,
                    profile.target,
                    profile.companions,
                    profile.total_slots,
                    profile.top_results,
                    progress=progress,
                    cancel_event=self.cancel_event,
                    stats_include_equipped_companions=profile.stats_include_equipped_companions,
                )
                self.worker_queue.put(("done", results, total, elapsed, self.cancel_event.is_set()))
            except Exception as exc:
                self.worker_queue.put(("error", str(exc), traceback.format_exc()))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()
        self.after(80, self._poll_worker_queue)

    def _poll_worker_queue(self):
        active = self.worker is not None and self.worker.is_alive()
        auto_followup = False
        try:
            while True:
                message = self.worker_queue.get_nowait()
                kind = message[0]
                if kind == "progress":
                    _, done, total = message
                    self.progressbar.configure(maximum=max(1, total), value=done)
                    pct = 100.0 * done / total if total else 100.0
                    self.progress_text_var.set(f"{done:,} / {total:,}  ({pct:.1f}%)")
                elif kind == "done":
                    _, results, total, elapsed, cancelled = message
                    self.results = results
                    self.refresh_results_tree()
                    self.optimize_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    if cancelled:
                        self.status_var.set(f"Search cancelled after {elapsed:.2f}s; showing the best teams examined so far.")
                        self.results_summary_label.configure(
                            text=f"Partial search • {len(results)} retained result(s) • {elapsed:.2f}s"
                        )
                    else:
                        self.progressbar.configure(value=total, maximum=max(1, total))
                        self.progress_text_var.set(f"{total:,} / {total:,}  (100.0%)")
                        self.status_var.set(f"Exact search completed: {total:,} teams in {elapsed:.2f}s.")
                        self.results_summary_label.configure(
                            text=f"Exact exhaustive search • {total:,} teams • {elapsed:.2f}s • top {len(results)} shown"
                        )
                    active = False
                elif kind == "error":
                    _, error, details = message
                    self.optimize_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.status_var.set("Optimization failed.")
                    messagebox.showerror("Optimization error", f"{error}\n\nTechnical details:\n{details}", parent=self)
                    active = False
        except queue.Empty:
            pass
        if active:
            self.after(80, self._poll_worker_queue)

    def cancel_optimization(self):
        if self.worker and self.worker.is_alive():
            self.cancel_event.set()
            self.status_var.set("Cancellation requested; finishing the current batch…")

    def refresh_results_tree(self):
        self.results_tree.delete(*self.results_tree.get_children())
        for index, result in enumerate(self.results, start=1):
            subs = ", ".join(f"{c.name} {c.rarity[0]}" for c in result.subs)
            self.results_tree.insert(
                "",
                "end",
                iid=str(index - 1),
                values=(
                    index,
                    fmt_pct(result.gain_pct, signed=True),
                    result.main.display_name,
                    subs,
                    fmt_number(result.score),
                ),
            )
        if self.results:
            self.results_tree.selection_set("0")
            self.results_tree.focus("0")
            self._show_selected_result()
        else:
            self._set_detail(self._empty_result_text())

    def _selected_result(self) -> Optional[OptimizationResult]:
        selection = self.results_tree.selection()
        if not selection:
            return None
        try:
            return self.results[int(selection[0])]
        except (ValueError, IndexError):
            return None

    def _show_selected_result(self, _event=None):
        result = self._selected_result()
        if result is None:
            return
        self._set_detail(self.result_report(result))

    def result_report(self, result: OptimizationResult) -> str:
        profile = self.last_optimized_profile or self.collect_profile()
        (
            model_stats,
            reference_state,
            current_team,
            current_main,
            _reconstruction_warnings,
            reference_label,
        ) = prepare_optimization_context(
            profile.stats,
            profile.target,
            profile.companions,
            profile.total_slots,
            profile.stats_include_equipped_companions,
        )
        state = result.state
        lines = [
            f"OPTIMIZED FOR: {profile.target.content_mode}",
            f"CLASS PROFILE: {profile.stats.character_class} (Lv. {profile.stats.character_level})",
            "",
            f"GAIN VS {reference_label.upper()}: {result.gain_pct:+.3f}%",
            f"RELATIVE SCORE:            {fmt_number(result.score, 4)}",
        ]

        if current_team:
            lines.extend(["", "CURRENT TEAM USED TO RECONSTRUCT BASELINE"])
            if current_main is not None:
                lines.append(f"  Main: {current_main.display_name} — {current_main.effect_text}")
            for companion in current_team:
                if current_main is None or companion.uid != current_main.uid:
                    lines.append(f"  Sub:  {companion.display_name} — {companion.effect_text}")
            lines.append(
                f"  Reconstructed unequipped Attack: {fmt_number(model_stats.attack)} "
                f"from displayed {fmt_number(profile.stats.attack)}"
            )

        lines.extend([
            "",
            "RECOMMENDED MAIN",
            f"  {result.main.display_name}",
            f"  {result.main.effect_text}",
        ])
        if result.main.main_bonus:
            lines.append(f"  Manual average active contribution: {result.main.main_bonus:+.2f}%")
        else:
            lines.append("  Main designation is heuristic only; active skill adds 0% to score.")
        lines.extend(["", "RECOMMENDED SUBS"])
        for companion in result.subs:
            lines.append(f"  • {companion.display_name} — {companion.effect_text}")

        lines.extend(["", "COMBINED RECOMMENDED EQUIP EFFECTS"])
        for key, value in sorted(result.effect_totals.items(), key=lambda item: EFFECT_LABELS.get(item[0], item[0])):
            suffix = "" if key in {"attack", "accuracy"} else "%"
            lines.append(f"  {EFFECT_LABELS.get(key, key)}: +{fmt_number(value)}{suffix}")

        comparison_title = "CURRENT → RECOMMENDED" if current_team else "UNEQUIPPED → RECOMMENDED"
        lines.extend(["", comparison_title])
        comparisons = [
            ("Attack", reference_state.attack, state.attack, ""),
            ("Main Stat", reference_state.total_main_stat, state.total_main_stat, ""),
            ("Critical Rate", reference_state.crit_rate, state.crit_rate, "%"),
            ("Attack Speed", reference_state.attack_speed, state.attack_speed, "%"),
            ("Min Damage", reference_state.min_damage, state.min_damage, "%"),
            ("Max Damage", reference_state.max_damage, state.max_damage, "%"),
            ("Normal Damage", reference_state.normal_damage, state.normal_damage, "%"),
            ("Boss Damage", reference_state.boss_damage, state.boss_damage, "%"),
            ("Status Damage", reference_state.status_damage, state.status_damage, "%"),
            ("Accuracy", reference_state.accuracy, state.accuracy, ""),
        ]
        for label, before, after, suffix in comparisons:
            if abs(after - before) > 1e-9 or label in {"Attack", "Critical Rate", "Attack Speed"}:
                lines.append(f"  {label:<18} {fmt_number(before):>12}{suffix} → {fmt_number(after):>12}{suffix}")

        lines.extend([
            "",
            "CONTENT SCORES",
            f"  Current/reference: {fmt_number(reference_state.score_selected, 4)}",
            f"  Recommended normal: {fmt_number(state.score_normal, 4)}",
            f"  Recommended boss:   {fmt_number(state.score_boss, 4)}",
            f"  Recommended arena:  {fmt_number(state.score_arena, 4)}",
        ])

        if state.warnings:
            lines.extend(["", "MODEL NOTES"])
            lines.extend(f"  • {warning}" for warning in state.warnings)
        lines.extend([
            "",
            "Interpretation",
            "  Equip-effect ranking is exhaustive for the pages entered.",
            "  Current equip effects are reversed before replacement teams are tested.",
            "  Combat utility, healing, crowd control, target count, movement,",
            "  and unmeasured Main active skills are not silently converted to DPS.",
        ])
        return "\n".join(lines)

    def _set_detail(self, text: str):
        self.result_detail.configure(state="normal")
        self.result_detail.delete("1.0", "end")
        self.result_detail.insert("1.0", text)
        self.result_detail.configure(state="disabled")

    def _empty_result_text(self) -> str:
        return (
            "No optimization result yet.\n\n"
            "1. Enter the stats currently displayed in-game.\n"
            "2. Add every owned companion page and its level.\n"
            "3. Mark the currently equipped Main and every Sub page.\n"
            "4. Choose the content target and run Optimize Team.\n\n"
            "The app reverses the current team's equip effects before testing\n"
            "replacement teams. Do not record stats while temporary combat buffs\n"
            "or a companion active skill are affecting the stat page.\n\n"
            "The search is exact for entered equip effects. Main active skills are\n"
            "excluded unless you provide a measured average bonus for a companion."
        )

    # ----- save/load/export -------------------------------------------------

    def _install_autosave_traces(self):
        for key, variable in self.stat_vars.items():
            variable.trace_add(
                "write", lambda *_args, field_key=key: self._on_stat_value_edited(field_key)
            )
        variables: List[object] = [
            self.total_slots_var,
            self.top_results_var,
            self.stats_include_equipped_var,
        ]
        variables.extend(self.target_vars.values())
        for variable in variables:
            try:
                variable.trace_add("write", lambda *_args: self._schedule_autosave())
            except AttributeError:
                pass

    def _schedule_autosave(self):
        if self._loading_profile:
            return
        if self._autosave_after_id is not None:
            try:
                self.after_cancel(self._autosave_after_id)
            except tk.TclError:
                pass
        self._autosave_after_id = self.after(1200, self._write_autosave)

    def _write_autosave(self, profile: Optional[Profile] = None):
        self._autosave_after_id = None
        if self._loading_profile:
            return
        try:
            profile = profile or self.collect_profile()
            write_json_atomic(self.autosave_path, profile_to_dict(profile))
        except Exception:
            # Keep the last valid autosave when the user is midway through an invalid field.
            return

    def _restore_autosave(self) -> bool:
        if not self.autosave_path.exists():
            return False
        try:
            payload = json.loads(self.autosave_path.read_text(encoding="utf-8"))
            profile = profile_from_dict(payload)
            self.apply_profile(profile)
            self.profile_path = None
            self.profile_title_var.set("Auto-restored session")
            self.status_var.set(f"Restored the last valid local session from {self.autosave_path}.")
            return True
        except Exception:
            return False

    def new_profile(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Search active", "Cancel the current search before starting a new profile.", parent=self)
            return
        roster_has_data = any(bool(row["owned"].get()) for row in self.roster_vars.values()) or bool(self.extra_companions)  # type: ignore[union-attr]
        if roster_has_data or self.profile_path:
            if not messagebox.askyesno("New profile", "Clear the current profile? Unsaved changes will be lost.", parent=self):
                return
        self.profile_path = None
        self.profile_title_var.set("Unsaved profile")
        self.apply_profile(Profile())
        self.status_var.set("New profile created.")

    def save_profile(self, save_as: bool = False):
        try:
            profile = self.collect_profile()
        except Exception as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self)
            return
        path = self.profile_path
        if save_as or path is None:
            if path is not None:
                initial = path.name
                initial_dir = str(path.parent)
            else:
                initial = safe_filename(f"{profile.stats.character_class}_companion_profile") + ".json"
                initial_dir = None
            dialog_options = {
                "parent": self,
                "title": "Save optimizer profile as" if save_as else "Save optimizer profile",
                "defaultextension": ".json",
                "filetypes": (("JSON profile", "*.json"), ("All files", "*.*")),
                "initialfile": initial,
            }
            if initial_dir:
                dialog_options["initialdir"] = initial_dir
            selected = filedialog.asksaveasfilename(**dialog_options)
            if not selected:
                return
            path = Path(selected)
        try:
            write_json_atomic(path, profile_to_dict(profile))
            self.profile_path = path
            self.profile_title_var.set(path.name)
            self.status_var.set(f"Saved profile to {path}.")
            self._write_autosave(profile)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)

    def load_profile(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Search active", "Cancel the current search before loading a profile.", parent=self)
            return
        selected = filedialog.askopenfilename(
            parent=self,
            title="Load optimizer profile",
            filetypes=(("JSON profile", "*.json"), ("All files", "*.*")),
        )
        if not selected:
            return
        path = Path(selected)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            profile = profile_from_dict(payload)
            self.apply_profile(profile)
            self.profile_path = path
            self.profile_title_var.set(path.name)
            self.status_var.set(f"Loaded {path.name}.")
            self._write_autosave(profile)
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc), parent=self)

    def export_results_csv(self):
        if not self.results:
            messagebox.showinfo("Export", "Run an optimization first.", parent=self)
            return
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Export optimizer results",
            defaultextension=".csv",
            filetypes=(("CSV file", "*.csv"), ("All files", "*.*")),
            initialfile="companion_optimizer_results.csv",
        )
        if not selected:
            return
        try:
            with open(selected, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Rank", "Gain %", "Relative score", "Main", "Subs", "Combined effects"])
                for rank, result in enumerate(self.results, start=1):
                    writer.writerow([
                        rank,
                        f"{result.gain_pct:.6f}",
                        f"{result.score:.8f}",
                        result.main.display_name,
                        " | ".join(c.display_name for c in result.subs),
                        " | ".join(
                            f"{EFFECT_LABELS.get(k, k)} +{v:g}" for k, v in sorted(result.effect_totals.items())
                        ),
                    ])
            self.status_var.set(f"Exported results to {selected}.")
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)

    def copy_selected_report(self):
        result = self._selected_result()
        if result is None:
            messagebox.showinfo("Copy", "Select a result first.", parent=self)
            return
        report = self.result_report(result)
        self.clipboard_clear()
        self.clipboard_append(report)
        self.status_var.set("Selected team report copied to clipboard.")

    # ----- misc -------------------------------------------------------------

    def _update_content_fields(self):
        if not hasattr(self, "normal_weight_entry"):
            return
        mode = self.target_vars["content_mode"].get()  # type: ignore[union-attr]
        self.normal_weight_entry.configure(state="normal" if mode == "Mixed stage" else "disabled")

    def show_help(self, start_page: str = "start"):
        window = getattr(self, "_help_window", None)
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_force()
            if start_page:
                for index, page in enumerate(window.PAGES):
                    if page["id"] == start_page:
                        window.show_page(index)
                        break
            return
        self._help_window = HelpBook(self, start_page=start_page)
        self._help_window.lift()
        self._help_window.focus_force()

    def show_bug_report(self):
        window = getattr(self, "_bug_report_window", None)
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_force()
            return
        self._bug_report_window = BugReportDialog(self)
        self._bug_report_window.lift()
        self._bug_report_window.focus_force()

    def show_about(self):
        text = (
            f"{APP_NAME} {APP_VERSION}\n\n"
            "Purpose\n"
            "• Exhaustively ranks all valid teams from the companion pages you enter.\n"
            "• Accepts the stats currently displayed with your existing team equipped.\n"
            "• Reverses the marked Main/Sub equip effects before testing replacements.\n"
            "• Separates exact equip effects from uncertain active-skill utility.\n\n"
            "Built-in data\n"
            "• All current roster companions, including Bishop, Paladin, Buccaneer, Corsair, Night Walker, and Wind Archer.\n"
            "• Attack Speed cap/diminishing stacking, Critical Rate cap, multiplicative Final Damage and Defense Penetration.\n"
            "• Public damage model with average min/max roll, expected critical value, attack speed, target damage, and defense reduction.\n\n"
            "Manual data\n"
            "• Only future/custom companion pages without verified formulas require an exact value copied from the game.\n"
            "• Main active bonus is optional and must be a measured, time-averaged whole-build percentage.\n\n"
            "Screenshot import\n"
            "• Reads multiple overlapping Stat Info screenshots locally with Tesseract.\n"
            "• Green fields were read, blue fields are inferred zero, amber fields need manual checking, and red fields conflict.\n"
            "• Every imported value is reviewed before it changes the profile.\n\n"
            "Saving\n"
            "• Changes are auto-saved to a per-user configuration folder and restored at launch.\n"
            "• Named JSON profiles can also be saved and loaded manually.\n\n"
            "Important limitations\n"
            "• Record stats outside combat without temporary buffs or an active companion skill affecting the page.\n"
            "• A displayed stat already pinned at a hard cap cannot always reveal its unique uncapped baseline.\n"
            "• Main companion animations, AI, target count, utility, healing, crowd control, and proc timing are not automatically simulated.\n"
            "• Accuracy/Evasion is disabled by default and clearly marked approximate when enabled.\n"
            "• This is a community modeling tool, not an official Nexon product.\n\n"
            "Data references: MapleStory Idle RPG Wiki and the public Maplestory Damage Calculator source/data."
        )
        messagebox.showinfo("About and model notes", text, parent=self)

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Exit", "An exact search is still running. Cancel it and exit?", parent=self):
                return
            self.cancel_event.set()
        self._write_autosave()
        self.destroy()

# ---------------------------------------------------------------------------
# Advanced account/build, robustness, Main-comparison, and planning models
# ---------------------------------------------------------------------------

MAIN_MODES = (
    "Automatic",
    "Equip effects only",
    "Lock selected Main",
    "Prefer damage Main",
    "Prefer utility Main",
)

RARITY_MAX_LEVEL = {
    "Common": 300,
    "Rare": 50,
    "Epic": 30,
    "Unique": 10,
    "Legendary": 16,
}


@dataclass
class MainSelectionOptions:
    mode: str = "Automatic"
    locked_main_uid: str = ""


@dataclass
class SensitivitySettings:
    vary_basic_attack: bool = False
    basic_attack_min: float = 30.0
    basic_attack_max: float = 70.0
    basic_attack_steps: int = 5
    vary_status_uptime: bool = False
    status_uptime_min: float = 0.0
    status_uptime_max: float = 75.0
    status_uptime_steps: int = 4
    vary_target_defense: bool = False
    target_defense_min: float = 0.0
    target_defense_max: float = 0.0
    target_defense_steps: int = 1
    vary_target_evasion: bool = False
    target_evasion_min: float = 0.0
    target_evasion_max: float = 0.0
    target_evasion_steps: int = 1


@dataclass
class AdvancedProfile(Profile):
    build_name: str = "Default Build"
    main_options: MainSelectionOptions = field(default_factory=MainSelectionOptions)
    sensitivity: SensitivitySettings = field(default_factory=SensitivitySettings)


@dataclass
class BuildProfile:
    name: str = "Default Build"
    stats: CharacterStats = field(default_factory=CharacterStats)
    target: TargetProfile = field(default_factory=TargetProfile)
    current_roles: Dict[str, str] = field(default_factory=dict)
    stats_include_equipped_companions: bool = True
    stat_sources: Dict[str, str] = field(default_factory=dict)
    main_options: MainSelectionOptions = field(default_factory=MainSelectionOptions)
    sensitivity: SensitivitySettings = field(default_factory=SensitivitySettings)


@dataclass
class AccountProfile:
    character_class: str = "Other / future class"
    character_level: int = 1
    companions: List[Companion] = field(default_factory=list)
    total_slots: int = 7
    top_results: int = 20
    builds: List[BuildProfile] = field(default_factory=lambda: [BuildProfile()])
    active_build: str = "Default Build"


@dataclass
class SensitivityTeamSummary:
    team_key: str
    main: Companion
    team: Tuple[Companion, ...]
    wins: int
    win_pct: float
    avg_regret_pct: float
    max_regret_pct: float
    basic_min: float
    basic_max: float
    status_min: float
    status_max: float


@dataclass
class SensitivityAnalysisResult:
    scenario_count: int
    nominal_result: OptimizationResult
    nominal_win_pct: float
    nominal_max_regret_pct: float
    modal_team_key: str
    confidence: str
    summaries: List[SensitivityTeamSummary]
    variable_influence: Dict[str, str]
    elapsed: float


@dataclass
class MainComparisonResult:
    main: Companion
    score: float
    gain_pct: float
    subs: Tuple[Companion, ...]
    team: Tuple[Companion, ...]


@dataclass
class UpgradeValueResult:
    companion: Companion
    next_level: int
    current_effect: float
    next_effect: float
    improvement_pct: float
    resulting_main: Companion
    resulting_team: Tuple[Companion, ...]
    enters_best_team: bool


@dataclass
class ReadinessIssue:
    severity: str
    message: str


@dataclass
class ReadinessReport:
    rating: str
    issues: List[ReadinessIssue]
    core_complete: bool
    current_team_complete: bool
    assumptions_complete: bool


def _construct_main_options(payload: object) -> MainSelectionOptions:
    if not isinstance(payload, dict):
        return MainSelectionOptions()
    return _construct_dataclass(MainSelectionOptions, payload)


def _construct_sensitivity(payload: object) -> SensitivitySettings:
    if not isinstance(payload, dict):
        return SensitivitySettings()
    return _construct_dataclass(SensitivitySettings, payload)


def build_to_dict(build: BuildProfile) -> Dict[str, object]:
    return {
        "name": build.name,
        "stats": asdict(build.stats),
        "target": asdict(build.target),
        "current_roles": dict(build.current_roles),
        "stats_include_equipped_companions": build.stats_include_equipped_companions,
        "stat_sources": dict(build.stat_sources),
        "main_options": asdict(build.main_options),
        "sensitivity": asdict(build.sensitivity),
    }


def build_from_dict(payload: Dict[str, object]) -> BuildProfile:
    return BuildProfile(
        name=str(payload.get("name", "Build")),
        stats=_construct_dataclass(CharacterStats, dict(payload.get("stats", {}))),
        target=_construct_dataclass(TargetProfile, dict(payload.get("target", {}))),
        current_roles={str(k): str(v) for k, v in dict(payload.get("current_roles", {})).items()},
        stats_include_equipped_companions=bool(payload.get("stats_include_equipped_companions", True)),
        stat_sources={str(k): str(v) for k, v in dict(payload.get("stat_sources", {})).items()},
        main_options=_construct_main_options(payload.get("main_options", {})),
        sensitivity=_construct_sensitivity(payload.get("sensitivity", {})),
    )


def account_to_dict(account: AccountProfile) -> Dict[str, object]:
    return {
        "account_version": 1,
        "app_version": APP_VERSION,
        "character_class": account.character_class,
        "character_level": account.character_level,
        "companions": [asdict(c) for c in account.companions],
        "total_slots": account.total_slots,
        "top_results": account.top_results,
        "builds": [build_to_dict(b) for b in account.builds],
        "active_build": account.active_build,
    }


def account_from_dict(payload: Dict[str, object], fallback_name: str = "Imported Build") -> AccountProfile:
    """Load a new account file or migrate a legacy single-build profile."""
    if "account_version" in payload:
        version = int(payload.get("account_version", 1))
        if version > 1:
            raise ValueError(f"This account uses version {version}, but this app supports account version 1.")
        companions = [
            _construct_dataclass(Companion, dict(item))
            for item in list(payload.get("companions", []))
        ]
        for companion in companions:
            companion.equipped_role = "Not equipped"
        builds = [build_from_dict(dict(item)) for item in list(payload.get("builds", []))]
        if not builds:
            builds = [BuildProfile(name="Default Build")]
        names = {b.name for b in builds}
        active = str(payload.get("active_build", builds[0].name))
        if active not in names:
            active = builds[0].name
        return AccountProfile(
            character_class=str(payload.get("character_class", builds[0].stats.character_class)),
            character_level=int(payload.get("character_level", builds[0].stats.character_level)),
            companions=companions,
            total_slots=int(payload.get("total_slots", 7)),
            top_results=int(payload.get("top_results", 20)),
            builds=builds,
            active_build=active,
        )

    legacy = profile_from_dict(payload)
    name = fallback_name.strip() or "Imported Build"
    roles = {
        c.uid: c.equipped_role
        for c in legacy.companions
        if c.equipped_role in {"Main", "Sub"}
    }
    shared = copy.deepcopy(legacy.companions)
    for companion in shared:
        companion.equipped_role = "Not equipped"
    build = BuildProfile(
        name=name,
        stats=copy.deepcopy(legacy.stats),
        target=copy.deepcopy(legacy.target),
        current_roles=roles,
        stats_include_equipped_companions=legacy.stats_include_equipped_companions,
        stat_sources=dict(legacy.stat_sources),
    )
    return AccountProfile(
        character_class=legacy.stats.character_class,
        character_level=legacy.stats.character_level,
        companions=shared,
        total_slots=legacy.total_slots,
        top_results=legacy.top_results,
        builds=[build],
        active_build=name,
    )


def _linspace(start: float, end: float, steps: int) -> List[float]:
    steps = max(1, int(steps))
    if steps == 1 or math.isclose(start, end, rel_tol=0.0, abs_tol=1e-12):
        return [float(start)]
    return [start + (end - start) * i / (steps - 1) for i in range(steps)]


def _team_key(team: Sequence[Companion], main: Companion) -> str:
    return main.uid + "|" + ",".join(sorted(c.uid for c in team))


def _damage_priority(content_mode: str) -> Tuple[str, ...]:
    if content_mode == "Normal farming":
        return MAIN_TIEBREAK["Normal farming"]
    if content_mode == "Arena / neither":
        return MAIN_TIEBREAK["Boss"]
    return MAIN_TIEBREAK.get(content_mode, MAIN_TIEBREAK["Boss"])


_MAIN_PRIORITY_RANK_CACHE: Dict[Tuple[str, ...], Dict[str, int]] = {}


def _main_priority_rank(priorities: Sequence[str]) -> Dict[str, int]:
    """Return a cached name-to-rank mapping for static Main tie-break lists."""
    key = tuple(priorities)
    rank = _MAIN_PRIORITY_RANK_CACHE.get(key)
    if rank is None:
        rank = {name: index for index, name in enumerate(key)}
        _MAIN_PRIORITY_RANK_CACHE[key] = rank
    return rank


def choose_main_advanced(
    team: Sequence[Companion],
    target: TargetProfile,
    options: Optional[MainSelectionOptions] = None,
    forced_uid: str = "",
) -> Companion:
    if not team:
        raise ValueError("Cannot choose a Main from an empty team.")
    options = options or MainSelectionOptions()
    mode = options.mode if options.mode in MAIN_MODES else "Automatic"
    locked_uid = forced_uid or (options.locked_main_uid if mode == "Lock selected Main" else "")
    if locked_uid:
        for companion in team:
            if companion.uid == locked_uid:
                return companion
        raise ValueError("The locked Main companion is not included in this candidate team.")

    if mode == "Prefer utility Main":
        priorities = MAIN_TIEBREAK["Arena / neither"]
    elif mode == "Prefer damage Main":
        priorities = _damage_priority(target.content_mode)
    else:
        priorities = MAIN_TIEBREAK.get(target.content_mode, MAIN_TIEBREAK["Boss"])
    rank = _main_priority_rank(priorities)
    include_measured_bonus = mode != "Equip effects only"
    return min(
        team,
        key=lambda c: (
            -c.main_bonus if include_measured_bonus else 0.0,
            rank.get(c.name, len(priorities)),
            -RARITY_ORDER.get(c.rarity, -1),
            -c.level,
            c.name.casefold(),
        ),
    )


def _main_bonus_enabled(options: Optional[MainSelectionOptions]) -> bool:
    return not options or options.mode != "Equip effects only"


def score_team_advanced(
    stats: CharacterStats,
    target: TargetProfile,
    team: Sequence[Companion],
    options: Optional[MainSelectionOptions] = None,
    forced_uid: str = "",
) -> Tuple[float, Companion]:
    main = choose_main_advanced(team, target, options, forced_uid=forced_uid)
    return (
        fast_team_score(
            stats,
            target,
            team,
            main,
            apply_main_bonus=_main_bonus_enabled(options),
        ),
        main,
    )


def evaluate_team_advanced(
    stats: CharacterStats,
    target: TargetProfile,
    team: Sequence[Companion],
    main: Companion,
    options: Optional[MainSelectionOptions] = None,
) -> Tuple[EffectiveState, Dict[str, float]]:
    if _main_bonus_enabled(options):
        return evaluate_team(stats, target, team, main)
    neutral_main = copy.copy(main)
    neutral_main.main_bonus = 0.0
    return evaluate_team(stats, target, team, neutral_main)


def prepare_advanced_context(
    profile: AdvancedProfile,
) -> Tuple[CharacterStats, EffectiveState, Tuple[Companion, ...], Optional[Companion], List[str], str]:
    if profile.stats_include_equipped_companions:
        current_team, current_main = validate_current_team(profile.companions, profile.total_slots)
        model_stats, warnings = reconstruct_unequipped_stats(profile.stats, current_team)
        reference_state, _ = evaluate_team_advanced(
            model_stats, profile.target, current_team, current_main, profile.main_options
        )
        return model_stats, reference_state, current_team, current_main, warnings, "Current equipped team"
    model_stats = copy.deepcopy(profile.stats)
    empty_state, _ = evaluate_team(model_stats, profile.target, ())
    return model_stats, empty_state, (), None, [], "Unequipped baseline"


def valid_team_count(companion_count: int, total_slots: int, options: Optional[MainSelectionOptions]) -> int:
    if total_slots < 1 or companion_count < total_slots:
        return 0
    if options and options.mode == "Lock selected Main":
        return math.comb(companion_count - 1, total_slots - 1)
    return math.comb(companion_count, total_slots)


def _iter_valid_teams(
    companions: Sequence[Companion],
    total_slots: int,
    options: Optional[MainSelectionOptions],
):
    if options and options.mode == "Lock selected Main":
        locked_uid = options.locked_main_uid
        locked = next((c for c in companions if c.uid == locked_uid), None)
        if locked is None:
            raise ValueError("Choose an owned companion page for Lock selected Main mode.")
        remaining = tuple(c for c in companions if c.uid != locked_uid)
        for others in itertools.combinations(remaining, total_slots - 1):
            yield (locked, *others)
        return
    yield from itertools.combinations(companions, total_slots)


def optimize_companions_advanced(
    profile: AdvancedProfile,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[List[OptimizationResult], int, float]:
    companions = profile.companions
    total_slots = profile.total_slots
    top_n = profile.top_results
    if total_slots < 1 or total_slots > 7:
        raise ValueError("Total companion slots must be from 1 to 7 (one main plus up to six subs).")
    if len(companions) < total_slots:
        raise ValueError(f"You own {len(companions)} pages, but selected {total_slots} total slots.")
    if top_n < 1:
        raise ValueError("Number of results must be at least 1.")

    seen: set[str] = set()
    for companion in companions:
        key = companion_key(companion.name, companion.rarity)
        if key in seen:
            raise ValueError(f"Duplicate page detected: {companion.name} {companion.rarity}.")
        seen.add(key)

    model_stats, reference_state, _current, _current_main, reconstruction_warnings, reference_label = (
        prepare_advanced_context(profile)
    )
    reference = reference_state.score_selected
    if reference <= 0.0:
        raise ValueError("Reference score is zero. Enter a positive displayed Attack value and valid multipliers.")

    total = valid_team_count(len(companions), total_slots, profile.main_options)
    start = time.perf_counter()
    heap: List[Tuple[float, int, Tuple[Companion, ...], Companion]] = []
    serial = 0
    for index, team in enumerate(_iter_valid_teams(companions, total_slots, profile.main_options), start=1):
        if cancel_event is not None and cancel_event.is_set():
            break
        score, main = score_team_advanced(model_stats, profile.target, team, profile.main_options)
        item = (score, serial, team, main)
        serial += 1
        if len(heap) < top_n:
            heapq.heappush(heap, item)
        elif score > heap[0][0]:
            heapq.heapreplace(heap, item)
        if progress is not None and (index == total or index % 5000 == 0):
            progress(index, total)

    results: List[OptimizationResult] = []
    for score, _, team, main in sorted(heap, key=lambda item: item[0], reverse=True):
        state, totals = evaluate_team_advanced(model_stats, profile.target, team, main, profile.main_options)
        if reconstruction_warnings:
            state.warnings = list(reconstruction_warnings) + state.warnings
        subs = tuple(c for c in team if c.uid != main.uid)
        results.append(
            OptimizationResult(
                score=score,
                gain_pct=(score / reference - 1.0) * 100.0,
                main=main,
                subs=subs,
                team=team,
                state=state,
                effect_totals=totals,
                reference_score=reference,
                reference_label=reference_label,
            )
        )
    return results, total, time.perf_counter() - start


def _scenario_values(profile: AdvancedProfile) -> List[Tuple[float, float, float, float]]:
    settings = profile.sensitivity
    vary_basic = settings.vary_basic_attack or (
        settings.basic_attack_steps > 1 and not math.isclose(settings.basic_attack_min, settings.basic_attack_max)
    )
    vary_status = settings.vary_status_uptime or (
        settings.status_uptime_steps > 1 and not math.isclose(settings.status_uptime_min, settings.status_uptime_max)
    )
    basics = (
        _linspace(settings.basic_attack_min, settings.basic_attack_max, settings.basic_attack_steps)
        if vary_basic
        else [profile.stats.basic_attack_share]
    )
    statuses = (
        _linspace(settings.status_uptime_min, settings.status_uptime_max, settings.status_uptime_steps)
        if vary_status
        else [profile.stats.status_uptime]
    )
    defenses = (
        _linspace(settings.target_defense_min, settings.target_defense_max, settings.target_defense_steps)
        if settings.vary_target_defense
        else [profile.target.target_defense]
    )
    evasions = (
        _linspace(settings.target_evasion_min, settings.target_evasion_max, settings.target_evasion_steps)
        if settings.vary_target_evasion
        else [profile.target.target_evasion]
    )
    scenarios = list(itertools.product(basics, statuses, defenses, evasions))
    if len(scenarios) > 250:
        raise ValueError(
            f"Sensitivity grid contains {len(scenarios)} scenarios. Reduce step counts to 250 or fewer."
        )
    return scenarios


def run_sensitivity_analysis(
    profile: AdvancedProfile,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> SensitivityAnalysisResult:
    start = time.perf_counter()
    scenarios = _scenario_values(profile)
    nominal_results, _, _ = optimize_companions_advanced(profile, cancel_event=cancel_event)
    if not nominal_results:
        raise ValueError("No nominal optimization result was produced.")
    nominal = nominal_results[0]
    nominal_key = _team_key(nominal.team, nominal.main)

    wins: Dict[str, int] = {}
    examples: Dict[str, Tuple[Companion, Tuple[Companion, ...]]] = {}
    scenario_records: List[Tuple[str, float, float, float, float, float]] = []
    nominal_regrets: List[float] = []
    total = len(scenarios)

    for index, (basic_share, status_uptime, defense, evasion) in enumerate(scenarios, start=1):
        if cancel_event is not None and cancel_event.is_set():
            break
        scenario_profile = copy.deepcopy(profile)
        scenario_profile.stats.basic_attack_share = basic_share
        scenario_profile.stats.status_uptime = status_uptime
        scenario_profile.target.target_defense = defense
        scenario_profile.target.target_evasion = evasion
        scenario_profile.top_results = 1
        scenario_results, _, _ = optimize_companions_advanced(scenario_profile, cancel_event=cancel_event)
        if not scenario_results:
            continue
        winner = scenario_results[0]
        key = _team_key(winner.team, winner.main)
        wins[key] = wins.get(key, 0) + 1
        examples[key] = (winner.main, winner.team)

        model_stats, _, _, _, _, _ = prepare_advanced_context(scenario_profile)
        nominal_score, _ = score_team_advanced(
            model_stats,
            scenario_profile.target,
            nominal.team,
            scenario_profile.main_options,
            forced_uid=nominal.main.uid,
        )
        regret = max(0.0, (winner.score / nominal_score - 1.0) * 100.0) if nominal_score > 0 else 100.0
        nominal_regrets.append(regret)
        scenario_records.append((key, basic_share, status_uptime, defense, evasion, regret))
        if progress is not None:
            progress(index, total)

    completed = len(scenario_records)
    if completed == 0:
        raise ValueError("Sensitivity analysis was cancelled before any scenario completed.")
    modal_key = max(wins, key=lambda key: wins[key])
    modal_count = wins[modal_key]
    nominal_count = wins.get(nominal_key, 0)
    nominal_win_pct = 100.0 * nominal_count / completed
    nominal_max_regret = max(nominal_regrets) if nominal_regrets else 0.0

    summaries: List[SensitivityTeamSummary] = []
    for key, count in sorted(wins.items(), key=lambda item: (-item[1], item[0])):
        rows = [r for r in scenario_records if r[0] == key]
        main, team = examples[key]
        regrets = [r[5] for r in rows]
        summaries.append(
            SensitivityTeamSummary(
                team_key=key,
                main=main,
                team=team,
                wins=count,
                win_pct=100.0 * count / completed,
                avg_regret_pct=sum(regrets) / len(regrets),
                max_regret_pct=max(regrets),
                basic_min=min(r[1] for r in rows),
                basic_max=max(r[1] for r in rows),
                status_min=min(r[2] for r in rows),
                status_max=max(r[2] for r in rows),
            )
        )

    if nominal_win_pct >= 90.0 and nominal_max_regret < 1.0:
        confidence = "High"
    elif nominal_win_pct >= 60.0 and nominal_max_regret < 3.0:
        confidence = "Moderate"
    else:
        confidence = "Estimate-sensitive"

    influence: Dict[str, str] = {}
    for label, index in (("Basic Attack share", 1), ("Status uptime", 2), ("Target Defense", 3), ("Target Evasion", 4)):
        grouped: Dict[float, set[str]] = {}
        for record in scenario_records:
            grouped.setdefault(record[index], set()).add(record[0])
        distinct_across_values = len({tuple(sorted(v)) for v in grouped.values()})
        if len(grouped) <= 1:
            influence[label] = "Fixed in this analysis"
        elif distinct_across_values <= 1:
            influence[label] = "Did not change the winning team across tested values"
        else:
            influence[label] = f"Changed the winning pattern across {len(grouped)} tested values"

    return SensitivityAnalysisResult(
        scenario_count=completed,
        nominal_result=nominal,
        nominal_win_pct=nominal_win_pct,
        nominal_max_regret_pct=nominal_max_regret,
        modal_team_key=modal_key,
        confidence=confidence,
        summaries=summaries,
        variable_influence=influence,
        elapsed=time.perf_counter() - start,
    )


def compare_all_mains(
    profile: AdvancedProfile,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[List[MainComparisonResult], int, float]:
    start = time.perf_counter()
    model_stats, reference_state, _, _, _, _ = prepare_advanced_context(profile)
    reference = reference_state.score_selected
    companions = profile.companions
    total_teams = math.comb(len(companions), profile.total_slots)
    total_checks = total_teams * profile.total_slots
    best: Dict[str, Tuple[float, Tuple[Companion, ...]]] = {}
    done = 0
    compare_options = copy.deepcopy(profile.main_options)
    if compare_options.mode == "Lock selected Main":
        compare_options.mode = "Automatic"
    for team in itertools.combinations(companions, profile.total_slots):
        if cancel_event is not None and cancel_event.is_set():
            break
        for main in team:
            score, _ = score_team_advanced(model_stats, profile.target, team, compare_options, forced_uid=main.uid)
            previous = best.get(main.uid)
            if previous is None or score > previous[0]:
                best[main.uid] = (score, team)
            done += 1
        if progress is not None and (done == total_checks or done % 5000 == 0):
            progress(done, total_checks)

    rows: List[MainComparisonResult] = []
    by_uid = {c.uid: c for c in companions}
    for uid, (score, team) in best.items():
        main = by_uid[uid]
        rows.append(
            MainComparisonResult(
                main=main,
                score=score,
                gain_pct=(score / reference - 1.0) * 100.0,
                subs=tuple(c for c in team if c.uid != uid),
                team=team,
            )
        )
    rows.sort(key=lambda row: row.score, reverse=True)
    return rows, total_checks, time.perf_counter() - start


def calculate_upgrade_values(
    profile: AdvancedProfile,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[List[UpgradeValueResult], int, float]:
    start = time.perf_counter()
    model_stats, _, _, _, _, _ = prepare_advanced_context(profile)
    eligible = {
        c.uid: c
        for c in profile.companions
        if c.source == "formula" and c.level < RARITY_MAX_LEVEL.get(c.rarity, 300)
    }
    if not eligible:
        return [], 0, time.perf_counter() - start

    baseline_score = -math.inf
    baseline_team: Tuple[Companion, ...] = ()
    baseline_main: Optional[Companion] = None
    best_upgrade_score: Dict[str, float] = {uid: -math.inf for uid in eligible}
    best_upgrade_team: Dict[str, Tuple[Companion, ...]] = {}
    best_upgrade_main: Dict[str, Companion] = {}
    total = valid_team_count(len(profile.companions), profile.total_slots, profile.main_options)

    for index, team in enumerate(_iter_valid_teams(profile.companions, profile.total_slots, profile.main_options), start=1):
        if cancel_event is not None and cancel_event.is_set():
            break
        score, main = score_team_advanced(model_stats, profile.target, team, profile.main_options)
        if score > baseline_score:
            baseline_score, baseline_team, baseline_main = score, team, main
        for pos, companion in enumerate(team):
            if companion.uid not in eligible:
                continue
            upgraded = copy.copy(companion)
            upgraded.level += 1
            upgraded.effect_type, upgraded.effect_value = companion_effect(
                upgraded.name, upgraded.rarity, upgraded.level
            )
            upgraded_team = list(team)
            upgraded_team[pos] = upgraded
            upgraded_tuple = tuple(upgraded_team)
            upgraded_score, upgraded_main = score_team_advanced(
                model_stats, profile.target, upgraded_tuple, profile.main_options
            )
            if upgraded_score > best_upgrade_score[companion.uid]:
                best_upgrade_score[companion.uid] = upgraded_score
                best_upgrade_team[companion.uid] = upgraded_tuple
                best_upgrade_main[companion.uid] = upgraded_main
        if progress is not None and (index == total or index % 2000 == 0):
            progress(index, total)

    if not math.isfinite(baseline_score) or baseline_main is None:
        raise ValueError("No valid team was available for upgrade analysis.")
    baseline_uids = {c.uid for c in baseline_team}
    results: List[UpgradeValueResult] = []
    for uid, companion in eligible.items():
        candidate_score = max(baseline_score, best_upgrade_score.get(uid, -math.inf))
        team = best_upgrade_team.get(uid, baseline_team)
        main = best_upgrade_main.get(uid, baseline_main)
        _, next_effect = companion_effect(companion.name, companion.rarity, companion.level + 1)
        results.append(
            UpgradeValueResult(
                companion=companion,
                next_level=companion.level + 1,
                current_effect=companion.effect_value,
                next_effect=next_effect,
                improvement_pct=(candidate_score / baseline_score - 1.0) * 100.0,
                resulting_main=main,
                resulting_team=team,
                enters_best_team=uid in {c.uid for c in team} or uid in baseline_uids,
            )
        )
    results.sort(key=lambda row: (-row.improvement_pct, row.companion.name, RARITY_ORDER.get(row.companion.rarity, 99)))
    return results, total, time.perf_counter() - start


def assess_profile_readiness(profile: AdvancedProfile) -> ReadinessReport:
    issues: List[ReadinessIssue] = []
    core_complete = True
    current_complete = True
    assumptions_complete = True

    if profile.stats.attack <= 0:
        issues.append(ReadinessIssue("error", "Attack must be positive."))
        core_complete = False
    if profile.stats.max_damage <= 0:
        issues.append(ReadinessIssue("error", "Max Damage Multiplier must be positive."))
        core_complete = False

    conflicts = [key for key, source in profile.stat_sources.items() if source == "conflict"]
    if conflicts:
        issues.append(ReadinessIssue("error", "Resolve screenshot conflicts: " + ", ".join(OCR_FIELD_DISPLAY.get(k, k) for k in conflicts)))
        core_complete = False

    try:
        if profile.stats_include_equipped_companions:
            validate_current_team(profile.companions, profile.total_slots)
    except ValueError as exc:
        issues.append(ReadinessIssue("error", str(exc)))
        current_complete = False

    if profile.main_options.mode == "Lock selected Main":
        if not profile.main_options.locked_main_uid or not any(
            c.uid == profile.main_options.locked_main_uid for c in profile.companions
        ):
            issues.append(ReadinessIssue("error", "Lock selected Main mode needs an owned companion page."))
            current_complete = False

    assumption_fields = ("basic_attack_share", "status_uptime", "current_main_stat_pct", "flat_attack_scaling_pct")
    uncovered = [
        key for key in assumption_fields
        if profile.stat_sources.get(key, "uncovered") == "uncovered"
    ]
    if uncovered:
        assumptions_complete = False
        issues.append(ReadinessIssue(
            "warning",
            "Unverified assumptions remain: " + ", ".join(OCR_FIELD_DISPLAY.get(k, k) for k in uncovered) + ". Sensitivity analysis can test the first two automatically.",
        ))

    if profile.stats.status_damage > 0 and profile.stats.status_uptime <= 0:
        issues.append(ReadinessIssue("info", "Status Damage is present but Status uptime is 0%; Status Damage companions will receive no modeled value."))
    if profile.target.content_mode == "Boss" and profile.stats.boss_damage == 0:
        issues.append(ReadinessIssue("info", "Boss mode has 0% displayed Boss Damage. This can be legitimate, but confirm the boss preset is active."))
    if any(c.effect_type == "accuracy" for c in profile.companions) and not profile.target.use_accuracy_approximation:
        issues.append(ReadinessIssue("info", "Accuracy companions are owned, but Accuracy/Evasion scoring is disabled. They will be valued only by Main preference, not hit rate."))
    if any(c.effect_type == "main_stat_pct" for c in profile.companions):
        if profile.stats.total_main_stat <= 0 or profile.stats.current_main_stat_pct <= 0:
            issues.append(ReadinessIssue("warning", "Buccaneer/Main Stat % pages need Total Main Stat and Current Main Stat % for accurate scoring."))
            assumptions_complete = False
    if profile.stats.flat_attack_scaling_pct > 500:
        issues.append(ReadinessIssue("warning", f"Flat Attack scaling is {profile.stats.flat_attack_scaling_pct:g}%. That is unusually high; verify this is an Attack percentage rather than a flat Attack value."))
        assumptions_complete = False
    if not (0 <= profile.stats.basic_attack_share <= 100):
        issues.append(ReadinessIssue("error", "Basic Attack share must be from 0% to 100%."))
        assumptions_complete = False
    if not (0 <= profile.stats.status_uptime <= 100):
        issues.append(ReadinessIssue("error", "Status uptime must be from 0% to 100%."))
        assumptions_complete = False

    if any(issue.severity == "error" for issue in issues):
        rating = "Not ready"
    elif any(issue.severity == "warning" for issue in issues):
        rating = "Ready with assumptions"
    else:
        rating = "Ready"
    return ReadinessReport(rating, issues, core_complete, current_complete, assumptions_complete)


# ---------------------------------------------------------------------------
# Version 2 interface: shared account, multiple builds, and analysis tools
# ---------------------------------------------------------------------------

class AdvancedOptimizerApp(OptimizerApp):
    def __init__(self):
        self.account_builds: Dict[str, BuildProfile] = {}
        self.active_build_name = "Default Build"
        self._build_syncing = True
        self._readiness_after_id: Optional[str] = None
        self.locked_main_display_to_uid: Dict[str, str] = {}
        self.last_sensitivity_result: Optional[SensitivityAnalysisResult] = None
        self.last_sensitivity_build: str = ""
        self.main_comparison_results: List[MainComparisonResult] = []
        self.upgrade_results: List[UpgradeValueResult] = []
        self.current_job_kind = ""
        self._help_window: Optional[HelpBook] = None
        self._bug_report_window: Optional[BugReportDialog] = None
        self._roster_role_menu: Optional[tk.Menu] = None
        super().__init__()
        self.bind_all("<F1>", lambda _event: self.show_help(), add="+")
        self.bind_all("<Control-Shift-B>", lambda _event: self.show_bug_report(), add="+")
        if not self.account_builds:
            try:
                default = self._snapshot_current_build("Default Build")
            except Exception:
                default = BuildProfile(name="Default Build")
            self.account_builds = {default.name: default}
            self.active_build_name = default.name
        self._build_syncing = False
        self._refresh_build_selector()
        self._refresh_locked_main_choices()
        self._update_main_mode_fields()
        self._refresh_readiness_panel()

    def _create_variables(self):
        OptimizerApp._create_variables(self)
        self.build_selector_var = tk.StringVar(value="Default Build")
        self.main_mode_var = tk.StringVar(value="Automatic")
        self.locked_main_var = tk.StringVar(value="")
        defaults = SensitivitySettings()
        self.sensitivity_vars: Dict[str, object] = {
            "vary_basic_attack": tk.BooleanVar(value=defaults.vary_basic_attack),
            "basic_attack_min": tk.StringVar(value=""),
            "basic_attack_max": tk.StringVar(value=""),
            "basic_attack_steps": tk.StringVar(value=str(defaults.basic_attack_steps)),
            "vary_status_uptime": tk.BooleanVar(value=defaults.vary_status_uptime),
            "status_uptime_min": tk.StringVar(value=""),
            "status_uptime_max": tk.StringVar(value=""),
            "status_uptime_steps": tk.StringVar(value=str(defaults.status_uptime_steps)),
            "vary_target_defense": tk.BooleanVar(value=defaults.vary_target_defense),
            "target_defense_min": tk.StringVar(value=""),
            "target_defense_max": tk.StringVar(value=""),
            "target_defense_steps": tk.StringVar(value=str(defaults.target_defense_steps)),
            "vary_target_evasion": tk.BooleanVar(value=defaults.vary_target_evasion),
            "target_evasion_min": tk.StringVar(value=""),
            "target_evasion_max": tk.StringVar(value=""),
            "target_evasion_steps": tk.StringVar(value=str(defaults.target_evasion_steps)),
        }
        self.readiness_summary_var = tk.StringVar(value="Checking profile readiness…")
        self.sensitivity_summary_var = tk.StringVar(value="Run sensitivity analysis to test uncertain assumptions.")
        self.main_summary_var = tk.StringVar(value="Compare the best Sub team for every possible Main companion.")
        self.upgrade_summary_var = tk.StringVar(value="Rank the modeled benefit of each companion's next level.")
        self.main_mode_var.trace_add("write", lambda *_: self._update_main_mode_fields())

    def _build_ui(self):
        """Build one scrollable, image-backed Companion Optimization workspace."""
        self._unified_workspace = True
        self._build_header()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(10, 8))
        self.workspace_tab = ttk.Frame(self.notebook, style="App.TFrame")
        self.notebook.add(self.workspace_tab, text="Companion Optimization")
        self.workspace_tab.columnconfigure(0, weight=1)
        self.workspace_tab.rowconfigure(0, weight=1)

        self.workspace_canvas = tk.Canvas(
            self.workspace_tab,
            background=COLORS["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.workspace_scrollbar = ttk.Scrollbar(
            self.workspace_tab,
            orient="vertical",
            command=self._workspace_yview,
        )
        self.workspace_canvas.configure(yscrollcommand=self.workspace_scrollbar.set)
        self.workspace_canvas.grid(row=0, column=0, sticky="nsew")
        self.workspace_scrollbar.grid(row=0, column=1, sticky="ns")
        self._workspace_bg_item = self.workspace_canvas.create_image(0, 0, anchor="nw")
        self._workspace_bg_photo = None
        self._workspace_resize_after = None
        self._workspace_windows: Dict[str, int] = {}
        self._workspace_result_y = 0

        # These names remain for the established optimization and analysis logic.
        self.character_tab = self.workspace_tab
        self.companion_tab = self.workspace_tab
        self.analysis_tab = self.workspace_tab

        self._build_workspace_stat_widgets()
        self._build_workspace_companion_widget()
        self._build_workspace_planning_widget()
        self._build_workspace_results_widget()

        self.workspace_canvas.bind("<Configure>", self._schedule_workspace_layout, add="+")
        self.workspace_canvas.bind_all("<MouseWheel>", self._workspace_mousewheel, add="+")
        self.workspace_canvas.bind_all("<Button-4>", lambda event: self._workspace_linux_wheel(event, -1), add="+")
        self.workspace_canvas.bind_all("<Button-5>", lambda event: self._workspace_linux_wheel(event, 1), add="+")
        self._build_status_bar()
        self.after(120, self._layout_workspace)

    def _on_root_resize_for_character_tab(self, _event=None):
        # Only the single Canvas background is resized. The floating widgets are
        # normal native controls and are never rebuilt during maximize/restore.
        self._schedule_workspace_layout()

    def _on_notebook_tab_changed_for_character_tab(self, _event=None):
        self._schedule_workspace_layout()

    def _widget_is_inside_workspace(self, widget) -> bool:
        current = widget
        while current is not None:
            if current is self.workspace_canvas:
                return True
            try:
                current = current.master
            except Exception:
                return False
        return False

    def _workspace_mousewheel(self, event):
        if not self._widget_is_inside_workspace(event.widget):
            return
        if isinstance(event.widget, (tk.Text, ttk.Treeview, ttk.Combobox)):
            return
        delta = -1 if event.delta > 0 else 1
        self.workspace_canvas.yview_scroll(delta * 3, "units")
        self._position_workspace_background()
        return "break"

    def _workspace_linux_wheel(self, event, direction: int):
        if not self._widget_is_inside_workspace(event.widget):
            return
        if isinstance(event.widget, (tk.Text, ttk.Treeview, ttk.Combobox)):
            return
        self.workspace_canvas.yview_scroll(direction * 3, "units")
        self._position_workspace_background()
        return "break"

    def _workspace_yview(self, *args):
        self.workspace_canvas.yview(*args)
        self._position_workspace_background()

    def _schedule_workspace_layout(self, _event=None):
        if self._workspace_resize_after is not None:
            try:
                self.after_cancel(self._workspace_resize_after)
            except tk.TclError:
                pass
        self._workspace_resize_after = self.after(120, self._layout_workspace)

    def _position_workspace_background(self):
        if not hasattr(self, "workspace_canvas"):
            return
        try:
            x = self.workspace_canvas.canvasx(0)
            y = self.workspace_canvas.canvasy(0)
            self.workspace_canvas.coords(self._workspace_bg_item, x, y)
            self.workspace_canvas.tag_lower(self._workspace_bg_item)
        except tk.TclError:
            pass

    def _refresh_workspace_background(self):
        if Image is None or ImageTk is None or self._background_original is None:
            return
        width = max(1, self.workspace_canvas.winfo_width())
        height = max(1, self.workspace_canvas.winfo_height())
        if width < 20 or height < 20:
            return
        source = self._background_original
        scale = max(width / source.width, height / source.height)
        resized = source.resize(
            (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
            Image.LANCZOS,
        )
        left = max(0, (resized.width - width) // 2)
        top = max(0, (resized.height - height) // 2)
        fitted = resized.crop((left, top, left + width, top + height))
        # Match the restrained backdrop used by the successful 2.4 layout.
        fitted = Image.blend(fitted, Image.new("RGBA", fitted.size, (248, 252, 255, 255)), 0.24)
        photo = ImageTk.PhotoImage(fitted)
        self._workspace_bg_photo = photo
        self.workspace_canvas.itemconfigure(self._workspace_bg_item, image=photo)
        self._position_workspace_background()

    def _canvas_window(self, name: str, widget) -> int:
        item = self._workspace_windows.get(name)
        if item is None:
            item = self.workspace_canvas.create_window(0, 0, window=widget, anchor="nw")
            self._workspace_windows[name] = item
        return item

    def _layout_workspace(self):
        """Lay out one fixed-proportion design surface and center it.

        Earlier unified builds switched between one- and two-column companion
        layouts based on a width breakpoint.  That made the relative geometry
        change dramatically between windowed and maximized states.  The 2.5.4
        workspace always uses the same reference composition: two stat columns
        on the left and two companion-class columns on the right.  The complete
        composition is centered as a unit; smaller windows scroll rather than
        reflowing individual sections.
        """
        self._workspace_resize_after = None
        if not hasattr(self, "workspace_canvas"):
            return
        try:
            self.update_idletasks()
            viewport_w = max(1, self.workspace_canvas.winfo_width())
            viewport_h = max(1, self.workspace_canvas.winfo_height())

            outer_margin = 24
            stat_gap = 16
            section_gap = 28
            group_gap = 10
            top_y = 24

            left_stat_width = max(widget.winfo_reqwidth() for widget in self._workspace_stat_left_widgets)
            right_stat_width = max(widget.winfo_reqwidth() for widget in self._workspace_stat_right_widgets)
            stats_width = left_stat_width + stat_gap + right_stat_width

            group_width = max(widget.winfo_reqwidth() for widget in self._workspace_companion_groups)
            companion_columns = 2
            companion_grid_width = group_width * companion_columns + group_gap

            page_content_width = stats_width + section_gap + companion_grid_width
            minimum_page_width = page_content_width + outer_margin * 2
            page_width = max(viewport_w, minimum_page_width)

            # Center the complete design surface, not each region separately.
            content_left = max(outer_margin, (page_width - page_content_width) // 2)
            stats_x = content_left
            companion_x = stats_x + stats_width + section_gap

            left_y = top_y
            for index, widget in enumerate(self._workspace_stat_left_widgets):
                item = self._canvas_window(f"stat_left_{index}", widget)
                self.workspace_canvas.coords(item, stats_x, left_y)
                left_y += widget.winfo_reqheight() + 10

            right_x = stats_x + left_stat_width + stat_gap
            right_y = top_y
            for index, widget in enumerate(self._workspace_stat_right_widgets):
                item = self._canvas_window(f"stat_right_{index}", widget)
                self.workspace_canvas.coords(item, right_x, right_y)
                right_y += widget.winfo_reqheight() + 10

            stats_bottom = max(left_y, right_y)

            companion_y = top_y
            header_item = self._canvas_window("companion_header", self.workspace_companion_outer)
            self.workspace_canvas.coords(header_item, companion_x, companion_y)
            self.workspace_canvas.itemconfigure(header_item, width=companion_grid_width)
            companion_y += self.workspace_companion_outer.winfo_reqheight() + 7

            grid_y = companion_y
            for row_start in range(0, len(self._workspace_companion_groups), companion_columns):
                row_widgets = self._workspace_companion_groups[row_start:row_start + companion_columns]
                row_height = max(widget.winfo_reqheight() for widget in row_widgets)
                for column, widget in enumerate(row_widgets):
                    index = row_start + column
                    x = companion_x + column * (group_width + group_gap)
                    item = self._canvas_window(f"companion_group_{index}", widget)
                    self.workspace_canvas.coords(item, x, grid_y)
                    self.workspace_canvas.itemconfigure(item, width=group_width)
                grid_y += row_height + 8

            companion_bottom = grid_y
            results_y = max(stats_bottom, companion_bottom) + 18

            planning_item = self._canvas_window("planning", self.workspace_planning_outer)
            self.workspace_canvas.coords(planning_item, content_left, results_y)
            self.workspace_canvas.itemconfigure(planning_item, width=page_content_width)

            results_y += self.workspace_planning_outer.winfo_reqheight() + 16
            results_item = self._canvas_window("results", self.workspace_results_outer)
            self.workspace_canvas.coords(results_item, content_left, results_y)
            self.workspace_canvas.itemconfigure(results_item, width=page_content_width)
            self._workspace_result_y = results_y

            total_height = results_y + self.workspace_results_outer.winfo_reqheight() + 36
            self.workspace_canvas.configure(scrollregion=(0, 0, page_width, total_height))

            # Keep the centered surface visible if a previous resize left the
            # canvas horizontally offset.  There is intentionally no responsive
            # column switch anymore.
            if page_width <= viewport_w:
                self.workspace_canvas.xview_moveto(0.0)
            else:
                # xview_moveto expects a fraction of the complete scrollregion,
                # not a fraction of only the scrollable remainder.
                visible_left = max(0.0, (page_width - viewport_w) / 2.0)
                self.workspace_canvas.xview_moveto(visible_left / max(1.0, float(page_width)))

            self._refresh_workspace_background()
        except (tk.TclError, AttributeError, ValueError):
            return

    def _build_workspace_stat_widgets(self):
        canvas = self.workspace_canvas
        self._workspace_stat_left_widgets = []
        self._workspace_stat_right_widgets = []

        character_outer, character = self._make_maple_section(canvas, "Character Stat")
        character.columnconfigure(0, minsize=170)
        self._form_combo(character, 0, "Class", self.stat_vars["character_class"], CLASS_NAMES)
        self._form_entry(character, 1, "Character level", self.stat_vars["character_level"])
        self._form_entry(character, 2, "Total companion slots", self.total_slots_var)
        self._form_entry(character, 3, "Results to keep", self.top_results_var)
        include_check = ttk.Checkbutton(
            character,
            text="Displayed stats include equipped companions",
            variable=self.stats_include_equipped_var,
        )
        include_check.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(7, 2))
        self._workspace_stat_left_widgets.append(character_outer)

        auto_holder = tk.Frame(canvas, background=COLORS["bg"], borderwidth=0, highlightthickness=0)
        self._build_autoassign_strip(auto_holder).pack()
        self._workspace_stat_left_widgets.append(auto_holder)

        content_outer, content = self._make_maple_section(canvas, "Content-specific Damage")
        content.columnconfigure(0, minsize=170)
        for idx, (label, key) in enumerate((
            ("Normal Monster Damage %", "normal_damage"),
            ("Boss Damage %", "boss_damage"),
            ("Basic Attack Damage %", "basic_attack_damage"),
            ("Skill Damage %", "skill_damage"),
            ("Basic Attack share %", "basic_attack_share"),
            ("Status Damage %", "status_damage"),
            ("Status uptime %", "status_uptime"),
        )):
            self._form_entry(content, idx, label, self.stat_vars[key], field_key=key)
        self._workspace_stat_left_widgets.append(content_outer)

        combat_outer, combat = self._make_maple_section(canvas, "Combat Stat")
        combat.columnconfigure(0, minsize=170)
        for idx, (label, key) in enumerate((
            ("Attack", "attack"),
            ("Damage %", "damage"),
            ("Stat Prop Damage %", "stat_prop_damage"),
            ("Critical Rate %", "crit_rate"),
            ("Critical Damage %", "crit_damage"),
            ("Attack Speed %", "attack_speed"),
            ("Min Damage Multiplier %", "min_damage"),
            ("Max Damage Multiplier %", "max_damage"),
        )):
            self._form_entry(combat, idx, label, self.stat_vars[key], field_key=key)
        self._workspace_stat_right_widgets.append(combat_outer)

        advanced_outer, advanced = self._make_maple_section(canvas, "Advanced Multipliers")
        advanced.columnconfigure(0, minsize=170)
        for idx, (label, key) in enumerate((
            ("Damage Amplification %", "damage_amp"),
            ("Final Damage %", "final_damage"),
            ("Defense Penetration %", "defense_pen"),
            ("Accuracy", "accuracy"),
            ("Total Main Stat", "total_main_stat"),
            ("Current Main Stat %", "current_main_stat_pct"),
            ("Flat Attack scaling %", "flat_attack_scaling_pct"),
        )):
            self._form_entry(advanced, idx, label, self.stat_vars[key], field_key=key)
        self._workspace_stat_right_widgets.append(advanced_outer)

        target_outer, target = self._make_maple_section(canvas, "Optimization Target")
        target.columnconfigure(0, minsize=170)
        ttk.Label(target, text="Content", style="WhitePanel.TLabel").grid(row=0, column=0, sticky="w", padx=(10, 8), pady=5)
        ttk.Combobox(target, textvariable=self.target_vars["content_mode"], values=CONTENT_MODES, state="readonly", width=17).grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(target, text="Normal share in Mixed %", style="WhitePanel.TLabel").grid(row=1, column=0, sticky="w", padx=(10, 8), pady=5)
        self.normal_weight_entry = ttk.Entry(target, textvariable=self.target_vars["normal_weight"], width=15)
        self.normal_weight_entry.grid(row=1, column=1, sticky="w", pady=5)
        ttk.Label(target, text="Target Defense", style="WhitePanel.TLabel").grid(row=2, column=0, sticky="w", padx=(10, 8), pady=5)
        ttk.Entry(target, textvariable=self.target_vars["target_defense"], width=15).grid(row=2, column=1, sticky="w", pady=5)
        ttk.Label(target, text="Target Evasion", style="WhitePanel.TLabel").grid(row=3, column=0, sticky="w", padx=(10, 8), pady=5)
        ttk.Entry(target, textvariable=self.target_vars["target_evasion"], width=15).grid(row=3, column=1, sticky="w", pady=5)
        self.accuracy_check = ttk.Checkbutton(
            target,
            text="Approximate Accuracy/Evasion miss rate",
            variable=self.target_vars["use_accuracy_approximation"],
        )
        self.accuracy_check.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(7, 2))
        self._workspace_stat_right_widgets.append(target_outer)

        # Retained for compatibility with code that expects the previous list.
        self._workspace_left_widgets = self._workspace_stat_left_widgets + self._workspace_stat_right_widgets

    def _build_workspace_companion_widget(self):
        self._load_roster_asset_manifest()

        header = tk.Frame(self.workspace_canvas, background="#050505", borderwidth=0, highlightthickness=0, height=34)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="Companion Collection",
            background="#050505",
            foreground="#f1d54b",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="left", padx=12)
        tk.Label(
            header,
            text="Portrait: owned  •  level chip: edit  •  role badge: choose Main/Sub",
            background="#050505",
            foreground="#d8e4ee",
        ).pack(side="left", padx=(18, 8))
        ttk.Label(header, textvariable=self.roster_count_var, style="DarkHeader.TLabel").pack(side="right", padx=12)
        self.workspace_companion_outer = header
        self._workspace_companion_groups = []

        # Keep the existing detail variables available to the data/update logic,
        # but remove the redundant visible detail and role-control panel.
        self.companion_detail_title_var = tk.StringVar(value="Select a portrait")
        self.companion_detail_state_var = tk.StringVar(value="")
        self.companion_detail_level_var = tk.StringVar(value="")
        self.companion_detail_role_var = tk.StringVar(value="")
        self.companion_detail_effect_var = tk.StringVar(value="")
        self.companion_detail_value_var = tk.StringVar(value="")
        self.companion_detail_asset_var = tk.StringVar(value="")
        self.companion_detail_main_bonus_entry = ttk.Entry(self.workspace_tab, width=1)

        for name in COMPANION_DISPLAY_ORDER:
            group_outer, group = self._make_compact_maple_section(self.workspace_canvas, name)
            group.configure(padx=4, pady=4)
            self._workspace_companion_groups.append(group_outer)
            rarities = RARITIES if name in COMMON_AVAILABLE else RARITIES[1:]
            for page_index, rarity in enumerate(rarities):
                key = companion_key(name, rarity)
                try:
                    default_effect, default_value = companion_effect(name, rarity, 1)
                except ValueError:
                    continue
                owned_var = tk.BooleanVar(value=False)
                level_var = tk.StringVar(value="1")
                role_var = tk.StringVar(value="Not equipped")
                effect_label_var = tk.StringVar(value=EFFECT_LABELS[default_effect])
                effect_value_var = tk.StringVar(value=f"{default_value:g}")
                main_bonus_var = tk.StringVar(value="0")
                self.roster_vars[key] = {
                    "name": name,
                    "rarity": rarity,
                    "formula": True,
                    "owned": owned_var,
                    "level": level_var,
                    "role": role_var,
                    "effect_label": effect_label_var,
                    "effect_value": effect_value_var,
                    "main_bonus": main_bonus_var,
                }
                tile = CompanionTile(
                    group,
                    key=key,
                    name=name,
                    rarity=rarity,
                    color_image=self._load_roster_photo(name, rarity, False),
                    gray_image=self._load_roster_photo(name, rarity, True),
                    placeholder=self._asset_is_placeholder(name, rarity),
                    on_select=self._select_roster_tile,
                    on_toggle=self._toggle_roster_owned_from_tile,
                    on_role=self._show_roster_role_menu,
                    on_level=self._commit_roster_level_from_tile,
                )
                tile.grid(row=0, column=page_index, padx=(0, 2), pady=0, sticky="nw")
                self.roster_tiles[key] = tile
                self.roster_widgets[key] = {"tile": tile}
                level_var.trace_add("write", lambda *_args, k=key: self._on_roster_level_changed(k))
                role_var.trace_add("write", lambda *_args, k=key: self._on_roster_role_changed(k))
                effect_label_var.trace_add("write", lambda *_args: self._schedule_autosave())
                effect_value_var.trace_add("write", lambda *_args: self._schedule_autosave())
                main_bonus_var.trace_add("write", lambda *_args, k=key: self._on_roster_detail_value_changed(k))

        if self.roster_vars:
            self._select_roster_tile(next(iter(self.roster_vars)))
        self._refresh_all_roster_tiles()

    def _build_workspace_planning_widget(self):
        outer, panel = self._make_maple_section(self.workspace_canvas, "Optimization Settings & Robustness")
        self.workspace_planning_outer = outer
        panel.columnconfigure(19, weight=1)
        ttk.Label(panel, text="Main", style="WhitePanel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 5), pady=3)
        ttk.Combobox(panel, textvariable=self.main_mode_var, values=MAIN_MODES, state="readonly", width=17).grid(row=0, column=1, sticky="w", padx=(0, 10), pady=3)
        ttk.Label(panel, text="Locked", style="WhitePanel.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 5), pady=3)
        self.locked_main_combo = ttk.Combobox(panel, textvariable=self.locked_main_var, values=(), state="disabled", width=20)
        self.locked_main_combo.grid(row=0, column=3, columnspan=2, sticky="w", padx=(0, 12), pady=3)
        self.main_compare_button = ttk.Button(panel, text="Compare Mains", command=self.start_main_comparison)
        self.main_compare_button.grid(row=0, column=16, sticky="e", padx=3)
        self.upgrade_button = ttk.Button(panel, text="Plan Upgrades", command=self.start_upgrade_analysis)
        self.upgrade_button.grid(row=0, column=17, sticky="e", padx=3)
        col = 0
        for label, prefix in (("Basic attack %", "basic_attack"), ("Status uptime %", "status_uptime"), ("Defense", "target_defense"), ("Evasion", "target_evasion")):
            ttk.Label(panel, text=label, style="WhitePanel.TLabel").grid(row=1, column=col, sticky="w", padx=(0, 4), pady=3)
            ttk.Entry(panel, textvariable=self.sensitivity_vars[f"{prefix}_min"], width=6).grid(row=1, column=col + 1, pady=3)
            ttk.Label(panel, text="–", style="WhitePanel.TLabel").grid(row=1, column=col + 2, padx=3)
            ttk.Entry(panel, textvariable=self.sensitivity_vars[f"{prefix}_max"], width=6).grid(row=1, column=col + 3, pady=3, padx=(0, 10))
            col += 4
        ttk.Label(panel, text="Leave ranges blank to skip robustness testing.", style="WhitePanel.TLabel").grid(row=2, column=0, columnspan=7, sticky="w", pady=(5, 1))
        ttk.Label(panel, textvariable=self.readiness_summary_var, style="WhitePanel.TLabel", wraplength=420).grid(row=2, column=8, columnspan=4, sticky="w", padx=(10, 0), pady=(5, 1))
        self.sensitivity_summary_label = ttk.Label(panel, textvariable=self.sensitivity_summary_var, style="WhitePanel.TLabel", wraplength=520)
        self.sensitivity_summary_label.grid(row=2, column=12, columnspan=7, sticky="w", padx=(10, 0), pady=(5, 1))
        self.readiness_text = tk.Text(panel, height=1, width=1)
        self.readiness_text.configure(state="disabled")
        self.unified_analysis_var = tk.StringVar(value="")

    def _build_workspace_results_widget(self):
        outer, panel = self._make_maple_section(self.workspace_canvas, "Optimization Results")
        self.workspace_results_outer = outer
        self.results_tab = panel
        panel.columnconfigure(0, weight=3)
        panel.columnconfigure(1, weight=2)
        panel.rowconfigure(1, weight=1)
        controls = tk.Frame(panel, background="#ffffff")
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.results_summary_label = ttk.Label(controls, text="Run the optimizer to compare every valid team.", style="WhitePanel.TLabel")
        self.results_summary_label.pack(side="left")
        self.cancel_button = ttk.Button(controls, text="Cancel", style="Danger.TButton", command=self.cancel_optimization, state="disabled")
        self.cancel_button.pack(side="right")
        ttk.Button(controls, text="Copy selected report", command=self.copy_selected_report).pack(side="right", padx=6)
        ttk.Button(controls, text="Export results CSV", command=self.export_results_csv).pack(side="right", padx=6)

        left = tk.Frame(panel, background="#ffffff")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        columns = ("rank", "gain", "main", "subs", "score")
        self.results_tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse", height=14)
        result_headings = {"rank": "#", "gain": "Gain", "main": "Main", "subs": "Sub companions", "score": "Relative score"}
        result_widths = {"rank": 42, "gain": 82, "main": 160, "subs": 430, "score": 110}
        for col in columns:
            self.results_tree.heading(col, text=result_headings[col])
            self.results_tree.column(col, width=result_widths[col], minwidth=40, anchor="w")
        self.results_tree.column("rank", anchor="center")
        self.results_tree.column("gain", anchor="e")
        self.results_tree.column("score", anchor="e")
        result_scroll = ttk.Scrollbar(left, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=result_scroll.set)
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        result_scroll.grid(row=0, column=1, sticky="ns")
        self.results_tree.bind("<<TreeviewSelect>>", self._show_selected_result)

        right = tk.Frame(panel, background="#ffffff", highlightbackground="#9fb2c4", highlightthickness=1, padx=8, pady=8)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.result_detail = tk.Text(
            right,
            height=18,
            wrap="word",
            background="#ffffff",
            foreground=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["selection"],
            relief="flat",
            borderwidth=0,
            padx=8,
            pady=8,
            font=("TkFixedFont", 10),
        )
        detail_scroll = ttk.Scrollbar(right, orient="vertical", command=self.result_detail.yview)
        self.result_detail.configure(yscrollcommand=detail_scroll.set)
        self.result_detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll.grid(row=0, column=1, sticky="ns")
        self.result_detail.insert("1.0", self._empty_result_text())
        self.result_detail.configure(state="disabled")

    def _build_header(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 12))
        header.pack(fill="x")
        text_frame = ttk.Frame(header, style="Header.TFrame")
        text_frame.pack(side="left", fill="x", expand=True)
        ttk.Label(text_frame, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            text_frame,
            text="Shared account • multiple content builds • exact search • robustness and upgrade analysis",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        build_bar = ttk.Frame(text_frame, style="Header.TFrame")
        build_bar.pack(anchor="w", pady=(8, 0))
        ttk.Label(build_bar, text="Active build", style="PanelMuted.TLabel").pack(side="left", padx=(0, 7))
        self.build_selector = ttk.Combobox(
            build_bar,
            textvariable=self.build_selector_var,
            values=(),
            state="readonly",
            width=24,
        )
        self.build_selector.pack(side="left")
        self.build_selector.bind("<<ComboboxSelected>>", self._on_build_selected)
        ttk.Button(build_bar, text="New build", command=self.new_build).pack(side="left", padx=(7, 3))
        ttk.Button(build_bar, text="Duplicate", command=self.duplicate_build).pack(side="left", padx=3)
        ttk.Button(build_bar, text="Rename", command=self.rename_build).pack(side="left", padx=3)
        ttk.Button(build_bar, text="Delete", command=self.delete_build).pack(side="left", padx=3)

        controls = ttk.Frame(header, style="Header.TFrame")
        controls.pack(side="right")
        ttk.Label(controls, textvariable=self.profile_title_var, style="PanelMuted.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="e", pady=(0, 4)
        )
        ttk.Button(controls, text="New account", command=self.new_profile).grid(row=1, column=0, padx=3)
        ttk.Button(controls, text="Load", command=self.load_profile).grid(row=1, column=1, padx=3)
        ttk.Button(controls, text="Save", command=self.save_profile).grid(row=1, column=2, padx=3)
        ttk.Button(controls, text="Save As…", command=lambda: self.save_profile(save_as=True)).grid(row=1, column=3, padx=3)
        ttk.Button(controls, text="Help", command=self.show_help).grid(row=1, column=4, padx=3)
        ttk.Button(controls, text="Report Bug", command=self.show_bug_report).grid(row=1, column=5, padx=3)
        self.optimize_button = ttk.Button(
            controls,
            text="Optimize Team",
            style="Accent.TButton",
            command=self.start_optimization,
        )
        self.optimize_button.grid(row=0, column=6, rowspan=2, padx=(14, 0), sticky="ns")

    def _build_status_bar(self):
        # Retain the version 2.0.0 layout preferred by the user.
        OptimizerApp._build_status_bar(self)

    def _build_analysis_tab(self):
        self.analysis_tab.columnconfigure(0, weight=1)
        self.analysis_tab.rowconfigure(2, weight=1)

        readiness = ttk.LabelFrame(self.analysis_tab, text="Profile readiness", padding=12)
        readiness.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        readiness.columnconfigure(0, weight=1)
        ttk.Label(readiness, textvariable=self.readiness_summary_var, style="Value.TLabel").grid(row=0, column=0, sticky="w")
        self.readiness_text = tk.Text(
            readiness,
            height=5,
            wrap="word",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            selectbackground=COLORS["selection"],
            relief="flat",
            borderwidth=0,
            padx=4,
            pady=4,
        )
        self.readiness_text.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.readiness_text.configure(state="disabled")

        main_options = ttk.LabelFrame(self.analysis_tab, text="Main companion handling", padding=12)
        main_options.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for col in range(5):
            main_options.columnconfigure(col, weight=1 if col in (1, 3) else 0)
        ttk.Label(main_options, text="Mode", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        mode = ttk.Combobox(main_options, textvariable=self.main_mode_var, values=MAIN_MODES, state="readonly")
        mode.grid(row=0, column=1, sticky="ew", padx=(0, 18))
        ToolTip(mode, "Automatic uses measured Main bonuses when supplied and otherwise the content heuristic. Equip effects only ignores Main active bonuses. Lock selected Main optimizes only its Sub team.")
        ttk.Label(main_options, text="Locked Main", style="Panel.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.locked_main_combo = ttk.Combobox(main_options, textvariable=self.locked_main_var, values=(), state="disabled")
        self.locked_main_combo.grid(row=0, column=3, sticky="ew", padx=(0, 18))
        ttk.Button(main_options, text="Compare every Main", command=self.start_main_comparison).grid(row=0, column=4, sticky="e")

        self.analysis_notebook = ttk.Notebook(self.analysis_tab)
        self.analysis_notebook.grid(row=2, column=0, sticky="nsew")
        self.sensitivity_page = ttk.Frame(self.analysis_notebook, style="App.TFrame")
        self.main_page = ttk.Frame(self.analysis_notebook, style="App.TFrame")
        self.upgrade_page = ttk.Frame(self.analysis_notebook, style="App.TFrame")
        self.analysis_notebook.add(self.sensitivity_page, text="Sensitivity & confidence")
        self.analysis_notebook.add(self.main_page, text="Main comparison")
        self.analysis_notebook.add(self.upgrade_page, text="Upgrade value")
        self._build_sensitivity_page()
        self._build_main_comparison_page()
        self._build_upgrade_page()

    def _build_sensitivity_page(self):
        page = self.sensitivity_page
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        controls = ttk.LabelFrame(page, text="Test ranges", padding=10)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for col in range(9):
            controls.columnconfigure(col, weight=1 if col in (1, 3, 5, 7) else 0)
        rows = [
            ("Basic Attack share", "basic_attack_min", "basic_attack_max", "basic_attack_steps"),
            ("Status uptime", "status_uptime_min", "status_uptime_max", "status_uptime_steps"),
        ]
        for row, (label, min_key, max_key, step_key) in enumerate(rows):
            ttk.Label(controls, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 6), pady=4)
            ttk.Label(controls, text="Min", style="PanelMuted.TLabel").grid(row=row, column=1, sticky="e")
            ttk.Entry(controls, textvariable=self.sensitivity_vars[min_key], width=8).grid(row=row, column=2, sticky="ew", padx=(4, 8))
            ttk.Label(controls, text="Max", style="PanelMuted.TLabel").grid(row=row, column=3, sticky="e")
            ttk.Entry(controls, textvariable=self.sensitivity_vars[max_key], width=8).grid(row=row, column=4, sticky="ew", padx=(4, 8))
            ttk.Label(controls, text="Samples", style="PanelMuted.TLabel").grid(row=row, column=5, sticky="e")
            ttk.Entry(controls, textvariable=self.sensitivity_vars[step_key], width=6).grid(row=row, column=6, sticky="ew", padx=(4, 12))

        self.vary_defense_check = ttk.Checkbutton(controls, text="Vary target Defense", variable=self.sensitivity_vars["vary_target_defense"], command=self._update_sensitivity_field_states)
        self.vary_defense_check.grid(row=2, column=0, sticky="w", pady=4)
        self.defense_range_entries = self._range_controls(controls, 2, "target_defense")
        self.vary_evasion_check = ttk.Checkbutton(controls, text="Vary target Evasion", variable=self.sensitivity_vars["vary_target_evasion"], command=self._update_sensitivity_field_states)
        self.vary_evasion_check.grid(row=3, column=0, sticky="w", pady=4)
        self.evasion_range_entries = self._range_controls(controls, 3, "target_evasion")
        self.sensitivity_button = ttk.Button(controls, text="Run sensitivity analysis", style="Accent.TButton", command=self.start_sensitivity_analysis)
        self.sensitivity_button.grid(row=0, column=8, rowspan=4, sticky="ns", padx=(14, 0))

        ttk.Label(page, textvariable=self.sensitivity_summary_var, style="Muted.TLabel", wraplength=1120).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        body = ttk.Frame(page, style="App.TFrame")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        columns = ("rank", "wins", "win_pct", "main", "team", "range")
        self.sensitivity_tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        headings = {"rank": "#", "wins": "Wins", "win_pct": "Win %", "main": "Main", "team": "Team", "range": "Winning estimate range"}
        widths = {"rank": 38, "wins": 60, "win_pct": 72, "main": 140, "team": 400, "range": 250}
        for col in columns:
            self.sensitivity_tree.heading(col, text=headings[col])
            self.sensitivity_tree.column(col, width=widths[col], anchor="w")
        self.sensitivity_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.sensitivity_tree.yview)
        self.sensitivity_tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=0, sticky="nse")
        self.sensitivity_detail = self._analysis_text(body)
        self.sensitivity_detail.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._update_sensitivity_field_states()

    def _range_controls(self, parent, row: int, prefix: str) -> Tuple[ttk.Entry, ttk.Entry, ttk.Entry]:
        ttk.Label(parent, text="Min", style="PanelMuted.TLabel").grid(row=row, column=1, sticky="e")
        min_entry = ttk.Entry(parent, textvariable=self.sensitivity_vars[f"{prefix}_min"], width=8)
        min_entry.grid(row=row, column=2, sticky="ew", padx=(4, 8))
        ttk.Label(parent, text="Max", style="PanelMuted.TLabel").grid(row=row, column=3, sticky="e")
        max_entry = ttk.Entry(parent, textvariable=self.sensitivity_vars[f"{prefix}_max"], width=8)
        max_entry.grid(row=row, column=4, sticky="ew", padx=(4, 8))
        ttk.Label(parent, text="Samples", style="PanelMuted.TLabel").grid(row=row, column=5, sticky="e")
        steps = ttk.Entry(parent, textvariable=self.sensitivity_vars[f"{prefix}_steps"], width=6)
        steps.grid(row=row, column=6, sticky="ew", padx=(4, 12))
        return min_entry, max_entry, steps

    def _analysis_text(self, parent):
        widget = tk.Text(
            parent,
            wrap="word",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["selection"],
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=10,
            font=("TkFixedFont", 10),
        )
        widget.configure(state="disabled")
        return widget

    def _build_main_comparison_page(self):
        page = self.main_page
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        bar = ttk.Frame(page, style="Panel.TFrame", padding=10)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(bar, textvariable=self.main_summary_var, style="Panel.TLabel").pack(side="left", fill="x", expand=True)
        self.main_compare_button = ttk.Button(bar, text="Compare every Main", style="Accent.TButton", command=self.start_main_comparison)
        self.main_compare_button.pack(side="right")
        ttk.Label(page, text="Each row locks that page as Main and exhaustively finds its best Sub companions. This separates equip-effect quality from uncertain active-skill utility.", style="Muted.TLabel", wraplength=1120).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        columns = ("rank", "gain", "main", "subs", "score")
        self.main_compare_tree = ttk.Treeview(page, columns=columns, show="headings", selectmode="browse")
        headings = {"rank": "#", "gain": "Gain", "main": "Forced Main", "subs": "Best Subs", "score": "Relative score"}
        widths = {"rank": 42, "gain": 80, "main": 180, "subs": 650, "score": 120}
        for col in columns:
            self.main_compare_tree.heading(col, text=headings[col])
            self.main_compare_tree.column(col, width=widths[col], anchor="w")
        self.main_compare_tree.grid(row=2, column=0, sticky="nsew")

    def _build_upgrade_page(self):
        page = self.upgrade_page
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        bar = ttk.Frame(page, style="Panel.TFrame", padding=10)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(bar, textvariable=self.upgrade_summary_var, style="Panel.TLabel").pack(side="left", fill="x", expand=True)
        self.upgrade_button = ttk.Button(bar, text="Calculate next-level values", style="Accent.TButton", command=self.start_upgrade_analysis)
        self.upgrade_button.pack(side="right")
        ttk.Label(page, text="The planner upgrades one owned formula-backed page by one level, reoptimizes the team, and reports the best modeled gain. It does not yet include copy/resource costs.", style="Muted.TLabel", wraplength=1120).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        columns = ("rank", "gain", "companion", "level", "effect", "team")
        self.upgrade_tree = ttk.Treeview(page, columns=columns, show="headings", selectmode="browse")
        headings = {"rank": "#", "gain": "Best gain", "companion": "Companion page", "level": "Upgrade", "effect": "Equip effect", "team": "Resulting best team"}
        widths = {"rank": 42, "gain": 90, "companion": 190, "level": 100, "effect": 220, "team": 560}
        for col in columns:
            self.upgrade_tree.heading(col, text=headings[col])
            self.upgrade_tree.column(col, width=widths[col], anchor="w")
        self.upgrade_tree.grid(row=2, column=0, sticky="nsew")

    def _update_sensitivity_field_states(self):
        if not hasattr(self, "defense_range_entries"):
            return
        for entry in self.defense_range_entries:
            entry.configure(state="normal" if bool(self.sensitivity_vars["vary_target_defense"].get()) else "disabled")
        for entry in self.evasion_range_entries:
            entry.configure(state="normal" if bool(self.sensitivity_vars["vary_target_evasion"].get()) else "disabled")

    def _update_main_mode_fields(self):
        if not hasattr(self, "locked_main_combo"):
            return
        mode = self.main_mode_var.get()
        self.locked_main_combo.configure(state="readonly" if mode == "Lock selected Main" else "disabled")
        self._schedule_autosave()

    def _refresh_locked_main_choices(self):
        if not hasattr(self, "locked_main_combo"):
            return
        old_uid = self.locked_main_display_to_uid.get(self.locked_main_var.get(), "")
        mapping: Dict[str, str] = {}
        for key, row in self.roster_vars.items():
            if not bool(row["owned"].get()):
                continue
            name = str(row["name"])
            rarity = str(row["rarity"])
            level = str(row["level"].get())
            display = f"{name} — {rarity} Lv. {level}"
            mapping[display] = self._stable_roster_uid(name, rarity)
        self.locked_main_display_to_uid = mapping
        values = tuple(mapping.keys())
        self.locked_main_combo.configure(values=values)
        if old_uid:
            for display, uid in mapping.items():
                if uid == old_uid:
                    self.locked_main_var.set(display)
                    break
        elif self.locked_main_var.get() not in mapping:
            self.locked_main_var.set(values[0] if values else "")

    def _selected_locked_uid(self) -> str:
        return self.locked_main_display_to_uid.get(self.locked_main_var.get(), "")

    def _collect_sensitivity_settings(self) -> SensitivitySettings:
        def raw(key: str) -> str:
            variable = self.sensitivity_vars[key]
            return str(variable.get()).strip()

        def count(key: str, default: int) -> int:
            value = raw(key)
            if not value:
                return default
            parsed = int(parse_number(value, field_name=key.replace("_", " ").title()))
            if not 1 <= parsed <= 25:
                raise ValueError(f"{key.replace('_', ' ').title()} must be from 1 to 25.")
            return parsed

        def optional_range(prefix: str, nominal: float, *, percent: bool, default_steps: int):
            lo_text = raw(f"{prefix}_min")
            hi_text = raw(f"{prefix}_max")
            if not lo_text and not hi_text:
                return False, nominal, nominal, 1
            if not lo_text or not hi_text:
                raise ValueError(f"Enter both the minimum and maximum for {prefix.replace('_', ' ')} or leave both blank.")
            lo = parse_number(lo_text, field_name=f"{prefix.replace('_', ' ').title()} minimum")
            hi = parse_number(hi_text, field_name=f"{prefix.replace('_', ' ').title()} maximum")
            if lo > hi:
                raise ValueError(f"{prefix.replace('_', ' ').title()} minimum cannot exceed maximum.")
            if percent and (lo < 0 or hi > 100):
                raise ValueError(f"{prefix.replace('_', ' ').title()} range must stay within 0–100.")
            if not percent and lo < 0:
                raise ValueError(f"{prefix.replace('_', ' ').title()} range cannot be negative.")
            return True, lo, hi, count(f"{prefix}_steps", default_steps)

        basic_on, basic_lo, basic_hi, basic_steps = optional_range(
            "basic_attack", parse_number(self.stat_vars["basic_attack_share"].get(), field_name="Basic Attack share"),
            percent=True, default_steps=5,
        )
        status_on, status_lo, status_hi, status_steps = optional_range(
            "status_uptime", parse_number(self.stat_vars["status_uptime"].get(), field_name="Status uptime"),
            percent=True, default_steps=5,
        )
        defense_on, defense_lo, defense_hi, defense_steps = optional_range(
            "target_defense", parse_number(self.target_vars["target_defense"].get(), field_name="Target Defense"),
            percent=False, default_steps=4,
        )
        evasion_on, evasion_lo, evasion_hi, evasion_steps = optional_range(
            "target_evasion", parse_number(self.target_vars["target_evasion"].get(), field_name="Target Evasion"),
            percent=False, default_steps=4,
        )
        return SensitivitySettings(
            vary_basic_attack=basic_on,
            basic_attack_min=basic_lo,
            basic_attack_max=basic_hi,
            basic_attack_steps=basic_steps,
            vary_status_uptime=status_on,
            status_uptime_min=status_lo,
            status_uptime_max=status_hi,
            status_uptime_steps=status_steps,
            vary_target_defense=defense_on,
            target_defense_min=defense_lo,
            target_defense_max=defense_hi,
            target_defense_steps=defense_steps,
            vary_target_evasion=evasion_on,
            target_evasion_min=evasion_lo,
            target_evasion_max=evasion_hi,
            target_evasion_steps=evasion_steps,
        )

    def collect_profile(self) -> AdvancedProfile:
        base = OptimizerApp.collect_profile(self)
        mode = self.main_mode_var.get()
        if mode not in MAIN_MODES:
            mode = "Automatic"
        return AdvancedProfile(
            stats=base.stats,
            target=base.target,
            companions=base.companions,
            total_slots=base.total_slots,
            top_results=base.top_results,
            stats_include_equipped_companions=base.stats_include_equipped_companions,
            stat_sources=base.stat_sources,
            build_name=self.active_build_name,
            main_options=MainSelectionOptions(mode=mode, locked_main_uid=self._selected_locked_uid()),
            sensitivity=self._collect_sensitivity_settings(),
        )

    def _snapshot_current_build(self, name: Optional[str] = None) -> BuildProfile:
        profile = self.collect_profile()
        roles = {c.uid: c.equipped_role for c in profile.companions if c.equipped_role in {"Main", "Sub"}}
        return BuildProfile(
            name=name or self.active_build_name,
            stats=copy.deepcopy(profile.stats),
            target=copy.deepcopy(profile.target),
            current_roles=roles,
            stats_include_equipped_companions=profile.stats_include_equipped_companions,
            stat_sources=dict(profile.stat_sources),
            main_options=copy.deepcopy(profile.main_options),
            sensitivity=copy.deepcopy(profile.sensitivity),
        )

    def _apply_build(self, build: BuildProfile):
        previous = self._loading_profile
        self._loading_profile = True
        self._build_syncing = True
        try:
            shared_class = self.stat_vars["character_class"].get()
            shared_level = self.stat_vars["character_level"].get()
            for field_info in fields(CharacterStats):
                key = field_info.name
                if key in {"character_class", "character_level"}:
                    continue
                self.stat_vars[key].set(str(getattr(build.stats, key)))
            self.stat_vars["character_class"].set(shared_class)
            self.stat_vars["character_level"].set(shared_level)
            for field_info in fields(TargetProfile):
                key = field_info.name
                self.target_vars[key].set(getattr(build.target, key))
            self.stats_include_equipped_var.set(build.stats_include_equipped_companions)
            self.stat_sources = dict(build.stat_sources)
            self._refresh_stat_source_styles()
            self.main_mode_var.set(build.main_options.mode)
            self._set_locked_uid(build.main_options.locked_main_uid)
            for field_info in fields(SensitivitySettings):
                variable = self.sensitivity_vars.get(field_info.name)
                if variable is not None:
                    variable.set(getattr(build.sensitivity, field_info.name))
            optional_prefixes = (
                ("basic_attack", build.sensitivity.vary_basic_attack),
                ("status_uptime", build.sensitivity.vary_status_uptime),
                ("target_defense", build.sensitivity.vary_target_defense),
                ("target_evasion", build.sensitivity.vary_target_evasion),
            )
            for prefix, enabled in optional_prefixes:
                if not enabled:
                    self.sensitivity_vars[f"{prefix}_min"].set("")
                    self.sensitivity_vars[f"{prefix}_max"].set("")
            self._roster_syncing = True
            for key, row in self.roster_vars.items():
                uid = self._stable_roster_uid(str(row["name"]), str(row["rarity"]))
                role = build.current_roles.get(uid, "Not equipped")
                if not bool(row["owned"].get()):
                    role = "Not equipped"
                row["role"].set(role)
            self._roster_syncing = False
            self.results = []
            self.last_optimized_profile = None
            self.last_sensitivity_result = None
            self.last_sensitivity_build = ""
            self.refresh_results_tree()
            self._clear_analysis_outputs()
        finally:
            self._roster_syncing = False
            self._build_syncing = False
            self._loading_profile = previous
        self._refresh_roster_count()
        self._update_sensitivity_field_states()
        self._update_main_mode_fields()
        self._refresh_readiness_panel()

    def _set_locked_uid(self, uid: str):
        self._refresh_locked_main_choices()
        for display, candidate_uid in self.locked_main_display_to_uid.items():
            if candidate_uid == uid:
                self.locked_main_var.set(display)
                return
        if self.locked_main_display_to_uid:
            self.locked_main_var.set(next(iter(self.locked_main_display_to_uid)))
        else:
            self.locked_main_var.set("")

    def collect_account(self) -> AccountProfile:
        build = self._snapshot_current_build(self.active_build_name)
        self.account_builds[self.active_build_name] = build
        companions = self._collect_roster_companions()
        for companion in companions:
            companion.equipped_role = "Not equipped"
        character_class = self.stat_vars["character_class"].get().strip() or "Other / future class"
        character_level = int(parse_number(self.stat_vars["character_level"].get(), field_name="Character level"))
        total_slots = int(parse_number(self.total_slots_var.get(), field_name="Total companion slots"))
        top_results = int(parse_number(self.top_results_var.get(), field_name="Results to keep"))
        builds = [copy.deepcopy(self.account_builds[name]) for name in self.account_builds]
        for item in builds:
            item.stats.character_class = character_class
            item.stats.character_level = character_level
        return AccountProfile(
            character_class=character_class,
            character_level=character_level,
            companions=companions,
            total_slots=total_slots,
            top_results=top_results,
            builds=builds,
            active_build=self.active_build_name,
        )

    def apply_account(self, account: AccountProfile):
        previous = self._loading_profile
        self._loading_profile = True
        self._build_syncing = True
        try:
            self.stat_vars["character_class"].set(account.character_class)
            self.stat_vars["character_level"].set(str(account.character_level))
            self.total_slots_var.set(str(account.total_slots))
            self.top_results_var.set(str(account.top_results))
            shared = copy.deepcopy(account.companions)
            for companion in shared:
                companion.equipped_role = "Not equipped"
            self._load_companions_into_roster(shared)
            self._loading_profile = True
            self.account_builds = {b.name: copy.deepcopy(b) for b in account.builds}
            if not self.account_builds:
                self.account_builds = {"Default Build": BuildProfile(name="Default Build")}
            self.active_build_name = account.active_build if account.active_build in self.account_builds else next(iter(self.account_builds))
            self._refresh_build_selector()
            self._apply_build(self.account_builds[self.active_build_name])
        finally:
            self._build_syncing = False
            self._loading_profile = previous
        self._refresh_locked_main_choices()
        self._refresh_readiness_panel()

    def apply_profile(self, profile: Profile):
        # Compatibility entry point for tests and legacy callers.
        roles = {c.uid: c.equipped_role for c in profile.companions if c.equipped_role in {"Main", "Sub"}}
        shared = copy.deepcopy(profile.companions)
        for companion in shared:
            companion.equipped_role = "Not equipped"
        build = BuildProfile(
            name="Imported Build",
            stats=copy.deepcopy(profile.stats),
            target=copy.deepcopy(profile.target),
            current_roles=roles,
            stats_include_equipped_companions=profile.stats_include_equipped_companions,
            stat_sources=dict(profile.stat_sources),
        )
        self.apply_account(AccountProfile(
            character_class=profile.stats.character_class,
            character_level=profile.stats.character_level,
            companions=shared,
            total_slots=profile.total_slots,
            top_results=profile.top_results,
            builds=[build],
            active_build=build.name,
        ))

    def _refresh_build_selector(self):
        if not hasattr(self, "build_selector"):
            return
        names = tuple(self.account_builds.keys()) or ("Default Build",)
        self.build_selector.configure(values=names)
        self.build_selector_var.set(self.active_build_name if self.active_build_name in names else names[0])

    def _on_build_selected(self, _event=None):
        if self._build_syncing:
            return
        selected = self.build_selector_var.get()
        if not selected or selected == self.active_build_name or selected not in self.account_builds:
            return
        old = self.active_build_name
        try:
            self.account_builds[old] = self._snapshot_current_build(old)
        except Exception as exc:
            messagebox.showerror("Cannot switch build", f"Fix the current build before switching:\n\n{exc}", parent=self)
            self._build_syncing = True
            self.build_selector_var.set(old)
            self._build_syncing = False
            return
        self.active_build_name = selected
        self._apply_build(self.account_builds[selected])
        self.status_var.set(f"Switched to build: {selected}.")
        self._schedule_autosave()

    def _unique_build_name(self, proposed: str) -> str:
        base = proposed.strip() or "Build"
        if base not in self.account_builds:
            return base
        index = 2
        while f"{base} {index}" in self.account_builds:
            index += 1
        return f"{base} {index}"

    def new_build(self):
        name = simpledialog.askstring("New build", "Build name:", initialvalue="New Build", parent=self)
        if not name:
            return
        try:
            self.account_builds[self.active_build_name] = self._snapshot_current_build(self.active_build_name)
        except Exception as exc:
            messagebox.showerror("Cannot create build", str(exc), parent=self)
            return
        name = self._unique_build_name(name)
        stats = CharacterStats(
            character_class=self.stat_vars["character_class"].get(),
            character_level=int(parse_number(self.stat_vars["character_level"].get(), field_name="Character level")),
        )
        build = BuildProfile(name=name, stats=stats)
        self.account_builds[name] = build
        self.active_build_name = name
        self._refresh_build_selector()
        self._apply_build(build)
        self.status_var.set(f"Created build: {name}.")
        self._schedule_autosave()

    def duplicate_build(self):
        try:
            current = self._snapshot_current_build(self.active_build_name)
        except Exception as exc:
            messagebox.showerror("Cannot duplicate build", str(exc), parent=self)
            return
        proposed = simpledialog.askstring("Duplicate build", "New build name:", initialvalue=f"{self.active_build_name} Copy", parent=self)
        if not proposed:
            return
        name = self._unique_build_name(proposed)
        duplicate = copy.deepcopy(current)
        duplicate.name = name
        self.account_builds[self.active_build_name] = current
        self.account_builds[name] = duplicate
        self.active_build_name = name
        self._refresh_build_selector()
        self._apply_build(duplicate)
        self.status_var.set(f"Duplicated build as {name}.")
        self._schedule_autosave()

    def rename_build(self):
        proposed = simpledialog.askstring("Rename build", "New name:", initialvalue=self.active_build_name, parent=self)
        if not proposed:
            return
        proposed = proposed.strip()
        if proposed != self.active_build_name and proposed in self.account_builds:
            messagebox.showerror("Rename build", "A build with that name already exists.", parent=self)
            return
        try:
            build = self._snapshot_current_build(proposed)
        except Exception as exc:
            messagebox.showerror("Cannot rename build", str(exc), parent=self)
            return
        old = self.active_build_name
        items = list(self.account_builds.items())
        self.account_builds.clear()
        for name, item in items:
            if name == old:
                self.account_builds[proposed] = build
            else:
                self.account_builds[name] = item
        self.active_build_name = proposed
        self._refresh_build_selector()
        self.status_var.set(f"Renamed build to {proposed}.")
        self._schedule_autosave()

    def delete_build(self):
        if len(self.account_builds) <= 1:
            messagebox.showinfo("Delete build", "An account must contain at least one build.", parent=self)
            return
        if not messagebox.askyesno("Delete build", f"Delete '{self.active_build_name}'?", parent=self):
            return
        del self.account_builds[self.active_build_name]
        self.active_build_name = next(iter(self.account_builds))
        self._refresh_build_selector()
        self._apply_build(self.account_builds[self.active_build_name])
        self.status_var.set(f"Deleted build; active build is now {self.active_build_name}.")
        self._schedule_autosave()

    def _clear_analysis_outputs(self):
        if hasattr(self, "sensitivity_tree"):
            self.sensitivity_tree.delete(*self.sensitivity_tree.get_children())
        if hasattr(self, "main_compare_tree"):
            self.main_compare_tree.delete(*self.main_compare_tree.get_children())
        if hasattr(self, "upgrade_tree"):
            self.upgrade_tree.delete(*self.upgrade_tree.get_children())
        self.main_comparison_results = []
        self.upgrade_results = []
        self.sensitivity_summary_var.set("Run sensitivity analysis to test uncertain assumptions.")
        self.main_summary_var.set("Compare the best Sub team for every possible Main companion.")
        self.upgrade_summary_var.set("Rank the modeled benefit of each companion's next level.")
        if hasattr(self, "sensitivity_detail"):
            self._set_text_widget(self.sensitivity_detail, "No sensitivity analysis has been run for this build.")
        if hasattr(self, "unified_analysis_text"):
            self._set_unified_analysis_text("Optional Main comparison and upgrade-planning results will appear here.")

    def _install_autosave_traces(self):
        OptimizerApp._install_autosave_traces(self)
        variables = [self.main_mode_var, self.locked_main_var]
        variables.extend(self.sensitivity_vars.values())
        for variable in variables:
            try:
                variable.trace_add("write", lambda *_: self._schedule_autosave())
            except AttributeError:
                pass

    def _schedule_autosave(self):
        OptimizerApp._schedule_autosave(self)
        if self._loading_profile:
            return
        if self._readiness_after_id is not None:
            try:
                self.after_cancel(self._readiness_after_id)
            except tk.TclError:
                pass
        self._readiness_after_id = self.after(350, self._refresh_readiness_panel)

    def _write_autosave(self, profile=None):
        self._autosave_after_id = None
        if self._loading_profile:
            return
        try:
            account = self.collect_account()
            write_json_atomic(self.autosave_path, account_to_dict(account))
        except Exception:
            return

    def _restore_autosave(self) -> bool:
        if not self.autosave_path.exists():
            return False
        try:
            payload = json.loads(self.autosave_path.read_text(encoding="utf-8"))
            account = account_from_dict(payload, "Restored Build")
            self.apply_account(account)
            self.profile_path = None
            self.profile_title_var.set("Auto-restored account")
            self.status_var.set(f"Restored the last valid account from {self.autosave_path}.")
            return True
        except Exception:
            return False

    def new_profile(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Search active", "Cancel the current search before starting a new account.", parent=self)
            return
        if not messagebox.askyesno("New account", "Clear the current account, all builds, and companion ownership?", parent=self):
            return
        self.profile_path = None
        self.profile_title_var.set("Unsaved account")
        self.account_builds = {"Default Build": BuildProfile(name="Default Build")}
        self.active_build_name = "Default Build"
        self._clear_roster_without_prompt()
        self.stat_vars["character_class"].set("Other / future class")
        self.stat_vars["character_level"].set("1")
        self.total_slots_var.set("7")
        self.top_results_var.set("20")
        self._refresh_build_selector()
        self._apply_build(self.account_builds[self.active_build_name])
        self.status_var.set("New account created.")

    def _clear_roster_without_prompt(self):
        self._roster_syncing = True
        try:
            for row in self.roster_vars.values():
                row["owned"].set(False)
                row["role"].set("Not equipped")
                row["level"].set("1")
            self.extra_companions = []
        finally:
            self._roster_syncing = False
        for key in self.roster_vars:
            self._set_roster_row_state(key)
        self._refresh_roster_count()

    def save_profile(self, save_as: bool = False):
        try:
            account = self.collect_account()
        except Exception as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self)
            return
        path = self.profile_path
        if save_as or path is None:
            initial = path.name if path else safe_filename(f"{account.character_class}_optimizer_account") + ".json"
            options = {
                "parent": self,
                "title": "Save optimizer account as" if save_as else "Save optimizer account",
                "defaultextension": ".json",
                "filetypes": (("JSON account", "*.json"), ("All files", "*.*")),
                "initialfile": initial,
            }
            if path:
                options["initialdir"] = str(path.parent)
            selected = filedialog.asksaveasfilename(**options)
            if not selected:
                return
            path = Path(selected)
        try:
            write_json_atomic(path, account_to_dict(account))
            self.profile_path = path
            self.profile_title_var.set(path.name)
            self.status_var.set(f"Saved account with {len(account.builds)} build(s) to {path}.")
            self._write_autosave()
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)

    def load_profile(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Search active", "Cancel the current search before loading an account.", parent=self)
            return
        selected = filedialog.askopenfilename(parent=self, title="Load optimizer account or legacy profile", filetypes=(("JSON files", "*.json"), ("All files", "*.*")))
        if not selected:
            return
        path = Path(selected)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            account = account_from_dict(payload, path.stem)
            self.apply_account(account)
            self.profile_path = path
            self.profile_title_var.set(path.name)
            self.status_var.set(f"Loaded {path.name} with {len(account.builds)} build(s).")
            self._write_autosave()
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc), parent=self)

    def _on_roster_owned_changed(self, key: str):
        OptimizerApp._on_roster_owned_changed(self, key)
        row = self.roster_vars[key]
        if not bool(row["owned"].get()):
            uid = self._stable_roster_uid(str(row["name"]), str(row["rarity"]))
            for build in self.account_builds.values():
                build.current_roles.pop(uid, None)
        self._refresh_locked_main_choices()
        self._refresh_readiness_panel()

    def _on_roster_level_changed(self, key: str):
        OptimizerApp._on_roster_level_changed(self, key)
        self._refresh_locked_main_choices()

    def _clear_roster(self):
        if not messagebox.askyesno("Clear ownership", "Uncheck every companion page across the shared account and clear all build slots?", parent=self):
            return
        self._clear_roster_without_prompt()
        for build in self.account_builds.values():
            build.current_roles.clear()
        self._schedule_autosave()

    def _refresh_roster_count(self):
        OptimizerApp._refresh_roster_count(self)
        self._refresh_locked_main_choices()
        if not self._loading_profile:
            self._refresh_readiness_panel()

    def _set_analysis_buttons(self, state: str):
        for name in ("sensitivity_button", "main_compare_button", "upgrade_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state=state)

    def _focus_results_region(self):
        try:
            self._layout_workspace()
            region = self.workspace_canvas.cget("scrollregion").split()
            total = max(1, int(float(region[3])))
            visible = max(1, self.workspace_canvas.winfo_height())
            fraction = min(1.0, max(0.0, self._workspace_result_y / max(1, total - visible)))
            self.workspace_canvas.yview_moveto(fraction)
            self._position_workspace_background()
        except Exception:
            pass

    def start_optimization(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            profile = self.collect_profile()
            readiness = assess_profile_readiness(profile)
            errors = [issue.message for issue in readiness.issues if issue.severity == "error"]
            if errors:
                raise ValueError("Profile readiness errors:\n• " + "\n• ".join(errors))
            prepare_advanced_context(profile)
            count = valid_team_count(len(profile.companions), profile.total_slots, profile.main_options)
            if count > 25_000_000 and not messagebox.askyesno("Large exact search", f"This exact search contains {count:,} teams. Continue?", parent=self):
                return
        except Exception as exc:
            messagebox.showerror("Cannot optimize", str(exc), parent=self)
            return
        self.cancel_event.clear()
        self.current_job_kind = "optimize"
        self.last_optimized_profile = copy.deepcopy(profile)
        self.results = []
        self.refresh_results_tree()
        self.optimize_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._set_analysis_buttons("disabled")
        self.progressbar.configure(value=0, maximum=max(1, count))
        self.progress_text_var.set(f"0 / {count:,}")
        self.status_var.set("Searching every valid team…")
        self._pending_auto_sensitivity = any((
            profile.sensitivity.vary_basic_attack,
            profile.sensitivity.vary_status_uptime,
            profile.sensitivity.vary_target_defense,
            profile.sensitivity.vary_target_evasion,
        ))
        self._focus_results_region()

        def progress(done: int, total: int):
            self.worker_queue.put(("progress", done, total))
        def run():
            try:
                results, total, elapsed = optimize_companions_advanced(profile, progress=progress, cancel_event=self.cancel_event)
                self.worker_queue.put(("done_opt", results, total, elapsed, self.cancel_event.is_set()))
            except Exception as exc:
                self.worker_queue.put(("error", str(exc), traceback.format_exc()))
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()
        self.after(80, self._poll_worker_queue)

    def _start_analysis_job(self, kind: str, total: int, runner: Callable[[], object], message: str):
        if self.worker and self.worker.is_alive():
            return
        self.cancel_event.clear()
        self.current_job_kind = kind
        self.optimize_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._set_analysis_buttons("disabled")
        self.progressbar.configure(value=0, maximum=max(1, total))
        self.progress_text_var.set(f"0 / {total:,}")
        self.status_var.set(message)
        self._focus_results_region()
        def run():
            try:
                result = runner()
                self.worker_queue.put((f"done_{kind}", result, self.cancel_event.is_set()))
            except Exception as exc:
                self.worker_queue.put(("error", str(exc), traceback.format_exc()))
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()
        self.after(80, self._poll_worker_queue)

    def start_sensitivity_analysis(self):
        try:
            profile = self.collect_profile()
            scenarios = _scenario_values(profile)
            teams = valid_team_count(len(profile.companions), profile.total_slots, profile.main_options)
            work = len(scenarios) * teams
            if work > 50_000_000 and not messagebox.askyesno("Large robustness analysis", f"This analysis tests {len(scenarios)} scenarios across about {work:,} team evaluations. Continue?", parent=self):
                return
        except Exception as exc:
            messagebox.showerror("Cannot run sensitivity analysis", str(exc), parent=self)
            return
        def progress(done: int, total: int):
            self.worker_queue.put(("progress", done, total))
        self._start_analysis_job(
            "sensitivity",
            len(scenarios),
            lambda: run_sensitivity_analysis(profile, progress=progress, cancel_event=self.cancel_event),
            f"Testing {len(scenarios)} assumption scenarios…",
        )

    def start_main_comparison(self):
        try:
            profile = self.collect_profile()
            checks = math.comb(len(profile.companions), profile.total_slots) * profile.total_slots
            if checks > 50_000_000 and not messagebox.askyesno("Large Main comparison", f"This comparison contains about {checks:,} Main/team checks. Continue?", parent=self):
                return
        except Exception as exc:
            messagebox.showerror("Cannot compare Mains", str(exc), parent=self)
            return
        def progress(done: int, total: int):
            self.worker_queue.put(("progress", done, total))
        self._start_analysis_job(
            "mains",
            checks,
            lambda: compare_all_mains(profile, progress=progress, cancel_event=self.cancel_event),
            "Finding the best Sub team for every possible Main…",
        )

    def start_upgrade_analysis(self):
        try:
            profile = self.collect_profile()
            teams = valid_team_count(len(profile.companions), profile.total_slots, profile.main_options)
            if teams * (profile.total_slots + 1) > 50_000_000 and not messagebox.askyesno("Large upgrade analysis", f"This planner will perform roughly {teams * (profile.total_slots + 1):,} team scores. Continue?", parent=self):
                return
        except Exception as exc:
            messagebox.showerror("Cannot calculate upgrades", str(exc), parent=self)
            return
        def progress(done: int, total: int):
            self.worker_queue.put(("progress", done, total))
        self._start_analysis_job(
            "upgrades",
            teams,
            lambda: calculate_upgrade_values(profile, progress=progress, cancel_event=self.cancel_event),
            "Calculating each companion's next-level value…",
        )

    def _poll_worker_queue(self):
        active = self.worker is not None and self.worker.is_alive()
        try:
            while True:
                message = self.worker_queue.get_nowait()
                kind = message[0]
                if kind == "progress":
                    _, done, total = message
                    self.progressbar.configure(maximum=max(1, total), value=done)
                    pct = 100.0 * done / total if total else 100.0
                    self.progress_text_var.set(f"{done:,} / {total:,}  ({pct:.1f}%)")
                elif kind == "done_opt":
                    _, results, total, elapsed, cancelled = message
                    self.results = results
                    self.refresh_results_tree()
                    if cancelled:
                        self.status_var.set(f"Search cancelled after {elapsed:.2f}s; showing retained teams.")
                    else:
                        self.status_var.set(f"Exact search completed: {total:,} teams in {elapsed:.2f}s.")
                    self.results_summary_label.configure(text=f"Exact exhaustive search • {total:,} teams • {elapsed:.2f}s • top {len(results)} shown")
                    auto_followup = bool(getattr(self, "_pending_auto_sensitivity", False) and not cancelled and results)
                    self._pending_auto_sensitivity = False
                    active = False
                elif kind == "done_sensitivity":
                    _, result, cancelled = message
                    if not cancelled:
                        self.last_sensitivity_result = result
                        self.last_sensitivity_build = self.active_build_name
                        self._display_sensitivity_result(result)
                        self.status_var.set(f"Sensitivity analysis completed: {result.scenario_count} scenarios in {result.elapsed:.2f}s.")
                    active = False
                elif kind == "done_mains":
                    _, payload, cancelled = message
                    if not cancelled:
                        rows, checks, elapsed = payload
                        self.main_comparison_results = rows
                        self._display_main_comparison(rows, checks, elapsed)
                        self.status_var.set(f"Main comparison completed: {checks:,} checks in {elapsed:.2f}s.")
                    active = False
                elif kind == "done_upgrades":
                    _, payload, cancelled = message
                    if not cancelled:
                        rows, teams, elapsed = payload
                        self.upgrade_results = rows
                        self._display_upgrade_results(rows, teams, elapsed)
                        self.status_var.set(f"Upgrade analysis completed in {elapsed:.2f}s.")
                    active = False
                elif kind == "error":
                    _, error, details = message
                    self.status_var.set("Analysis failed.")
                    messagebox.showerror("Optimizer error", f"{error}\n\nTechnical details:\n{details}", parent=self)
                    active = False
        except queue.Empty:
            pass
        if not active:
            self.optimize_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")
            self._set_analysis_buttons("normal")
            self.current_job_kind = ""
            if auto_followup:
                self.status_var.set("Team search complete; running requested robustness ranges…")
                self.after(180, self.start_sensitivity_analysis)
        else:
            self.after(80, self._poll_worker_queue)

    def _display_sensitivity_result(self, result: SensitivityAnalysisResult):
        self.sensitivity_summary_var.set(
            f"{result.confidence} confidence • nominal team won {result.nominal_win_pct:.1f}% of "
            f"{result.scenario_count} scenarios • worst missed gain {result.nominal_max_regret_pct:.3f}%"
        )
        lines = [
            "ROBUSTNESS ANALYSIS",
            f"Confidence: {result.confidence}",
            f"Nominal team wins: {result.nominal_win_pct:.1f}% of {result.scenario_count} scenarios",
            f"Worst missed gain from keeping it: {result.nominal_max_regret_pct:.3f}%",
        ]
        if result.variable_influence:
            lines.append("Range influence:")
            for variable, summary in result.variable_influence.items():
                lines.append(f"  {variable}: {summary}")
        if result.summaries:
            lines.append("Top scenario winners:")
            for index, row in enumerate(result.summaries[:5], start=1):
                subs = ", ".join(c.name for c in row.team if c.uid != row.main.uid)
                lines.append(f"  {index}. {row.win_pct:.1f}% — Main {row.main.name}; {subs}")
        self._set_unified_analysis_text("\n".join(lines))
        self._show_selected_result()

    def _display_main_comparison(self, rows: List[MainComparisonResult], checks: int, elapsed: float):
        self.main_comparison_results = rows
        self.main_summary_var.set(f"{len(rows)} possible Mains compared • {checks:,} checks • {elapsed:.2f}s")
        lines = ["MAIN COMPANION COMPARISON", self.main_summary_var.get(), ""]
        for index, row in enumerate(rows[:10], start=1):
            subs = ", ".join(c.name for c in row.subs)
            lines.append(f"{index}. {row.gain_pct:+.3f}% — {row.main.display_name}; {subs}")
        self._set_unified_analysis_text("\n".join(lines))

    def _display_upgrade_results(self, rows: List[UpgradeValueResult], teams: int, elapsed: float):
        self.upgrade_results = rows
        self.upgrade_summary_var.set(f"{len(rows)} next-level upgrades ranked • {teams:,} valid teams • {elapsed:.2f}s")
        lines = ["COMPANION UPGRADE VALUE", self.upgrade_summary_var.get(), ""]
        for index, row in enumerate(rows[:10], start=1):
            lines.append(
                f"{index}. {row.improvement_pct:+.4f}% — {row.companion.display_name} "
                f"Lv. {row.companion.level} → {row.next_level}"
            )
        self._set_unified_analysis_text("\n".join(lines))

    def _set_unified_analysis_text(self, text: str):
        variable = getattr(self, "unified_analysis_var", None)
        if variable is not None:
            variable.set(text)
        detail = getattr(self, "result_detail", None)
        if detail is not None:
            self._set_text_widget(detail, text)
        widget = getattr(self, "unified_analysis_text", None)
        if widget is not None:
            self._set_text_widget(widget, text)

    def _set_text_widget(self, widget: tk.Text, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _refresh_readiness_panel(self):
        self._readiness_after_id = None
        if not hasattr(self, "readiness_text"):
            return
        try:
            report = assess_profile_readiness(self.collect_profile())
            self.readiness_summary_var.set(report.rating)
            if report.issues:
                symbols = {"error": "ERROR", "warning": "CHECK", "info": "NOTE"}
                text = "\n".join(f"{symbols.get(issue.severity, 'NOTE')}: {issue.message}" for issue in report.issues)
            else:
                text = "Core stats, current team, and modeled assumptions are internally consistent."
        except Exception as exc:
            self.readiness_summary_var.set("Not ready")
            text = str(exc)
        self._set_text_widget(self.readiness_text, text)

    def result_report(self, result: OptimizationResult) -> str:
        profile = self.last_optimized_profile or self.collect_profile()
        if not isinstance(profile, AdvancedProfile):
            profile = AdvancedProfile(
                stats=profile.stats, target=profile.target, companions=profile.companions,
                total_slots=profile.total_slots, top_results=profile.top_results,
                stats_include_equipped_companions=profile.stats_include_equipped_companions,
                stat_sources=profile.stat_sources,
            )
        model_stats, reference_state, current_team, current_main, _, reference_label = prepare_advanced_context(profile)
        state = result.state
        lines = [
            f"BUILD: {profile.build_name}",
            f"OPTIMIZED FOR: {profile.target.content_mode}",
            f"MAIN MODE: {profile.main_options.mode}",
            f"CLASS PROFILE: {profile.stats.character_class} (Lv. {profile.stats.character_level})",
            "",
            f"GAIN VS {reference_label.upper()}: {result.gain_pct:+.3f}%",
            f"RELATIVE SCORE:            {fmt_number(result.score, 4)}",
        ]
        try:
            rank = self.results.index(result)
            if rank + 1 < len(self.results):
                gap = (result.score / self.results[rank + 1].score - 1.0) * 100.0
                lines.append(f"GAP TO NEXT TEAM:          {gap:.4f}%")
        except ValueError:
            pass
        if self.last_sensitivity_result and self.last_sensitivity_build == profile.build_name:
            lines.append(f"ROBUSTNESS:                {self.last_sensitivity_result.confidence}; nominal wins {self.last_sensitivity_result.nominal_win_pct:.1f}%")

        if current_team:
            lines.extend(["", "CURRENT TEAM USED TO RECONSTRUCT BASELINE"])
            lines.append(f"  Main: {current_main.display_name if current_main else 'Unknown'}")
            for companion in current_team:
                if current_main is None or companion.uid != current_main.uid:
                    lines.append(f"  Sub:  {companion.display_name}")
            lines.append(f"  Reconstructed unequipped Attack: {fmt_number(model_stats.attack)} from displayed {fmt_number(profile.stats.attack)}")

        lines.extend(["", "RECOMMENDED TEAM", f"  Main: {result.main.display_name} — {result.main.effect_text}"])
        for companion in result.subs:
            lines.append(f"  Sub:  {companion.display_name} — {companion.effect_text}")
        if profile.main_options.mode == "Equip effects only":
            lines.append("  Main active bonuses are deliberately excluded from scoring.")
        elif result.main.main_bonus:
            lines.append(f"  Measured Main adjustment included: {result.main.main_bonus:+.2f}%")
        else:
            lines.append("  Main active skill contribution remains heuristic/unmeasured.")

        lines.extend(["", "WHY THIS TEAM / SWAP COSTS"])
        selected_uids = {c.uid for c in result.team}
        excluded = [c for c in profile.companions if c.uid not in selected_uids]
        for companion in result.team:
            if profile.main_options.mode == "Lock selected Main" and companion.uid == profile.main_options.locked_main_uid:
                lines.append(f"  {companion.display_name}: locked as Main; not eligible for replacement analysis.")
                continue
            reduced = tuple(c for c in result.team if c.uid != companion.uid)
            marginal_text = ""
            if reduced:
                try:
                    reduced_score, _ = score_team_advanced(model_stats, profile.target, reduced, profile.main_options)
                    marginal = (result.score / reduced_score - 1.0) * 100.0 if reduced_score > 0 else 0.0
                    marginal_text = f"; removal loses about {marginal:.3f}%"
                except Exception:
                    marginal_text = ""
            best_replacement = None
            best_score = -math.inf
            for candidate in excluded:
                candidate_team = tuple(candidate if c.uid == companion.uid else c for c in result.team)
                try:
                    score, _ = score_team_advanced(model_stats, profile.target, candidate_team, profile.main_options)
                except Exception:
                    continue
                if score > best_score:
                    best_score, best_replacement = score, candidate
            if best_replacement is not None:
                swap_loss = (result.score / best_score - 1.0) * 100.0 if best_score > 0 else 0.0
                lines.append(f"  {companion.display_name}: {companion.effect_text}{marginal_text}; best swap is {best_replacement.display_name} at {swap_loss:.3f}% lower score.")
            else:
                lines.append(f"  {companion.display_name}: {companion.effect_text}{marginal_text}.")

        lines.extend(["", "COMBINED EQUIP EFFECTS"])
        for key, value in sorted(result.effect_totals.items(), key=lambda item: EFFECT_LABELS.get(item[0], item[0])):
            suffix = "" if key in {"attack", "accuracy"} else "%"
            lines.append(f"  {EFFECT_LABELS.get(key, key)}: +{fmt_number(value)}{suffix}")

        lines.extend(["", "CURRENT/REFERENCE → RECOMMENDED"])
        comparisons = [
            ("Attack", reference_state.attack, state.attack, ""),
            ("Main Stat", reference_state.total_main_stat, state.total_main_stat, ""),
            ("Critical Rate", reference_state.crit_rate, state.crit_rate, "%"),
            ("Attack Speed", reference_state.attack_speed, state.attack_speed, "%"),
            ("Min Damage", reference_state.min_damage, state.min_damage, "%"),
            ("Max Damage", reference_state.max_damage, state.max_damage, "%"),
            ("Normal Damage", reference_state.normal_damage, state.normal_damage, "%"),
            ("Boss Damage", reference_state.boss_damage, state.boss_damage, "%"),
            ("Status Damage", reference_state.status_damage, state.status_damage, "%"),
            ("Accuracy", reference_state.accuracy, state.accuracy, ""),
        ]
        for label, before, after, suffix in comparisons:
            if abs(after - before) > 1e-9 or label in {"Attack", "Critical Rate", "Attack Speed"}:
                lines.append(f"  {label:<18} {fmt_number(before):>12}{suffix} → {fmt_number(after):>12}{suffix}")

        lines.extend(["", "CONTENT SCORES", f"  Reference:          {fmt_number(reference_state.score_selected, 4)}", f"  Recommended normal:{fmt_number(state.score_normal, 4):>14}", f"  Recommended boss:  {fmt_number(state.score_boss, 4):>14}", f"  Recommended arena: {fmt_number(state.score_arena, 4):>14}"])
        if state.warnings:
            lines.extend(["", "MODEL NOTES"])
            lines.extend(f"  • {warning}" for warning in state.warnings)
        lines.extend(["", "Interpretation", "  The team search is exhaustive for the owned pages entered and the selected Main mode.", "  Swap costs are local comparisons after replacing one selected page with the best excluded page.", "  Sensitivity analysis is the preferred way to handle uncertain Basic Attack share and Status uptime."])
        return "\n".join(lines)

    def show_about(self):
        text = (
            f"{APP_NAME} {APP_VERSION}\n\n"
            "Current scope\n"
            "• One shared account stores class, level, companion ownership/levels, and slots.\n"
            "• Portrait-grid collection editor with direct ownership, level, and current-role controls.\n"
            "• Multiple builds store their own screenshots, stats, current team, target, Main mode, and uncertainty ranges.\n"
            "• Legacy single-profile JSON files are migrated into one imported build.\n\n"
            "Analysis\n"
            "• Exact equip-effect optimization with optional Main lock and Main preference modes.\n"
            "• Sensitivity/confidence analysis across Basic Attack share, Status uptime, Defense, and Evasion ranges.\n"
            "• Best Sub team comparison for every possible Main.\n"
            "• Next-level companion value planner and per-result swap explanations.\n"
            "• Profile readiness checks flag conflicts, missing current slots, and suspicious assumptions.\n\n"
            "Limitations\n"
            "• Main companion animations, AI, healing, crowd control, target count, and unmeasured active skills are not fully simulated.\n"
            "• Upgrade values model equip effects only and do not include copy/resource costs.\n"
            "• Accuracy/Evasion remains optional and approximate.\n"
            "• This is a community modeling tool, not an official Nexon product."
        )
        messagebox.showinfo("About and model notes", text, parent=self)


def main() -> int:
    try:
        app = AdvancedOptimizerApp()
        app.mainloop()
        return 0
    except Exception as exc:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        log_path = write_crash_log(
            "Application startup or main loop", exc_type, exc_value, exc_traceback
        )
        print(f"{APP_NAME} failed to start: {exc}", file=sys.stderr)
        traceback.print_exc()
        try:
            root = tk.Tk()
            root.withdraw()
            apply_window_icon(root)
            location = f"\n\nA crash log was saved to:\n{log_path}" if log_path else ""
            messagebox.showerror(
                APP_NAME,
                f"The program failed to start:\n\n{exc}{location}",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
