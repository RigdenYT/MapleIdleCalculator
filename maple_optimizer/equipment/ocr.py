"""Screen capture, stable-region monitoring, and color-aware Potential OCR."""

from __future__ import annotations

import difflib
from collections import Counter
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageGrab, ImageOps, ImageStat

from .data import (
    OCR_ALIASES,
    OCR_FLAT_MAX_BY_RARITY,
    OCR_PERCENT_MAX_BY_RARITY,
    PERCENT_OPTIONS,
    POTENTIAL_RARITIES,
    SLOT_SPECIAL_LEGAL_VALUES,
    SLOT_SPECIAL_OPTIONS,
    SPECIAL_OPTION_TO_SLOTS,
)
from .models import (
    CaptureRegion,
    POTENTIAL_UNIT_FLAT,
    POTENTIAL_UNIT_PERCENT,
    PotentialLine,
    PotentialOCRResult,
    normalize_potential_unit,
)


def capture_full_screen() -> Image.Image:
    errors: List[str] = []
    try:
        image = ImageGrab.grab(all_screens=True)
        if image.width > 0 and image.height > 0:
            return image.convert("RGB")
    except Exception as exc:
        errors.append(f"Pillow ImageGrab: {exc}")

    spectacle = shutil.which("spectacle")
    if spectacle:
        with tempfile.TemporaryDirectory(prefix="maple-potential-capture-") as temp_dir:
            path = Path(temp_dir) / "screen.png"
            commands = (
                [spectacle, "-b", "-n", "-o", str(path)],
                [spectacle, "--background", "--nonotify", "--output", str(path)],
            )
            for command in commands:
                try:
                    completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
                    if completed.returncode == 0 and path.exists():
                        return Image.open(path).convert("RGB")
                    errors.append((completed.stderr or completed.stdout or "Spectacle failed").strip())
                except Exception as exc:
                    errors.append(f"Spectacle: {exc}")

    raise RuntimeError(
        "Could not capture the screen. Under KDE/Wayland, install Spectacle or use "
        "Read Screenshot File instead.\n\n" + "\n".join(error for error in errors if error)
    )


def crop_region(image: Image.Image, region: CaptureRegion) -> Image.Image:
    nx1, ny1, nx2, ny2 = region.normalized()
    x1 = int(round(nx1 * image.width))
    y1 = int(round(ny1 * image.height))
    x2 = int(round(nx2 * image.width))
    y2 = int(round(ny2 * image.height))
    x1, x2 = sorted((max(0, x1), min(image.width, x2)))
    y1, y2 = sorted((max(0, y1), min(image.height, y2)))
    if x2 - x1 < 40 or y2 - y1 < 40:
        raise ValueError("The saved Potential capture region is too small. Calibrate it again.")
    return image.crop((x1, y1, x2, y2))



POTENTIAL_CANONICAL_SIZE = (780, 234)


def _contiguous_groups(values: Sequence[int]) -> List[Tuple[int, int]]:
    values = list(values)
    if not values:
        return []
    groups: List[Tuple[int, int]] = []
    start = previous = int(values[0])
    for value in values[1:]:
        value = int(value)
        if value <= previous + 1:
            previous = value
            continue
        groups.append((start, previous))
        start = previous = value
    groups.append((start, previous))
    return groups


