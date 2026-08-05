"""Configured Potential option-rate profiles and exact three-line analysis.

The game publishes a separate configured distribution for each equipment slot,
Potential rarity, and line number. Missing or collector-marked incomplete tables
are never fabricated: exact calculations are enabled only when all three line
distributions are complete. Rank-up planning uses the saved in-game progress
counter plus the configured early-rank probability.
"""

from __future__ import annotations

import copy
import csv
from bisect import bisect_left, bisect_right
import io
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from .data import (
    EQUIPMENT_SLOTS,
    POTENTIAL_EARLY_RANK_UP_CHANCE,
    POTENTIAL_OPTIONS,
    POTENTIAL_RANK_REQUIREMENTS,
    POTENTIAL_RARITIES,
)
from .engine import apply_line, remove_line
from .models import PotentialLine, normalize_potential_unit

RATE_SCHEMA_VERSION = 2
RATE_SOURCE_DEFAULT = "NEXON NOW / in-game Option Rates (configured rates)"


@dataclass(frozen=True)
class PotentialRateOutcome:
    line: PotentialLine
    probability: float

    @property
    def key(self) -> Tuple[str, float, str]:
        return (self.line.stat_name, round(float(self.line.value), 10), self.line.unit)


@dataclass(frozen=True)
class PotentialStoppingCondition:
    """One in-game preferred-option condition that often identifies an acceptable roll."""

    stat_name: str
    minimum_value: float
    unit: str
    trigger_probability: float
    qualifying_probability: float
    success_coverage: float
    precision: float
    average_gain_on_qualifying: float
    line_numbers: Tuple[int, ...] = ()

    @property
    def display_value(self) -> str:
        suffix = "%" if self.unit == "percent" else ("s" if self.unit == "seconds" else "")
        return f"{self.minimum_value:g}{suffix}"


@dataclass(frozen=True)
class PotentialExactOutcome:
    """One complete three-line result, retained for a concise stopping example."""

    lines: Tuple[PotentialLine, PotentialLine, PotentialLine]
    probability: float
    gain_pct: float


@dataclass
class PotentialRateProfile:
    source: str = RATE_SOURCE_DEFAULT
    captured_at: str = ""
    notes: str = ""
    # key: (equipment slot, rarity, 1-based line number)
    distributions: Dict[Tuple[str, str, int], Tuple[PotentialRateOutcome, ...]] = field(default_factory=dict)
    # Configured early rank-up chance. It is repeated on each in-game line tab,
    # but stored once per equipment slot and rarity here.
    rank_up_probabilities: Dict[Tuple[str, str], float] = field(default_factory=dict)
    # Collector-marked incomplete sections are retained for visible warnings but
    # deliberately excluded from exact calculations.
    incomplete_sections: Dict[Tuple[str, str, int], str] = field(default_factory=dict)

    def distribution(self, slot: str, rarity: str, line_number: int) -> Tuple[PotentialRateOutcome, ...]:
        return self.distributions.get((str(slot), str(rarity), int(line_number)), ())

    def has_complete_table(self, slot: str, rarity: str) -> bool:
        return all(bool(self.distribution(slot, rarity, line_number)) for line_number in (1, 2, 3))

    def missing_lines(self, slot: str, rarity: str) -> Tuple[int, ...]:
        return tuple(line for line in (1, 2, 3) if not self.distribution(slot, rarity, line))

    def section_reason(self, slot: str, rarity: str, line_number: int) -> str:
        return self.incomplete_sections.get((str(slot), str(rarity), int(line_number)), "not collected")

    def rank_up_probability(self, slot: str, rarity: str) -> float:
        value = self.rank_up_probabilities.get((str(slot), str(rarity)))
        if value is None:
            value = POTENTIAL_EARLY_RANK_UP_CHANCE.get(str(rarity), 0.0)
        return max(0.0, min(1.0, float(value)))

    def completed_tables(self) -> int:
        return sum(
            1
            for slot in EQUIPMENT_SLOTS
            for rarity in POTENTIAL_RARITIES
            if self.has_complete_table(slot, rarity)
        )

    def outcome_count(self) -> int:
        return sum(len(items) for items in self.distributions.values())


@dataclass(frozen=True)
class PotentialRateAnalysis:
    slot: str
    rarity: str
    success_probability: float
    chance_with_budget: float
    expected_cubes_to_success: float
    expected_positive_gain_per_cube: float
    expected_net_gain_per_cube: float
    average_gain_on_success: float
    better_probability: float
    equal_probability: float
    worse_probability: float
    severe_loss_probability: float
    average_loss_on_worse: float
    median_gain_pct: float
    chance_end_worse_with_budget: float
    expected_final_gain_with_budget: float
    modeled_probability_mass: float
    combination_count: int
    minimum_gain_pct: float
    current_score: float
    progress: int = 0
    progress_total: int = 0
    rank_up_probability_per_cube: float = 0.0
    chance_to_rank_up_with_budget: float = 0.0
    expected_cubes_to_rank_up: float = math.inf
    cubes_to_guaranteed_rank_up: int = 0
    next_rarity: str = ""
    next_rarity_success_probability: float = 0.0
    next_rarity_expected_gain_per_cube: float = 0.0
    cubes_for_50pct_success: int = 0
    rank_aware_chance_with_budget: float = 0.0
    rank_aware_expected_cubes_to_success: float = math.inf
    stopping_conditions: Tuple[PotentialStoppingCondition, ...] = ()
    stopping_condition_coverage: float = 0.0
    top_exact_outcomes: Tuple[PotentialExactOutcome, ...] = ()
    warnings: Tuple[str, ...] = ()
    # Finite-budget, irreversible-reroll policy. These fields describe the
    # result of choosing between stopping now and rerolling, then making the
    # same choice again after every observed result.
    optimal_policy_available: bool = False
    optimal_should_reroll: bool = False
    optimal_reroll_value_gain_pct: float = 0.0
    optimal_expected_final_gain_pct: float = 0.0
    optimal_chance_end_better: float = 0.0
    optimal_chance_end_equal: float = 1.0
    optimal_chance_end_worse: float = 0.0
    optimal_severe_loss_probability: float = 0.0
    optimal_next_stop_threshold_gain_pct: float = math.nan
    optimal_rank_stop_threshold_gain_pct: float = math.nan
    optimal_cubes_to_positive_value: int = 0
    optimal_policy_note: str = ""


@dataclass(frozen=True)
class PotentialRatePriority:
    slot: str
    rarity: str
    success_probability: float
    chance_with_budget: float
    expected_cubes_to_success: float
    expected_positive_gain_per_cube: float
    expected_net_gain_per_cube: float
    average_gain_on_success: float
    better_probability: float
    worse_probability: float
    severe_loss_probability: float
    chance_end_worse_with_budget: float
    expected_final_gain_with_budget: float
    modeled_probability_mass: float
    combination_count: int
    minimum_gain_pct: float
    recommendation: str
    progress: int = 0
    progress_total: int = 0
    rank_up_probability_per_cube: float = 0.0
    chance_to_rank_up_with_budget: float = 0.0
    expected_cubes_to_rank_up: float = math.inf
    cubes_to_guaranteed_rank_up: int = 0
    next_rarity: str = ""
    next_rarity_success_probability: float = 0.0
    next_rarity_expected_gain_per_cube: float = 0.0
    cubes_for_50pct_success: int = 0
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class _EnumeratedDistribution:
    success_probability: float
    expected_positive_gain: float
    expected_net_gain: float
    average_gain_on_success: float
    better_probability: float
    equal_probability: float
    worse_probability: float
    severe_loss_probability: float
    average_loss_on_worse: float
    median_gain_pct: float
    modeled_probability_mass: float
    combination_count: int
    current_score: float
    warnings: Tuple[str, ...]
    stopping_conditions: Tuple[PotentialStoppingCondition, ...]
    stopping_condition_coverage: float
    top_exact_outcomes: Tuple[PotentialExactOutcome, ...]
    # Aggregated complete-roll score changes, relative to the active current
    # Potential. This is retained compactly for the optimal stopping solver.
    gain_distribution: Tuple[Tuple[float, float], ...]


