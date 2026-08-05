"""Typed result models for the Hero Power and Ability planner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class AbilityLine:
    stat_name: str
    value: float
    locked: bool = False
    tier: str = "Normal"
    slot_number: int = 0


@dataclass(frozen=True)
class TierLineRecommendation:
    slot_number: int
    stat_name: str
    minimum_value: float
    maximum_value: float
    minimum_marginal_gain_pct: float
    maximum_marginal_gain_pct: float
    minimum_cumulative_gain_pct: float
    maximum_cumulative_gain_pct: float


@dataclass(frozen=True)
class TierRecommendation:
    tier: str
    slot_count: int
    probability_pct: float
    available: bool
    minimum_total_gain_pct: float
    maximum_total_gain_pct: float
    lines: Tuple[TierLineRecommendation, ...]


@dataclass(frozen=True)
class ReplacementThreshold:
    """Estimated roll threshold that would improve one current slot."""

    tier: str
    stat_name: str
    minimum_accepted_value: float
    maximum_value: float
    maximum_gain_pct: float
    estimated_probability_per_rolled_slot: float


@dataclass(frozen=True)
class SuccessfulPattern:
    """Practical accepted outcome surfaced by the reroll planner."""

    signature: Tuple[str, ...]
    description: str
    share_of_successes_pct: float
    probability_per_attempt_pct: float
    minimum_gain_pct: float
    average_gain_pct: float
    maximum_gain_pct: float


@dataclass(frozen=True)
class RerollStrategy:
    """Budget-aware estimate for rerolling a specific set of slots."""

    rerolled_slots: Tuple[int, ...]
    locked_slots: Tuple[int, ...]
    locked_count: int
    first_attempt_cost: int
    attempts_affordable: int
    ending_reconfiguration_level: int
    first_attempt_success_probability_pct: float
    first_attempt_margin_pct: float
    budget_success_probability_pct: float
    top_three_first_attempt_probability_pct: float
    top_three_budget_probability_pct: float
    top_three_expected_attempts_given_success: float
    top_three_expected_spend_given_success: float
    expected_spend_until_stop: float
    expected_spend_given_success: float
    expected_gain_given_success_pct: float
    expected_gain_per_1000_medals: float
    top_success_patterns: Tuple[SuccessfulPattern, ...]
    simulation_samples: int


@dataclass(frozen=True)
class AbilityActionPlan:
    """Complete decision plan generated from the current Ability preset."""

    current_score: float
    current_total_gain_pct: float
    usable_medals: int
    reserved_medals: int
    minimum_accepted_gain_pct: float
    recommended_strategy: RerollStrategy | None
    safest_strategy: RerollStrategy | None
    highest_upside_strategy: RerollStrategy | None
    strategies: Tuple[RerollStrategy, ...]