def locate_potential_panel_bounds(image: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """Locate the actual Potential card inside an approximate calibration crop.

    The card's large inner option box has a distinctive neutral charcoal fill.
    Detecting that rectangle lets the OCR geometry remain stable when the user
    leaves modest margins around the card, moves the game window, or changes
    between 1080p and 1440p.
    """
    source = image.convert("RGB")
    width, height = source.size
    if width < 180 or height < 90:
        return None

    pixels = source.load()
    mask_rows: List[bytearray] = []
    row_counts: List[int] = []
    for y in range(height):
        row = bytearray(width)
        count = 0
        for x in range(width):
            red, green, blue = pixels[x, y]
            average = (red + green + blue) / 3.0
            spread = max(red, green, blue) - min(red, green, blue)
            # The inner Potential box is normally around RGB 49/48/49. Keep a
            # tolerant range for capture compression and game-window scaling.
            matched = 42.0 <= average <= 68.0 and spread <= 14
            if matched:
                row[x] = 1
                count += 1
        mask_rows.append(row)
        row_counts.append(count)

    row_threshold = max(36, int(width * 0.28))
    row_groups = _contiguous_groups(
        index for index, count in enumerate(row_counts) if count >= row_threshold
    )
    minimum_group_height = max(35, int(height * 0.14))
    row_groups = [
        group for group in row_groups
        if group[1] - group[0] + 1 >= minimum_group_height
    ]

    candidates: List[Tuple[float, int, int, int, int]] = []
    for y1, y2 in row_groups:
        candidate_height = y2 - y1 + 1
        col_counts = [0] * width
        for y in range(y1, y2 + 1):
            row = mask_rows[y]
            for x, matched in enumerate(row):
                if matched:
                    col_counts[x] += 1
        col_threshold = max(25, int(candidate_height * 0.42))
        col_groups = _contiguous_groups(
            index for index, count in enumerate(col_counts) if count >= col_threshold
        )
        for x1, x2 in col_groups:
            candidate_width = x2 - x1 + 1
            if candidate_width < 160 or candidate_height < 70:
                continue
            aspect = candidate_width / max(1.0, float(candidate_height))
            if not 2.1 <= aspect <= 5.0:
                continue
            matched_pixels = sum(
                sum(mask_rows[y][x1:x2 + 1])
                for y in range(y1, y2 + 1)
            )
            density = matched_pixels / max(1.0, candidate_width * candidate_height)
            aspect_score = max(0.2, 1.0 - abs(aspect - 2.85) / 5.0)
            score = candidate_width * candidate_height * density * aspect_score
            candidates.append((score, x1, y1, x2 + 1, y2 + 1))

    if not candidates:
        return None
    _score, inner_left, inner_top, inner_right, inner_bottom = max(candidates)
    inner_width = inner_right - inner_left
    inner_height = inner_bottom - inner_top

    # Expand from the inner charcoal rectangle to the whole card, including
    # the left-side "Potential Options" label and outer border. Ratios are
    # derived from the game panel and remain stable across window sizes.
    left = max(0, int(round(inner_left - inner_width * 0.235)))
    right = min(width, int(round(inner_right + inner_width * 0.022)))
    top = max(0, int(round(inner_top - inner_height * 0.055)))
    bottom = min(height, int(round(inner_bottom + inner_height * 0.055)))
    if right - left < 200 or bottom - top < 90:
        return None
    return left, top, right, bottom


def normalize_potential_panel(
    image: Image.Image,
) -> Tuple[Image.Image, Tuple[str, ...], Optional[Tuple[int, int, int, int]]]:
    """Localize and normalize a roughly selected Potential card."""
    source = image.convert("RGB")
    bounds = locate_potential_panel_bounds(source)
    warnings: List[str] = []
    if bounds is None:
        warnings.append(
            "Could not locate the full Potential card inside the calibrated region. "
            "Recalibrate around the complete card, including its left label and outer border."
        )
        cropped = source
    else:
        cropped = source.crop(bounds)
    normalized = cropped.resize(POTENTIAL_CANONICAL_SIZE, Image.Resampling.LANCZOS)
    return normalized, tuple(warnings), bounds


def build_potential_debug_overlay(image: Image.Image) -> Image.Image:
    """Show the normalized OCR header and row geometry for calibration review."""
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    boxes = (
        ("header", (0.0, 0.0, 1.0, 0.28), "cyan"),
        ("line 1", (0.15, 0.27, 1.0, 0.46), "yellow"),
        ("line 2", (0.15, 0.44, 1.0, 0.63), "lime"),
        ("line 3", (0.15, 0.61, 1.0, 0.82), "orange"),
    )
    for label, box, color in boxes:
        x1, y1, x2, y2 = box
        rect = (
            int(round(x1 * overlay.width)),
            int(round(y1 * overlay.height)),
            int(round(x2 * overlay.width)),
            int(round(y2 * overlay.height)),
        )
        draw.rectangle(rect, outline=color, width=3)
        draw.text((rect[0] + 4, rect[1] + 3), label, fill=color)
    return overlay


def region_fingerprint(image: Image.Image) -> bytes:
    """Return a small quantized fingerprint suitable for cheap change detection."""
    thumb = ImageOps.grayscale(image).resize((96, 48), Image.Resampling.BILINEAR)
    values = thumb.get_flattened_data() if hasattr(thumb, "get_flattened_data") else thumb.getdata()
    return bytes((pixel // 12) * 12 for pixel in values)


def fingerprint_distance(first: bytes, second: bytes) -> float:
    if not first or not second or len(first) != len(second):
        return 255.0
    return sum(abs(a - b) for a, b in zip(first, second)) / len(first)


def _runtime_env(tessdata: Optional[Path]) -> Dict[str, str]:
    env = dict(os.environ)
    if tessdata:
        env["TESSDATA_PREFIX"] = str(tessdata)
    return env


def _run_tesseract(
    image: Image.Image,
    executable: Path,
    tessdata: Optional[Path],
    *,
    psm: int = 6,
    whitelist: str = "",
) -> str:
    with tempfile.TemporaryDirectory(prefix="maple-potential-ocr-") as temp_dir:
        source = Path(temp_dir) / "potential.png"
        image.save(source)
        command = [str(executable), str(source), "stdout", "--psm", str(psm), "-l", "eng"]
        if whitelist:
            command.extend(["-c", f"tessedit_char_whitelist={whitelist}"])
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            env=_runtime_env(tessdata),
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "Tesseract failed").strip())
        return completed.stdout.strip()


def _scale(image: Image.Image, factor: int = 4) -> Image.Image:
    return image.resize((max(1, image.width * factor), max(1, image.height * factor)), Image.Resampling.LANCZOS)


def _color_text_mask(image: Image.Image, *, include_yellow: bool = True, include_white: bool = True) -> Image.Image:
    source = _scale(image.convert("RGB"), 4)
    pixels = []
    source_pixels = source.get_flattened_data() if hasattr(source, "get_flattened_data") else source.getdata()
    for red, green, blue in source_pixels:
        white = include_white and min(red, green, blue) >= 125 and max(red, green, blue) - min(red, green, blue) <= 85
        yellow = include_yellow and red >= 150 and green >= 115 and blue <= 175 and red + green >= blue * 2.0
        cyan = red <= 120 and green >= 125 and blue >= 125
        pixels.append(255 if white or yellow or cyan else 0)
    mask = Image.new("L", source.size)
    mask.putdata(pixels)
    mask = mask.filter(ImageFilter.MaxFilter(3))
    return mask.convert("RGB")


def _gray_variants(image: Image.Image) -> Sequence[Image.Image]:
    enlarged = _scale(image.convert("RGB"), 4)
    gray = ImageOps.grayscale(enlarged)
    gray = ImageEnhance.Sharpness(gray).enhance(2.0)
    contrast = ImageEnhance.Contrast(gray).enhance(2.3)
    threshold_120 = contrast.point(lambda pixel: 255 if pixel >= 120 else 0)
    threshold_155 = contrast.point(lambda pixel: 255 if pixel >= 155 else 0)
    return (
        enlarged,
        contrast.convert("RGB"),
        threshold_120.convert("RGB"),
        threshold_155.convert("RGB"),
        _color_text_mask(image, include_yellow=True, include_white=True),
        _color_text_mask(image, include_yellow=True, include_white=False),
        _color_text_mask(image, include_yellow=False, include_white=True),
    )


def _normalize_label(label: str) -> str:
    label = label.replace("|", "I").replace("1NT", "INT").replace("lNT", "INT")
    normalized = re.sub(r"[^A-Za-z ]+", " ", label).strip().lower()
    return re.sub(r"\s+", " ", normalized)


def _label_tokens(label: str) -> Tuple[str, ...]:
    normalized = _normalize_label(label)
    tokens = []
    for token in normalized.split():
        token = {
            "crit": "critical",
            "atk": "attack",
            "def": "defense",
            "minimum": "min",
            "maximum": "max",
            "darnage": "damage",
        }.get(token, token)
        tokens.append(token)
    return tuple(tokens)


# Compound damage labels must contain their distinguishing modifier. This keeps
# a clean or partially read "Damage" from being silently expanded to Boss
# Monster Damage merely because the shorter string is a suffix of the longer.
_REQUIRED_LABEL_TOKENS = {
    "Final Damage": {"final"},
    "Critical Damage": {"critical"},
    "Boss Monster Damage": {"boss"},
    "Normal Monster Damage": {"normal"},
    "Basic Attack Damage": {"basic"},
    "Skill Damage": {"skill"},
    "Damage Taken Decrease": {"taken", "decrease"},
    "Min Damage Multiplier": {"min", "multiplier"},
    "Max Damage Multiplier": {"max", "multiplier"},
}


def _canonical_stat(label: str, percent: bool) -> Optional[str]:
    result, _confidence = _canonical_stat_with_confidence(label, percent)
    return result


def _canonical_stat_with_confidence(label: str, percent: bool) -> Tuple[Optional[str], float]:
    normalized = _normalize_label(label)
    if not normalized:
        return None, 0.0
    input_tokens = set(_label_tokens(label))

    # Exact aliases always win. In particular, exact Damage can never resolve
    # to a longer damage option.
    exact_matches: List[str] = []
    for canonical, aliases in OCR_ALIASES.items():
        if any(normalized == _normalize_label(alias) for alias in aliases):
            exact_matches.append(canonical)
    if exact_matches:
        canonical = min(exact_matches, key=lambda item: (len(_label_tokens(item)), item))
        if percent and canonical in {"Attack", "Max HP", "Max MP", "Main Stat"}:
            canonical += " %"
        return canonical, 1.0

    best: Optional[Tuple[float, str]] = None
    for canonical, aliases in OCR_ALIASES.items():
        required = _REQUIRED_LABEL_TOKENS.get(canonical, set())
        # Never invent a modifier that the OCR did not read.
        if required and not required.issubset(input_tokens):
            continue
        for alias in aliases:
            candidate = _normalize_label(alias)
            candidate_tokens = set(_label_tokens(alias))
            if not candidate:
                continue
            sequence_score = difflib.SequenceMatcher(None, normalized, candidate).ratio()
            overlap = len(input_tokens & candidate_tokens)
            precision = overlap / max(1, len(input_tokens))
            recall = overlap / max(1, len(candidate_tokens))
            token_score = 0.0 if precision + recall == 0 else 2.0 * precision * recall / (precision + recall)
            score = sequence_score * 0.58 + token_score * 0.42
            # Short primary-stat labels must remain close to exact; fuzzy INT
            # should not become an unrelated long option.
            if canonical in {"STR", "DEX", "INT", "LUK"} and len(normalized) <= 4:
                score = max(score, sequence_score)
            if best is None or score > best[0]:
                best = (score, canonical)
    if best is None or best[0] < 0.64:
        return None, 0.0
    canonical = best[1]
    if canonical == "Damage" and input_tokens - {"damage"}:
        return None, 0.0
    if percent and canonical in {"Attack", "Max HP", "Max MP", "Main Stat"}:
        canonical += " %"
    return canonical, best[0]

def _parse_number_text(text: str) -> Tuple[Optional[float], bool, float]:
    cleaned = text.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    cleaned = cleaned.replace("·", ".").replace("•", ".").replace("٫", ".")
    match = re.search(r"(-?\d[\d,]*(?:\.\d+)?)\s*(%)?", cleaned)
    if not match:
        return None, False, 0.0
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None, False, 0.0
    confidence = 1.0 if match.group(0).strip() == cleaned.strip() else 0.88
    return value, bool(match.group(2)), confidence


def _value_is_plausible(
    stat_name: str,
    value: float,
    unit: str = "",
    *,
    rarity: str = "",
    equipment_slot: str = "",
) -> bool:
    if not (0.0 <= value <= 1_000_000.0):
        return False
    normalized_unit = normalize_potential_unit(stat_name, unit)
    if stat_name in {"Cooldown Reduction", "All Skill Levels", "Basic Attack Targets", "Accuracy", "Evasion"} and value > 100.0:
        return False

    # Exact slot-special values are available and are therefore stronger than
    # the broad generic plausibility limits below.
    special = SLOT_SPECIAL_OPTIONS.get(equipment_slot)
    legal_by_rank = SLOT_SPECIAL_LEGAL_VALUES.get(equipment_slot, {})
    if special == stat_name and rarity in legal_by_rank:
        return any(abs(value - legal) <= 0.011 for legal in legal_by_rank[rarity])

    if normalized_unit == POTENTIAL_UNIT_PERCENT or stat_name in PERCENT_OPTIONS:
        cap = OCR_PERCENT_MAX_BY_RARITY.get(rarity, 500.0)
        return value <= cap + 1e-9
    cap = OCR_FLAT_MAX_BY_RARITY.get(rarity, 1_000_000.0)
    return value <= cap + 1e-9


def _sane_value(
    stat_name: str,
    value: float,
    unit: str = "",
    *,
    rarity: str = "",
    equipment_slot: str = "",
) -> bool:
    return _value_is_plausible(
        stat_name,
        value,
        unit,
        rarity=rarity,
        equipment_slot=equipment_slot,
    )


def _numeric_candidates(text: str) -> List[Tuple[float, bool, float, str]]:
    """Return OCR number candidates, including decimal-loss recovery options."""
    value, percent, confidence = _parse_number_text(text)
    if value is None:
        return []
    cleaned = text.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    cleaned = cleaned.replace("·", ".").replace("•", ".").replace("٫", ".")
    candidates: List[Tuple[float, bool, float, str]] = [(value, percent, confidence, "")]
    numeric_match = re.search(r"\d[\d,]*(?:\.\d+)?", cleaned)
    numeric_text = numeric_match.group(0).replace(",", "") if numeric_match else ""
    # Tiny decimal points are the most common loss in this UI. Only propose
    # recovery when OCR returned an integer with at least two digits.
    if numeric_text and "." not in numeric_text and numeric_text.isdigit() and len(numeric_text) >= 2:
        candidates.append((value / 10.0, percent, confidence * 0.90, f"Recovered a likely missing decimal: {value:g} → {value / 10.0:g}."))
        if len(numeric_text) >= 3:
            candidates.append((value / 100.0, percent, confidence * 0.78, f"Recovered a likely missing decimal: {value:g} → {value / 100.0:g}."))
    return candidates


def _select_numeric_candidate(
    texts: Sequence[str],
    stat_name: str,
    *,
    rarity: str = "",
    equipment_slot: str = "",
) -> Tuple[Optional[float], bool, float, str]:
    scored: List[Tuple[float, float, bool, str]] = []
    for text in texts:
        for value, percent, confidence, warning in _numeric_candidates(text):
            unit = POTENTIAL_UNIT_PERCENT if percent else POTENTIAL_UNIT_FLAT
            plausible = _value_is_plausible(
                stat_name,
                value,
                unit,
                rarity=rarity,
                equipment_slot=equipment_slot,
            )
            if not plausible:
                continue
            score = confidence
            if warning:
                score -= 0.04
            # Prefer an explicitly seen decimal over a reconstructed one when
            # both are plausible, but prefer a reconstructed legal value over
            # an impossible raw integer such as Rare 45%.
            if "." in text:
                score += 0.05
            scored.append((score, value, percent, warning))
    if not scored:
        return None, False, 0.0, ""
    scored.sort(key=lambda item: (item[0], -abs(item[1])), reverse=True)
    score, value, percent, warning = scored[0]
    return value, percent, max(0.0, min(1.0, score)), warning

def _make_line(stat_name: str, value: float, percent: bool) -> PotentialLine:
    return PotentialLine(
        stat_name,
        value,
        POTENTIAL_UNIT_PERCENT if percent else POTENTIAL_UNIT_FLAT,
    )


def parse_potential_text(text: str) -> PotentialOCRResult:
    """Fallback parser for whole-panel OCR and tests."""
    cleaned_lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    cleaned_lines = [line for line in cleaned_lines if line]
    joined = "\n".join(cleaned_lines)

    rarity = ""
    for candidate in POTENTIAL_RARITIES:
        if re.search(rf"\b{re.escape(candidate)}\b", joined, re.IGNORECASE):
            rarity = candidate
            break

    progress = 0
    progress_total = 0
    progress_match = re.search(r"\b(\d{1,4})\s*/\s*(\d{1,4})\b", joined)
    if progress_match:
        progress = int(progress_match.group(1))
        progress_total = int(progress_match.group(2))

    lines: List[PotentialLine] = []
    confidences: List[float] = []
    warnings: List[str] = []
    value_pattern = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*(%)?\s*[.,;:|]*\s*$")
    for line in cleaned_lines:
        if re.search(r"Potential\s+Options?", line, re.IGNORECASE):
            line = re.sub(r"Potential\s+Options?", "", line, flags=re.IGNORECASE).strip()
        match = value_pattern.search(line)
        if not match:
            continue
        label = line[: match.start()].strip(" :-@[]()")
        label = re.sub(r"^(?:Potential|Options?)\s+", "", label, flags=re.IGNORECASE).strip()
        if not label or re.search(r"\b(?:Rare|Epic|Unique|Legendary|Mystic|Normal)\b", label, re.IGNORECASE):
            continue
        percent = bool(match.group(2))
        stat_name, label_confidence = _canonical_stat_with_confidence(label, percent)
        if stat_name is None:
            continue
        value, recovered_percent, value_confidence, recovery_warning = _select_numeric_candidate(
            [match.group(0)], stat_name, rarity=rarity
        )
        if value is None:
            continue
        percent = recovered_percent or percent
        unit = POTENTIAL_UNIT_PERCENT if percent else POTENTIAL_UNIT_FLAT
        if not _sane_value(stat_name, value, unit, rarity=rarity):
            continue
        lines.append(_make_line(stat_name, value, percent))
        confidences.append(min(label_confidence, value_confidence))
        if recovery_warning:
            warnings.append(recovery_warning)

    deduped: List[PotentialLine] = []
    deduped_confidence: List[float] = []
    for line, confidence in zip(lines, confidences):
        if line not in deduped:
            deduped.append(line)
            deduped_confidence.append(confidence)
    lines = deduped[:3]
    confidences = deduped_confidence[:3]

    if not rarity:
        warnings.append("Potential rarity was not recognized.")
    if len(lines) != 3:
        warnings.append(f"Recognized {len(lines)} of 3 Potential lines.")
    overall = (sum(confidences) / len(confidences) if confidences else 0.0) * (1.0 if rarity else 0.8)
    return PotentialOCRResult(
        rarity=rarity,
        progress=progress,
        progress_total=progress_total,
        lines=tuple(lines),
        raw_text=text.strip(),
        warnings=tuple(warnings),
        line_confidences=tuple(confidences),
        confidence=overall,
    )


def _crop_fraction(image: Image.Image, x1: float, y1: float, x2: float, y2: float) -> Image.Image:
    return image.crop((
        int(image.width * x1),
        int(image.height * y1),
        max(int(image.width * x2), int(image.width * x1) + 1),
        max(int(image.height * y2), int(image.height * y1) + 1),
    ))


def _read_header(image: Image.Image, executable: Path, tessdata: Optional[Path]) -> Tuple[str, int, int, str]:
    header = _crop_fraction(image, 0.0, 0.0, 1.0, 0.28)
    texts: List[str] = []
    for variant in (_color_text_mask(header), _gray_variants(header)[2]):
        texts.append(_run_tesseract(variant, executable, tessdata, psm=6))
    joined = "\n".join(texts)
    rarity = ""
    for candidate in POTENTIAL_RARITIES:
        if re.search(rf"\b{re.escape(candidate)}\b", joined, re.IGNORECASE):
            rarity = candidate
            break
    progress = progress_total = 0
    for text in texts:
        match = re.search(r"(\d{1,4})\s*/\s*(\d{1,4})", text)
        if match:
            progress, progress_total = int(match.group(1)), int(match.group(2))
            break
    return rarity, progress, progress_total, joined


def _read_header_fast(image: Image.Image, executable: Path, tessdata: Optional[Path]) -> Tuple[str, int, int, str]:
    """Read the Potential header with one Tesseract launch.

    This is deliberately conservative: an incomplete fast read falls back to
    the full multi-variant pipeline instead of being accepted optimistically.
    """
    header = _crop_fraction(image, 0.0, 0.0, 1.0, 0.28)
    text = _run_tesseract(_color_text_mask(header), executable, tessdata, psm=6)
    rarity = ""
    for candidate in POTENTIAL_RARITIES:
        if re.search(rf"\b{re.escape(candidate)}\b", text, re.IGNORECASE):
            rarity = candidate
            break
    progress = progress_total = 0
    match = re.search(r"(\d{1,4})\s*/\s*(\d{1,4})", text)
    if match:
        progress, progress_total = int(match.group(1)), int(match.group(2))
    return rarity, progress, progress_total, text


def _read_row(
    row: Image.Image,
    executable: Path,
    tessdata: Optional[Path],
    *,
    rarity: str = "",
    equipment_slot: str = "",
) -> Tuple[Optional[PotentialLine], float, str, Tuple[str, ...]]:
    raw_parts: List[str] = []
    warnings: List[str] = []

    # Whole-row passes are useful when spacing is clean. The token-aware label
    # matcher prevents a short Damage read from being promoted to Boss Damage.
    fast_variants = (
        _color_text_mask(row, include_yellow=True, include_white=True),
        _gray_variants(row)[2],
        _gray_variants(row)[1],
    )
    parsed: List[Tuple[float, PotentialLine, str]] = []
    for variant in fast_variants:
        text = _run_tesseract(variant, executable, tessdata, psm=7)
        if not text:
            continue
        raw_parts.append(f"row:{text}")
        match = re.search(r"(-?\d[\d,]*(?:[.·•]\d+)?)\s*(%)?\s*$", text)
        if not match:
            continue
        label = text[: match.start()].strip(" :-@[]()")
        stat, label_confidence = _canonical_stat_with_confidence(label, bool(match.group(2)))
        if stat is None:
            continue
        value, percent, value_confidence, recovery_warning = _select_numeric_candidate(
            [match.group(0)],
            stat,
            rarity=rarity,
            equipment_slot=equipment_slot,
        )
        if value is None:
            continue
        unit = POTENTIAL_UNIT_PERCENT if (percent or bool(match.group(2))) else POTENTIAL_UNIT_FLAT
        if not _sane_value(
            stat,
            value,
            unit,
            rarity=rarity,
            equipment_slot=equipment_slot,
        ):
            continue
        score = min(1.0, 0.68 * label_confidence + 0.32 * value_confidence + 0.03)
        parsed.append((score, PotentialLine(stat, value, unit), recovery_warning))
        if score >= 0.92 and not recovery_warning:
            return PotentialLine(stat, value, unit), score, " | ".join(raw_parts), tuple(warnings)
    if parsed:
        parsed.sort(reverse=True, key=lambda item: item[0])
        confidence, line, recovery_warning = parsed[0]
        if recovery_warning:
            warnings.append(recovery_warning)
        return line, confidence, " | ".join(raw_parts), tuple(warnings)

    # Split label/value passes preserve tiny decimal points better. The value
    # crop deliberately includes an unthresholded high-resolution grayscale
    # variant because aggressive morphology can erase the dot in 4.5%.
    label_crop = _crop_fraction(row, 0.0, 0.0, 0.80, 1.0)
    value_crop = _crop_fraction(row, 0.64, 0.0, 1.0, 1.0)
    label_candidates: List[Tuple[float, str]] = []
    value_texts: List[str] = []
    for variant in (
        _color_text_mask(label_crop),
        _gray_variants(label_crop)[2],
        _gray_variants(label_crop)[1],
    ):
        label_text = _run_tesseract(variant, executable, tessdata, psm=7)
        if label_text:
            raw_parts.append(f"label:{label_text}")
            stat, confidence = _canonical_stat_with_confidence(label_text, False)
            if stat:
                label_candidates.append((confidence, stat))

    enlarged_value = _scale(value_crop.convert("RGB"), 6)
    gray_value = ImageOps.grayscale(enlarged_value)
    gray_value = ImageEnhance.Sharpness(gray_value).enhance(2.5)
    gray_value = ImageEnhance.Contrast(gray_value).enhance(2.0)
    decimal_variants = (
        enlarged_value,
        gray_value.convert("RGB"),
        gray_value.point(lambda pixel: 255 if pixel >= 105 else 0).convert("RGB"),
        gray_value.point(lambda pixel: 255 if pixel >= 145 else 0).convert("RGB"),
        _color_text_mask(value_crop),
    )
    for variant in decimal_variants:
        value_text = _run_tesseract(
            variant,
            executable,
            tessdata,
            psm=7,
            whitelist="0123456789.,·•-%",
        )
        if value_text:
            raw_parts.append(f"value:{value_text}")
            value_texts.append(value_text)

    label_candidates.sort(reverse=True)
    for label_confidence, stat in label_candidates:
        value, percent, value_confidence, recovery_warning = _select_numeric_candidate(
            value_texts,
            stat,
            rarity=rarity,
            equipment_slot=equipment_slot,
        )
        if value is None:
            continue
        normalized_stat = stat
        if percent and stat in {"Attack", "Max HP", "Max MP", "Main Stat"}:
            normalized_stat += " %"
        unit = POTENTIAL_UNIT_PERCENT if percent else POTENTIAL_UNIT_FLAT
        if _sane_value(
            normalized_stat,
            value,
            unit,
            rarity=rarity,
            equipment_slot=equipment_slot,
        ):
            confidence = min(1.0, 0.65 * label_confidence + 0.35 * value_confidence)
            if recovery_warning:
                warnings.append(recovery_warning)
            return PotentialLine(normalized_stat, value, unit), confidence, " | ".join(raw_parts), tuple(warnings)
    return None, 0.0, " | ".join(raw_parts), tuple(warnings)

def _read_row_fast(
    row: Image.Image,
    executable: Path,
    tessdata: Optional[Path],
    *,
    rarity: str = "",
    equipment_slot: str = "",
) -> Tuple[Optional[PotentialLine], float, str, Tuple[str, ...]]:
    """Attempt one high-value whole-row OCR pass.

    Clean Potential panels normally resolve with one process per row. Any
    missing label, value, decimal, or plausibility check sends the image to the
    slower defensive reader rather than starting every fallback up front.
    """
    text = _run_tesseract(
        _color_text_mask(row, include_yellow=True, include_white=True),
        executable,
        tessdata,
        psm=7,
    )
    if not text:
        return None, 0.0, "", ()
    match = re.search(r"(-?\d[\d,]*(?:[.·•]\d+)?)\s*(%)?\s*$", text)
    if not match:
        return None, 0.0, f"row:{text}", ()
    label = text[: match.start()].strip(" :-@[]()")
    stat, label_confidence = _canonical_stat_with_confidence(label, bool(match.group(2)))
    if stat is None:
        return None, 0.0, f"row:{text}", ()
    value, percent, value_confidence, recovery_warning = _select_numeric_candidate(
        [match.group(0)],
        stat,
        rarity=rarity,
        equipment_slot=equipment_slot,
    )
    if value is None:
        return None, 0.0, f"row:{text}", ()
    unit = POTENTIAL_UNIT_PERCENT if (percent or bool(match.group(2))) else POTENTIAL_UNIT_FLAT
    if not _sane_value(stat, value, unit, rarity=rarity, equipment_slot=equipment_slot):
        return None, 0.0, f"row:{text}", ()
    warnings = (recovery_warning,) if recovery_warning else ()
    confidence = min(1.0, 0.68 * label_confidence + 0.32 * value_confidence + 0.03)
    return PotentialLine(stat, value, unit), confidence, f"row:{text}", warnings


def _validate_result(
    result: PotentialOCRResult,
    *,
    equipment_slot: str = "",
    expected_rarity: str = "",
) -> PotentialOCRResult:
    warnings = list(result.warnings)
    confidences = list(result.line_confidences)
    adjusted_confidence = result.confidence
    if expected_rarity and result.rarity and expected_rarity != result.rarity:
        warnings.append(f"OCR read {result.rarity}, while the saved slot is {expected_rarity}. Verify the rank-up or OCR result.")
        adjusted_confidence *= 0.90
    for index, line in enumerate(result.lines):
        valid_slots = SPECIAL_OPTION_TO_SLOTS.get(line.stat_name)
        if valid_slots and equipment_slot and equipment_slot not in valid_slots:
            warnings.append(f"Line {index + 1} read {line.stat_name}, which is not valid for {equipment_slot}.")
            if index < len(confidences):
                confidences[index] *= 0.35
            adjusted_confidence *= 0.75
        if not _value_is_plausible(
            line.stat_name,
            line.value,
            line.unit,
            rarity=result.rarity or expected_rarity,
            equipment_slot=equipment_slot,
        ):
            warnings.append(
                f"Line {index + 1} value {line.display_value} is not plausible for "
                f"{result.rarity or expected_rarity or 'the selected rank'} {line.stat_name}."
            )
            if index < len(confidences):
                confidences[index] *= 0.25
            adjusted_confidence *= 0.70
    if len(result.lines) != 3:
        adjusted_confidence *= 0.55
    if confidences:
        adjusted_confidence = min(adjusted_confidence, sum(confidences) / len(confidences))
    return PotentialOCRResult(
        rarity=result.rarity,
        progress=result.progress,
        progress_total=result.progress_total,
        lines=result.lines,
        raw_text=result.raw_text,
        warnings=tuple(dict.fromkeys(warnings)),
        line_confidences=tuple(confidences),
        confidence=max(0.0, min(1.0, adjusted_confidence)),
    )


def read_potential_image(
    image: Image.Image,
    executable: Path,
    tessdata: Optional[Path] = None,
    *,
    equipment_slot: str = "",
    expected_rarity: str = "",
) -> PotentialOCRResult:
    """Read header and each Potential line independently for higher reliability."""
    rarity, progress, progress_total, header_text = _read_header(image, executable, tessdata)
    # The option area occupies the lower ~72% of a normally calibrated panel.
    # Slight overlap makes the reader tolerant of a loose user-drawn box.
    row_bounds = ((0.27, 0.46), (0.44, 0.63), (0.61, 0.82))
    lines: List[PotentialLine] = []
    confidences: List[float] = []
    raw_rows: List[str] = []
    warnings: List[str] = []
    for y1, y2 in row_bounds:
        row = _crop_fraction(image, 0.15, y1, 1.0, y2)
        line, confidence, raw, row_warnings = _read_row(
            row,
            executable,
            tessdata,
            rarity=rarity or expected_rarity,
            equipment_slot=equipment_slot,
        )
        raw_rows.append(raw)
        warnings.extend(row_warnings)
        if line is not None:
            lines.append(line)
            confidences.append(confidence)

    # Fall back to the whole-panel parser if segmentation missed rows.
    fallback_texts: List[str] = []
    if len(lines) != 3 or not rarity:
        for variant in (_color_text_mask(image), _gray_variants(image)[2]):
            fallback_texts.append(_run_tesseract(variant, executable, tessdata, psm=6))
        fallback = max((parse_potential_text(text) for text in fallback_texts), key=lambda item: (len(item.lines), item.confidence))
        if len(lines) != 3 and len(fallback.lines) == 3:
            lines = list(fallback.lines)
            confidences = list(fallback.line_confidences)
        if not rarity:
            rarity = fallback.rarity
        if not progress_total and fallback.progress_total:
            progress, progress_total = fallback.progress, fallback.progress_total

    if not rarity:
        warnings.append("Potential rarity was not recognized.")
    if len(lines) != 3:
        warnings.append(f"Recognized {len(lines)} of 3 Potential lines.")
    if confidences and min(confidences) < 0.70:
        weak = ", ".join(str(index + 1) for index, confidence in enumerate(confidences) if confidence < 0.70)
        warnings.append(f"Low OCR confidence on line(s) {weak}; review before accepting.")
    overall = (sum(confidences) / len(confidences) if confidences else 0.0)
    if rarity:
        overall = min(1.0, overall + 0.05)
    raw_text = "HEADER\n" + header_text + "\n\nROWS\n" + "\n---\n".join(raw_rows)
    if fallback_texts:
        raw_text += "\n\nWHOLE PANEL FALLBACK\n" + "\n---\n".join(fallback_texts)
    result = PotentialOCRResult(
        rarity=rarity,
        progress=progress,
        progress_total=progress_total,
        lines=tuple(lines[:3]),
        raw_text=raw_text.strip(),
        warnings=tuple(warnings),
        line_confidences=tuple(confidences[:3]),
        confidence=overall,
    )
    return _validate_result(result, equipment_slot=equipment_slot, expected_rarity=expected_rarity)


def read_potential_image_fast(
    image: Image.Image,
    executable: Path,
    tessdata: Optional[Path] = None,
    *,
    equipment_slot: str = "",
    expected_rarity: str = "",
) -> PotentialOCRResult:
    """Use four Tesseract launches for a clean panel: header plus three rows."""
    rarity, progress, progress_total, header_text = _read_header_fast(image, executable, tessdata)
    row_bounds = ((0.27, 0.46), (0.44, 0.63), (0.61, 0.82))
    lines: List[PotentialLine] = []
    confidences: List[float] = []
    raw_rows: List[str] = []
    warnings: List[str] = []
    for y1, y2 in row_bounds:
        row = _crop_fraction(image, 0.15, y1, 1.0, y2)
        line, confidence, raw, row_warnings = _read_row_fast(
            row,
            executable,
            tessdata,
            rarity=rarity or expected_rarity,
            equipment_slot=equipment_slot,
        )
        raw_rows.append(raw)
        warnings.extend(row_warnings)
        if line is not None:
            lines.append(line)
            confidences.append(confidence)
    if not rarity:
        warnings.append("Fast OCR did not recognize the Potential rarity.")
    if not progress_total:
        warnings.append("Fast OCR did not recognize rank progress.")
    if len(lines) != 3:
        warnings.append(f"Fast OCR recognized {len(lines)} of 3 Potential lines.")
    overall = sum(confidences) / len(confidences) if confidences else 0.0
    if rarity and progress_total:
        overall = min(1.0, overall + 0.03)
    raw_text = "FAST HEADER\n" + header_text + "\n\nFAST ROWS\n" + "\n---\n".join(raw_rows)
    return _validate_result(
        PotentialOCRResult(
            rarity=rarity,
            progress=progress,
            progress_total=progress_total,
            lines=tuple(lines[:3]),
            raw_text=raw_text.strip(),
            warnings=tuple(warnings),
            line_confidences=tuple(confidences[:3]),
            confidence=overall,
        ),
        equipment_slot=equipment_slot,
        expected_rarity=expected_rarity,
    )


def potential_result_is_reliable(
    result: PotentialOCRResult,
    *,
    threshold: float = 0.84,
    require_progress: bool = True,
) -> bool:
    """Return whether a result can bypass repeated-capture verification."""
    if not result.complete or result.confidence < threshold:
        return False
    if require_progress and result.progress_total <= 0:
        return False
    if len(result.line_confidences) != 3 or min(result.line_confidences) < 0.80:
        return False
    serious_markers = ("not plausible", "not valid for", "disagreed", "recognized 0", "recognized 1", "recognized 2")
    joined = " ".join(result.warnings).lower()
    return not any(marker in joined for marker in serious_markers)


def read_potential_staged(
    images: Sequence[Image.Image],
    executable: Path,
    tessdata: Optional[Path] = None,
    *,
    equipment_slot: str = "",
    expected_rarity: str = "",
) -> PotentialOCRResult:
    """Fast-first OCR; invoke defensive consensus only when confidence requires it."""
    image_list = list(images)
    if not image_list:
        raise ValueError("No Potential capture images were provided.")
    newest = image_list[-1]
    fast = read_potential_image_fast(
        newest,
        executable,
        tessdata,
        equipment_slot=equipment_slot,
        expected_rarity=expected_rarity,
    )
    if potential_result_is_reliable(fast):
        return PotentialOCRResult(
            rarity=fast.rarity,
            progress=fast.progress,
            progress_total=fast.progress_total,
            lines=fast.lines,
            raw_text=fast.raw_text,
            warnings=tuple(dict.fromkeys((*fast.warnings, "Accepted by the fast four-pass OCR path."))),
            line_confidences=fast.line_confidences,
            confidence=fast.confidence,
        )

    first_full = read_potential_image(
        newest,
        executable,
        tessdata,
        equipment_slot=equipment_slot,
        expected_rarity=expected_rarity,
    )
    if potential_result_is_reliable(first_full, threshold=0.80):
        return first_full
    if len(image_list) == 1:
        return first_full

    full_results = [first_full]
    # Read older stable frames only after the newest frame remains ambiguous.
    for image in reversed(image_list[:-1]):
        full_results.append(
            read_potential_image(
                image,
                executable,
                tessdata,
                equipment_slot=equipment_slot,
                expected_rarity=expected_rarity,
            )
        )
        if len(full_results) >= 2:
            signatures = Counter(_result_signature(result) for result in full_results if result.complete)
            if signatures and signatures.most_common(1)[0][1] >= 2:
                break
        if len(full_results) >= 3:
            break
    return consensus_potential_results(full_results)


def _result_signature(result: PotentialOCRResult) -> str:
    parts = [result.rarity, f"{result.progress}/{result.progress_total}"]
    parts.extend(f"{line.stat_name}:{line.unit}:{line.value:.8g}" for line in result.lines)
    return "|".join(parts)


def consensus_potential_results(results: Sequence[PotentialOCRResult]) -> PotentialOCRResult:
    """Combine repeated captures and require agreement before auto-acceptance."""
    usable = [result for result in results if result is not None]
    if not usable:
        return PotentialOCRResult("", 0, 0, (), "", ("No OCR captures were available.",), (), 0.0)

    complete = [result for result in usable if result.complete]
    signatures = Counter(_result_signature(result) for result in complete)
    if signatures:
        signature, count = signatures.most_common(1)[0]
        matching = [result for result in complete if _result_signature(result) == signature]
        if count >= 2:
            selected = max(matching, key=lambda result: result.confidence)
            warnings = list(selected.warnings)
            warnings.append(f"OCR agreed across {count} stable captures.")
            return PotentialOCRResult(
                rarity=selected.rarity,
                progress=selected.progress,
                progress_total=selected.progress_total,
                lines=selected.lines,
                raw_text="\n\n=== STABLE CAPTURE ===\n".join(result.raw_text for result in matching),
                warnings=tuple(dict.fromkeys(warnings)),
                line_confidences=selected.line_confidences,
                confidence=min(1.0, selected.confidence + 0.04),
            )

    # Exact whole-result agreement can fail when only the header jitters. Try a
    # position-by-position majority before forcing manual review.
    if len(complete) >= 3:
        rarity_counts = Counter(result.rarity for result in complete if result.rarity)
        rarity = rarity_counts.most_common(1)[0][0] if rarity_counts else ""
        progress_counts = Counter((result.progress, result.progress_total) for result in complete)
        progress, progress_total = progress_counts.most_common(1)[0][0]
        lines: List[PotentialLine] = []
        confidences: List[float] = []
        agreed = True
        for index in range(3):
            line_counts = Counter(
                (result.lines[index].stat_name, result.lines[index].unit, round(result.lines[index].value, 6))
                for result in complete
            )
            key, count = line_counts.most_common(1)[0]
            if count < 2:
                agreed = False
                break
            stat, unit, value = key
            lines.append(PotentialLine(stat, value, unit))
            source_confidences = [
                result.line_confidences[index]
                for result in complete
                if index < len(result.line_confidences)
                and (
                    result.lines[index].stat_name,
                    result.lines[index].unit,
                    round(result.lines[index].value, 6),
                ) == key
            ]
            confidences.append(sum(source_confidences) / len(source_confidences) if source_confidences else 0.75)
        if agreed:
            return PotentialOCRResult(
                rarity=rarity,
                progress=progress,
                progress_total=progress_total,
                lines=tuple(lines),
                raw_text="\n\n=== STABLE CAPTURE ===\n".join(result.raw_text for result in complete),
                warnings=("OCR reached line-by-line agreement across three stable captures.",),
                line_confidences=tuple(confidences),
                confidence=min(0.94, sum(confidences) / len(confidences) if confidences else 0.0),
            )

    selected = max(usable, key=lambda result: (result.complete, result.confidence, len(result.lines)))
    warnings = list(selected.warnings)
    warnings.append("Stable captures disagreed; review the current-scan fields before saving.")
    return PotentialOCRResult(
        rarity=selected.rarity,
        progress=selected.progress,
        progress_total=selected.progress_total,
        lines=selected.lines,
        raw_text="\n\n=== DISAGREEING CAPTURE ===\n".join(result.raw_text for result in usable),
        warnings=tuple(dict.fromkeys(warnings)),
        line_confidences=selected.line_confidences,
        confidence=min(selected.confidence, 0.58),
    )


def read_potential_consensus(
    images: Sequence[Image.Image],
    executable: Path,
    tessdata: Optional[Path] = None,
    *,
    equipment_slot: str = "",
    expected_rarity: str = "",
) -> PotentialOCRResult:
    """OCR repeated stable captures, reading a third only when the first two disagree."""
    image_list = list(images)
    if not image_list:
        raise ValueError("No Potential capture images were provided.")
    results: List[PotentialOCRResult] = []
    for image in image_list[:2]:
        results.append(
            read_potential_image(
                image,
                executable,
                tessdata,
                equipment_slot=equipment_slot,
                expected_rarity=expected_rarity,
            )
        )
    if len(results) >= 2 and results[0].complete and _result_signature(results[0]) == _result_signature(results[1]):
        return consensus_potential_results(results)
    if len(image_list) >= 3:
        results.append(
            read_potential_image(
                image_list[2],
                executable,
                tessdata,
                equipment_slot=equipment_slot,
                expected_rarity=expected_rarity,
            )
        )
    return consensus_potential_results(results)