@dataclass(frozen=True)
class _PolicyMetrics:
    expected_gain: float
    better: float
    equal: float
    worse: float
    severe_loss: float


@dataclass(frozen=True)
class _OptimalStoppingPlan:
    available: bool
    should_reroll: bool = False
    reroll_value_gain_pct: float = 0.0
    expected_final_gain_pct: float = 0.0
    chance_end_better: float = 0.0
    chance_end_equal: float = 1.0
    chance_end_worse: float = 0.0
    severe_loss_probability: float = 0.0
    next_stop_threshold_gain_pct: float = math.nan
    rank_stop_threshold_gain_pct: float = math.nan
    cubes_to_positive_value: int = 0
    note: str = ""


class _GainDistributionIndex:
    """Fast threshold queries for one rarity's complete-roll gains."""

    def __init__(self, records: Sequence[Tuple[float, float]]):
        merged: Dict[float, float] = {}
        for gain, probability in records:
            if probability <= 0.0:
                continue
            key = round(float(gain), 10)
            merged[key] = merged.get(key, 0.0) + float(probability)
        if not merged:
            raise ValueError("The configured roll distribution is empty.")
        total = sum(merged.values())
        self.gains = tuple(sorted(merged))
        self.probabilities = tuple(merged[gain] / total for gain in self.gains)
        prefix_probability = [0.0]
        prefix_gain = [0.0]
        for gain, probability in zip(self.gains, self.probabilities):
            prefix_probability.append(prefix_probability[-1] + probability)
            prefix_gain.append(prefix_gain[-1] + gain * probability)
        self.prefix_probability = tuple(prefix_probability)
        self.prefix_gain = tuple(prefix_gain)
        self.total_gain = prefix_gain[-1]

    def expected_max(self, continuation_gain: float) -> float:
        index = bisect_left(self.gains, continuation_gain)
        probability_below = self.prefix_probability[index]
        gain_at_or_above = self.total_gain - self.prefix_gain[index]
        return continuation_gain * probability_below + gain_at_or_above

    def policy_metrics(self, continuation_gain: Optional[float], continuation: _PolicyMetrics) -> _PolicyMetrics:
        # None means this is the final cube: every result is necessarily final.
        index = 0 if continuation_gain is None else bisect_left(self.gains, continuation_gain)
        probability_continue = 0.0 if continuation_gain is None else self.prefix_probability[index]
        expected_stop = self.total_gain - self.prefix_gain[index]

        positive_start = max(index, bisect_right(self.gains, 1e-12))
        negative_end = max(index, bisect_left(self.gains, -1e-12))
        equal_start = max(index, bisect_left(self.gains, -1e-12))
        equal_end = max(equal_start, bisect_right(self.gains, 1e-12))
        severe_end = max(index, bisect_right(self.gains, -5.0 + 1e-12))

        probability_stop_better = 1.0 - self.prefix_probability[positive_start]
        probability_stop_worse = max(0.0, self.prefix_probability[negative_end] - self.prefix_probability[index])
        probability_stop_equal = max(0.0, self.prefix_probability[equal_end] - self.prefix_probability[equal_start])
        probability_stop_severe = max(0.0, self.prefix_probability[severe_end] - self.prefix_probability[index])

        if continuation_gain is None:
            return _PolicyMetrics(
                expected_gain=self.total_gain,
                better=max(0.0, min(1.0, probability_stop_better)),
                equal=max(0.0, min(1.0, probability_stop_equal)),
                worse=max(0.0, min(1.0, probability_stop_worse)),
                severe_loss=max(0.0, min(1.0, probability_stop_severe)),
            )
        return _PolicyMetrics(
            expected_gain=expected_stop + probability_continue * continuation.expected_gain,
            better=probability_stop_better + probability_continue * continuation.better,
            equal=probability_stop_equal + probability_continue * continuation.equal,
            worse=probability_stop_worse + probability_continue * continuation.worse,
            severe_loss=probability_stop_severe + probability_continue * continuation.severe_loss,
        )


def _coerce_probability(value: object) -> float:
    """Accept either decimal probabilities or strings ending in percent."""
    if value is None or value == "":
        raise ValueError("Probability is empty.")
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            raise ValueError("Probability is empty.")
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        number = float(text)
    else:
        number = float(value)
    if number > 1.0 + 1e-12:
        number /= 100.0
    if not math.isfinite(number) or number < 0.0 or number > 1.0 + 1e-9:
        raise ValueError(f"Invalid probability {value!r}.")
    return max(0.0, min(1.0, number))


def _canonical_line(stat: object, value: object, unit: object = "") -> PotentialLine:
    stat_name = str(stat or "").strip()
    if stat_name not in POTENTIAL_OPTIONS:
        raise ValueError(f"Unknown Potential option {stat_name!r}.")
    numeric = float(str(value).replace(",", "").replace("%", "").replace("s", "").strip())
    normalized_unit = normalize_potential_unit(stat_name, str(unit or ""))
    value_text = str(value).strip().lower()
    if value_text.endswith("%"):
        normalized_unit = "percent"
    elif value_text.endswith("s"):
        normalized_unit = "seconds"
    return PotentialLine(stat_name, numeric, normalized_unit)


def _normalize_distribution(
    outcomes: Iterable[PotentialRateOutcome], *, tolerance: float = 0.002
) -> Tuple[PotentialRateOutcome, ...]:
    merged: MutableMapping[Tuple[str, float, str], Tuple[PotentialLine, float]] = {}
    for outcome in outcomes:
        if outcome.probability <= 0.0:
            continue
        key = outcome.key
        line, probability = merged.get(key, (outcome.line, 0.0))
        merged[key] = (line, probability + float(outcome.probability))
    if not merged:
        raise ValueError("A rate distribution contains no positive-probability outcomes.")
    total = sum(probability for _line, probability in merged.values())
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("A rate distribution has an invalid probability total.")
    if abs(total - 1.0) > tolerance:
        raise ValueError(
            f"Configured probabilities total {total * 100:.6f}%, not 100%. "
            "Check that the full Option Rates page was imported."
        )
    normalized = [
        PotentialRateOutcome(line, probability / total)
        for line, probability in merged.values()
    ]
    normalized.sort(key=lambda item: (item.line.stat_name, item.line.unit, item.line.value))
    return tuple(normalized)


def _record_rank_probability(profile: PotentialRateProfile, slot: str, rarity: str, raw: object) -> None:
    if raw is None or raw == "":
        return
    value = _coerce_probability(raw)
    key = (slot, rarity)
    existing = profile.rank_up_probabilities.get(key)
    if existing is not None and abs(existing - value) > 0.00005:
        raise ValueError(
            f"Conflicting rank-up probabilities for {slot} {rarity}: "
            f"{existing * 100:.4f}% and {value * 100:.4f}%."
        )
    profile.rank_up_probabilities[key] = value


