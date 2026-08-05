"""Pure calculation engine for Potential roll comparison."""

from __future__ import annotations

import copy
import math
from typing import Callable, Dict, Iterable, List, Mapping, Sequence, Tuple

from .data import POTENTIAL_RANK_REQUIREMENTS, SLOT_SPECIAL_HIGH_VALUES, SLOT_SPECIAL_OPTIONS
from .models import PotentialComparison, PotentialLine, PotentialSlotPriority


def _pct_gain(old: float, new: float) -> float:
    if old <= 0:
        return 0.0
    return (new / old - 1.0) * 100.0


def _main_stat_factor(stats) -> float:
    return max(0.0, 1.0 + float(getattr(stats, "current_main_stat_pct", 0.0)) / 100.0)


def _apply_flat_main_stat(stats, value: float) -> None:
    stats.total_main_stat += value
    stats.attack += value * (1.0 + float(getattr(stats, "flat_attack_scaling_pct", 0.0)) / 100.0)
    stats.stat_prop_damage += value / 100.0


def _apply_main_stat_percent(stats, value: float) -> None:
    current_pct = float(getattr(stats, "current_main_stat_pct", 0.0))
    old_factor = max(1e-9, 1.0 + current_pct / 100.0)
    raw_stat = stats.total_main_stat / old_factor
    new_pct = current_pct + value
    new_total = raw_stat * max(0.0, 1.0 + new_pct / 100.0)
    _apply_flat_main_stat(stats, new_total - stats.total_main_stat)
    stats.current_main_stat_pct = new_pct


def _remove_main_stat_percent(stats, value: float) -> None:
    current_pct = float(getattr(stats, "current_main_stat_pct", 0.0))
    old_factor = max(1e-9, 1.0 + current_pct / 100.0)
    raw_stat = stats.total_main_stat / old_factor
    new_pct = current_pct - value
    new_total = raw_stat * max(0.0, 1.0 + new_pct / 100.0)
    _apply_flat_main_stat(stats, new_total - stats.total_main_stat)
    stats.current_main_stat_pct = new_pct


def _remove_diminishing(total: float, source: float, cap: float) -> float:
    source = max(0.0, min(cap, source))
    factor = 1.0 - source / cap
    if factor <= 1e-12:
        return 0.0
    remaining_after = 1.0 - max(0.0, min(cap, total)) / cap
    remaining_before = remaining_after / factor
    return max(0.0, min(cap, cap * (1.0 - remaining_before)))


def _combine_diminishing(total: float, source: float, cap: float) -> float:
    total = max(0.0, min(cap, total))
    source = max(0.0, min(cap, source))
    return cap * (1.0 - (1.0 - total / cap) * (1.0 - source / cap))


def _canonical_line(line: PotentialLine, main_stat_name: str) -> Tuple[str, float]:
    """Map a stored Potential line to the character-stat operation it represents."""
    stat_name = line.stat_name
    value = float(line.value)
    if stat_name in {"STR", "DEX", "INT", "LUK"}:
        if stat_name != main_stat_name:
            return "Unmodeled", value
        return ("Main Stat %" if line.is_percent else "Main Stat"), value
    if stat_name in {"Main Stat", "Attack", "Max HP", "Max MP"} and line.is_percent:
        return f"{stat_name} %", value
    return stat_name, value


