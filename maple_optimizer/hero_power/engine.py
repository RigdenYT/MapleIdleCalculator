"""Pure calculations for Hero Power and Ability planning.

This module intentionally has no Tkinter dependency.  It accepts the desktop
application's stat objects and scoring callbacks, which keeps the optimizer
logic reusable by tests and a future browser interface.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Sequence, Tuple, TypeVar

from .data import (
    ABILITY_MEDALS_TO_NEXT,
    ABILITY_RANGES,
    ABILITY_REROLL_COST,
    ABILITY_TIER_PROBABILITIES,
    ABILITY_TIERS,
)
from .models import (
    AbilityActionPlan,
    AbilityLine,
    ReplacementThreshold,
    RerollStrategy,
    SuccessfulPattern,
    TierLineRecommendation,
    TierRecommendation,
)

StatsT = TypeVar("StatsT")
TargetT = TypeVar("TargetT")
ScoreFunction = Callable[[StatsT, TargetT], float]
CombineFunction = Callable[[float, Iterable[float], float], float]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ability_source_factor(value: float, cap: float) -> float:
    return max(1e-9, 1.0 - value / cap)


def remove_diminishing_sources(total: float, sources: Sequence[float], cap: float) -> float:
    product = 1.0
    for value in sources:
        product *= ability_source_factor(value, cap)
    if product <= 1e-9:
        return 0.0
    return _clamp(cap * (1.0 - (1.0 - _clamp(total, 0.0, cap) / cap) / product), 0.0, cap)


def apply_flat_main_stat(stats: StatsT, delta: float) -> None:
    stats.total_main_stat = max(0.0, stats.total_main_stat + delta)
    stats.attack = max(0.0, stats.attack + delta * (1.0 + stats.flat_attack_scaling_pct / 100.0))
    stats.stat_prop_damage = max(0.0, stats.stat_prop_damage + delta / 100.0)


def apply_ability_line(
    stats: StatsT,
    stat_name: str,
    value: float,
    combine_diminishing: CombineFunction,
) -> None:
    if stat_name == "Main Stat":
        apply_flat_main_stat(stats, value)
    elif stat_name == "Accuracy":
        stats.accuracy += value
    elif stat_name == "Damage":
        stats.damage += value
    elif stat_name == "Min Damage Multiplier":
        stats.min_damage += value
    elif stat_name == "Max Damage Multiplier":
        stats.max_damage += value
    elif stat_name == "Critical Rate":
        stats.crit_rate += value
    elif stat_name == "Attack Speed":
        stats.attack_speed = combine_diminishing(stats.attack_speed, [value], 150.0)
    elif stat_name == "Defense Penetration":
        stats.defense_pen = combine_diminishing(stats.defense_pen, [value], 100.0)
    elif stat_name == "Boss Monster Damage":
        stats.boss_damage += value
    elif stat_name == "Normal Monster Damage":
        stats.normal_damage += value


def remove_ability_lines(
    stats: StatsT,
    lines: Sequence[Tuple[str, float]],
) -> StatsT:
    result = copy.deepcopy(stats)
    speed_sources = [value for name, value in lines if name == "Attack Speed"]
    penetration_sources = [value for name, value in lines if name == "Defense Penetration"]
    if speed_sources:
        result.attack_speed = remove_diminishing_sources(result.attack_speed, speed_sources, 150.0)
    if penetration_sources:
        result.defense_pen = remove_diminishing_sources(result.defense_pen, penetration_sources, 100.0)
    for name, value in lines:
        if name in {"Attack Speed", "Defense Penetration"}:
            continue
        if name == "Main Stat":
            apply_flat_main_stat(result, -value)
        elif name == "Accuracy":
            result.accuracy = max(0.0, result.accuracy - value)
        elif name == "Damage":
            result.damage -= value
        elif name == "Min Damage Multiplier":
            result.min_damage -= value
        elif name == "Max Damage Multiplier":
            result.max_damage -= value
        elif name == "Critical Rate":
            result.crit_rate -= value
        elif name == "Boss Monster Damage":
            result.boss_damage -= value
        elif name == "Normal Monster Damage":
            result.normal_damage -= value
    return result


def apply_lines(
    stats: StatsT,
    lines: Sequence[Tuple[str, float]],
    combine_diminishing: CombineFunction,
) -> StatsT:
    result = copy.deepcopy(stats)
    for stat_name, value in lines:
        apply_ability_line(result, stat_name, value, combine_diminishing)
    return result


def percentage_gain(new_score: float, old_score: float) -> float:
    return (new_score / old_score - 1.0) * 100.0 if old_score > 0 else 0.0


def current_line_contributions(
    base_stats: StatsT,
    current_lines: Sequence[AbilityLine],
    target: TargetT,
    score_fn: ScoreFunction,
    combine_diminishing: CombineFunction,
) -> Tuple[float, List[float]]:
    current_stats = apply_lines(
        base_stats,
        [(line.stat_name, line.value) for line in current_lines],
        combine_diminishing,
    )
    current_score = score_fn(current_stats, target)
    contributions: List[float] = []
    for index in range(len(current_lines)):
        without = apply_lines(
            base_stats,
            [
                (line.stat_name, line.value)
                for line_index, line in enumerate(current_lines)
                if line_index != index
            ],
            combine_diminishing,
        )
        contributions.append(percentage_gain(current_score, score_fn(without, target)))
    return current_score, contributions


@dataclass
class _BeamState:
    sequence: Tuple[int, ...]
    last_candidate_index: int
    stats: object
    score: float


def _best_maximum_sequence(
    base_stats: StatsT,
    target: TargetT,
    candidates: Sequence[Tuple[str, float, float]],
    slot_count: int,
    score_fn: ScoreFunction,
    combine_diminishing: CombineFunction,
    beam_width: int,
) -> Tuple[int, ...]:
    base_score = score_fn(base_stats, target)
    beam: List[_BeamState] = [_BeamState((), 0, copy.deepcopy(base_stats), base_score)]
    for _depth in range(slot_count):
        expanded: List[_BeamState] = []
        for state in beam:
            for candidate_index in range(state.last_candidate_index, len(candidates)):
                stat_name, _minimum, maximum = candidates[candidate_index]
                trial = copy.deepcopy(state.stats)
                apply_ability_line(trial, stat_name, maximum, combine_diminishing)
                expanded.append(
                    _BeamState(
                        sequence=state.sequence + (candidate_index,),
                        last_candidate_index=candidate_index,
                        stats=trial,
                        score=score_fn(trial, target),
                    )
                )
        if not expanded:
            break
        expanded.sort(key=lambda state: (state.score, tuple(-i for i in state.sequence)), reverse=True)
        beam = expanded[: max(1, beam_width)]
    return beam[0].sequence if beam else ()




def _order_sequence_by_marginal_gain(
    base_stats: StatsT,
    target: TargetT,
    candidates: Sequence[Tuple[str, float, float]],
    sequence: Sequence[int],
    score_fn: ScoreFunction,
    combine_diminishing: CombineFunction,
) -> Tuple[int, ...]:
    """Order a chosen multiset so the most useful next pick is shown first."""
    remaining = list(sequence)
    ordered: List[int] = []
    working = copy.deepcopy(base_stats)
    while remaining:
        best_position = 0
        best_score = float("-inf")
        for position, candidate_index in enumerate(remaining):
            stat_name, _minimum, maximum = candidates[candidate_index]
            trial = copy.deepcopy(working)
            apply_ability_line(trial, stat_name, maximum, combine_diminishing)
            score = score_fn(trial, target)
            if score > best_score + 1e-12:
                best_position = position
                best_score = score
        candidate_index = remaining.pop(best_position)
        stat_name, _minimum, maximum = candidates[candidate_index]
        apply_ability_line(working, stat_name, maximum, combine_diminishing)
        ordered.append(candidate_index)
    return tuple(ordered)


def optimize_tier(
    base_stats: StatsT,
    target: TargetT,
    tier: str,
    slot_count: int,
    reconfiguration_level: int,
    score_fn: ScoreFunction,
    combine_diminishing: CombineFunction,
    *,
    beam_width: int = 64,
) -> TierRecommendation:
    if tier not in ABILITY_TIERS:
        raise ValueError(f"Unknown Ability tier: {tier}")
    slot_count = int(_clamp(slot_count, 1, 7))
    reconfiguration_level = int(_clamp(reconfiguration_level, 1, 20))
    candidates = [
        (stat_name, ranges[tier][0], ranges[tier][1])
        for stat_name, ranges in ABILITY_RANGES.items()
        if tier in ranges
    ]
    sequence = _best_maximum_sequence(
        base_stats,
        target,
        candidates,
        slot_count,
        score_fn,
        combine_diminishing,
        beam_width,
    )
    sequence = _order_sequence_by_marginal_gain(
        base_stats,
        target,
        candidates,
        sequence,
        score_fn,
        combine_diminishing,
    )

    baseline_score = score_fn(base_stats, target)
    minimum_stats = copy.deepcopy(base_stats)
    maximum_stats = copy.deepcopy(base_stats)
    minimum_previous_score = baseline_score
    maximum_previous_score = baseline_score
    result_lines: List[TierLineRecommendation] = []

    for slot_number, candidate_index in enumerate(sequence, start=1):
        stat_name, minimum, maximum = candidates[candidate_index]
        apply_ability_line(minimum_stats, stat_name, minimum, combine_diminishing)
        apply_ability_line(maximum_stats, stat_name, maximum, combine_diminishing)
        minimum_score = score_fn(minimum_stats, target)
        maximum_score = score_fn(maximum_stats, target)
        result_lines.append(
            TierLineRecommendation(
                slot_number=slot_number,
                stat_name=stat_name,
                minimum_value=minimum,
                maximum_value=maximum,
                minimum_marginal_gain_pct=percentage_gain(minimum_score, minimum_previous_score),
                maximum_marginal_gain_pct=percentage_gain(maximum_score, maximum_previous_score),
                minimum_cumulative_gain_pct=percentage_gain(minimum_score, baseline_score),
                maximum_cumulative_gain_pct=percentage_gain(maximum_score, baseline_score),
            )
        )
        minimum_previous_score = minimum_score
        maximum_previous_score = maximum_score

    probability = ABILITY_TIER_PROBABILITIES[reconfiguration_level][ABILITY_TIERS.index(tier)]
    minimum_total = result_lines[-1].minimum_cumulative_gain_pct if result_lines else 0.0
    maximum_total = result_lines[-1].maximum_cumulative_gain_pct if result_lines else 0.0
    return TierRecommendation(
        tier=tier,
        slot_count=slot_count,
        probability_pct=probability,
        available=probability > 0.0,
        minimum_total_gain_pct=minimum_total,
        maximum_total_gain_pct=maximum_total,
        lines=tuple(result_lines),
    )


def optimize_all_tiers(
    base_stats: StatsT,
    target: TargetT,
    slot_count: int,
    reconfiguration_level: int,
    score_fn: ScoreFunction,
    combine_diminishing: CombineFunction,
    *,
    beam_width: int = 64,
) -> Tuple[TierRecommendation, ...]:
    return tuple(
        optimize_tier(
            base_stats,
            target,
            tier,
            slot_count,
            reconfiguration_level,
            score_fn,
            combine_diminishing,
            beam_width=beam_width,
        )
        for tier in ABILITY_TIERS
    )


@dataclass(frozen=True)
class _PatternOutcomeEstimate:
    signature: Tuple[str, ...]
    probability: float
    average_gain_pct: float
    minimum_gain_pct: float
    maximum_gain_pct: float


@dataclass(frozen=True)
class _LevelOutcomeEstimate:
    success_probability: float
    conditional_gain_pct: float
    margin_95_pct: float
    patterns: Tuple[SuccessfulPattern, ...]
    pattern_estimates: Dict[Tuple[str, ...], _PatternOutcomeEstimate]


@dataclass(frozen=True)
class _StoppingMetrics:
    success_probability: float
    expected_attempts_given_success: float
    expected_spend_given_success: float
    expected_spend_until_stop: float


def _tier_options(tier: str) -> Tuple[Tuple[str, float, float], ...]:
    return tuple(
        (stat_name, ranges[tier][0], ranges[tier][1])
        for stat_name, ranges in ABILITY_RANGES.items()
        if tier in ranges
    )


def _sample_ability_line(rng: random.Random, level: int) -> Tuple[str, str, float, float]:
    """Importance-sample one line and return its likelihood weight.

    A 50/50 mixture of the real tier distribution and a uniform distribution
    across currently available tiers ensures rare Legendary/Mystic outcomes are
    represented without discarding the exact published tier probabilities.
    Option and value sampling follow the planner's labeled equal/uniform model.
    """
    published = [value / 100.0 for value in ABILITY_TIER_PROBABILITIES[level]]
    available = [index for index, probability in enumerate(published) if probability > 0.0]
    uniform_probability = 1.0 / len(available)
    proposal = [
        (0.5 * probability + 0.5 * uniform_probability) if index in available else 0.0
        for index, probability in enumerate(published)
    ]
    draw = rng.random()
    cumulative = 0.0
    tier_index = available[-1]
    for index, probability in enumerate(proposal):
        cumulative += probability
        if probability > 0.0 and draw <= cumulative:
            tier_index = index
            break
    tier = ABILITY_TIERS[tier_index]
    options = _tier_options(tier)
    stat_name, minimum, maximum = options[rng.randrange(len(options))]
    value = minimum if maximum <= minimum else rng.uniform(minimum, maximum)
    importance_weight = published[tier_index] / proposal[tier_index]
    return tier, stat_name, value, importance_weight


def _stable_seed(*parts: object) -> int:
    payload = "|".join(repr(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _simulate_level_outcomes(
    base_stats: StatsT,
    target: TargetT,
    current_lines: Sequence[AbilityLine],
    rerolled_slots: Sequence[int],
    level: int,
    minimum_gain_pct: float,
    score_fn: ScoreFunction,
    combine_diminishing: CombineFunction,
    samples: int,
) -> _LevelOutcomeEstimate:
    rerolled_set = set(rerolled_slots)
    kept = [line for line in current_lines if line.slot_number not in rerolled_set]
    current_stats = apply_lines(
        base_stats,
        [(line.stat_name, line.value) for line in current_lines],
        combine_diminishing,
    )
    current_score = score_fn(current_stats, target)
    rng = random.Random(
        _stable_seed(
            level,
            tuple(sorted(rerolled_slots)),
            tuple((line.slot_number, line.tier, line.stat_name, round(line.value, 6)) for line in current_lines),
            round(minimum_gain_pct, 6),
            samples,
        )
    )
    total_weight = 0.0
    total_weight_squared = 0.0
    success_weight = 0.0
    gain_weighted_sum = 0.0
    pattern_counts: Dict[Tuple[str, ...], float] = defaultdict(float)
    pattern_gains: Dict[Tuple[str, ...], float] = defaultdict(float)
    pattern_minimum_gains: Dict[Tuple[str, ...], float] = {}
    pattern_maximum_gains: Dict[Tuple[str, ...], float] = {}
    kept_pairs = [(line.stat_name, line.value) for line in kept]
    ordered_slots = tuple(sorted(rerolled_slots))

    for _ in range(max(1, samples)):
        rolled = [_sample_ability_line(rng, level) for _slot in ordered_slots]
        sample_weight = math.prod(item[3] for item in rolled)
        total_weight += sample_weight
        total_weight_squared += sample_weight * sample_weight
        trial = apply_lines(
            base_stats,
            kept_pairs + [(stat_name, value) for _tier, stat_name, value, _weight in rolled],
            combine_diminishing,
        )
        gain = percentage_gain(score_fn(trial, target), current_score)
        if gain + 1e-12 < minimum_gain_pct:
            continue
        success_weight += sample_weight
        gain_weighted_sum += sample_weight * gain
        signature = tuple(f"{tier} {stat_name}" for tier, stat_name, _value, _weight in rolled)
        pattern_counts[signature] += sample_weight
        pattern_gains[signature] += sample_weight * gain
        pattern_minimum_gains[signature] = min(pattern_minimum_gains.get(signature, gain), gain)
        pattern_maximum_gains[signature] = max(pattern_maximum_gains.get(signature, gain), gain)

    probability = success_weight / total_weight if total_weight > 0 else 0.0
    conditional_gain = gain_weighted_sum / success_weight if success_weight > 0 else 0.0
    effective_samples = (
        total_weight * total_weight / total_weight_squared
        if total_weight_squared > 0 else 1.0
    )
    margin = 1.96 * math.sqrt(
        probability * (1.0 - probability) / max(1.0, effective_samples)
    )

    pattern_estimates: Dict[Tuple[str, ...], _PatternOutcomeEstimate] = {}
    for signature, weighted_count in pattern_counts.items():
        pattern_estimates[signature] = _PatternOutcomeEstimate(
            signature=signature,
            probability=(weighted_count / total_weight if total_weight > 0 else 0.0),
            average_gain_pct=pattern_gains[signature] / weighted_count,
            minimum_gain_pct=pattern_minimum_gains[signature],
            maximum_gain_pct=pattern_maximum_gains[signature],
        )

    # Rank outcomes by their unconditional expected improvement contribution:
    # P(outcome) × E[gain | outcome]. This favors useful, obtainable results.
    ranked_signatures = sorted(
        pattern_counts,
        key=lambda signature: (pattern_gains[signature], pattern_counts[signature], signature),
        reverse=True,
    )
    patterns: List[SuccessfulPattern] = []
    for signature in ranked_signatures[:5]:
        estimate = pattern_estimates[signature]
        weighted_count = pattern_counts[signature]
        patterns.append(
            SuccessfulPattern(
                signature=signature,
                description=" + ".join(signature),
                share_of_successes_pct=(weighted_count / success_weight * 100.0)
                if success_weight > 0 else 0.0,
                probability_per_attempt_pct=estimate.probability * 100.0,
                minimum_gain_pct=estimate.minimum_gain_pct,
                average_gain_pct=estimate.average_gain_pct,
                maximum_gain_pct=estimate.maximum_gain_pct,
            )
        )
    return _LevelOutcomeEstimate(
        success_probability=probability,
        conditional_gain_pct=conditional_gain,
        margin_95_pct=margin,
        patterns=tuple(patterns),
        pattern_estimates=pattern_estimates,
    )


def _accumulate_stopping_metrics(
    probabilities: Sequence[float],
    costs: Sequence[int],
) -> _StoppingMetrics:
    """Combine a changing per-attempt success chance without double-counting.

    Each attempt is independent, but its probability and cost may change after a
    Reconfiguration Level increase. The calculation tracks the probability of
    reaching each attempt, then assigns success to the first successful attempt.
    """
    if len(probabilities) != len(costs):
        raise ValueError("probability and cost schedules must have the same length")
    survival = 1.0
    cumulative_spend = 0.0
    expected_spend_until_stop = 0.0
    success_weighted_attempts = 0.0
    success_weighted_spend = 0.0
    for attempt_index, (probability, cost) in enumerate(zip(probabilities, costs), start=1):
        probability = _clamp(float(probability), 0.0, 1.0)
        cost = max(0, int(cost))
        expected_spend_until_stop += survival * cost
        cumulative_spend += cost
        first_success = survival * probability
        success_weighted_attempts += first_success * attempt_index
        success_weighted_spend += first_success * cumulative_spend
        survival *= 1.0 - probability
    success_probability = 1.0 - survival
    return _StoppingMetrics(
        success_probability=success_probability,
        expected_attempts_given_success=(
            success_weighted_attempts / success_probability
            if success_probability > 0.0 else math.inf
        ),
        expected_spend_given_success=(
            success_weighted_spend / success_probability
            if success_probability > 0.0 else math.inf
        ),
        expected_spend_until_stop=expected_spend_until_stop,
    )

def _attempt_schedule(
    starting_level: int,
    medals_used_toward_next: int,
    usable_medals: int,
    locked_count: int,
) -> Tuple[Tuple[int, int], ...]:
    """Return (level, cost) for every affordable attempt, including level-ups."""
    level = int(_clamp(starting_level, 1, 20))
    progress = max(0, int(medals_used_toward_next))
    budget = max(0, int(usable_medals))
    schedule: List[Tuple[int, int]] = []
    while level < 20:
        required = ABILITY_MEDALS_TO_NEXT.get(level)
        if required is None or progress < required:
            break
        progress -= required
        level += 1
    if locked_count < 0 or locked_count >= len(ABILITY_REROLL_COST[level]):
        return ()
    while True:
        cost = ABILITY_REROLL_COST[level][locked_count]
        if cost <= 0 or budget < cost:
            break
        schedule.append((level, cost))
        budget -= cost
        if level < 20:
            progress += cost
            while level < 20:
                required = ABILITY_MEDALS_TO_NEXT.get(level)
                if required is None or progress < required:
                    break
                progress -= required
                level += 1
    return tuple(schedule)


def estimate_replacement_thresholds(
    base_stats: StatsT,
    current_lines: Sequence[AbilityLine],
    slot_number: int,
    target: TargetT,
    reconfiguration_level: int,
    minimum_gain_pct: float,
    score_fn: ScoreFunction,
    combine_diminishing: CombineFunction,
    *,
    limit: int = 10,
    value_probability_buckets: int = 101,
) -> Tuple[ReplacementThreshold, ...]:
    """Estimate practical one-slot accept thresholds under the documented ranges.

    Tier probabilities are published.  Option types are treated as equally likely
    within a tier and values as uniformly distributed across the shown range.
    """
    level = int(_clamp(reconfiguration_level, 1, 20))
    target_line = next((line for line in current_lines if line.slot_number == slot_number), None)
    if target_line is None:
        return ()
    current_stats = apply_lines(
        base_stats,
        [(line.stat_name, line.value) for line in current_lines],
        combine_diminishing,
    )
    current_score = score_fn(current_stats, target)
    required_score = current_score * (1.0 + minimum_gain_pct / 100.0)
    kept = [line for line in current_lines if line.slot_number != slot_number]
    kept_stats = apply_lines(
        base_stats,
        [(line.stat_name, line.value) for line in kept],
        combine_diminishing,
    )
    results: List[ReplacementThreshold] = []

    for tier_index, tier in enumerate(ABILITY_TIERS):
        tier_probability = ABILITY_TIER_PROBABILITIES[level][tier_index] / 100.0
        if tier_probability <= 0:
            continue
        options = _tier_options(tier)
        option_probability = 1.0 / len(options)
        for stat_name, minimum, maximum in options:
            maximum_trial = copy.deepcopy(kept_stats)
            apply_ability_line(maximum_trial, stat_name, maximum, combine_diminishing)
            maximum_score = score_fn(maximum_trial, target)
            if maximum_score + 1e-12 < required_score:
                continue
            minimum_trial = copy.deepcopy(kept_stats)
            apply_ability_line(minimum_trial, stat_name, minimum, combine_diminishing)
            if score_fn(minimum_trial, target) >= required_score:
                threshold = minimum
            else:
                low, high = minimum, maximum
                for _ in range(48):
                    midpoint = (low + high) / 2.0
                    trial = copy.deepcopy(kept_stats)
                    apply_ability_line(trial, stat_name, midpoint, combine_diminishing)
                    if score_fn(trial, target) >= required_score:
                        high = midpoint
                    else:
                        low = midpoint
                threshold = high
            buckets = max(3, value_probability_buckets)
            qualifying = 0
            for bucket in range(buckets):
                value = minimum + (maximum - minimum) * bucket / (buckets - 1)
                if value + 1e-9 >= threshold:
                    qualifying += 1
            estimated_probability = tier_probability * option_probability * qualifying / buckets
            results.append(
                ReplacementThreshold(
                    tier=tier,
                    stat_name=stat_name,
                    minimum_accepted_value=threshold,
                    maximum_value=maximum,
                    maximum_gain_pct=percentage_gain(maximum_score, current_score),
                    estimated_probability_per_rolled_slot=estimated_probability,
                )
            )
    results.sort(
        key=lambda item: (
            item.estimated_probability_per_rolled_slot,
            item.maximum_gain_pct,
            -ABILITY_TIERS.index(item.tier),
        ),
        reverse=True,
    )
    return tuple(results[: max(1, limit)])


def analyze_reroll_strategies(
    base_stats: StatsT,
    current_lines: Sequence[AbilityLine],
    target: TargetT,
    reconfiguration_level: int,
    medals_available: int,
    medals_reserved: int,
    medals_used_toward_next: int,
    minimum_gain_pct: float,
    maximum_rerolled_slots: int,
    score_fn: ScoreFunction,
    combine_diminishing: CombineFunction,
    *,
    optimization_approach: str = "Balanced",
    samples_per_level: int = 8000,
) -> AbilityActionPlan:
    """Compare one- and multi-slot reroll strategies using the user's budget.

    The three highlighted outcomes are selected once at the starting
    Reconfiguration Level. Their budget probability then tracks those exact same
    outcomes through every later level instead of silently changing what counts
    as the top three after a level-up.
    """
    current_lines = tuple(sorted(current_lines, key=lambda line: line.slot_number))
    usable_medals = max(0, int(medals_available) - max(0, int(medals_reserved)))
    reserved = max(0, int(medals_reserved))
    current_stats = apply_lines(
        base_stats,
        [(line.stat_name, line.value) for line in current_lines],
        combine_diminishing,
    )
    current_score = score_fn(current_stats, target)
    baseline_score = score_fn(base_stats, target)
    current_total_gain = percentage_gain(current_score, baseline_score)
    maximum_rerolled_slots = int(_clamp(maximum_rerolled_slots, 1, max(1, len(current_lines))))
    approach = str(optimization_approach or "Balanced").strip().title()
    if approach not in {"Conservative", "Balanced", "Aggressive"}:
        approach = "Balanced"
    strategies: List[RerollStrategy] = []
    all_slots = tuple(line.slot_number for line in current_lines)
    level_cache: Dict[Tuple[Tuple[int, ...], int], _LevelOutcomeEstimate] = {}

    for rerolled_count in range(1, min(maximum_rerolled_slots, len(current_lines)) + 1):
        for rerolled_slots in itertools.combinations(all_slots, rerolled_count):
            locked_slots = tuple(slot for slot in all_slots if slot not in rerolled_slots)
            locked_count = len(locked_slots)
            starting_level = int(_clamp(reconfiguration_level, 1, 20))
            if locked_count >= len(ABILITY_REROLL_COST[starting_level]):
                continue
            schedule = _attempt_schedule(
                starting_level,
                medals_used_toward_next,
                usable_medals,
                locked_count,
            )
            distinct_levels = sorted({level for level, _cost in schedule} or {starting_level})
            for level in distinct_levels:
                cache_key = (tuple(rerolled_slots), level)
                if cache_key not in level_cache:
                    level_cache[cache_key] = _simulate_level_outcomes(
                        base_stats,
                        target,
                        current_lines,
                        rerolled_slots,
                        level,
                        minimum_gain_pct,
                        score_fn,
                        combine_diminishing,
                        samples_per_level,
                    )

            initial = level_cache[(tuple(rerolled_slots), starting_level)]
            displayed_signatures = tuple(
                pattern.signature for pattern in initial.patterns[:3]
            )
            any_probabilities: List[float] = []
            top_three_probabilities: List[float] = []
            costs: List[int] = []
            success_weighted_gain = 0.0
            any_survival = 1.0
            for level, cost in schedule:
                estimate = level_cache[(tuple(rerolled_slots), level)]
                any_probability = estimate.success_probability
                top_three_probability = min(
                    1.0,
                    sum(
                        estimate.pattern_estimates.get(
                            signature,
                            _PatternOutcomeEstimate(signature, 0.0, 0.0, 0.0, 0.0),
                        ).probability
                        for signature in displayed_signatures
                    ),
                )
                any_probabilities.append(any_probability)
                top_three_probabilities.append(top_three_probability)
                costs.append(cost)
                first_success = any_survival * any_probability
                success_weighted_gain += first_success * estimate.conditional_gain_pct
                any_survival *= 1.0 - any_probability

            any_metrics = _accumulate_stopping_metrics(any_probabilities, costs)
            top_three_metrics = _accumulate_stopping_metrics(top_three_probabilities, costs)
            budget_success = any_metrics.success_probability
            expected_gain_given_success = (
                success_weighted_gain / budget_success if budget_success > 0 else 0.0
            )
            expected_gain_unconditional = success_weighted_gain
            efficiency = (
                expected_gain_unconditional / any_metrics.expected_spend_until_stop * 1000.0
                if any_metrics.expected_spend_until_stop > 0 else 0.0
            )
            initial_top_three_probability = sum(
                initial.pattern_estimates[signature].probability
                for signature in displayed_signatures
                if signature in initial.pattern_estimates
            )
            strategies.append(
                RerollStrategy(
                    rerolled_slots=tuple(rerolled_slots),
                    locked_slots=locked_slots,
                    locked_count=locked_count,
                    first_attempt_cost=ABILITY_REROLL_COST[starting_level][locked_count],
                    attempts_affordable=len(schedule),
                    ending_reconfiguration_level=(schedule[-1][0] if schedule else starting_level),
                    first_attempt_success_probability_pct=initial.success_probability * 100.0,
                    first_attempt_margin_pct=initial.margin_95_pct * 100.0,
                    budget_success_probability_pct=budget_success * 100.0,
                    top_three_first_attempt_probability_pct=initial_top_three_probability * 100.0,
                    top_three_budget_probability_pct=top_three_metrics.success_probability * 100.0,
                    top_three_expected_attempts_given_success=top_three_metrics.expected_attempts_given_success,
                    top_three_expected_spend_given_success=top_three_metrics.expected_spend_given_success,
                    expected_spend_until_stop=any_metrics.expected_spend_until_stop,
                    expected_spend_given_success=any_metrics.expected_spend_given_success,
                    expected_gain_given_success_pct=expected_gain_given_success,
                    expected_gain_per_1000_medals=efficiency,
                    top_success_patterns=initial.patterns,
                    simulation_samples=samples_per_level,
                )
            )

    def balanced_key(item: RerollStrategy):
        return (
            item.expected_gain_per_1000_medals,
            item.budget_success_probability_pct,
            item.expected_gain_given_success_pct,
            tuple(-slot for slot in item.rerolled_slots),
        )

    def conservative_key(item: RerollStrategy):
        return (
            item.top_three_budget_probability_pct,
            item.budget_success_probability_pct,
            item.expected_gain_per_1000_medals,
            -len(item.rerolled_slots),
        )

    def aggressive_key(item: RerollStrategy):
        return (
            item.expected_gain_given_success_pct,
            item.top_three_budget_probability_pct,
            item.expected_gain_per_1000_medals,
            len(item.rerolled_slots),
        )

    key_function = {
        "Conservative": conservative_key,
        "Balanced": balanced_key,
        "Aggressive": aggressive_key,
    }[approach]
    strategies.sort(key=key_function, reverse=True)
    viable = [item for item in strategies if item.attempts_affordable > 0]
    recommended = viable[0] if viable else None
    safest = max(
        viable,
        key=lambda item: (
            item.budget_success_probability_pct,
            item.top_three_budget_probability_pct,
            item.expected_gain_per_1000_medals,
        ),
        default=None,
    )
    highest_upside = max(
        viable,
        key=lambda item: (
            item.expected_gain_given_success_pct,
            item.budget_success_probability_pct,
        ),
        default=None,
    )
    return AbilityActionPlan(
        current_score=current_score,
        current_total_gain_pct=current_total_gain,
        usable_medals=usable_medals,
        reserved_medals=reserved,
        minimum_accepted_gain_pct=minimum_gain_pct,
        recommended_strategy=recommended,
        safest_strategy=safest,
        highest_upside_strategy=highest_upside,
        strategies=tuple(strategies),
    )