def profile_from_dict(data: Mapping[str, object]) -> PotentialRateProfile:
    profile = PotentialRateProfile(
        source=str(data.get("source", RATE_SOURCE_DEFAULT) or RATE_SOURCE_DEFAULT),
        captured_at=str(data.get("captured_at", "") or ""),
        notes=str(data.get("notes", "") or ""),
    )
    for raw_missing in data.get("incomplete_sections", []) if isinstance(data.get("incomplete_sections", []), list) else []:
        if not isinstance(raw_missing, Mapping):
            continue
        try:
            key = (str(raw_missing["slot"]), str(raw_missing["rarity"]), int(raw_missing["line"]))
        except (KeyError, TypeError, ValueError):
            continue
        profile.incomplete_sections[key] = str(raw_missing.get("reason", "marked incomplete"))

    entries = data.get("distributions", [])
    if isinstance(entries, Mapping):
        expanded = []
        for key, outcomes in entries.items():
            try:
                slot, rarity, line_text = str(key).split("|", 2)
            except ValueError as exc:
                raise ValueError(f"Invalid configured-rate key {key!r}.") from exc
            expanded.append({"slot": slot, "rarity": rarity, "line": int(line_text), "outcomes": outcomes})
        entries = expanded
    if not isinstance(entries, list):
        raise ValueError("Configured-rate profile must contain a distributions list.")

    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("Each configured-rate distribution must be an object.")
        slot = str(entry.get("slot", "")).strip()
        rarity = str(entry.get("rarity", "")).strip()
        line_number = int(entry.get("line", 0))
        if slot not in EQUIPMENT_SLOTS:
            raise ValueError(f"Unknown equipment slot {slot!r} in configured rates.")
        if rarity not in POTENTIAL_RARITIES:
            raise ValueError(f"Unknown Potential rarity {rarity!r} in configured rates.")
        if line_number not in (1, 2, 3):
            raise ValueError("Configured-rate line number must be 1, 2, or 3.")
        _record_rank_probability(profile, slot, rarity, entry.get("rank_up_probability"))
        key = (slot, rarity, line_number)
        if entry.get("complete") is False:
            reason = str(entry.get("reason") or "collector marked this section incomplete or uncertain")
            profile.incomplete_sections[key] = reason
            continue
        raw_outcomes = entry.get("outcomes", [])
        if not isinstance(raw_outcomes, list):
            raise ValueError(f"{slot} {rarity} line {line_number} outcomes must be a list.")
        parsed: List[PotentialRateOutcome] = []
        for raw in raw_outcomes:
            if not isinstance(raw, Mapping):
                raise ValueError("Each configured-rate outcome must be an object.")
            line = _canonical_line(raw.get("stat"), raw.get("value"), raw.get("unit", ""))
            probability = _coerce_probability(raw.get("probability", 0.0))
            parsed.append(PotentialRateOutcome(line, probability))
        profile.distributions[key] = _normalize_distribution(parsed)
        profile.incomplete_sections.pop(key, None)
    return profile


def profile_to_dict(profile: PotentialRateProfile) -> Dict[str, object]:
    distributions = []
    for (slot, rarity, line_number), outcomes in sorted(profile.distributions.items()):
        distributions.append({
            "slot": slot,
            "rarity": rarity,
            "line": line_number,
            "rank_up_probability": profile.rank_up_probabilities.get((slot, rarity)),
            "complete": True,
            "probability_total": 1.0,
            "outcomes": [
                {
                    "stat": outcome.line.stat_name,
                    "value": outcome.line.value,
                    "unit": outcome.line.unit,
                    "probability": outcome.probability,
                }
                for outcome in outcomes
            ],
        })
    incomplete = [
        {"slot": slot, "rarity": rarity, "line": line_number, "reason": reason}
        for (slot, rarity, line_number), reason in sorted(profile.incomplete_sections.items())
    ]
    return {
        "schema_version": RATE_SCHEMA_VERSION,
        "source": profile.source,
        "captured_at": profile.captured_at,
        "notes": profile.notes,
        "distributions": distributions,
        "incomplete_sections": incomplete,
    }


def load_profile(path: Path) -> PotentialRateProfile:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return profile_from_csv(path.read_text(encoding="utf-8-sig"))
    return profile_from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_profile(path: Path, profile: PotentialRateProfile) -> None:
    Path(path).write_text(json.dumps(profile_to_dict(profile), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def profile_from_csv(text: str) -> PotentialRateProfile:
    reader = csv.DictReader(io.StringIO(text))
    required = {"slot", "rarity", "line", "stat", "value", "unit", "probability"}
    if not reader.fieldnames or not required.issubset({name.strip().lower() for name in reader.fieldnames}):
        raise ValueError("CSV must contain slot, rarity, line, stat, value, unit, and probability columns.")
    grouped: Dict[Tuple[str, str, int], List[PotentialRateOutcome]] = {}
    rank_rates: Dict[Tuple[str, str], float] = {}
    source = RATE_SOURCE_DEFAULT
    captured_at = ""
    for raw in reader:
        row = {str(key).strip().lower(): value for key, value in raw.items()}
        slot = str(row.get("slot", "")).strip()
        rarity = str(row.get("rarity", "")).strip()
        line_number = int(str(row.get("line", "0")).strip())
        if slot not in EQUIPMENT_SLOTS or rarity not in POTENTIAL_RARITIES or line_number not in (1, 2, 3):
            raise ValueError(f"Invalid CSV rate row: {slot!r}, {rarity!r}, line {line_number!r}.")
        line = _canonical_line(row.get("stat"), row.get("value"), row.get("unit", ""))
        grouped.setdefault((slot, rarity, line_number), []).append(
            PotentialRateOutcome(line, _coerce_probability(row.get("probability", 0.0)))
        )
        rank_raw = row.get("rank_up_probability")
        if rank_raw not in (None, ""):
            rank_rates[(slot, rarity)] = _coerce_probability(rank_raw)
        source = str(row.get("source") or source)
        captured_at = str(row.get("captured_at") or captured_at)
    profile = PotentialRateProfile(source=source, captured_at=captured_at, rank_up_probabilities=rank_rates)
    for key, outcomes in grouped.items():
        profile.distributions[key] = _normalize_distribution(outcomes)
    return profile


def empty_csv_template(slot: str = "Cape", rarity: str = "Rare") -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "slot", "rarity", "line", "stat", "value", "unit", "probability",
        "rank_up_probability", "source", "captured_at",
    ])
    for line_number in (1, 2, 3):
        writer.writerow([slot, rarity, line_number, "Damage", 0, "percent", "0%", "", RATE_SOURCE_DEFAULT, ""])
    return output.getvalue()


def merge_profiles(base: PotentialRateProfile, incoming: PotentialRateProfile) -> PotentialRateProfile:
    merged = PotentialRateProfile(
        source=incoming.source or base.source,
        captured_at=incoming.captured_at or base.captured_at,
        notes=incoming.notes or base.notes,
        distributions=dict(base.distributions),
        rank_up_probabilities=dict(base.rank_up_probabilities),
        incomplete_sections=dict(base.incomplete_sections),
    )
    merged.distributions.update(incoming.distributions)
    merged.rank_up_probabilities.update(incoming.rank_up_probabilities)
    merged.incomplete_sections.update(incoming.incomplete_sections)
    for key in merged.distributions:
        merged.incomplete_sections.pop(key, None)
    return merged


def _state_lines(state: Mapping[str, object]) -> List[PotentialLine]:
    lines: List[PotentialLine] = []
    for item in list(state.get("lines", []))[:3]:
        if isinstance(item, PotentialLine):
            lines.append(item)
        elif isinstance(item, Mapping):
            stat = str(item.get("stat", "")).strip()
            if not stat:
                continue
            try:
                value = float(str(item.get("value", 0)).replace(",", ""))
            except (TypeError, ValueError):
                continue
            lines.append(PotentialLine(stat, value, str(item.get("unit", ""))))
    return lines


