"""Verified labels and conservative metadata for Equipment Potential."""

from __future__ import annotations

SLOT_STATUS_OPTIONS = ("Auto", "Unlocked", "Locked")

EQUIPMENT_SLOTS = (
    "Hat",
    "Top",
    "Bottom",
    "Gloves",
    "Shoes",
    "Cape",
    "Belt",
    "Shoulder",
    "Ring",
    "Necklace",
    "Earrings",
    "Face Accessory",
    "Eye Accessory",
)

POTENTIAL_RARITIES = (
    "Normal",
    "Rare",
    "Epic",
    "Unique",
    "Legendary",
    "Mystic",
)

POTENTIAL_RANK_REQUIREMENTS = {
    "Normal": 42,
    "Rare": 75,
    "Epic": 150,
    "Unique": 333,
    "Legendary": 714,
    "Mystic": 0,
}

POTENTIAL_EARLY_RANK_UP_CHANCE = {
    "Normal": 0.06,
    "Rare": 0.03333,
    "Epic": 0.0167,
    "Unique": 0.006,
    "Legendary": 0.0021,
    "Mystic": 0.0,
}

# Canonical option names accepted by the manual editor and OCR normalizer.
# A subset can be scored exactly by the existing character model. Other lines
# remain visible and are flagged as utility/unmodeled rather than assigned a
# fabricated damage value.
POTENTIAL_OPTIONS = (
    "STR",
    "DEX",
    "INT",
    "LUK",
    "Main Stat",
    "Main Stat %",
    "Attack",
    "Attack %",
    "Max HP",
    "Max HP %",
    "Max MP",
    "Max MP %",
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
    "Accuracy",
    "Evasion",
    "Defense",
    "Damage Taken Decrease",
    "Buff Duration",
    "Companion Duration",
    "Cooldown Reduction",
    "All Skill Levels",
    "Basic Attack Targets",
    "Meso Drop",
    "EXP Gain",
    "MP Recovery Per Sec",
)

