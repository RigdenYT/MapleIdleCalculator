"""Data models for equipment Potential roll comparison, OCR, and priority."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

POTENTIAL_UNIT_FLAT = "flat"
POTENTIAL_UNIT_PERCENT = "percent"
POTENTIAL_UNIT_SECONDS = "seconds"

# These options are percentage-based in the game even when their displayed
# label does not contain a percent sign. Ambiguous options such as STR/DEX/INT/
# LUK, Main Stat, Attack, Max HP, and Max MP are deliberately omitted because
# they can roll as either flat values or percentages.
AMBIGUOUS_UNIT_OPTIONS = {"STR", "DEX", "INT", "LUK", "Main Stat", "Attack", "Max HP", "Max MP"}

INHERENT_PERCENT_OPTIONS = {
    "Damage",
    "Final Damage",
    "Critical Rate",
    "Critical Damage",
    "Min Damage Multiplier",
    "Max Damage Multiplier",
    "Boss Monster Damage",
    "Normal Monster Damage",
    "Basic Attack Damage",
    "Skill Damage",
    "Attack Speed",
    "Defense Penetration",
    "Damage Taken Decrease",
    "Buff Duration",
    "Companion Duration",
    "Meso Drop",
    "EXP Gain",
}

INHERENT_SECONDS_OPTIONS = {"Cooldown Reduction"}


def normalize_potential_unit(stat_name: str, unit: str = "") -> str:
    """Return the persisted unit for a Potential line.

    Older account files did not include a unit. Their ambiguous primary-stat
    lines must remain flat because that is how versions through 2.8.2 scored
    them. Explicit ``%`` option names and inherently percentage-based options
    can still be migrated safely as percentages.
    """
    name = str(stat_name).strip()
    normalized = str(unit or "").strip().lower()
    if name in INHERENT_SECONDS_OPTIONS or normalized in {"s", "sec", "secs", "second", "seconds"}:
        return POTENTIAL_UNIT_SECONDS
    if name.endswith("%") or name in INHERENT_PERCENT_OPTIONS:
        return POTENTIAL_UNIT_PERCENT
    if name not in AMBIGUOUS_UNIT_OPTIONS:
        return POTENTIAL_UNIT_FLAT
    if normalized in {"%", "pct", "percent", "percentage"}:
        return POTENTIAL_UNIT_PERCENT
    return POTENTIAL_UNIT_FLAT


@dataclass(frozen=True)
class PotentialLine:
    stat_name: str
    value: float
    unit: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "unit", normalize_potential_unit(self.stat_name, self.unit))

    @property
    def is_percent(self) -> bool:
        return self.unit == POTENTIAL_UNIT_PERCENT

    @property
    def is_seconds(self) -> bool:
        return self.unit == POTENTIAL_UNIT_SECONDS

    @property
    def display_name(self) -> str:
        name = self.stat_name.strip()
        if self.is_percent and not name.endswith("%"):
            return f"{name} %"
        return name

    @property
    def display_value(self) -> str:
        if self.is_percent:
            suffix = "%"
        elif self.is_seconds:
            suffix = "s"
        else:
            suffix = ""
        return f"{self.value:g}{suffix}"


@dataclass(frozen=True)
class PotentialOCRResult:
    rarity: str
    progress: int
    progress_total: int
    lines: Tuple[PotentialLine, ...]
    raw_text: str
    warnings: Tuple[str, ...] = ()
    line_confidences: Tuple[float, ...] = ()
    confidence: float = 0.0

    @property
    def complete(self) -> bool:
        return bool(self.rarity) and len(self.lines) == 3


@dataclass(frozen=True)
class PotentialComparison:
    current_score: float
    candidate_score: float
    gain_pct: float
    modeled_current_lines: int
    modeled_candidate_lines: int
    warnings: Tuple[str, ...] = ()


@dataclass
class PotentialSlotState:
    rarity: str = "Rare"
    progress: int = 0
    progress_total: int = 75
    current_lines: List[PotentialLine] = field(default_factory=list)
    observed_rolls: int = 0
    observed_improvements: int = 0
    observed_signatures: List[str] = field(default_factory=list)
    configured: bool = False


@dataclass(frozen=True)
class PotentialSlotPriority:
    slot: str
    priority_score: float
    current_gain_pct: float
    special_replacement_gain_pct: float
    progress_fraction: float
    observed_improvement_rate: float
    observed_trials: int
    special_option: str
    special_value: float
    confidence: str
    reason: str


@dataclass(frozen=True)
class CaptureRegion:
    x1: float
    y1: float
    x2: float
    y2: float
    source_width: int
    source_height: int

    def normalized(self) -> Tuple[float, float, float, float]:
        width = max(1, self.source_width)
        height = max(1, self.source_height)
        return (
            self.x1 / width,
            self.y1 / height,
            self.x2 / width,
            self.y2 / height,
        )