def _next_rarity(rarity: str) -> str:
    try:
        index = POTENTIAL_RARITIES.index(rarity)
    except ValueError:
        return ""
    return POTENTIAL_RARITIES[index + 1] if index + 1 < len(POTENTIAL_RARITIES) else ""


def _cubes_for_probability(probability: float, target: float = 0.5) -> int:
    probability = max(0.0, min(1.0, float(probability)))
    target = max(0.0, min(0.999999, float(target)))
    if probability <= 0.0:
        return 0
    if probability >= 1.0:
        return 1
    return max(1, int(math.ceil(math.log1p(-target) / math.log1p(-probability))))


def _rank_up_plan(
    profile: PotentialRateProfile,
    *,
    slot: str,
    rarity: str,
    progress: int,
    progress_total: int,
    cubes: int,
) -> Tuple[float, float, float, int, str]:
    next_rarity = _next_rarity(rarity)
    if not next_rarity:
        return 0.0, 0.0, math.inf, 0, ""
    q = profile.rank_up_probability(slot, rarity)
    total = int(progress_total) if int(progress_total) > 0 else int(POTENTIAL_RANK_REQUIREMENTS.get(rarity, 0))
    current = max(0, int(progress))
    remaining = max(1, total - current) if total > 0 else 0
    cubes = max(0, int(cubes))
    if remaining and cubes >= remaining:
        chance = 1.0
    else:
        chance = 1.0 - (1.0 - q) ** cubes if q > 0.0 else 0.0
    if remaining <= 0:
        expected = math.inf
    elif q > 0.0:
        expected = (1.0 - (1.0 - q) ** remaining) / q
    else:
        expected = float(remaining)
    return q, max(0.0, min(1.0, chance)), expected, remaining, next_rarity


def _enumerate_distribution_set(
    displayed_stats,
    target,
    *,
    current_lines: Sequence[PotentialLine],
    distributions: Sequence[Sequence[PotentialRateOutcome]],
    minimum_gain_pct: float,
    main_stat_name: str,
    score_fn: Callable[[object, object], float],
    collect_guidance: bool = False,
) -> _EnumeratedDistribution:
    current_score = float(score_fn(displayed_stats, target))
    baseline = copy.deepcopy(displayed_stats)
    current_unmodeled = []
    for line in current_lines:
        if not remove_line(baseline, line, main_stat_name):
            current_unmodeled.append(line.display_name)
    threshold_score = current_score * (1.0 + minimum_gain_pct / 100.0)
    success_probability = 0.0
    positive_gain_sum = 0.0
    net_gain_sum = 0.0
    successful_gain_sum = 0.0
    better_probability = 0.0
    equal_probability = 0.0
    worse_probability = 0.0
    severe_loss_probability = 0.0
    worse_gain_sum = 0.0
    gain_records: List[Tuple[float, float]] = []
    modeled_mass = 0.0
    combination_count = 0
    unmodeled_options = set()

    # Guidance is deliberately collected only for the currently selected slot.
    # Equipment-wide ranking keeps this disabled to avoid retaining tens of
    # thousands of combinations for every slot on each UI refresh.
    thresholds_by_option: Dict[Tuple[str, str], Tuple[float, ...]] = {}
    option_lines: Dict[Tuple[str, str, float], set] = {}
    if collect_guidance:
        values: Dict[Tuple[str, str], set] = {}
        for line_number, distribution in enumerate(distributions, start=1):
            for outcome in distribution:
                option_key = (outcome.line.stat_name, outcome.line.unit)
                values.setdefault(option_key, set()).add(float(outcome.line.value))
                option_lines.setdefault(
                    (outcome.line.stat_name, outcome.line.unit, float(outcome.line.value)),
                    set(),
                ).add(line_number)
        thresholds_by_option = {
            key: tuple(sorted(numeric_values))
            for key, numeric_values in values.items()
        }

    condition_total: Dict[Tuple[str, str, float], float] = {}
    condition_success: Dict[Tuple[str, str, float], float] = {}
    condition_gain: Dict[Tuple[str, str, float], float] = {}
    successful_records: List[Tuple[float, float, frozenset]] = []
    exact_outcomes: List[PotentialExactOutcome] = []

    for first in distributions[0]:
        stats1 = copy.deepcopy(baseline)
        modeled1 = apply_line(stats1, first.line, main_stat_name)
        if not modeled1:
            unmodeled_options.add(first.line.display_name)
        for second in distributions[1]:
            stats2 = copy.deepcopy(stats1)
            modeled2 = apply_line(stats2, second.line, main_stat_name)
            if not modeled2:
                unmodeled_options.add(second.line.display_name)
            p12 = first.probability * second.probability
            for third in distributions[2]:
                probability = p12 * third.probability
                combination_count += 1
                stats3 = copy.deepcopy(stats2)
                modeled3 = apply_line(stats3, third.line, main_stat_name)
                if not modeled3:
                    unmodeled_options.add(third.line.display_name)
                if modeled1 and modeled2 and modeled3:
                    modeled_mass += probability
                candidate_score = float(score_fn(stats3, target))
                gain_pct = ((candidate_score / current_score) - 1.0) * 100.0 if current_score > 0 else 0.0
                net_gain_sum += probability * gain_pct
                if gain_pct > 1e-12:
                    positive_gain_sum += probability * gain_pct
                    better_probability += probability
                elif gain_pct < -1e-12:
                    worse_probability += probability
                    worse_gain_sum += probability * gain_pct
                    if gain_pct <= -5.0:
                        severe_loss_probability += probability
                else:
                    equal_probability += probability
                gain_records.append((gain_pct, probability))
                qualifies = gain_pct > 1e-12 if minimum_gain_pct <= 0.0 else candidate_score >= threshold_score - 1e-12

                met_conditions = set()
                if collect_guidance:
                    for line in (first.line, second.line, third.line):
                        option_key = (line.stat_name, line.unit)
                        for threshold in thresholds_by_option.get(option_key, ()):
                            if float(line.value) + 1e-12 >= threshold:
                                met_conditions.add((line.stat_name, line.unit, float(threshold)))
                    for condition in met_conditions:
                        condition_total[condition] = condition_total.get(condition, 0.0) + probability

                if qualifies:
                    success_probability += probability
                    successful_gain_sum += probability * gain_pct
                    if collect_guidance:
                        for condition in met_conditions:
                            condition_success[condition] = condition_success.get(condition, 0.0) + probability
                            condition_gain[condition] = condition_gain.get(condition, 0.0) + probability * gain_pct
                        successful_records.append((probability, gain_pct, frozenset(met_conditions)))
                        exact_outcomes.append(
                            PotentialExactOutcome(
                                lines=(first.line, second.line, third.line),
                                probability=probability,
                                gain_pct=gain_pct,
                            )
                        )

    success_probability = max(0.0, min(1.0, success_probability))
    better_probability = max(0.0, min(1.0, better_probability))
    equal_probability = max(0.0, min(1.0, equal_probability))
    worse_probability = max(0.0, min(1.0, worse_probability))
    severe_loss_probability = max(0.0, min(1.0, severe_loss_probability))
    average_gain = 0.0 if success_probability <= 0.0 else successful_gain_sum / success_probability
    average_loss = 0.0 if worse_probability <= 0.0 else worse_gain_sum / worse_probability
    median_gain = 0.0
    if gain_records:
        cumulative = 0.0
        for gain, probability in sorted(gain_records, key=lambda item: item[0]):
            cumulative += probability
            if cumulative >= 0.5 - 1e-12:
                median_gain = gain
                break
    warnings: List[str] = []
    if current_unmodeled:
        warnings.append("Current utility/unmodeled line(s): " + ", ".join(sorted(set(current_unmodeled))) + ".")
    if unmodeled_options:
        warnings.append(
            "Configured table includes utility/unmodeled options treated as zero direct damage: "
            + ", ".join(sorted(unmodeled_options))
            + "."
        )

    selected_conditions: List[PotentialStoppingCondition] = []
    covered_success = 0.0
    if collect_guidance and success_probability > 0.0:
        candidates: Dict[Tuple[str, str, float], PotentialStoppingCondition] = {}
        for key, qualifying_mass in condition_success.items():
            trigger_mass = condition_total.get(key, 0.0)
            if trigger_mass <= 0.0 or qualifying_mass <= 0.0:
                continue
            precision = qualifying_mass / trigger_mass
            stat_name, unit, threshold = key
            average_condition_gain = condition_gain.get(key, 0.0) / qualifying_mass
            lines = set()
            # A threshold can be satisfied by any line carrying the same option
            # at that value or above.
            for (candidate_stat, candidate_unit, candidate_value), line_numbers in option_lines.items():
                if candidate_stat == stat_name and candidate_unit == unit and candidate_value + 1e-12 >= threshold:
                    lines.update(line_numbers)
            # A preferred-option alert should be meaningfully more selective
            # than the baseline roll chance. Very broad conditions with poor
            # precision create nuisance stops and are omitted.
            minimum_precision = max(0.25, success_probability * 1.5)
            if precision + 1e-12 < minimum_precision:
                continue
            candidates[key] = PotentialStoppingCondition(
                stat_name=stat_name,
                minimum_value=threshold,
                unit=unit,
                trigger_probability=trigger_mass,
                qualifying_probability=qualifying_mass,
                success_coverage=(qualifying_mass / success_probability if success_probability > 0.0 else 0.0),
                precision=precision,
                average_gain_on_qualifying=average_condition_gain,
                line_numbers=tuple(sorted(lines)),
            )

        # Greedily choose up to three conditions that cover new accepted-result
        # probability rather than three near-duplicate thresholds for one stat.
        remaining = dict(candidates)
        covered_indices = set()
        for _ in range(3):
            best_key = None
            best_score = -1.0
            best_new_mass = 0.0
            for key, condition in remaining.items():
                new_mass = sum(
                    probability
                    for index, (probability, _gain, conditions) in enumerate(successful_records)
                    if index not in covered_indices and key in conditions
                )
                if new_mass <= 0.0:
                    continue
                # Prefer useful coverage and a high chance that a trigger is a
                # genuinely acceptable complete roll. A low-precision condition
                # remains a watch item, never an auto-accept rule.
                precision_weight = 0.35 + 0.65 * condition.precision
                score = new_mass * precision_weight * max(0.1, condition.average_gain_on_qualifying)
                if score > best_score:
                    best_score = score
                    best_key = key
                    best_new_mass = new_mass
            if best_key is None:
                break
            chosen = remaining.pop(best_key)
            selected_conditions.append(chosen)
            for index, (_probability, _gain, conditions) in enumerate(successful_records):
                if best_key in conditions:
                    covered_indices.add(index)
            covered_success += best_new_mass
            # Remove weaker thresholds for exactly the same stat/unit when they
            # add almost no new accepted-result coverage.
            for key in list(remaining):
                if key[:2] == best_key[:2]:
                    incremental = sum(
                        probability
                        for index, (probability, _gain, conditions) in enumerate(successful_records)
                        if index not in covered_indices and key in conditions
                    )
                    if incremental < success_probability * 0.01:
                        remaining.pop(key, None)

    top_exact: Tuple[PotentialExactOutcome, ...] = ()
    if collect_guidance and exact_outcomes:
        exact_outcomes.sort(
            key=lambda item: (
                -(item.probability * max(item.gain_pct, 0.05)),
                -item.probability,
                -item.gain_pct,
                tuple(line.display_name for line in item.lines),
            )
        )
        top_exact = tuple(exact_outcomes[:3])

    merged_gains: Dict[float, float] = {}
    for gain, probability in gain_records:
        key = round(float(gain), 10)
        merged_gains[key] = merged_gains.get(key, 0.0) + float(probability)
    gain_distribution = tuple(
        (gain, probability)
        for gain, probability in sorted(merged_gains.items())
        if probability > 0.0
    )

    return _EnumeratedDistribution(
        success_probability=success_probability,
        expected_positive_gain=positive_gain_sum,
        expected_net_gain=net_gain_sum,
        average_gain_on_success=average_gain,
        better_probability=better_probability,
        equal_probability=equal_probability,
        worse_probability=worse_probability,
        severe_loss_probability=severe_loss_probability,
        average_loss_on_worse=average_loss,
        median_gain_pct=median_gain,
        modeled_probability_mass=max(0.0, min(1.0, modeled_mass)),
        combination_count=combination_count,
        current_score=current_score,
        warnings=tuple(warnings),
        stopping_conditions=tuple(selected_conditions),
        stopping_condition_coverage=max(0.0, min(success_probability, covered_success)),
        top_exact_outcomes=top_exact,
        gain_distribution=gain_distribution,
    )