def apply_line(stats, line: PotentialLine, main_stat_name: str) -> bool:
    name, value = _canonical_line(line, main_stat_name)
    if name == "Main Stat":
        _apply_flat_main_stat(stats, value)
    elif name == "Main Stat %":
        _apply_main_stat_percent(stats, value)
    elif name == "Attack":
        stats.attack += value
    elif name == "Attack %":
        stats.attack *= max(0.0, 1.0 + value / 100.0)
    elif name == "Damage":
        stats.damage += value
    elif name == "Final Damage":
        stats.final_damage = (1.0 + stats.final_damage / 100.0) * (1.0 + value / 100.0) * 100.0 - 100.0
    elif name == "Critical Rate":
        stats.crit_rate += value
    elif name == "Critical Damage":
        stats.crit_damage += value
    elif name == "Min Damage Multiplier":
        stats.min_damage += value
    elif name == "Max Damage Multiplier":
        stats.max_damage += value
    elif name == "Boss Monster Damage":
        stats.boss_damage += value
    elif name == "Normal Monster Damage":
        stats.normal_damage += value
    elif name == "Basic Attack Damage":
        stats.basic_attack_damage += value
    elif name == "Skill Damage":
        stats.skill_damage += value
    elif name == "Attack Speed":
        stats.attack_speed = _combine_diminishing(stats.attack_speed, value, 150.0)
    elif name == "Defense Penetration":
        stats.defense_pen = _combine_diminishing(stats.defense_pen, value, 100.0)
    elif name == "Accuracy":
        stats.accuracy += value
    else:
        return False
    return True


def remove_line(stats, line: PotentialLine, main_stat_name: str) -> bool:
    name, value = _canonical_line(line, main_stat_name)
    if name == "Main Stat":
        _apply_flat_main_stat(stats, -value)
    elif name == "Main Stat %":
        _remove_main_stat_percent(stats, value)
    elif name == "Attack":
        stats.attack -= value
    elif name == "Attack %":
        stats.attack /= max(1e-9, 1.0 + value / 100.0)
    elif name == "Damage":
        stats.damage -= value
    elif name == "Final Damage":
        stats.final_damage = ((1.0 + stats.final_damage / 100.0) / max(1e-9, 1.0 + value / 100.0) - 1.0) * 100.0
    elif name == "Critical Rate":
        stats.crit_rate -= value
    elif name == "Critical Damage":
        stats.crit_damage -= value
    elif name == "Min Damage Multiplier":
        stats.min_damage -= value
    elif name == "Max Damage Multiplier":
        stats.max_damage -= value
    elif name == "Boss Monster Damage":
        stats.boss_damage -= value
    elif name == "Normal Monster Damage":
        stats.normal_damage -= value
    elif name == "Basic Attack Damage":
        stats.basic_attack_damage -= value
    elif name == "Skill Damage":
        stats.skill_damage -= value
    elif name == "Attack Speed":
        stats.attack_speed = _remove_diminishing(stats.attack_speed, value, 150.0)
    elif name == "Defense Penetration":
        stats.defense_pen = _remove_diminishing(stats.defense_pen, value, 100.0)
    elif name == "Accuracy":
        stats.accuracy -= value
    else:
        return False
    return True


def stats_after_replacing_roll(
    displayed_stats,
    current_lines: Sequence[PotentialLine],
    candidate_lines: Sequence[PotentialLine],
    main_stat_name: str,
):
    """Return modeled character stats after irreversibly replacing one roll.

    The equipment planner keeps this session-only snapshot so consecutive OCR
    rerolls remain internally consistent even before the user re-enters the
    changed character totals from the game.
    """
    updated = copy.deepcopy(displayed_stats)
    warnings: List[str] = []
    for line in current_lines:
        if not remove_line(updated, line, main_stat_name):
            warnings.append(f"Current {line.display_name} is not yet included in the damage model.")
    for line in candidate_lines:
        if not apply_line(updated, line, main_stat_name):
            warnings.append(f"New {line.display_name} is not yet included in the damage model.")
    return updated, tuple(dict.fromkeys(warnings))


