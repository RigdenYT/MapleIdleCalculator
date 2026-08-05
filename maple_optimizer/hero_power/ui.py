"""Tkinter presentation layer for the Hero Power and Ability planner."""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, List

from .data import (
    ABILITY_ESTIMATE_MODEL,
    ABILITY_MEDALS_TO_NEXT,
    ABILITY_RANGES,
    ABILITY_REROLL_COST,
    ABILITY_STATS,
    ABILITY_TIER_PROBABILITIES,
    ABILITY_TIERS,
    HERO_POWER_STATS,
)
from .engine import (
    analyze_reroll_strategies,
    apply_ability_line,
    apply_flat_main_stat,
    current_line_contributions,
    estimate_replacement_thresholds,
    optimize_all_tiers,
    percentage_gain,
    remove_ability_lines,
)
from .models import AbilityLine


def initialize_state(app) -> None:
    app.hero_stage_var = tk.StringVar(value="4")
    app.hero_tokens_var = tk.StringVar(value="217")
    app.ability_reconfig_var = tk.StringVar(value="2")
    app.ability_medals_var = tk.StringVar(value="23495")
    app.ability_target_tier_var = tk.StringVar(value="Legendary")
    app.ability_slots_var = tk.StringVar(value="3")
    app.ability_reserved_medals_var = tk.StringVar(value="0")
    app.ability_level_progress_var = tk.StringVar(value="0")
    app.ability_min_gain_var = tk.StringVar(value="0.25")
    app.ability_approach_var = tk.StringVar(value="Balanced")
    app.ability_max_reroll_slots_var = tk.StringVar(value="2")
    app.ability_included_var = tk.BooleanVar(value=True)
    hero_defaults = {
        "Attack": ("2", "785", "815", "296"),
        "Max HP": ("0", "14500", "15100", "280"),
        "Defense": ("0", "725", "755", "280"),
        "Main Stat": ("0", "350", "360", "280"),
        "Damage": ("6", "7.8", "8.1", "331"),
        "Accuracy": ("0", "0", "1", "600"),
    }
    app.hero_upgrade_vars = {
        name: {
            key: tk.StringVar(value=value)
            for key, value in zip(("level", "current", "next", "cost"), values)
        }
        for name, values in hero_defaults.items()
    }
    app.ability_line_vars = []
    for index in range(7):
        app.ability_line_vars.append(
            {
                "enabled": tk.BooleanVar(value=index < 3),
                "tier": tk.StringVar(value="Unique"),
                "stat": tk.StringVar(value="Attack Speed" if index < 2 else "Main Stat"),
                "value": tk.StringVar(value=("8.8", "7.2", "400", "0", "0", "0", "0")[index]),
                "locked": tk.BooleanVar(value=index < 3),
            }
        )
    app.hero_summary_var = tk.StringVar(
        value="Enter the current and next values shown in Hero Power, then analyze."
    )
    app.ability_summary_var = tk.StringVar(
        value="Recommendations will be generated for every Ability tier."
    )
    app.hero_plan_action_var = tk.StringVar(value="Press Analyze")
    app.hero_plan_lock_var = tk.StringVar(value="Enter your current Ability lines first.")
    app.hero_plan_chance_var = tk.StringVar(value="—")
    app.hero_plan_chance_caption_var = tk.StringVar(
        value="Chance of one of the top three practical outcomes"
    )
    app.hero_plan_budget_var = tk.StringVar(value="—")
    app.hero_plan_budget_caption_var = tk.StringVar(value="Cost and attempts")
    app.hero_plan_slots_var = tk.StringVar(value="No action plan calculated yet.")
    app.hero_plan_note_var = tk.StringVar(
        value="Probability is estimated from published tier rates and labeled option/value assumptions."
    )
    app.hero_details_expanded = False
    app.hero_next_upgrade_var = tk.StringVar(value="Analyze to rank Hero Power upgrades.")
    app.hero_option_vars = [
        {
            "title": tk.StringVar(value=f"Option {index}"),
            "detail": tk.StringVar(value="—"),
        }
        for index in range(1, 4)
    ]



APPROACH_MINIMUM_GAINS = {
    "Conservative": "0.10",
    "Balanced": "0.25",
    "Aggressive": "0.75",
}


def _apply_approach_preset(app) -> None:
    value = APPROACH_MINIMUM_GAINS.get(str(app.ability_approach_var.get()))
    if value is not None:
        app.ability_min_gain_var.set(value)