def _rank_aware_budget_success(
    profile: PotentialRateProfile,
    *,
    slot: str,
    rarity: str,
    progress: int,
    progress_total: int,
    cubes: int,
    success_by_rarity: Mapping[str, float],
) -> Tuple[float, float, Tuple[str, ...]]:
    """Return first-success probability across rank transitions.

    Assumption: when a cube causes an early or guaranteed rank increase, that
    same cube draws its three Potential lines from the newly reached rarity.
    The UI labels this assumption explicitly until the transition animation is
    verified in-game.
    """

    cubes = max(0, int(cubes))
    if cubes <= 0:
        return 0.0, math.inf, ()

    start_rarity = str(rarity)
    start_progress = max(0, int(progress))
    start_total = int(progress_total) if int(progress_total) > 0 else int(
        POTENTIAL_RANK_REQUIREMENTS.get(start_rarity, 0)
    )
    alive: Dict[Tuple[str, int, int], float] = {
        (start_rarity, start_progress, start_total): 1.0
    }
    cumulative_success = 0.0
    weighted_success_step = 0.0
    warnings: List[str] = []

    for step in range(1, cubes + 1):
        next_alive: Dict[Tuple[str, int, int], float] = {}
        for (current_rarity, current_progress, current_total), mass in alive.items():
            if mass <= 0.0:
                continue
            current_success = success_by_rarity.get(current_rarity)
            if current_success is None:
                warnings.append(
                    f"Rank-aware budget stops at {current_rarity}: complete rates were not collected."
                )
                next_alive[(current_rarity, current_progress, current_total)] = (
                    next_alive.get((current_rarity, current_progress, current_total), 0.0) + mass
                )
                continue

            next_rarity = _next_rarity(current_rarity)
            if not next_rarity:
                first_success = mass * current_success
                cumulative_success += first_success
                weighted_success_step += first_success * step
                failed = mass * (1.0 - current_success)
                next_alive[(current_rarity, 0, 0)] = next_alive.get((current_rarity, 0, 0), 0.0) + failed
                continue

            total = current_total if current_total > 0 else int(
                POTENTIAL_RANK_REQUIREMENTS.get(current_rarity, 0)
            )
            guaranteed = total > 0 and current_progress + 1 >= total
            q = 1.0 if guaranteed else profile.rank_up_probability(slot, current_rarity)
            q = max(0.0, min(1.0, q))

            stay_mass = mass * (1.0 - q)
            if stay_mass > 0.0:
                first_success = stay_mass * current_success
                cumulative_success += first_success
                weighted_success_step += first_success * step
                failed = stay_mass * (1.0 - current_success)
                new_progress = current_progress + 1 if total > 0 else 0
                state = (current_rarity, new_progress, total)
                next_alive[state] = next_alive.get(state, 0.0) + failed

            rank_mass = mass * q
            if rank_mass > 0.0:
                next_success = success_by_rarity.get(next_rarity)
                if next_success is None:
                    warnings.append(
                        f"Rank-aware budget stops after reaching {next_rarity}: complete rates were not collected."
                    )
                    state = (
                        next_rarity,
                        0,
                        int(POTENTIAL_RANK_REQUIREMENTS.get(next_rarity, 0)),
                    )
                    next_alive[state] = next_alive.get(state, 0.0) + rank_mass
                else:
                    first_success = rank_mass * next_success
                    cumulative_success += first_success
                    weighted_success_step += first_success * step
                    failed = rank_mass * (1.0 - next_success)
                    state = (
                        next_rarity,
                        0,
                        int(POTENTIAL_RANK_REQUIREMENTS.get(next_rarity, 0)),
                    )
                    next_alive[state] = next_alive.get(state, 0.0) + failed

        alive = {
            state: probability
            for state, probability in next_alive.items()
            if probability > 1e-15
        }
        if not alive:
            break

    cumulative_success = max(0.0, min(1.0, cumulative_success))
    expected_step = (
        weighted_success_step / cumulative_success
        if cumulative_success > 0.0
        else math.inf
    )
    return cumulative_success, expected_step, tuple(dict.fromkeys(warnings))