def compare_rolls(
    displayed_stats,
    target,
    current_lines: Sequence[PotentialLine],
    candidate_lines: Sequence[PotentialLine],
    main_stat_name: str,
    score_fn: Callable[[object, object], float],
) -> PotentialComparison:
    current_score = float(score_fn(displayed_stats, target))
    baseline = copy.deepcopy(displayed_stats)
    modeled_current = 0
    modeled_candidate = 0
    warnings: List[str] = []

    for line in current_lines:
        if remove_line(baseline, line, main_stat_name):
            modeled_current += 1
        else:
            warnings.append(f"Current {line.display_name} is not yet included in the damage model.")

    candidate_stats = copy.deepcopy(baseline)
    for line in candidate_lines:
        if apply_line(candidate_stats, line, main_stat_name):
            modeled_candidate += 1
        else:
            warnings.append(f"New {line.display_name} is not yet included in the damage model.")

    candidate_score = float(score_fn(candidate_stats, target))
    return PotentialComparison(
        current_score=current_score,
        candidate_score=candidate_score,
        gain_pct=_pct_gain(current_score, candidate_score),
        modeled_current_lines=modeled_current,
        modeled_candidate_lines=modeled_candidate,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def roll_signature(rarity: str, lines: Sequence[PotentialLine]) -> str:
    parts = [rarity]
    parts.extend(f"{line.stat_name}:{line.unit}:{line.value:.8g}" for line in lines)
    return "|".join(parts)


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> Tuple[float, float]:
    if trials <= 0:
        return (0.0, 1.0)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def chance_with_budget(per_roll_probability: float, cubes: int) -> float:
    cubes = max(0, int(cubes))
    p = max(0.0, min(1.0, per_roll_probability))
    return 1.0 - (1.0 - p) ** cubes


def _state_lines(state: Mapping[str, object]) -> List[PotentialLine]:
    result: List[PotentialLine] = []
    raw_lines = state.get("lines", [])
    if not isinstance(raw_lines, list):
        return result
    for item in raw_lines[:3]:
        if isinstance(item, PotentialLine):
            result.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        stat = str(item.get("stat", ""))
        try:
            value = float(item.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        if stat:
            result.append(PotentialLine(stat, value, str(item.get("unit", ""))))
    return result


def slot_eligibility(state: Mapping[str, object]) -> Tuple[bool, str]:
    """Return whether a slot should participate in equipment-wide priority.

    Auto mode follows the user's requested quality-of-life rule: an unscanned
    slot whose three values are all zero is assumed to be locked. Manual Locked
    always excludes it; manual Unlocked overrides the zero heuristic but still
    requires three usable lines so an incomplete editor cannot distort ranking.
    """
    status = str(state.get("slot_status", "Auto") or "Auto").strip().title()
    if status not in {"Auto", "Unlocked", "Locked"}:
        status = "Auto"
    if status == "Locked":
        return False, "marked locked"
    lines = _state_lines(state)
    if len(lines) != 3:
        return False, "current Potential is incomplete"
    has_nonzero = any(abs(float(line.value)) > 1e-12 for line in lines)
    configured = bool(state.get("configured", False)) or has_nonzero
    if status == "Unlocked":
        if not configured:
            return False, "marked unlocked but no current Potential is saved"
        return True, "manually marked unlocked"
    if not configured or not has_nonzero:
        return False, "auto-detected as not unlocked (all three values are zero)"
    return True, "auto-detected as unlocked"


def _state_configured(state: Mapping[str, object]) -> bool:
    eligible, _reason = slot_eligibility(state)
    return eligible


def rank_equipment_slots(
    displayed_stats,
    target,
    slot_states: Mapping[str, Mapping[str, object]],
    main_stat_name: str,
    score_fn: Callable[[object, object], float],
) -> Tuple[PotentialSlotPriority, ...]:
    """Rank configured equipment slots by practical cube opportunity.

    Exact per-option cube weights are not publicly available in a stable table,
    so this deliberately avoids fabricating an official expected-gain-per-cube
    value. The ranking combines three transparent signals: the current set's
    modeled contribution, verified slot-special headroom at the current rarity,
    and rank-up/observed-roll evidence.
    """

    current_score = float(score_fn(displayed_stats, target))
    raw_rows: List[Dict[str, object]] = []
    for slot, state in slot_states.items():
        if not isinstance(state, Mapping) or not _state_configured(state):
            continue
        lines = _state_lines(state)
        if len(lines) != 3:
            continue
        baseline = copy.deepcopy(displayed_stats)
        modeled = 0
        for line in lines:
            if remove_line(baseline, line, main_stat_name):
                modeled += 1
        baseline_score = float(score_fn(baseline, target))
        current_gain = _pct_gain(baseline_score, current_score)

        rarity = str(state.get("rarity", "Rare"))
        special_option = SLOT_SPECIAL_OPTIONS.get(slot, "")
        special_value = float(SLOT_SPECIAL_HIGH_VALUES.get(slot, {}).get(rarity, 0.0))
        special_replacement_gain = 0.0
        if special_option and special_value > 0.0:
            candidate = copy.deepcopy(baseline)
            if apply_line(candidate, PotentialLine(special_option, special_value), main_stat_name):
                special_score = float(score_fn(candidate, target))
                special_replacement_gain = _pct_gain(current_score, special_score)

        try:
            progress = max(0.0, float(state.get("progress", 0.0)))
        except (TypeError, ValueError):
            progress = 0.0
        try:
            total = float(state.get("progress_total", 0.0))
        except (TypeError, ValueError):
            total = 0.0
        if total <= 0.0:
            total = float(POTENTIAL_RANK_REQUIREMENTS.get(rarity, 0))
        progress_fraction = min(1.0, progress / total) if total > 0.0 else 0.0

        try:
            trials = max(0, int(state.get("observed_rolls", 0)))
            successes = max(0, int(state.get("observed_improvements", 0)))
        except (TypeError, ValueError):
            trials = successes = 0
        observed_rate = min(1.0, successes / trials) if trials else 0.0
        raw_rows.append({
            "slot": slot,
            "current_gain": current_gain,
            "modeled": modeled,
            "special_option": special_option,
            "special_value": special_value,
            "special_gain": special_replacement_gain,
            "progress_fraction": progress_fraction,
            "trials": trials,
            "observed_rate": observed_rate,
        })

    if not raw_rows:
        return ()
    strongest_current = max(float(row["current_gain"]) for row in raw_rows)
    results: List[PotentialSlotPriority] = []
    for row in raw_rows:
        current_gain = float(row["current_gain"])
        weakness = max(0.0, strongest_current - current_gain)
        special_gain = max(0.0, float(row["special_gain"]))
        progress_fraction = float(row["progress_fraction"])
        observed_rate = float(row["observed_rate"])
        trials = int(row["trials"])
        # Scores are percentage-point-like opportunity units. Observed data only
        # becomes influential after a modest sample and never pretends to be an
        # official cube probability.
        empirical_weight = min(1.0, trials / 30.0)
        empirical_signal = observed_rate * empirical_weight
        priority_score = (
            special_gain * 1.5
            + weakness * 0.45
            + progress_fraction * 0.40
            + empirical_signal * 0.80
        )
        reasons: List[str] = []
        if weakness > 0.05:
            reasons.append(f"current set is {weakness:.2f} points behind your strongest saved slot")
        if special_gain > 0.05:
            reasons.append(f"verified {row['special_option']} headroom is about {special_gain:+.2f}%")
        if progress_fraction >= 0.75:
            reasons.append(f"rank-up progress is {progress_fraction * 100:.0f}% complete")
        if trials:
            reasons.append(f"observed improvement rate is {observed_rate * 100:.1f}% over {trials} roll(s)")
        if not reasons:
            reasons.append("current saved set has the lowest modeled contribution among comparable slots")
        if trials >= 30:
            confidence = "Developing"
        elif trials >= 10:
            confidence = "Early"
        else:
            confidence = "Headroom estimate"
        results.append(PotentialSlotPriority(
            slot=str(row["slot"]),
            priority_score=priority_score,
            current_gain_pct=current_gain,
            special_replacement_gain_pct=float(row["special_gain"]),
            progress_fraction=progress_fraction,
            observed_improvement_rate=observed_rate,
            observed_trials=trials,
            special_option=str(row["special_option"]),
            special_value=float(row["special_value"]),
            confidence=confidence,
            reason="; ".join(reasons),
        ))
    results.sort(key=lambda item: (-item.priority_score, item.slot))
    return tuple(results)
