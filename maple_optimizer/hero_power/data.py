"""Verified public-data tables used by the Hero Power and Ability planner."""

from __future__ import annotations

from typing import Dict, Tuple

ABILITY_TIERS = ("Normal", "Rare", "Epic", "Unique", "Legendary", "Mystic")
ABILITY_STATS = (
    "Main Stat", "Max HP", "Max MP", "Accuracy", "Evasion", "MP Recovery Per Sec",
    "Damage", "Debuff Tolerance", "Min Damage Multiplier", "Max Damage Multiplier",
    "Critical Rate", "Critical Resistance", "Attack Speed", "Damage Taken Decrease",
    "Meso Drop", "EXP Gain", "Defense Penetration", "Boss Monster Damage",
    "Normal Monster Damage",
)

ABILITY_RANGES: Dict[str, Dict[str, Tuple[float, float]]] = {
    "Main Stat": {"Normal": (40, 60), "Rare": (100, 150), "Epic": (200, 300), "Unique": (400, 700), "Legendary": (800, 1200), "Mystic": (1500, 2500)},
    "Max HP": {"Normal": (1200, 1500), "Rare": (1800, 3000), "Epic": (4500, 9000), "Unique": (15000, 30000), "Legendary": (35000, 65000), "Mystic": (70000, 115000)},
    "Max MP": {"Normal": (30, 40), "Rare": (50, 70), "Epic": (100, 150), "Unique": (200, 400), "Legendary": (500, 800), "Mystic": (900, 1500)},
    "Accuracy": {"Normal": (2, 3), "Rare": (4, 5), "Epic": (6, 8), "Unique": (10, 12), "Legendary": (14, 16), "Mystic": (20, 25)},
    "Evasion": {"Normal": (2, 3), "Rare": (4, 5), "Epic": (6, 8), "Unique": (10, 12), "Legendary": (14, 16), "Mystic": (20, 25)},
    "MP Recovery Per Sec": {"Normal": (3, 5), "Rare": (6, 10), "Epic": (11, 20), "Unique": (21, 30), "Legendary": (40, 60), "Mystic": (80, 150)},
    "Damage": {"Rare": (3, 5), "Epic": (7, 10), "Unique": (12, 15), "Legendary": (18, 25), "Mystic": (28, 40)},
    "Debuff Tolerance": {"Rare": (4, 5), "Epic": (6, 8), "Unique": (10, 12), "Legendary": (14, 16), "Mystic": (18, 25)},
    "Min Damage Multiplier": {"Epic": (7, 10), "Unique": (12, 15), "Legendary": (18, 25), "Mystic": (28, 40)},
    "Max Damage Multiplier": {"Epic": (7, 10), "Unique": (12, 15), "Legendary": (18, 25), "Mystic": (28, 40)},
    "Critical Rate": {"Epic": (3, 6), "Unique": (7, 9), "Legendary": (10, 14), "Mystic": (15, 20)},
    "Critical Resistance": {"Epic": (4.5, 9), "Unique": (10.5, 13.5), "Legendary": (15, 21), "Mystic": (22.5, 30)},
    "Attack Speed": {"Unique": (7, 9), "Legendary": (10, 14), "Mystic": (15, 20)},
    "Damage Taken Decrease": {"Unique": (2, 3), "Legendary": (4, 6), "Mystic": (7, 10)},
    "Meso Drop": {"Legendary": (5, 8), "Mystic": (9, 15)},
    "EXP Gain": {"Legendary": (5, 8), "Mystic": (9, 15)},
    "Defense Penetration": {"Legendary": (8, 12), "Mystic": (14, 20)},
    "Boss Monster Damage": {"Legendary": (18, 25), "Mystic": (28, 40)},
    "Normal Monster Damage": {"Legendary": (18, 25), "Mystic": (28, 40)},
}

ABILITY_TIER_PROBABILITIES = {
    1: (60, 35, 4.7, .3, 0, 0), 2: (59.3, 35, 5, .7, 0, 0),
    3: (50, 35, 13.5, 1.5, 0, 0), 4: (40, 35, 22.5, 2.5, 0, 0),
    5: (30, 32, 34.3, 3.5, .2, 0), 6: (25, 32, 39, 3.6, .4, 0),
    7: (25, 32, 38.5, 3.7, .8, 0), 8: (25, 32, 38.33, 3.65, 1, .02),
    9: (25, 32, 38.28, 3.6, 1.09, .03), 10: (25, 32, 38.23, 3.55, 1.18, .04),
    11: (25, 32, 38.17, 3.5, 1.27, .06), 12: (25, 32, 38.11, 3.45, 1.36, .08),
    13: (25, 32, 38.05, 3.4, 1.45, .10), 14: (25, 32, 37.99, 3.35, 1.54, .12),
    15: (25, 32, 37.93, 3.3, 1.63, .14), 16: (25, 32, 37.87, 3.25, 1.72, .16),
    17: (25, 32, 37.81, 3.2, 1.81, .18), 18: (25, 32, 37.75, 3.15, 1.9, .20),
    19: (25, 32, 37.69, 3.1, 1.99, .22), 20: (25, 32, 37.63, 3.05, 2.08, .24),
}

ABILITY_REROLL_COST = {
    1: (20, 30, 40, 50, 60, 70), 2: (30, 45, 60, 75, 90, 105),
    3: (40, 60, 80, 100, 120, 140), 4: (50, 75, 100, 125, 150, 175),
    5: (55, 83, 110, 138, 165, 193), 6: (60, 90, 120, 150, 180, 210),
    7: (65, 98, 130, 163, 195, 228), 8: (68, 102, 136, 170, 204, 238),
    9: (71, 107, 142, 178, 213, 249), 10: (74, 111, 148, 185, 222, 259),
    11: (77, 116, 154, 193, 231, 270), 12: (80, 120, 160, 200, 240, 280),
    13: (83, 125, 166, 208, 249, 291), 14: (86, 129, 172, 215, 258, 301),
    15: (89, 134, 178, 223, 267, 312), 16: (91, 137, 182, 228, 273, 319),
    17: (93, 140, 186, 233, 279, 326), 18: (95, 143, 190, 238, 285, 333),
    19: (97, 146, 194, 243, 291, 340), 20: (99, 149, 198, 248, 297, 347),
}

ABILITY_MEDALS_TO_NEXT = {
    1: 5000, 2: 12000, 3: 18000, 4: 25200, 5: 35300,
    6: 49400, 7: 69200, 8: 96900, 9: 135700, 10: 176400,
    11: 229300, 12: 298100, 13: 387500, 14: 503800, 15: 604600,
    16: 725500, 17: 870600, 18: 1044700, 19: 1253600,
}

# The official/public tables expose tier probabilities and value ranges, but no
# verified per-option or per-value weights were available during implementation.
# The action planner therefore labels its estimates and uses equal option weights
# within a tier plus a uniform value distribution across the displayed range.
ABILITY_ESTIMATE_MODEL = (
    "Published tier probability; estimated equal option chance within each tier; "
    "estimated uniform value distribution across the displayed range."
)

HERO_POWER_STATS = ("Attack", "Max HP", "Defense", "Main Stat", "Damage", "Accuracy")