def _optimal_stopping_plan(
    profile: PotentialRateProfile,
    *,
    slot: str,
    rarity: str,
    progress: int,
    progress_total: int,
    cubes: int,
    summaries_by_rarity: Mapping[str, _EnumeratedDistribution],
) -> _OptimalStoppingPlan:
    """Solve the finite-budget irreversible reroll decision.

    At every observed roll, the policy chooses between stopping with that active
    result and spending another cube. The objective is risk-neutral expected
    modeled damage at the end of the available budget. Rank-up branches use the
    newly reached rarity's result table on the triggering cube, matching the
    explicit assumption used by the rest of the rank-aware planner.
    """

    cubes = max(0, int(cubes))
    if cubes <= 0:
        return _OptimalStoppingPlan(
            available=True,
            note="No cubes remain, so stopping is mandatory.",
        )
    try:
        start_index = POTENTIAL_RARITIES.index(str(rarity))
    except ValueError:
        return _OptimalStoppingPlan(False, note=f"Unknown Potential rarity {rarity!r}.")

    indexes: Dict[str, _GainDistributionIndex] = {}
    missing: List[str] = []
    for candidate_rarity in POTENTIAL_RARITIES[start_index:]:
        summary = summaries_by_rarity.get(candidate_rarity)
        if summary is None:
            missing.append(candidate_rarity)
            continue
        try:
            indexes[candidate_rarity] = _GainDistributionIndex(summary.gain_distribution)
        except Exception as exc:
            return _OptimalStoppingPlan(False, note=f"Could not index {candidate_rarity} outcomes: {exc}")
    # Any higher rarity can be reached early or by guarantee over a long enough
    # session. Refuse to call the policy exact if one of those tables is absent.
    if missing:
        return _OptimalStoppingPlan(
            False,
            note="Optimal stopping is unavailable because complete future-rarity rates are missing for: "
            + ", ".join(missing)
            + ".",
        )

    start_total = int(progress_total) if int(progress_total) > 0 else int(
        POTENTIAL_RANK_REQUIREMENTS.get(rarity, 0)
    )
    if start_total > 0:
        start_progress = max(0, min(int(progress), start_total - 1))
    else:
        start_progress = 0
    start_state = (str(rarity), start_progress, start_total)

    totals: Dict[str, int] = {}
    states: List[Tuple[str, int, int]] = []
    for candidate_rarity in POTENTIAL_RARITIES[start_index:]:
        if candidate_rarity == rarity:
            total = start_total
        else:
            total = int(POTENTIAL_RANK_REQUIREMENTS.get(candidate_rarity, 0))
        totals[candidate_rarity] = total
        if _next_rarity(candidate_rarity) and total > 0:
            states.extend((candidate_rarity, value, total) for value in range(total))
        else:
            states.append((candidate_rarity, 0, total))
    if start_state not in states:
        states.append(start_state)

    def branches(state: Tuple[str, int, int]):
        current_rarity, current_progress, current_total = state
        next_rarity = _next_rarity(current_rarity)
        if not next_rarity:
            return ((1.0, current_rarity, state),)
        total = current_total if current_total > 0 else int(
            POTENTIAL_RANK_REQUIREMENTS.get(current_rarity, 0)
        )
        next_state = (next_rarity, 0, totals.get(next_rarity, int(POTENTIAL_RANK_REQUIREMENTS.get(next_rarity, 0))))
        guaranteed = total > 0 and current_progress + 1 >= total
        q = 1.0 if guaranteed else profile.rank_up_probability(slot, current_rarity)
        q = max(0.0, min(1.0, q))
        result = []
        if q < 1.0 - 1e-15:
            stay_progress = current_progress + 1 if total > 0 else 0
            stay_state = (current_rarity, stay_progress, total)
            result.append((1.0 - q, current_rarity, stay_state))
        if q > 1e-15:
            result.append((q, next_rarity, next_state))
        return tuple(result)

    # Search beyond the current budget so the UI can distinguish "stop" from
    # "save until the policy turns positive." The dynamic program uses only
    # the previous horizon, so the 500-cube search is modest in memory.
    search_horizon = max(cubes, 500)
    zero_metrics = _PolicyMetrics(0.0, 0.0, 1.0, 0.0, 0.0)
    values_previous: Dict[Tuple[str, int, int], float] = {state: 0.0 for state in states}
    metrics_previous: Dict[Tuple[str, int, int], _PolicyMetrics] = {state: zero_metrics for state in states}
    first_positive = 0
    budget_value = 0.0
    budget_metrics = zero_metrics
    next_stop_threshold = math.nan
    rank_stop_threshold = math.nan

    for horizon in range(1, search_horizon + 1):
        values_current: Dict[Tuple[str, int, int], float] = {}
        metrics_current: Dict[Tuple[str, int, int], _PolicyMetrics] = {}
        for state in states:
            expected_gain = 0.0
            better = equal = worse = severe = 0.0
            for branch_probability, result_rarity, next_state in branches(state):
                index = indexes.get(result_rarity)
                if index is None or next_state not in values_previous:
                    return _OptimalStoppingPlan(
                        False,
                        note=f"Optimal stopping reached an unmodeled {result_rarity} rank state.",
                    )
                if horizon == 1:
                    branch_metrics = index.policy_metrics(None, zero_metrics)
                    branch_value = index.total_gain
                else:
                    continuation_value = values_previous[next_state]
                    branch_value = index.expected_max(continuation_value)
                    branch_metrics = index.policy_metrics(continuation_value, metrics_previous[next_state])
                expected_gain += branch_probability * branch_value
                better += branch_probability * branch_metrics.better
                equal += branch_probability * branch_metrics.equal
                worse += branch_probability * branch_metrics.worse
                severe += branch_probability * branch_metrics.severe_loss
            values_current[state] = expected_gain
            metrics_current[state] = _PolicyMetrics(
                expected_gain=expected_gain,
                better=max(0.0, min(1.0, better)),
                equal=max(0.0, min(1.0, equal)),
                worse=max(0.0, min(1.0, worse)),
                severe_loss=max(0.0, min(1.0, severe)),
            )

        start_value = values_current[start_state]
        if not first_positive and start_value > 1e-9:
            first_positive = horizon
        if horizon == cubes:
            budget_value = start_value
            budget_metrics = metrics_current[start_state]
            if cubes > 1:
                for branch_probability, result_rarity, next_state in branches(start_state):
                    if branch_probability <= 0.0:
                        continue
                    threshold = values_previous[next_state]
                    if result_rarity == rarity and math.isnan(next_stop_threshold):
                        next_stop_threshold = threshold
                    elif result_rarity != rarity and math.isnan(rank_stop_threshold):
                        rank_stop_threshold = threshold
        values_previous = values_current
        metrics_previous = metrics_current
        if horizon >= cubes and first_positive and (first_positive <= cubes or horizon >= first_positive):
            # Once the requested budget and the first positive horizon are both
            # known, no additional search is needed.
            break

    should_reroll = budget_value > 1e-9
    save_to = first_positive if (not should_reroll and first_positive > cubes) else 0
    return _OptimalStoppingPlan(
        available=True,
        should_reroll=should_reroll,
        reroll_value_gain_pct=budget_value,
        expected_final_gain_pct=max(0.0, budget_value),
        chance_end_better=budget_metrics.better,
        chance_end_equal=budget_metrics.equal,
        chance_end_worse=budget_metrics.worse,
        severe_loss_probability=budget_metrics.severe_loss,
        next_stop_threshold_gain_pct=next_stop_threshold,
        rank_stop_threshold_gain_pct=rank_stop_threshold,
        cubes_to_positive_value=save_to,
        note=(
            "Risk-neutral optimal stopping: after each irreversible reroll, stop when the active result is worth at least "
            "the expected value of continuing with the remaining cubes. Utility options that are not modeled for damage "
            "remain zero-valued, and rank-up-triggering cubes are assumed to use the new rarity's table."
        ),
    )