PERCENT_OPTIONS = {
    "Main Stat %",
    "Attack %",
    "Max HP %",
    "Max MP %",
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

OCR_ALIASES = {
    "STR": ("STR", "5TR"),
    "DEX": ("DEX", "OEX"),
    "INT": ("INT", "lNT", "1NT", "|NT", "I NT"),
    "LUK": ("LUK", "LUX"),
    "Main Stat": ("Main Stat",),
    "Attack": ("Attack", "Atk"),
    "Max HP": ("Max HP", "Maximum HP", "MaxHP"),
    "Max MP": ("Max MP", "Maximum MP", "MaxMP"),
    "Damage": ("Damage", "Darnage"),
    "Final Damage": ("Final Damage", "Final Darnage"),
    "Critical Rate": ("Critical Rate", "Crit Rate"),
    "Critical Damage": ("Critical Damage", "Crit Damage", "Critical Darnage"),
    "Min Damage Multiplier": ("Min Damage Multiplier", "Minimum Damage Multiplier"),
    "Max Damage Multiplier": ("Max Damage Multiplier", "Maximum Damage Multiplier"),
    "Boss Monster Damage": ("Boss Monster Damage", "Boss Damage"),
    "Normal Monster Damage": ("Normal Monster Damage", "Normal Damage"),
    "Basic Attack Damage": ("Basic Attack Damage",),
    "Skill Damage": ("Skill Damage",),
    "Attack Speed": ("Attack Speed",),
    "Defense Penetration": ("Defense Penetration", "Def Penetration", "Defense Pen"),
    "Accuracy": ("Accuracy",),
    "Evasion": ("Evasion",),
    "Defense": ("Defense", "Defence"),
    "Damage Taken Decrease": ("Damage Taken Decrease",),
    "Buff Duration": ("Buff Duration", "Buff Duration Increase"),
    "Companion Duration": ("Companion Duration", "Companion Summoning Duration Increase"),
    "Cooldown Reduction": ("Cooldown Reduction", "Cooldown", "Skill Cooldown Decrease"),
    "All Skill Levels": ("All Skill Levels", "All Skills"),
    "Basic Attack Targets": ("Basic Attack Targets", "Basic Attack Target Increase"),
    "Meso Drop": ("Meso Drop",),
    "EXP Gain": ("EXP Gain", "Experience Gain"),
    "MP Recovery Per Sec": ("MP Recovery Per Sec", "MP Recovery"),
}

# Publicly documented slot-exclusive lines.
SLOT_SPECIAL_OPTIONS = {
    "Gloves": "Critical Damage",
    "Cape": "Final Damage",
    "Bottom": "Final Damage",
    "Earrings": "Skill Damage",
    "Ring": "All Skill Levels",
    "Necklace": "All Skill Levels",
    "Hat": "Cooldown Reduction",
    "Shoes": "Companion Duration",
    "Belt": "Buff Duration",
    "Top": "Basic Attack Targets",
    "Shoulder": "Defense Penetration",
    "Face Accessory": "Final Damage",
    # Eye Accessory's special option is Main Stat per character level, which is
    # deliberately left unmodeled until the exact character-level interaction
    # is represented in the scoring engine.
}

# High-value (yellow first-line) value for each verified slot-exclusive option.
# Normal and Rare do not provide these special options. Values are sourced from
# the MapleStory Idle RPG Wiki Potential table and are used only for transparent
# opportunity/headroom ranking, not as an invented roll probability table.
SLOT_SPECIAL_HIGH_VALUES = {
    "Hat": {"Epic": 0.5, "Unique": 1.0, "Legendary": 1.5, "Mystic": 2.0},
    "Top": {"Unique": 1.0, "Legendary": 2.0, "Mystic": 3.0},
    "Bottom": {"Epic": 3.0, "Unique": 5.0, "Legendary": 8.0, "Mystic": 12.0},
    "Gloves": {"Epic": 10.0, "Unique": 20.0, "Legendary": 30.0, "Mystic": 50.0},
    "Ring": {"Epic": 5.0, "Unique": 8.0, "Legendary": 12.0, "Mystic": 16.0},
    "Necklace": {"Epic": 5.0, "Unique": 8.0, "Legendary": 12.0, "Mystic": 16.0},
    "Earrings": {"Epic": 8.0, "Unique": 14.0, "Legendary": 21.0, "Mystic": 30.0},
    "Cape": {"Epic": 3.0, "Unique": 5.0, "Legendary": 8.0, "Mystic": 12.0},
    "Shoulder": {"Unique": 8.0, "Legendary": 12.0, "Mystic": 20.0},
    "Belt": {"Epic": 5.0, "Unique": 8.0, "Legendary": 12.0, "Mystic": 20.0},
    "Shoes": {"Epic": 5.0, "Unique": 8.0, "Legendary": 12.0, "Mystic": 20.0},
    "Face Accessory": {"Epic": 3.0, "Unique": 5.0, "Legendary": 8.0, "Mystic": 12.0},
}

# Special options are only valid on their listed equipment slot. This allows
# OCR to reject a confident but impossible label instead of silently accepting
# it as a real roll.
SPECIAL_OPTION_TO_SLOTS = {}
for _slot, _option in SLOT_SPECIAL_OPTIONS.items():
    SPECIAL_OPTION_TO_SLOTS.setdefault(_option, set()).add(_slot)


# Exact values currently documented for equipment-slot-exclusive options.
# The first value at a rank is the high/yellow value and the optional second
# value is the regular value. These are used for OCR validation only; they are
# not treated as option probabilities.
SLOT_SPECIAL_LEGAL_VALUES = {
    "Hat": {"Epic": {0.5}, "Unique": {0.5, 1.0}, "Legendary": {1.0, 1.5}, "Mystic": {1.5, 2.0}},
    "Top": {"Unique": {1.0}, "Legendary": {1.0, 2.0}, "Mystic": {2.0, 3.0}},
    "Bottom": {"Epic": {3.0}, "Unique": {3.0, 5.0}, "Legendary": {5.0, 8.0}, "Mystic": {8.0, 12.0}},
    "Gloves": {"Epic": {10.0}, "Unique": {10.0, 20.0}, "Legendary": {20.0, 30.0}, "Mystic": {30.0, 50.0}},
    "Ring": {"Epic": {5.0}, "Unique": {5.0, 8.0}, "Legendary": {8.0, 12.0}, "Mystic": {12.0, 16.0}},
    "Necklace": {"Epic": {5.0}, "Unique": {5.0, 8.0}, "Legendary": {8.0, 12.0}, "Mystic": {12.0, 16.0}},
    "Earrings": {"Epic": {8.0}, "Unique": {8.0, 14.0}, "Legendary": {14.0, 21.0}, "Mystic": {21.0, 30.0}},
    "Cape": {"Epic": {3.0}, "Unique": {3.0, 5.0}, "Legendary": {5.0, 8.0}, "Mystic": {8.0, 12.0}},
    "Shoulder": {"Unique": {8.0}, "Legendary": {8.0, 12.0}, "Mystic": {12.0, 20.0}},
    "Belt": {"Epic": {5.0}, "Unique": {5.0, 8.0}, "Legendary": {8.0, 12.0}, "Mystic": {12.0, 20.0}},
    "Shoes": {"Epic": {5.0}, "Unique": {5.0, 8.0}, "Legendary": {8.0, 12.0}, "Mystic": {12.0, 20.0}},
    "Face Accessory": {"Epic": {3.0}, "Unique": {3.0, 5.0}, "Legendary": {5.0, 8.0}, "Mystic": {8.0, 12.0}},
}

# Conservative OCR plausibility limits for generic percentage and flat lines.
# The complete internal option-weight/value table is not exposed in a stable
# machine-readable source, so these limits intentionally only reject obvious
# decimal-loss errors rather than claiming every in-range number is legal.
OCR_PERCENT_MAX_BY_RARITY = {
    "Normal": 12.0,
    "Rare": 20.0,
    "Epic": 35.0,
    "Unique": 50.0,
    "Legendary": 80.0,
    "Mystic": 120.0,
}

OCR_FLAT_MAX_BY_RARITY = {
    "Normal": 5_000.0,
    "Rare": 15_000.0,
    "Epic": 40_000.0,
    "Unique": 100_000.0,
    "Legendary": 250_000.0,
    "Mystic": 500_000.0,
}