def build_tab(app, colors: Dict[str, str]) -> None:
    tab = app.hero_power_tab
    tab.columnconfigure(0, weight=1)
    tab.rowconfigure(0, weight=1)
    canvas = tk.Canvas(tab, background=colors["bg"], highlightthickness=0)
    scroll = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    body = tk.Frame(canvas, background=colors["bg"])
    window = canvas.create_window(0, 0, window=body, anchor="nw")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
    body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    app.hero_power_canvas = canvas

    title = tk.Frame(body, background="#26384d", padx=18, pady=13)
    title.pack(fill="x", padx=18, pady=(18, 10))
    tk.Label(
        title,
        text="HERO POWER & ABILITY",
        background="#26384d",
        foreground="#d7ff45",
        font=("TkDefaultFont", 17, "bold"),
    ).pack(side="left")
    tk.Label(
        title,
        text="Tier-by-tier upgrade and reroll planning for the active build",
        background="#26384d",
        foreground="#ffffff",
        font=("TkDefaultFont", 10),
    ).pack(side="left", padx=16)
    ttk.Button(
        title,
        text="Analyze",
        style="Accent.TButton",
        command=app.analyze_hero_power,
    ).pack(side="right")

    baseline_outer, baseline = app._make_maple_section(body, "Shared Character Baseline")
    baseline_outer.pack(fill="x", padx=18, pady=8)
    shared = (
        ("Attack", "attack"),
        ("Main Stat", "total_main_stat"),
        ("Damage %", "damage"),
        ("Critical Rate %", "crit_rate"),
        ("Critical Damage %", "crit_damage"),
        ("Attack Speed %", "attack_speed"),
        ("Boss Damage %", "boss_damage"),
        ("Normal Damage %", "normal_damage"),
        ("Defense Pen. %", "defense_pen"),
        ("Accuracy", "accuracy"),
    )
    for index, (label, key) in enumerate(shared):
        row, column = divmod(index, 5)
        cell = tk.Frame(baseline, background="#ffffff")
        cell.grid(row=row, column=column, sticky="ew", padx=5, pady=4)
        baseline.columnconfigure(column, weight=1)
        ttk.Label(cell, text=label, style="WhitePanel.TLabel").pack(anchor="w")
        ttk.Entry(cell, textvariable=app.stat_vars[key], width=14).pack(fill="x")
    ttk.Checkbutton(
        baseline,
        text="Current Ability lines are already included in these Character Stats",
        variable=app.ability_included_var,
    ).grid(row=2, column=0, columnspan=5, sticky="w", padx=5, pady=(7, 2))

    columns = tk.Frame(body, background=colors["bg"])
    columns.pack(fill="both", expand=True, padx=18, pady=8)
    columns.columnconfigure(0, weight=1)
    columns.columnconfigure(1, weight=1)
    left_outer, left = app._make_maple_section(columns, "Hero Power Enhancements")
    right_outer, right = app._make_maple_section(columns, "Ability Preset")
    left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
    right_outer.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

    top = tk.Frame(left, background="#ffffff")
    top.grid(row=0, column=0, columnspan=6, sticky="ew", pady=(0, 8))
    ttk.Label(top, text="Stage", style="WhitePanel.TLabel").pack(side="left")
    ttk.Entry(top, textvariable=app.hero_stage_var, width=6).pack(side="left", padx=(5, 16))
    ttk.Label(top, text="Hero Tokens", style="WhitePanel.TLabel").pack(side="left")
    ttk.Entry(top, textvariable=app.hero_tokens_var, width=12).pack(side="left", padx=5)
    for column, text in enumerate(("Stat", "Lv.", "Current", "Next", "Cost", "Gain / token")):
        ttk.Label(left, text=text, style="WhitePanel.TLabel").grid(
            row=1, column=column, sticky="w", padx=4, pady=3
        )
    app.hero_gain_labels = {}
    for row_index, name in enumerate(HERO_POWER_STATS, start=2):
        values = app.hero_upgrade_vars[name]
        ttk.Label(left, text=name, style="WhitePanel.TLabel").grid(
            row=row_index, column=0, sticky="w", padx=4, pady=3
        )
        ttk.Entry(left, textvariable=values["level"], width=5).grid(row=row_index, column=1, padx=3)
        ttk.Entry(left, textvariable=values["current"], width=9).grid(row=row_index, column=2, padx=3)
        ttk.Entry(left, textvariable=values["next"], width=9).grid(row=row_index, column=3, padx=3)
        ttk.Entry(left, textvariable=values["cost"], width=8).grid(row=row_index, column=4, padx=3)
        label = ttk.Label(left, text="—", style="WhitePanel.TLabel")
        label.grid(row=row_index, column=5, sticky="w", padx=4)
        app.hero_gain_labels[name] = label
    ttk.Label(
        left,
        textvariable=app.hero_summary_var,
        style="WhitePanel.TLabel",
        wraplength=520,
        justify="left",
    ).grid(row=8, column=0, columnspan=6, sticky="ew", padx=4, pady=(10, 4))

    meta = tk.Frame(right, background="#ffffff")
    meta.grid(row=0, column=0, columnspan=6, sticky="ew", pady=(0, 8))
    ttk.Label(meta, text="Reconfig. level", style="WhitePanel.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Entry(meta, textvariable=app.ability_reconfig_var, width=5).grid(row=0, column=1, padx=(5, 12))
    ttk.Label(meta, text="Medals", style="WhitePanel.TLabel").grid(row=0, column=2, sticky="w")
    ttk.Entry(meta, textvariable=app.ability_medals_var, width=10).grid(row=0, column=3, padx=(5, 12))
    ttk.Label(meta, text="Unlocked slots", style="WhitePanel.TLabel").grid(row=0, column=4, sticky="w")
    ttk.Entry(meta, textvariable=app.ability_slots_var, width=5).grid(row=0, column=5, padx=5)
    ttk.Label(meta, text="Focused reroll tier", style="WhitePanel.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
    ttk.Combobox(
        meta,
        textvariable=app.ability_target_tier_var,
        values=ABILITY_TIERS,
        state="readonly",
        width=11,
    ).grid(row=1, column=2, columnspan=2, sticky="w", pady=(6, 0))
    ttk.Label(
        meta,
        text="The ideal tier report remains available below the action plan.",
        style="WhitePanel.TLabel",
    ).grid(row=1, column=4, columnspan=2, sticky="w", padx=(8, 0), pady=(6, 0))
    ttk.Label(meta, text="Reserve medals", style="WhitePanel.TLabel").grid(
        row=2, column=0, sticky="w", pady=(7, 0)
    )
    ttk.Entry(meta, textvariable=app.ability_reserved_medals_var, width=9).grid(
        row=2, column=1, sticky="w", padx=(5, 12), pady=(7, 0)
    )
    ttk.Label(meta, text="Used toward next Lv.", style="WhitePanel.TLabel").grid(
        row=2, column=2, sticky="w", pady=(7, 0)
    )
    ttk.Entry(meta, textvariable=app.ability_level_progress_var, width=9).grid(
        row=2, column=3, sticky="w", padx=(5, 12), pady=(7, 0)
    )
    ttk.Label(meta, text="Minimum gain %", style="WhitePanel.TLabel").grid(
        row=2, column=4, sticky="w", pady=(7, 0)
    )
    ttk.Entry(meta, textvariable=app.ability_min_gain_var, width=7).grid(
        row=2, column=5, sticky="w", padx=5, pady=(7, 0)
    )
    ttk.Label(meta, text="Approach", style="WhitePanel.TLabel").grid(
        row=3, column=0, sticky="w", pady=(7, 0)
    )
    approach_box = ttk.Combobox(
        meta,
        textvariable=app.ability_approach_var,
        values=("Conservative", "Balanced", "Aggressive"),
        state="readonly",
        width=13,
    )
    approach_box.grid(row=3, column=1, sticky="w", padx=(5, 12), pady=(7, 0))
    approach_box.bind("<<ComboboxSelected>>", lambda _event: _apply_approach_preset(app))
    ttk.Label(meta, text="Compare up to", style="WhitePanel.TLabel").grid(
        row=3, column=2, sticky="w", pady=(7, 0)
    )
    ttk.Combobox(
        meta,
        textvariable=app.ability_max_reroll_slots_var,
        values=("1", "2", "3"),
        state="readonly",
        width=4,
    ).grid(row=3, column=3, sticky="w", padx=(5, 12), pady=(7, 0))
    ttk.Label(
        meta,
        text="slots at once. Conservative favors success chance; Aggressive favors larger accepted gains.",
        style="WhitePanel.TLabel",
        wraplength=310,
        justify="left",
    ).grid(row=3, column=4, columnspan=2, sticky="w", padx=(6, 0), pady=(7, 0))

    for column, text in enumerate(("Use", "Tier", "Option", "Value", "Lock", "Contribution")):
        ttk.Label(right, text=text, style="WhitePanel.TLabel").grid(
            row=4, column=column, sticky="w", padx=3, pady=3
        )
    app.ability_gain_labels = []
    for index, row in enumerate(app.ability_line_vars, start=1):
        ttk.Checkbutton(right, variable=row["enabled"]).grid(row=index + 4, column=0)
        ttk.Combobox(
            right,
            textvariable=row["tier"],
            values=ABILITY_TIERS,
            state="readonly",
            width=10,
        ).grid(row=index + 4, column=1, padx=2, pady=2)
        ttk.Combobox(
            right,
            textvariable=row["stat"],
            values=ABILITY_STATS,
            state="readonly",
            width=24,
        ).grid(row=index + 4, column=2, padx=2, pady=2)
        ttk.Entry(right, textvariable=row["value"], width=9).grid(row=index + 4, column=3, padx=2, pady=2)
        ttk.Checkbutton(right, variable=row["locked"]).grid(row=index + 4, column=4)
        label = ttk.Label(right, text="—", style="WhitePanel.TLabel")
        label.grid(row=index + 4, column=5, sticky="w", padx=3)
        app.ability_gain_labels.append(label)
    ttk.Label(
        right,
        textvariable=app.ability_summary_var,
        style="WhitePanel.TLabel",
        wraplength=620,
        justify="left",
    ).grid(row=12, column=0, columnspan=6, sticky="ew", padx=4, pady=(10, 4))

    results_outer, results = app._make_maple_section(body, "Recommended Action")
    results_outer.pack(fill="both", expand=True, padx=18, pady=(8, 20))
    results.columnconfigure(0, weight=1)

    summary = tk.Frame(results, background="#ffffff")
    summary.grid(row=0, column=0, sticky="ew")
    for column in range(3):
        summary.columnconfigure(column, weight=1, uniform="hero-plan-card")

    def metric_card(column, heading, value_var, caption_var, background, accent):
        card = tk.Frame(
            summary,
            background=background,
            highlightbackground=accent,
            highlightthickness=2,
            padx=14,
            pady=12,
        )
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0))
        tk.Label(
            card,
            text=heading.upper(),
            background=background,
            foreground="#52677b",
            font=("TkDefaultFont", 8, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            textvariable=value_var,
            background=background,
            foreground="#18324a",
            font=("TkDefaultFont", 17, "bold"),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", pady=(5, 3))
        tk.Label(
            card,
            textvariable=caption_var,
            background=background,
            foreground="#52677b",
            font=("TkDefaultFont", 9),
            wraplength=270,
            justify="left",
        ).pack(anchor="w")
        return card

    metric_card(
        0,
        "Do this next",
        app.hero_plan_action_var,
        app.hero_plan_lock_var,
        "#eef6ff",
        "#6fa9dc",
    )
    metric_card(
        1,
        "Estimated top 3 chance",
        app.hero_plan_chance_var,
        app.hero_plan_chance_caption_var,
        "#f4f9df",
        "#9fbd36",
    )
    metric_card(
        2,
        "Medal plan",
        app.hero_plan_budget_var,
        app.hero_plan_budget_caption_var,
        "#fff5e6",
        "#d8983a",
    )

    slot_strip = tk.Frame(results, background="#26384d", padx=14, pady=10)
    slot_strip.grid(row=1, column=0, sticky="ew", pady=(12, 10))
    tk.Label(
        slot_strip,
        text="SLOT PLAN",
        background="#26384d",
        foreground="#d7ff45",
        font=("TkDefaultFont", 9, "bold"),
    ).pack(side="left")
    tk.Label(
        slot_strip,
        textvariable=app.hero_plan_slots_var,
        background="#26384d",
        foreground="#ffffff",
        font=("TkDefaultFont", 10, "bold"),
        wraplength=860,
        justify="left",
    ).pack(side="left", padx=(16, 0))

    options_header = tk.Frame(results, background="#ffffff")
    options_header.grid(row=2, column=0, sticky="ew", pady=(2, 5))
    tk.Label(
        options_header,
        text="STOP REROLLING IF YOU GET ANY OF THESE",
        background="#ffffff",
        foreground="#26384d",
        font=("TkDefaultFont", 11, "bold"),
    ).pack(side="left")
    tk.Label(
        options_header,
        text="The displayed percentage tracks these exact outcomes across your Medal budget",
        background="#ffffff",
        foreground="#66798c",
        font=("TkDefaultFont", 9),
    ).pack(side="left", padx=(12, 0))

    options = tk.Frame(results, background="#ffffff")
    options.grid(row=3, column=0, sticky="ew")
    options.columnconfigure(1, weight=1)
    app.hero_option_rows = []
    for index, variables in enumerate(app.hero_option_vars, start=1):
        rank = tk.Label(
            options,
            text=str(index),
            background="#26384d",
            foreground="#d7ff45",
            font=("TkDefaultFont", 11, "bold"),
            width=3,
            pady=9,
        )
        rank.grid(row=index - 1, column=0, sticky="ns", pady=3)
        row = tk.Frame(
            options,
            background="#f7f9fb",
            highlightbackground="#d5dee7",
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        row.grid(row=index - 1, column=1, sticky="ew", padx=(7, 0), pady=3)
        tk.Label(
            row,
            textvariable=variables["title"],
            background="#f7f9fb",
            foreground="#18324a",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            row,
            textvariable=variables["detail"],
            background="#f7f9fb",
            foreground="#5f7285",
            font=("TkDefaultFont", 9),
            wraplength=880,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
        app.hero_option_rows.append(row)

    footer = tk.Frame(results, background="#ffffff")
    footer.grid(row=4, column=0, sticky="ew", pady=(12, 2))
    footer.columnconfigure(0, weight=1)
    note = tk.Label(
        footer,
        textvariable=app.hero_plan_note_var,
        background="#ffffff",
        foreground="#5f7285",
        font=("TkDefaultFont", 9),
        wraplength=760,
        justify="left",
    )
    note.grid(row=0, column=0, sticky="w")
    app.hero_details_button = ttk.Button(
        footer,
        text="Show detailed analysis",
        command=lambda: _toggle_details(app),
    )
    app.hero_details_button.grid(row=0, column=1, sticky="e", padx=(12, 0))

    hero_next = tk.Frame(
        results,
        background="#f7f9fb",
        highlightbackground="#d5dee7",
        highlightthickness=1,
        padx=12,
        pady=9,
    )
    hero_next.grid(row=5, column=0, sticky="ew", pady=(8, 0))
    tk.Label(
        hero_next,
        text="HERO POWER NEXT",
        background="#f7f9fb",
        foreground="#52677b",
        font=("TkDefaultFont", 8, "bold"),
    ).pack(side="left")
    tk.Label(
        hero_next,
        textvariable=app.hero_next_upgrade_var,
        background="#f7f9fb",
        foreground="#18324a",
        font=("TkDefaultFont", 10, "bold"),
        wraplength=800,
        justify="left",
    ).pack(side="left", padx=(14, 0))

    app.hero_details_frame = tk.Frame(results, background="#ffffff")
    app.hero_details_frame.grid(row=6, column=0, sticky="nsew", pady=(12, 0))
    app.hero_details_frame.grid_remove()
    app.hero_details_frame.columnconfigure(0, weight=1)
    app.hero_details_frame.rowconfigure(0, weight=1)
    result_scroll = ttk.Scrollbar(app.hero_details_frame, orient="vertical")
    app.hero_result_text = tk.Text(
        app.hero_details_frame,
        height=24,
        wrap="word",
        background="#f8fafc",
        foreground=colors["text"],
        relief="solid",
        borderwidth=1,
        padx=12,
        pady=10,
        yscrollcommand=result_scroll.set,
    )
    result_scroll.configure(command=app.hero_result_text.yview)
    app.hero_result_text.grid(row=0, column=0, sticky="nsew")
    result_scroll.grid(row=0, column=1, sticky="ns")
    app.hero_result_text.insert(
        "1.0",
        "Detailed calculations will appear here after Analyze.",
    )
    app.hero_result_text.configure(state="disabled")



def _toggle_details(app) -> None:
    if app.hero_details_frame.winfo_ismapped():
        app.hero_details_frame.grid_remove()
        app.hero_details_button.configure(text="Show detailed analysis")
        app.hero_details_expanded = False
    else:
        app.hero_details_frame.grid()
        app.hero_details_button.configure(text="Hide detailed analysis")
        app.hero_details_expanded = True
        app.hero_result_text.see("1.0")



def collect_current_lines(app, parse_number: Callable[..., float]) -> List[AbilityLine]:
    lines: List[AbilityLine] = []
    for index, row in enumerate(app.ability_line_vars, start=1):
        if not bool(row["enabled"].get()):
            continue
        value = parse_number(row["value"].get(), field_name=f"Ability slot {index}")
        lines.append(
            AbilityLine(
                stat_name=str(row["stat"].get()),
                value=float(value),
                locked=bool(row["locked"].get()),
                tier=str(row["tier"].get()),
                slot_number=index,
            )
        )
    return lines


def collect_state(app) -> Dict[str, object]:
    return {
        "stage": app.hero_stage_var.get(),
        "tokens": app.hero_tokens_var.get(),
        "reconfig": app.ability_reconfig_var.get(),
        "medals": app.ability_medals_var.get(),
        "target_tier": app.ability_target_tier_var.get(),
        "unlocked_slots": app.ability_slots_var.get(),
        "reserved_medals": app.ability_reserved_medals_var.get(),
        "level_progress": app.ability_level_progress_var.get(),
        "minimum_gain": app.ability_min_gain_var.get(),
        "approach": app.ability_approach_var.get(),
        "max_reroll_slots": app.ability_max_reroll_slots_var.get(),
        "details_expanded": bool(getattr(app, "hero_details_expanded", False)),
        "included": bool(app.ability_included_var.get()),
        "upgrades": {
            name: {key: variable.get() for key, variable in row.items()}
            for name, row in app.hero_upgrade_vars.items()
        },
        "lines": [
            {
                key: (variable.get() if hasattr(variable, "get") else variable)
                for key, variable in row.items()
            }
            for row in app.ability_line_vars
        ],
    }


def apply_state(app, data: object) -> None:
    if not isinstance(data, dict):
        return
    variable_map = (
        ("stage", app.hero_stage_var),
        ("tokens", app.hero_tokens_var),
        ("reconfig", app.ability_reconfig_var),
        ("medals", app.ability_medals_var),
        ("target_tier", app.ability_target_tier_var),
        ("unlocked_slots", app.ability_slots_var),
        ("reserved_medals", app.ability_reserved_medals_var),
        ("level_progress", app.ability_level_progress_var),
        ("minimum_gain", app.ability_min_gain_var),
        ("approach", app.ability_approach_var),
        ("max_reroll_slots", app.ability_max_reroll_slots_var),
    )
    for key, variable in variable_map:
        if key in data:
            variable.set(str(data[key]))
    if "included" in data:
        app.ability_included_var.set(bool(data["included"]))
    if "details_expanded" in data:
        app.hero_details_expanded = bool(data["details_expanded"])
        if hasattr(app, "hero_details_frame"):
            if app.hero_details_expanded:
                app.hero_details_frame.grid()
                app.hero_details_button.configure(text="Hide detailed analysis")
            else:
                app.hero_details_frame.grid_remove()
                app.hero_details_button.configure(text="Show detailed analysis")
    upgrades = data.get("upgrades", {})
    if isinstance(upgrades, dict):
        for name, row in upgrades.items():
            if name in app.hero_upgrade_vars and isinstance(row, dict):
                for key, value in row.items():
                    if key in app.hero_upgrade_vars[name]:
                        app.hero_upgrade_vars[name][key].set(str(value))
    lines = data.get("lines", [])
    if isinstance(lines, list):
        for destination, source in zip(app.ability_line_vars, lines):
            if isinstance(source, dict):
                for key, value in source.items():
                    if key in destination and hasattr(destination[key], "set"):
                        destination[key].set(value)


def _format_value_range(minimum: float, maximum: float) -> str:
    if minimum == maximum:
        return f"{minimum:g}"
    return f"{minimum:g}–{maximum:g}"


def _format_slots(slots: tuple[int, ...]) -> str:
    return ", ".join(str(slot) for slot in slots) if slots else "none"


def _format_strategy_line(strategy) -> str:
    return (
        f"reroll slot(s) {_format_slots(strategy.rerolled_slots)}; "
        f"lock {_format_slots(strategy.locked_slots)}; cost {strategy.first_attempt_cost:,} initially; "
        f"{strategy.attempts_affordable:,} attempt(s); "
        f"{strategy.budget_success_probability_pct:.1f}% chance within budget; "
        f"{strategy.expected_gain_per_1000_medals:.4f} expected accepted gain per 1,000 medals"
    )


def _validate_ability_inputs(
    app,
    current: List[AbilityLine],
    unlocked_slots: int,
    reconfiguration_level: int,
    medals: int,
    reserved_medals: int,
    level_progress: int,
) -> None:
    if reserved_medals > medals:
        raise ValueError("Reserved Medals cannot exceed the total Medals available.")
    if reconfiguration_level < 20:
        required = ABILITY_MEDALS_TO_NEXT[reconfiguration_level]
        if level_progress >= required:
            raise ValueError(
                f"Medals used toward next level must be below {required:,} at "
                f"Reconfiguration Level {reconfiguration_level}; the game would already have advanced the level."
            )
    elif level_progress > 0:
        raise ValueError("Reconfiguration Level 20 has no next-level Medal progress.")
    if not current:
        raise ValueError("Enable and enter every currently unlocked Ability slot before analyzing.")
    if len(current) != unlocked_slots:
        raise ValueError(
            f"Unlocked slots is set to {unlocked_slots}, but {len(current)} enabled lines were entered. "
            "Enter one current line for every unlocked slot so the reroll recommendation is valid."
        )
    disabled_locked = [
        index
        for index, row in enumerate(app.ability_line_vars, start=1)
        if not bool(row["enabled"].get()) and bool(row["locked"].get())
    ]
    if disabled_locked:
        raise ValueError(
            "Disabled Ability slots cannot be marked locked. Clear Lock for slot(s): "
            + ", ".join(str(slot) for slot in disabled_locked)
        )
    for line in current:
        ranges = ABILITY_RANGES.get(line.stat_name, {})
        if line.tier not in ranges:
            raise ValueError(
                f"Slot {line.slot_number}: {line.stat_name} is not available at {line.tier} tier."
            )
        minimum, maximum = ranges[line.tier]
        if line.value < minimum - 1e-9 or line.value > maximum + 1e-9:
            raise ValueError(
                f"Slot {line.slot_number}: {line.tier} {line.stat_name} must be between "
                f"{minimum:g} and {maximum:g}; entered {line.value:g}."
            )
        tier_index = ABILITY_TIERS.index(line.tier)
        if ABILITY_TIER_PROBABILITIES[reconfiguration_level][tier_index] <= 0.0:
            raise ValueError(
                f"Slot {line.slot_number}: {line.tier} cannot occur at Reconfiguration Level "
                f"{reconfiguration_level}. Check the entered level or tier."
            )


def analyze(
    app,
    *,
    parse_number: Callable[..., float],
    clamp: Callable[[float, float, float], float],
    score_fn: Callable[[object, object], float],
    combine_diminishing: Callable[[float, List[float], float], float],
) -> None:
    try:
        profile = app.collect_profile()
        current = collect_current_lines(app, parse_number)
        current_pairs = [(line.stat_name, line.value) for line in current]
        base = (
            remove_ability_lines(profile.stats, current_pairs)
            if app.ability_included_var.get()
            else copy.deepcopy(profile.stats)
        )
        baseline_score = score_fn(base, profile.target)
        current_score, contributions = current_line_contributions(
            base,
            current,
            profile.target,
            score_fn,
            combine_diminishing,
        )

        for label in app.ability_gain_labels:
            label.configure(text="—")
        ability_rows = []
        for line, gain in zip(current, contributions):
            app.ability_gain_labels[line.slot_number - 1].configure(text=f"{gain:+.3f}%")
            ability_rows.append((gain, line))

        profile_score = score_fn(profile.stats, profile.target)
        hero_rows = []
        for name, row in app.hero_upgrade_vars.items():
            current_value = parse_number(row["current"].get() or "0", field_name=f"{name} current")
            next_value = parse_number(row["next"].get() or "0", field_name=f"{name} next")
            cost = max(0.0, parse_number(row["cost"].get() or "0", field_name=f"{name} cost"))
            trial = copy.deepcopy(profile.stats)
            delta = next_value - current_value
            if name == "Attack":
                trial.attack += delta
            elif name == "Main Stat":
                apply_flat_main_stat(trial, delta)
            elif name == "Damage":
                trial.damage += delta
            elif name == "Accuracy":
                trial.accuracy += delta
            gain = percentage_gain(score_fn(trial, profile.target), profile_score)
            efficiency = gain / cost if cost > 0 else 0.0
            hero_rows.append((efficiency, gain, cost, name, current_value, next_value))
            app.hero_gain_labels[name].configure(
                text=(f"{gain:+.3f}% / {efficiency:.6f}" if cost > 0 else f"{gain:+.3f}%")
            )
        offensive = sorted(
            (row for row in hero_rows if row[1] > 1e-10 and row[2] > 0),
            reverse=True,
        )
        app.hero_summary_var.set(
            f"Best next offensive value: {offensive[0][3]} "
            f"({offensive[0][1]:+.3f}% for {offensive[0][2]:g} tokens)."
            if offensive
            else "Enter valid next values and costs; HP and Defense are utility upgrades."
        )

        level = int(
            clamp(
                parse_number(app.ability_reconfig_var.get() or "1", field_name="Reconfiguration level"),
                1,
                20,
            )
        )
        unlocked_slots = int(
            clamp(
                parse_number(app.ability_slots_var.get() or "1", field_name="Unlocked Ability slots"),
                1,
                7,
            )
        )
        app.ability_slots_var.set(str(unlocked_slots))
        medals = max(0, int(parse_number(app.ability_medals_var.get() or "0", field_name="Medals")))
        reserved_medals = max(
            0,
            int(parse_number(app.ability_reserved_medals_var.get() or "0", field_name="Reserved medals")),
        )
        level_progress = max(
            0,
            int(parse_number(app.ability_level_progress_var.get() or "0", field_name="Medals used toward next level")),
        )
        minimum_gain = max(
            0.0,
            parse_number(app.ability_min_gain_var.get() or "0", field_name="Minimum accepted gain"),
        )
        max_rerolled = int(
            clamp(
                parse_number(app.ability_max_reroll_slots_var.get() or "2", field_name="Maximum rerolled slots"),
                1,
                3,
            )
        )
        max_rerolled = min(max_rerolled, max(1, len(current)))
        app.ability_max_reroll_slots_var.set(str(max_rerolled))
        approach = str(app.ability_approach_var.get() or "Balanced").title()
        if approach not in APPROACH_MINIMUM_GAINS:
            approach = "Balanced"
            app.ability_approach_var.set(approach)
        _validate_ability_inputs(
            app,
            current,
            unlocked_slots,
            level,
            medals,
            reserved_medals,
            level_progress,
        )

        tier_recommendations = optimize_all_tiers(
            base,
            profile.target,
            unlocked_slots,
            level,
            score_fn,
            combine_diminishing,
        )
        action_plan = analyze_reroll_strategies(
            base,
            current,
            profile.target,
            level,
            medals,
            reserved_medals,
            level_progress,
            minimum_gain,
            max_rerolled,
            score_fn,
            combine_diminishing,
            optimization_approach=approach,
        )

        focused_tier = app.ability_target_tier_var.get()
        current_locked_count = sum(1 for line in current if line.locked)
        current_reroll_cost = (
            ABILITY_REROLL_COST[level][current_locked_count]
            if current_locked_count < len(ABILITY_REROLL_COST[level])
            else None
        )
        current_rolls = (
            int(action_plan.usable_medals // current_reroll_cost)
            if current_reroll_cost else 0
        )
        tier_probability = ABILITY_TIER_PROBABILITIES[level][ABILITY_TIERS.index(focused_tier)]
        recommended = action_plan.recommended_strategy
        if recommended:
            app.ability_summary_var.set(
                f"Reroll slot(s) {_format_slots(recommended.rerolled_slots)}; keep and lock "
                f"{_format_slots(recommended.locked_slots)}. The three best practical outcomes "
                f"have an estimated {recommended.top_three_budget_probability_pct:.1f}% chance "
                "within the usable Medal budget."
            )
        else:
            app.ability_summary_var.set(
                "No reroll strategy is affordable with the usable medal budget and available lock-cost table."
            )

        # Populate the concise decision dashboard.  The full mathematical report
        # remains available behind the optional details button.
        for index, variables in enumerate(app.hero_option_vars, start=1):
            variables["title"].set(f"Option {index}")
            variables["detail"].set("No qualifying outcome was estimated.")

        if offensive:
            best = offensive[0]
            app.hero_next_upgrade_var.set(
                f"{best[3]} {best[4]:g} → {best[5]:g} • {best[2]:g} tokens • "
                f"{best[1]:+.3f}% modeled damage"
            )
        else:
            app.hero_next_upgrade_var.set(
                "No entered Hero Power upgrade currently produces modeled offensive gain."
            )

        if recommended is None:
            app.hero_plan_action_var.set("No affordable reroll")
            app.hero_plan_lock_var.set("Reduce the Medal reserve or enter a larger budget.")
            app.hero_plan_chance_var.set("0%")
            app.hero_plan_chance_caption_var.set("No affordable attempts are available.")
            app.hero_plan_budget_var.set(f"{action_plan.usable_medals:,} usable")
            app.hero_plan_budget_caption_var.set(
                f"{medals:,} total • {reserved_medals:,} reserved"
            )
            app.hero_plan_slots_var.set("Keep all current slots until a reroll is affordable.")
            app.hero_plan_note_var.set(
                "Detailed analysis explains why no strategy could be evaluated."
            )
        else:
            reroll_word = "Slot" if len(recommended.rerolled_slots) == 1 else "Slots"
            reroll_display = " + ".join(str(slot) for slot in recommended.rerolled_slots)
            app.hero_plan_action_var.set(f"Reroll {reroll_word} {reroll_display}")
            app.hero_plan_lock_var.set(
                f"Keep and lock {_format_slots(recommended.locked_slots)}"
                if recommended.locked_slots
                else "Reroll without locking another slot"
            )
            app.hero_plan_chance_var.set(
                f"{recommended.top_three_budget_probability_pct:.1f}%"
            )
            if recommended.top_three_expected_attempts_given_success < float("inf"):
                expected_caption = (
                    f"~{recommended.top_three_expected_attempts_given_success:.1f} attempts / "
                    f"{recommended.top_three_expected_spend_given_success:,.0f} Medals when successful"
                )
            else:
                expected_caption = "No qualifying top-three success was estimated"
            app.hero_plan_chance_caption_var.set(
                f"Within {action_plan.usable_medals:,} usable Medals • {expected_caption}"
            )
            app.hero_plan_budget_var.set(f"{recommended.first_attempt_cost:,} / roll")
            app.hero_plan_budget_caption_var.set(
                f"Up to {recommended.attempts_affordable:,} attempts • "
                f"{reserved_medals:,} protected • {approach}"
            )
            keep_display = _format_slots(recommended.locked_slots)
            app.hero_plan_slots_var.set(
                f"REROLL {reroll_display}   •   KEEP / LOCK {keep_display}"
            )
            app.hero_plan_note_var.set(
                f"Accept one of the outcomes above only when the full rolled result meets the "
                f"selected {minimum_gain:g}% improvement. Then enter the new line(s) and press "
                "Analyze again. Probability is estimated, not an official exact rate."
            )

            threshold_lookup = {}
            if len(recommended.rerolled_slots) == 1:
                slot = recommended.rerolled_slots[0]
                for threshold in estimate_replacement_thresholds(
                    base,
                    current,
                    slot,
                    profile.target,
                    level,
                    minimum_gain,
                    score_fn,
                    combine_diminishing,
                    limit=30,
                ):
                    threshold_lookup[f"{threshold.tier} {threshold.stat_name}"] = threshold

            displayed = list(recommended.top_success_patterns[:3])
            for index, pattern in enumerate(displayed):
                title = pattern.description
                threshold = threshold_lookup.get(pattern.description)
                if threshold is not None:
                    title = (
                        f"{pattern.description} {threshold.minimum_accepted_value:.2f}+"
                    )
                app.hero_option_vars[index]["title"].set(title)
                combination_note = (
                    " • combined two-slot result"
                    if len(recommended.rerolled_slots) > 1 else ""
                )
                app.hero_option_vars[index]["detail"].set(
                    f"{pattern.probability_per_attempt_pct:.3f}% per attempt • "
                    f"accepted gain {pattern.minimum_gain_pct:+.3f}% to "
                    f"{pattern.maximum_gain_pct:+.3f}% "
                    f"(average {pattern.average_gain_pct:+.3f}%){combination_note}"
                )

        output: List[str] = []
        output.append(f"ACTIVE BUILD: {app.active_build_name} — {profile.target.content_mode}")
        output.append(
            f"Current Ability contribution: {percentage_gain(current_score, baseline_score):+.3f}% "
            f"versus the reconstructed no-Ability baseline."
        )
        output.append(
            f"Budget: {medals:,} medals total − {reserved_medals:,} reserved = "
            f"{action_plan.usable_medals:,} usable. Approach: {approach}. "
            f"Minimum accepted improvement: {minimum_gain:g}%."
        )
        output.append(f"Probability model: {ABILITY_ESTIMATE_MODEL}\n")

        output.append("DO THIS NEXT")
        recommended = action_plan.recommended_strategy
        if recommended is None:
            output.append("  No affordable strategy could be evaluated. Reduce the reserve or enter more medals.")
        else:
            output.append(f"  Reroll slot(s): {_format_slots(recommended.rerolled_slots)}")
            output.append(f"  Lock slot(s): {_format_slots(recommended.locked_slots)}")
            output.append(f"  Initial cost: {recommended.first_attempt_cost:,} medals per attempt")
            output.append(
                f"  Affordable attempts: {recommended.attempts_affordable:,}; modeled ending "
                f"Reconfiguration Level: {recommended.ending_reconfiguration_level}"
            )
            output.append(
                f"  Estimated success on the first attempt: "
                f"{recommended.first_attempt_success_probability_pct:.2f}% "
                f"± {recommended.first_attempt_margin_pct:.2f}% (95% simulation margin)"
            )
            output.append(
                f"  Estimated chance of at least one accepted improvement within budget: "
                f"{recommended.budget_success_probability_pct:.1f}%"
            )
            output.append(
                f"  Estimated chance of one of the three highlighted practical outcomes: "
                f"{recommended.top_three_budget_probability_pct:.1f}% within budget "
                f"({recommended.top_three_first_attempt_probability_pct:.3f}% initially per attempt)"
            )
            if recommended.top_three_expected_attempts_given_success < float("inf"):
                output.append(
                    f"  Expected top-three success timing, conditional on success: "
                    f"{recommended.top_three_expected_attempts_given_success:.1f} attempts and "
                    f"{recommended.top_three_expected_spend_given_success:,.0f} Medals"
                )
            output.append(
                "  The budget calculation tracks the same three displayed outcome categories "
                "through Reconfiguration Level changes; it does not replace them with a new top three."
            )
            if recommended.expected_spend_given_success < float("inf"):
                output.append(
                    f"  Estimated medals spent when a success occurs: "
                    f"{recommended.expected_spend_given_success:,.0f}"
                )
            output.append(
                f"  Average accepted result: {recommended.expected_gain_given_success_pct:+.3f}% "
                f"damage versus the current preset"
            )
            output.append(
                f"  Efficiency: {recommended.expected_gain_per_1000_medals:.4f} "
                f"probability-adjusted damage gain per 1,000 medals spent"
            )
            output.append(
                f"  Failure risk: {100.0 - recommended.budget_success_probability_pct:.1f}% chance "
                f"the usable budget ends without reaching the selected {minimum_gain:g}% threshold"
            )
            if recommended.top_success_patterns:
                output.append("  Common successful first-attempt patterns:")
                for pattern in recommended.top_success_patterns:
                    output.append(
                        f"    • {pattern.description} — {pattern.probability_per_attempt_pct:.3f}% "
                        f"per attempt; {pattern.share_of_successes_pct:.1f}% of simulated successes; "
                        f"gain {pattern.minimum_gain_pct:+.3f}% to {pattern.maximum_gain_pct:+.3f}% "
                        f"(average {pattern.average_gain_pct:+.3f}%)"
                    )

        output.append("\nCURRENT PRESET DIAGNOSIS")
        recommended_slots = set(recommended.rerolled_slots) if recommended else set()
        if ability_rows:
            for gain, line in sorted(ability_rows, key=lambda item: item[1].slot_number):
                if line.slot_number in recommended_slots:
                    status = "REROLL NEXT"
                elif recommended:
                    status = "KEEP AND LOCK FOR THIS PLAN"
                else:
                    status = "KEEP — NO AFFORDABLE PLAN"
                output.append(
                    f"  Slot {line.slot_number}: {line.tier} {line.stat_name} {line.value:g} — "
                    f"{gain:+.3f}% isolated contribution — {status}"
                )
        else:
            output.append("  No enabled lines entered.")

        if recommended:
            output.append("\nACCEPT / STOP THRESHOLDS")
            output.append(
                "For each recommended slot, these are estimated one-slot-equivalent rolls that "
                f"would beat the complete current preset by at least {minimum_gain:g}%."
            )
            if len(recommended.rerolled_slots) > 1:
                output.append(
                    "When rerolling multiple slots together, the combined result is what matters; "
                    "one line can compensate for another, so use these as practical preferred-option guides."
                )
            for slot in recommended.rerolled_slots:
                thresholds = estimate_replacement_thresholds(
                    base,
                    current,
                    slot,
                    profile.target,
                    level,
                    minimum_gain,
                    score_fn,
                    combine_diminishing,
                    limit=8,
                )
                output.append(f"\n  SLOT {slot}")
                if not thresholds:
                    output.append("    No currently obtainable single-line roll reaches the selected threshold.")
                    continue
                for threshold in thresholds:
                    output.append(
                        f"    • {threshold.tier} {threshold.stat_name} "
                        f"{threshold.minimum_accepted_value:.2f}+ (max {threshold.maximum_value:g}) — "
                        f"up to {threshold.maximum_gain_pct:+.3f}% — estimated "
                        f"{threshold.estimated_probability_per_rolled_slot * 100.0:.3f}% per rolled slot"
                    )

        output.append("\nREROLL STRATEGY COMPARISON")
        if action_plan.strategies:
            for rank, strategy in enumerate(action_plan.strategies[:10], start=1):
                marker = " ← RECOMMENDED" if strategy == recommended else ""
                output.append(f"  {rank}. {_format_strategy_line(strategy)}{marker}")
            if action_plan.safest_strategy and action_plan.safest_strategy != recommended:
                output.append(
                    "  Safest by budget success probability: "
                    + _format_strategy_line(action_plan.safest_strategy)
                )
            if action_plan.highest_upside_strategy and action_plan.highest_upside_strategy != recommended:
                output.append(
                    "  Highest average successful upside: "
                    + _format_strategy_line(action_plan.highest_upside_strategy)
                )
        else:
            output.append("  No strategies were available for comparison.")

        output.append("\nIDEAL TIER-BY-TIER REFERENCE")
        output.append(
            "This remains the theoretical N-slot destination, not the primary action recommendation."
        )
        for recommendation in tier_recommendations:
            availability = (
                f"{recommendation.probability_pct:g}% chance per rolled slot"
                if recommendation.available
                else f"unavailable at Reconfiguration Level {level}"
            )
            output.append(
                f"\n{recommendation.tier.upper()} — {availability} — complete-set gain "
                f"{recommendation.minimum_total_gain_pct:+.3f}% to "
                f"{recommendation.maximum_total_gain_pct:+.3f}%"
            )
            for line in recommendation.lines:
                output.append(
                    f"  {line.slot_number}. {line.stat_name} "
                    f"{_format_value_range(line.minimum_value, line.maximum_value)} — "
                    f"marginal {line.minimum_marginal_gain_pct:+.3f}% to "
                    f"{line.maximum_marginal_gain_pct:+.3f}%"
                )

        output.append("\nHERO POWER NEXT-UPGRADE VALUE")
        for rank, (efficiency, gain, cost, name, current_value, next_value) in enumerate(
            sorted(hero_rows, reverse=True),
            start=1,
        ):
            note = "offensive" if gain > 0 else "utility / no direct damage in current model"
            output.append(
                f"  {rank}. {name}: {current_value:g} → {next_value:g}, cost {cost:g}, "
                f"gain {gain:+.3f}%, gain/token {efficiency:.6f} — {note}"
            )

        output.append("\nFOCUSED TIER AND CURRENT LOCK CHECK")
        if current_reroll_cost is None:
            output.append(
                f"  Current lock boxes: {current_locked_count}; the verified reroll-cost table "
                f"does not include that many locks. {focused_tier} tier chance at Level {level}: "
                f"{tier_probability:g}% per rolled slot."
            )
        else:
            output.append(
                f"  Current lock boxes: {current_locked_count}; initial cost {current_reroll_cost:,}; "
                f"about {current_rolls:,} attempts before modeled level changes. "
                f"{focused_tier} tier chance at Level {level}: {tier_probability:g}% per rolled slot."
            )

        output.append("\nMODEL LIMITS")
        output.append(
            "  • Published tier probabilities, reroll costs, and level-up medal requirements are used directly."
        )
        output.append(
            "  • Exact option-type and value weights were not available in the verified public tables. "
            "The displayed improvement probabilities are estimates using equal option weights within "
            "each tier and a uniform value distribution."
        )
        output.append(
            "  • The planner assumes repeated rerolls continue until a complete result reaches the "
            "minimum accepted gain or the usable budget is exhausted."
        )
        output.append(
            "  • HP, Defense, Evasion, MP, drop, EXP, tolerance, and damage reduction are utility "
            "lines and do not receive an offensive score."
        )
        output.append(
            "  • Hero Power costs and next values remain manual because a complete verified fixed-stat "
            "cost table is not available."
        )

        app.hero_result_text.configure(state="normal")
        app.hero_result_text.delete("1.0", "end")
        app.hero_result_text.insert("1.0", "\n".join(output))
        app.hero_result_text.configure(state="disabled")
    except Exception as exc:
        messagebox.showerror("Hero Power analysis", str(exc), parent=app)