def analyze_configured_rates(
    displayed_stats,
    target,
    *,
    slot: str,
    rarity: str,
    current_lines: Sequence[PotentialLine],
    minimum_gain_pct: float,
    cubes: int,
    main_stat_name: str,
    score_fn: Callable[[object, object], float],
    profile: PotentialRateProfile,
    progress: int = 0,
    progress_total: int = 0,
    include_guidance: bool = False,
    include_rank_aware: bool = False,
) -> PotentialRateAnalysis:
    if len(current_lines) != 3:
        raise ValueError(f"{slot} current Potential must contain exactly three lines.")
    distributions = [profile.distribution(slot, rarity, line_number) for line_number in (1, 2, 3)]
    missing = [str(index + 1) for index, items in enumerate(distributions) if not items]
    if missing:
        details = [f"line {line}: {profile.section_reason(slot, rarity, int(line))}" for line in missing]
        raise KeyError(f"Configured Option Rates are missing for {slot} {rarity} ({'; '.join(details)}).")

    minimum_gain_pct = max(0.0, float(minimum_gain_pct))
    cubes = max(0, int(cubes))
    summary = _enumerate_distribution_set(
        displayed_stats,
        target,
        current_lines=current_lines,
        distributions=distributions,
        minimum_gain_pct=minimum_gain_pct,
        main_stat_name=main_stat_name,
        score_fn=score_fn,
        collect_guidance=include_guidance,
    )
    success_probability = summary.success_probability
    positive_gain_sum = summary.expected_positive_gain
    net_gain_sum = summary.expected_net_gain
    average_gain = summary.average_gain_on_success
    better_probability = summary.better_probability
    equal_probability = summary.equal_probability
    worse_probability = summary.worse_probability
    severe_loss_probability = summary.severe_loss_probability
    average_loss = summary.average_loss_on_worse
    median_gain = summary.median_gain_pct
    modeled_mass = summary.modeled_probability_mass
    combination_count = summary.combination_count
    current_score = summary.current_score
    warnings = summary.warnings
    stopping_conditions = summary.stopping_conditions
    stopping_coverage = summary.stopping_condition_coverage
    top_exact_outcomes = summary.top_exact_outcomes
    budget_chance = 1.0 - (1.0 - success_probability) ** cubes
    expected_cubes = math.inf if success_probability <= 0.0 else 1.0 / success_probability
    q, rank_chance, expected_rank, remaining, next_rarity = _rank_up_plan(
        profile,
        slot=slot,
        rarity=rarity,
        progress=progress,
        progress_total=progress_total,
        cubes=cubes,
    )
    next_success = 0.0
    next_ev = 0.0
    warning_list = list(warnings)
    success_by_rarity: Dict[str, float] = {rarity: success_probability}
    summaries_by_rarity: Dict[str, _EnumeratedDistribution] = {rarity: summary}

    if next_rarity:
        if profile.has_complete_table(slot, next_rarity):
            next_distributions = [profile.distribution(slot, next_rarity, line) for line in (1, 2, 3)]
            next_summary = _enumerate_distribution_set(
                displayed_stats,
                target,
                current_lines=current_lines,
                distributions=next_distributions,
                minimum_gain_pct=minimum_gain_pct,
                main_stat_name=main_stat_name,
                score_fn=score_fn,
            )
            next_success = next_summary.success_probability
            next_ev = next_summary.expected_positive_gain
            next_warnings = next_summary.warnings
            success_by_rarity[next_rarity] = next_success
            summaries_by_rarity[next_rarity] = next_summary
            warning_list.extend(next_warnings)
        else:
            missing_next = ", ".join(str(line) for line in profile.missing_lines(slot, next_rarity))
            warning_list.append(
                f"Next-rarity preview unavailable: {slot} {next_rarity} rate line(s) {missing_next or '1, 2, 3'} were not collected."
            )

    rank_aware_chance = budget_chance
    rank_aware_expected = expected_cubes
    if include_rank_aware and cubes > 0:
        try:
            start_index = POTENTIAL_RARITIES.index(rarity)
        except ValueError:
            start_index = len(POTENTIAL_RARITIES)
        for future_rarity in POTENTIAL_RARITIES[start_index + 1:]:
            if future_rarity in success_by_rarity:
                continue
            if not profile.has_complete_table(slot, future_rarity):
                break
            future_distributions = [
                profile.distribution(slot, future_rarity, line)
                for line in (1, 2, 3)
            ]
            future_summary = _enumerate_distribution_set(
                displayed_stats,
                target,
                current_lines=current_lines,
                distributions=future_distributions,
                minimum_gain_pct=minimum_gain_pct,
                main_stat_name=main_stat_name,
                score_fn=score_fn,
            )
            future_success = future_summary.success_probability
            future_warnings = future_summary.warnings
            success_by_rarity[future_rarity] = future_success
            summaries_by_rarity[future_rarity] = future_summary
            warning_list.extend(future_warnings)

        rank_aware_chance, rank_aware_expected, rank_warnings = _rank_aware_budget_success(
            profile,
            slot=slot,
            rarity=rarity,
            progress=progress,
            progress_total=progress_total,
            cubes=cubes,
            success_by_rarity=success_by_rarity,
        )
        warning_list.extend(rank_warnings)

    optimal_plan = _OptimalStoppingPlan(False, note="Rank-aware optimal stopping was not requested.")
    if include_rank_aware:
        optimal_plan = _optimal_stopping_plan(
            profile,
            slot=slot,
            rarity=rarity,
            progress=progress,
            progress_total=progress_total,
            cubes=cubes,
            summaries_by_rarity=summaries_by_rarity,
        )
        if not optimal_plan.available and optimal_plan.note:
            warning_list.append(optimal_plan.note)

    failure_probability = max(0.0, 1.0 - success_probability)
    failure_gain_sum = net_gain_sum - success_probability * average_gain
    average_failure_gain = failure_gain_sum / failure_probability if failure_probability > 1e-12 else 0.0
    if cubes <= 0:
        chance_end_worse = 0.0
        expected_final_gain = 0.0
    else:
        chance_end_worse = ((1.0 - success_probability) ** max(0, cubes - 1)) * worse_probability
        expected_final_gain = budget_chance * average_gain + (1.0 - budget_chance) * average_failure_gain

    return PotentialRateAnalysis(
        slot=slot,
        rarity=rarity,
        success_probability=success_probability,
        chance_with_budget=max(0.0, min(1.0, budget_chance)),
        expected_cubes_to_success=expected_cubes,
        expected_positive_gain_per_cube=positive_gain_sum,
        expected_net_gain_per_cube=net_gain_sum,
        average_gain_on_success=average_gain,
        better_probability=better_probability,
        equal_probability=equal_probability,
        worse_probability=worse_probability,
        severe_loss_probability=severe_loss_probability,
        average_loss_on_worse=average_loss,
        median_gain_pct=median_gain,
        chance_end_worse_with_budget=max(0.0, min(1.0, chance_end_worse)),
        expected_final_gain_with_budget=expected_final_gain,
        modeled_probability_mass=modeled_mass,
        combination_count=combination_count,
        minimum_gain_pct=minimum_gain_pct,
        current_score=current_score,
        progress=max(0, int(progress)),
        progress_total=max(0, int(progress_total)),
        rank_up_probability_per_cube=q,
        chance_to_rank_up_with_budget=rank_chance,
        expected_cubes_to_rank_up=expected_rank,
        cubes_to_guaranteed_rank_up=remaining,
        next_rarity=next_rarity,
        next_rarity_success_probability=next_success,
        next_rarity_expected_gain_per_cube=next_ev,
        cubes_for_50pct_success=_cubes_for_probability(success_probability, 0.5),
        rank_aware_chance_with_budget=max(0.0, min(1.0, rank_aware_chance)),
        rank_aware_expected_cubes_to_success=rank_aware_expected,
        stopping_conditions=stopping_conditions,
        stopping_condition_coverage=stopping_coverage,
        top_exact_outcomes=top_exact_outcomes,
        warnings=tuple(dict.fromkeys(warning_list)),
        optimal_policy_available=optimal_plan.available,
        optimal_should_reroll=optimal_plan.should_reroll,
        optimal_reroll_value_gain_pct=optimal_plan.reroll_value_gain_pct,
        optimal_expected_final_gain_pct=optimal_plan.expected_final_gain_pct,
        optimal_chance_end_better=optimal_plan.chance_end_better,
        optimal_chance_end_equal=optimal_plan.chance_end_equal,
        optimal_chance_end_worse=optimal_plan.chance_end_worse,
        optimal_severe_loss_probability=optimal_plan.severe_loss_probability,
        optimal_next_stop_threshold_gain_pct=optimal_plan.next_stop_threshold_gain_pct,
        optimal_rank_stop_threshold_gain_pct=optimal_plan.rank_stop_threshold_gain_pct,
        optimal_cubes_to_positive_value=optimal_plan.cubes_to_positive_value,
        optimal_policy_note=optimal_plan.note,
    )

def rank_slots_by_configured_rates(
    displayed_stats,
    target,
    slot_states: Mapping[str, Mapping[str, object]],
    *,
    minimum_gain_pct: float,
    cubes: int,
    main_stat_name: str,
    score_fn: Callable[[object, object], float],
    profile: PotentialRateProfile,
    eligibility_fn: Callable[[Mapping[str, object]], Tuple[bool, str]],
) -> Tuple[PotentialRatePriority, ...]:
    rows: List[PotentialRatePriority] = []
    for slot, state in slot_states.items():
        eligible, _reason = eligibility_fn(state)
        if not eligible:
            continue
        rarity = str(state.get("rarity", "Rare"))
        if not profile.has_complete_table(slot, rarity):
            continue
        current_lines = _state_lines(state)
        try:
            progress = int(float(state.get("progress", 0) or 0))
            progress_total = int(float(state.get("progress_total", 0) or 0))
        except (TypeError, ValueError):
            progress = progress_total = 0
        analysis = analyze_configured_rates(
            displayed_stats,
            target,
            slot=slot,
            rarity=rarity,
            current_lines=current_lines,
            minimum_gain_pct=minimum_gain_pct,
            cubes=cubes,
            main_stat_name=main_stat_name,
            score_fn=score_fn,
            profile=profile,
            progress=progress,
            progress_total=progress_total,
        )
        if analysis.success_probability <= 0.0:
            recommendation = "STOP / MOVE ON"
        elif (
            analysis.next_rarity
            and analysis.cubes_to_guaranteed_rank_up > 0
            and cubes >= analysis.cubes_to_guaranteed_rank_up
            and analysis.next_rarity_expected_gain_per_cube > analysis.expected_positive_gain_per_cube * 1.05
        ):
            recommendation = "PUSH RANK-UP"
        elif analysis.expected_final_gain_with_budget <= 0.0:
            recommendation = "STOP — TOO RISKY"
        elif analysis.chance_with_budget < 0.35 and analysis.cubes_for_50pct_success > cubes:
            recommendation = "SAVE FOR 50% SESSION"
        elif analysis.expected_final_gain_with_budget < 0.10:
            recommendation = "LOW-VALUE ROLL"
        else:
            recommendation = "ROLL"
        rows.append(PotentialRatePriority(
            slot=slot,
            rarity=rarity,
            success_probability=analysis.success_probability,
            chance_with_budget=analysis.chance_with_budget,
            expected_cubes_to_success=analysis.expected_cubes_to_success,
            expected_positive_gain_per_cube=analysis.expected_positive_gain_per_cube,
            expected_net_gain_per_cube=analysis.expected_net_gain_per_cube,
            average_gain_on_success=analysis.average_gain_on_success,
            better_probability=analysis.better_probability,
            worse_probability=analysis.worse_probability,
            severe_loss_probability=analysis.severe_loss_probability,
            chance_end_worse_with_budget=analysis.chance_end_worse_with_budget,
            expected_final_gain_with_budget=analysis.expected_final_gain_with_budget,
            modeled_probability_mass=analysis.modeled_probability_mass,
            combination_count=analysis.combination_count,
            minimum_gain_pct=analysis.minimum_gain_pct,
            recommendation=recommendation,
            progress=analysis.progress,
            progress_total=analysis.progress_total,
            rank_up_probability_per_cube=analysis.rank_up_probability_per_cube,
            chance_to_rank_up_with_budget=analysis.chance_to_rank_up_with_budget,
            expected_cubes_to_rank_up=analysis.expected_cubes_to_rank_up,
            cubes_to_guaranteed_rank_up=analysis.cubes_to_guaranteed_rank_up,
            next_rarity=analysis.next_rarity,
            next_rarity_success_probability=analysis.next_rarity_success_probability,
            next_rarity_expected_gain_per_cube=analysis.next_rarity_expected_gain_per_cube,
            cubes_for_50pct_success=analysis.cubes_for_50pct_success,
            warnings=analysis.warnings,
        ))
    rows.sort(
        key=lambda row: (
            -row.expected_final_gain_with_budget,
            row.chance_end_worse_with_budget,
            -row.success_probability,
            row.expected_cubes_to_success,
            row.slot,
        )
    )
    return tuple(rows)
