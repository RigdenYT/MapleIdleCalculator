"""Tkinter UI for Equipment Potential capture, comparison, and roll tracking."""

from __future__ import annotations

import copy
import math
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageTk

from .data import (
    EQUIPMENT_SLOTS,
    POTENTIAL_OPTIONS,
    POTENTIAL_RANK_REQUIREMENTS,
    POTENTIAL_RARITIES,
    SLOT_SPECIAL_OPTIONS,
    SLOT_STATUS_OPTIONS,
)
from .engine import chance_with_budget, compare_rolls, rank_equipment_slots, roll_signature, slot_eligibility, stats_after_replacing_roll, wilson_interval
from .models import (
    AMBIGUOUS_UNIT_OPTIONS,
    INHERENT_PERCENT_OPTIONS,
    CaptureRegion,
    POTENTIAL_UNIT_FLAT,
    POTENTIAL_UNIT_PERCENT,
    POTENTIAL_UNIT_SECONDS,
    PotentialLine,
    PotentialOCRResult,
    normalize_potential_unit,
)
from .potential_rates import (
    PotentialRateProfile,
    analyze_configured_rates,
    empty_csv_template,
    load_profile as load_rate_profile,
    merge_profiles,
    profile_from_dict as rate_profile_from_dict,
    profile_to_dict as rate_profile_to_dict,
    rank_slots_by_configured_rates,
    save_profile as save_rate_profile,
)
from .ocr import (
    capture_full_screen,
    crop_region,
    fingerprint_distance,
    consensus_potential_results,
    potential_result_is_reliable,
    read_potential_consensus,
    read_potential_image,
    read_potential_image_fast,
    read_potential_staged,
    region_fingerprint,
    normalize_potential_panel,
    build_potential_debug_overlay,
)


class CaptureRegionDialog(tk.Toplevel):
    """Let the user drag a reusable rectangle over a screenshot."""

    def __init__(self, parent, image: Image.Image):
        super().__init__(parent)
        self.title("Select Potential capture region")
        self.transient(parent)
        self.grab_set()
        self.result: Optional[CaptureRegion] = None
        self.source = image.convert("RGB")
        max_width = 1200
        max_height = 760
        scale = min(max_width / self.source.width, max_height / self.source.height, 1.0)
        self.display = self.source.resize(
            (max(1, int(self.source.width * scale)), max(1, int(self.source.height * scale))),
            Image.Resampling.LANCZOS,
        )
        self.scale = scale
        self.photo = ImageTk.PhotoImage(self.display)
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text=("Drag around the ENTIRE active Potential Options card, including the left label, "
                  "rarity/progress, all three lines, and the outer border. A modest margin is fine."),
        ).pack(anchor="w", pady=(0, 8))
        self.canvas = tk.Canvas(
            outer,
            width=self.display.width,
            height=self.display.height,
            highlightthickness=1,
            highlightbackground="#536579",
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.start: Optional[Tuple[int, int]] = None
        self.rectangle: Optional[int] = None
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save Region", command=self._save).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        self.geometry(f"{min(self.display.width + 40, self.winfo_screenwidth() - 80)}x{min(self.display.height + 110, self.winfo_screenheight() - 80)}")

    def _press(self, event):
        self.start = (event.x, event.y)
        if self.rectangle is not None:
            self.canvas.delete(self.rectangle)
        self.rectangle = self.canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#d7ff45",
            width=3,
        )

    def _drag(self, event):
        if self.start is None or self.rectangle is None:
            return
        self.canvas.coords(self.rectangle, self.start[0], self.start[1], event.x, event.y)

    def _release(self, event):
        self._drag(event)

    def _save(self):
        if self.rectangle is None:
            messagebox.showwarning("Select a region", "Drag a box around the Potential panel first.", parent=self)
            return
        x1, y1, x2, y2 = self.canvas.coords(self.rectangle)
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        source_width = (x2 - x1) / max(self.scale, 1e-9)
        source_height = (y2 - y1) / max(self.scale, 1e-9)
        if source_width < 180 or source_height < 90:
            messagebox.showwarning(
                "Region too small",
                "Select the entire active Potential Options card, including its left label and outer border.",
                parent=self,
            )
            return
        inverse = 1.0 / max(self.scale, 1e-9)
        self.result = CaptureRegion(
            x1=x1 * inverse,
            y1=y1 * inverse,
            x2=x2 * inverse,
            y2=y2 * inverse,
            source_width=self.source.width,
            source_height=self.source.height,
        )
        self.destroy()


class PotentialCalibrationPreviewDialog(tk.Toplevel):
    """Confirm that the approximate selection localized to the intended card."""

    def __init__(self, parent, image: Image.Image):
        super().__init__(parent)
        self.title("Confirm Potential capture calibration")
        self.transient(parent)
        self.grab_set()
        self.accepted = False
        preview = build_potential_debug_overlay(image)
        max_width = 900
        scale = min(1.0, max_width / max(1, preview.width))
        shown = preview.resize(
            (max(1, int(preview.width * scale)), max(1, int(preview.height * scale))),
            Image.Resampling.LANCZOS,
        )
        self.photo = ImageTk.PhotoImage(shown)
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text=(
                "The program localized and normalized the Potential card. Confirm that the cyan header box and "
                "three colored line boxes cover the rarity/progress and all three active option rows."
            ),
            wraplength=900,
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(outer, image=self.photo).pack()
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Retry", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Use This Calibration", command=self._accept).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _accept(self) -> None:
        self.accepted = True
        self.destroy()


UNIT_LABELS = ("Flat", "%", "sec")


def _unit_label(unit: str) -> str:
    if unit == POTENTIAL_UNIT_PERCENT:
        return "%"
    if unit == POTENTIAL_UNIT_SECONDS:
        return "sec"
    return "Flat"


def _unit_value(label: str) -> str:
    normalized = str(label).strip().lower()
    if normalized == "%":
        return POTENTIAL_UNIT_PERCENT
    if normalized in {"sec", "s", "seconds"}:
        return POTENTIAL_UNIT_SECONDS
    return POTENTIAL_UNIT_FLAT


def _default_unit_label(stat_name: str) -> str:
    return _unit_label(normalize_potential_unit(stat_name, ""))


def _empty_line() -> Dict[str, object]:
    return {"stat": "Damage", "value": "0", "unit": POTENTIAL_UNIT_PERCENT}


def _default_slot_state() -> Dict[str, object]:
    return {
        "rarity": "Rare",
        "progress": "0",
        "progress_total": "60",
        "lines": [_empty_line(), _empty_line(), _empty_line()],
        "observed_rolls": 0,
        "observed_improvements": 0,
        "observed_signatures": [],
        "reroll_history": [],
        "configured": False,
        "slot_status": "Auto",
    }


def _schedule_priority_refresh(app, delay_ms: int = 180) -> None:
    """Debounce equipment-priority recalculation after any relevant edit."""
    if getattr(app, "potential_loading_state", False):
        return
    previous = getattr(app, "potential_priority_refresh_after_id", None)
    if previous and hasattr(app, "after_cancel"):
        try:
            app.after_cancel(previous)
        except Exception:
            pass
    if not hasattr(app, "after") or not hasattr(app, "refresh_potential_priority"):
        return

    def refresh():
        app.potential_priority_refresh_after_id = None
        try:
            app.refresh_potential_priority()
        except Exception:
            pass

    app.potential_priority_refresh_after_id = app.after(delay_ms, refresh)


def _invalidate_potential_effective_stats(app) -> None:
    """Use newly entered character totals after the user edits shared stats."""
    if getattr(app, "potential_loading_state", False):
        return
    app.potential_effective_stats_override = None
    _schedule_priority_refresh(app)


def _potential_stats(app, profile):
    override = getattr(app, "potential_effective_stats_override", None)
    return copy.deepcopy(override if override is not None else profile.stats)


def _slot_status_changed(app) -> None:
    if getattr(app, "potential_loading_state", False):
        return
    slot = getattr(app, "_potential_loaded_slot", None) or app.potential_selected_slot_var.get()
    if slot in getattr(app, "potential_slots_state", {}):
        status = app.potential_slot_status_var.get()
        app.potential_slots_state[slot]["slot_status"] = status if status in SLOT_STATUS_OPTIONS else "Auto"
    _schedule_priority_refresh(app)


def initialize_state(app) -> None:
    app.potential_selected_slot_var = tk.StringVar(value="Cape")
    app.potential_cubes_var = tk.StringVar(value="68")
    app.potential_min_gain_var = tk.StringVar(value="0.25")
    app.potential_auto_deduct_var = tk.BooleanVar(value=True)
    app.potential_auto_scan_var = tk.BooleanVar(value=False)
    app.potential_auto_scan_button_var = tk.StringVar(value="Start Auto Scan")
    app.potential_monitor_status_var = tk.StringVar(value="Auto scan is off")
    app.potential_capture_status_var = tk.StringVar(value="Capture region not calibrated")
    app.potential_result_title_var = tk.StringVar(value="READ OR ENTER A NEW ROLL")
    app.potential_result_detail_var = tk.StringVar(
        value="Scan the visible current Potential once, then use automatic scanning or Read New Roll after each reroll."
    )
    app.potential_odds_var = tk.StringVar(value="Configured rates are not loaded; observed-roll odds will be shown instead.")
    app.potential_stopping_rules_var = tk.StringVar(
        value="Scan and save a complete current Potential to generate configured-rate stopping targets."
    )
    app.potential_rank_aware_plan_var = tk.StringVar(
        value="Rank-aware cube planning appears when complete configured tables are available."
    )
    app.potential_rate_status_var = tk.StringVar(
        value="Configured Option Rates: no profile loaded. Import JSON/CSV to enable exact next-roll and cube-budget odds."
    )
    app.potential_bundled_rate_profile = PotentialRateProfile()
    app.potential_imported_rate_profile = PotentialRateProfile()
    app.potential_rate_profile = PotentialRateProfile()
    app.potential_rate_analysis_cache = {}
    app.potential_exact_odds_text = ""
    app.potential_slot_note_var = tk.StringVar(value="")
    app.potential_slot_status_var = tk.StringVar(value="Auto")
    app.potential_candidate_context_var = tk.StringVar(
        value="Detected reroll / manual entry — an actual cube permanently replaces the previous result."
    )
    app.potential_record_reroll_button_var = tk.StringVar(value="Record Entered Reroll as Current")
    app.potential_candidate_origin = "manual_entry"
    app.potential_candidate_rarity_var = tk.StringVar(value="Rare")
    app.potential_candidate_progress_var = tk.StringVar(value="0")
    app.potential_candidate_progress_total_var = tk.StringVar(value="60")
    app.potential_current_rarity_var = tk.StringVar(value="Rare")
    app.potential_current_progress_var = tk.StringVar(value="0")
    app.potential_current_progress_total_var = tk.StringVar(value="60")
    app.potential_current_line_vars = [
        {
            "stat": tk.StringVar(value="Damage"),
            "value": tk.StringVar(value="0"),
            "unit": tk.StringVar(value="%"),
        }
        for _ in range(3)
    ]
    app.potential_candidate_line_vars = [
        {
            "stat": tk.StringVar(value="Damage"),
            "value": tk.StringVar(value="0"),
            "unit": tk.StringVar(value="%"),
        }
        for _ in range(3)
    ]
    # Create the visible priority variables once during application startup.
    # Account loading must update these objects with .set(...) rather than
    # replacing them after the labels have already been bound.
    app.potential_priority_title_var = tk.StringVar(value="SCAN CURRENT POTENTIALS TO BUILD A PRIORITY LIST")
    app.potential_priority_rows_vars = [tk.StringVar(value="—") for _ in range(3)]
    app.potential_priority_note_var = tk.StringVar(
        value="The ranking uses saved current-set value, verified slot-special headroom, rank progress, and observed rolls."
    )
    app.potential_slots_state = {slot: _default_slot_state() for slot in EQUIPMENT_SLOTS}
    app.potential_capture_region: Optional[CaptureRegion] = None
    app.potential_last_candidate_signature = ""
    app.potential_last_comparison = None
    app.potential_monitor_running = False
    app.potential_monitor_busy = False
    app.potential_monitor_after_id = None
    app.potential_monitor_baseline_fingerprint = b""
    app.potential_monitor_pending_fingerprint = b""
    app.potential_monitor_pending_image = None
    app.potential_monitor_stable_frames = 0
    app.potential_monitor_stable_images = []
    app.potential_monitor_last_result_signature = ""
    app.potential_monitor_generation = 0
    app.potential_manual_ocr_running = False
    app.potential_manual_ocr_generation = 0
    app.potential_manual_ocr_queue = __import__("queue").Queue()
    app.potential_manual_ocr_after_id = None
    app.potential_priority_refresh_after_id = None
    app.potential_loading_state = False
    app.potential_pending_previous_snapshot = None
    app.potential_pending_reroll_cube_deducted = False
    app.potential_effective_stats_override = None
    app.potential_selected_slot_var.trace_add("write", lambda *_: _switch_slot(app))
    app.potential_slot_status_var.trace_add("write", lambda *_: _slot_status_changed(app))
    for variable in (
        app.potential_current_rarity_var,
        app.potential_current_progress_var,
        app.potential_current_progress_total_var,
        app.potential_cubes_var,
        app.potential_min_gain_var,
    ):
        variable.trace_add("write", lambda *_: _schedule_priority_refresh(app))
    for row in app.potential_current_line_vars:
        for variable in row.values():
            variable.trace_add("write", lambda *_: _schedule_priority_refresh(app))
    # The relative value of Potential lines depends on the selected build's
    # character totals and target. Keep the equipment-wide recommendation in
    # sync when those shared inputs change as well.
    for variable in list(getattr(app, "stat_vars", {}).values()):
        try:
            variable.trace_add("write", lambda *_: _invalidate_potential_effective_stats(app))
        except AttributeError:
            pass
    for variable in list(getattr(app, "target_vars", {}).values()):
        try:
            variable.trace_add("write", lambda *_: _schedule_priority_refresh(app))
        except AttributeError:
            pass


def _make_line_editor(parent, row: int, row_vars: Dict[str, tk.StringVar], *, title: str = ""):
    if title:
        ttk.Label(parent, text=title, style="WhitePanel.TLabel").grid(row=row, column=0, sticky="w", padx=4, pady=3)
    combo = ttk.Combobox(
        parent,
        textvariable=row_vars["stat"],
        values=POTENTIAL_OPTIONS,
        state="readonly",
        width=23,
    )
    combo.grid(row=row, column=1, sticky="ew", padx=4, pady=3)
    entry = ttk.Entry(parent, textvariable=row_vars["value"], width=10)
    entry.grid(row=row, column=2, sticky="ew", padx=4, pady=3)
    unit_combo = ttk.Combobox(
        parent,
        textvariable=row_vars["unit"],
        values=UNIT_LABELS,
        state="readonly",
        width=6,
    )
    unit_combo.grid(row=row, column=3, sticky="ew", padx=4, pady=3)

    def sync_unit_from_stat(_event=None):
        stat_name = row_vars["stat"].get().strip()
        if stat_name not in AMBIGUOUS_UNIT_OPTIONS:
            row_vars["unit"].set(_default_unit_label(stat_name))

    combo.bind("<<ComboboxSelected>>", sync_unit_from_stat)
    unit_combo.bind("<<ComboboxSelected>>", sync_unit_from_stat)
    sync_unit_from_stat()
    return combo, entry, unit_combo


def build_tab(app, colors: Dict[str, str]) -> None:
    tab = app.equipment_tab
    tab.columnconfigure(0, weight=1)
    tab.rowconfigure(0, weight=1)
    canvas = tk.Canvas(tab, background=colors["bg"], highlightthickness=0)
    scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    body = tk.Frame(canvas, background=colors["bg"])
    window = canvas.create_window(0, 0, window=body, anchor="nw")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
    body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    app.equipment_canvas = canvas

    title = tk.Frame(body, background="#26384d", padx=18, pady=13)
    title.pack(fill="x", padx=18, pady=(18, 10))
    tk.Label(
        title,
        text="EQUIPMENT ENHANCEMENT",
        background="#26384d",
        foreground="#d7ff45",
        font=("TkDefaultFont", 17, "bold"),
    ).pack(side="left")
    tk.Label(
        title,
        text="Irreversible reroll risk, automatic current-state tracking, and stopping guidance",
        background="#26384d",
        foreground="#ffffff",
        font=("TkDefaultFont", 10),
    ).pack(side="left", padx=16)

    controls_outer, controls = app._make_maple_section(body, "Potential Capture")
    controls_outer.pack(fill="x", padx=18, pady=8)
    ttk.Label(controls, text="Equipment slot", style="WhitePanel.TLabel").grid(row=0, column=0, sticky="w", padx=4)
    ttk.Combobox(
        controls,
        textvariable=app.potential_selected_slot_var,
        values=EQUIPMENT_SLOTS,
        state="readonly",
        width=20,
    ).grid(row=0, column=1, sticky="w", padx=4)
    ttk.Label(controls, text="Slot status", style="WhitePanel.TLabel").grid(row=0, column=2, sticky="w", padx=(18, 4))
    ttk.Combobox(
        controls,
        textvariable=app.potential_slot_status_var,
        values=SLOT_STATUS_OPTIONS,
        state="readonly",
        width=11,
    ).grid(row=0, column=3, sticky="w", padx=4)
    ttk.Label(controls, text="Cubes available", style="WhitePanel.TLabel").grid(row=0, column=4, sticky="w", padx=(18, 4))
    ttk.Entry(controls, textvariable=app.potential_cubes_var, width=10).grid(row=0, column=5, sticky="w", padx=4)
    ttk.Label(controls, text="Minimum improvement %", style="WhitePanel.TLabel").grid(row=0, column=6, sticky="w", padx=(18, 4))
    ttk.Entry(controls, textvariable=app.potential_min_gain_var, width=8).grid(row=0, column=7, sticky="w", padx=4)
    ttk.Checkbutton(
        controls,
        text="Deduct one cube after each detected reroll",
        variable=app.potential_auto_deduct_var,
    ).grid(row=1, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 2))
    ttk.Button(controls, text="Calibrate Potential Card", command=app.calibrate_potential_capture).grid(row=1, column=2, padx=4, pady=(8, 2))
    app.potential_scan_current_button = ttk.Button(
        controls,
        text="Scan Current Potential",
        style="Accent.TButton",
        command=app.scan_current_potential,
    )
    app.potential_scan_current_button.grid(row=1, column=3, padx=4, pady=(8, 2))
    app.potential_scan_current_auto_button = ttk.Button(
        controls,
        text="Scan Current & Start Auto Scan",
        command=app.scan_current_and_start_auto_scan,
    )
    app.potential_scan_current_auto_button.grid(row=1, column=4, padx=4, pady=(8, 2))
    ttk.Button(
        controls,
        textvariable=app.potential_auto_scan_button_var,
        command=app.toggle_potential_auto_scan,
    ).grid(row=1, column=6, padx=4, pady=(8, 2))
    app.potential_read_live_button = ttk.Button(controls, text="Read New Roll", command=app.read_potential_live)
    app.potential_read_live_button.grid(row=2, column=3, padx=4, pady=(5, 2))
    ttk.Button(controls, text="Read Screenshot File", command=app.read_potential_file).grid(row=2, column=4, padx=4, pady=(5, 2))
    ttk.Label(
        controls,
        textvariable=app.potential_capture_status_var,
        style="WhitePanel.TLabel",
        wraplength=1100,
    ).grid(row=3, column=0, columnspan=8, sticky="w", padx=4, pady=(7, 2))
    ttk.Label(
        controls,
        textvariable=app.potential_monitor_status_var,
        style="WhitePanel.TLabel",
        wraplength=1100,
    ).grid(row=4, column=0, columnspan=8, sticky="w", padx=4, pady=(2, 2))

    priority_outer, priority = app._make_maple_section(body, "Cube Priority")
    priority_outer.pack(fill="x", padx=18, pady=8)
    priority_card = tk.Frame(priority, background="#26384d", padx=16, pady=12)
    priority_card.pack(fill="x", padx=3, pady=3)
    tk.Label(
        priority_card,
        textvariable=app.potential_priority_title_var,
        background="#26384d",
        foreground="#d7ff45",
        font=("TkDefaultFont", 14, "bold"),
    ).pack(anchor="w")
    for variable in app.potential_priority_rows_vars:
        tk.Label(
            priority_card,
            textvariable=variable,
            background="#26384d",
            foreground="#ffffff",
            justify="left",
            wraplength=1100,
        ).pack(anchor="w", pady=(5, 0))
    priority_actions = tk.Frame(priority, background="#ffffff")
    priority_actions.pack(fill="x", padx=4, pady=(7, 3))
    ttk.Button(
        priority_actions,
        text="Refresh Equipment Priority",
        command=app.refresh_potential_priority,
    ).pack(side="left")
    ttk.Button(
        priority_actions,
        text="Import Configured Rates",
        command=app.import_potential_configured_rates,
    ).pack(side="left", padx=(8, 0))
    ttk.Button(
        priority_actions,
        text="Export Rate Template",
        command=app.export_potential_rate_template,
    ).pack(side="left", padx=(8, 0))
    ttk.Button(
        priority_actions,
        text="Export Loaded Rates",
        command=app.export_potential_configured_rates,
    ).pack(side="left", padx=(8, 0))
    ttk.Button(
        priority_actions,
        text="Clear Rates",
        command=app.clear_potential_configured_rates,
    ).pack(side="left", padx=(8, 0))
    ttk.Label(
        priority,
        textvariable=app.potential_rate_status_var,
        style="WhitePanel.TLabel",
        wraplength=1100,
    ).pack(anchor="w", padx=4, pady=(2, 3))
    ttk.Label(priority, textvariable=app.potential_priority_note_var, style="WhitePanel.TLabel", wraplength=1100).pack(anchor="w", padx=4, pady=(2, 4))

    columns = tk.Frame(body, background=colors["bg"])
    columns.pack(fill="x", padx=18, pady=8)
    columns.columnconfigure(0, weight=1)
    columns.columnconfigure(1, weight=1)
    current_outer, current = app._make_maple_section(columns, "Current Active Potential")
    candidate_outer, candidate = app._make_maple_section(columns, "Detected Reroll / OCR Review")
    current_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
    candidate_outer.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

    for panel, rarity_var, progress_var, total_var in (
        (current, app.potential_current_rarity_var, app.potential_current_progress_var, app.potential_current_progress_total_var),
        (candidate, app.potential_candidate_rarity_var, app.potential_candidate_progress_var, app.potential_candidate_progress_total_var),
    ):
        meta = tk.Frame(panel, background="#ffffff")
        meta.grid(row=0, column=0, columnspan=4, sticky="ew", padx=4, pady=(0, 5))
        ttk.Label(meta, text="Rarity", style="WhitePanel.TLabel").pack(side="left")
        ttk.Combobox(meta, textvariable=rarity_var, values=POTENTIAL_RARITIES, state="readonly", width=12).pack(side="left", padx=(5, 12))
        ttk.Entry(meta, textvariable=total_var, width=6).pack(side="right", padx=(2, 0))
        ttk.Label(meta, text="/", style="WhitePanel.TLabel").pack(side="right")
        ttk.Entry(meta, textvariable=progress_var, width=6).pack(side="right", padx=(5, 2))
        ttk.Label(meta, text="Progress", style="WhitePanel.TLabel").pack(side="right")
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(2, weight=0)
        panel.columnconfigure(3, weight=0)

    for index, row_vars in enumerate(app.potential_current_line_vars, start=1):
        _make_line_editor(current, index, row_vars, title=f"Line {index}")
    ttk.Button(current, text="Save Edited Current Lines", command=app.save_current_potential).grid(row=5, column=0, columnspan=4, sticky="ew", padx=4, pady=(10, 2))
    ttk.Button(current, text="Reset Observed Odds", command=app.reset_potential_history).grid(row=6, column=0, columnspan=4, sticky="ew", padx=4, pady=2)
    ttk.Label(current, textvariable=app.potential_slot_note_var, style="WhitePanel.TLabel", wraplength=480).grid(row=7, column=0, columnspan=6, sticky="w", padx=4, pady=(8, 2))

    for index, row_vars in enumerate(app.potential_candidate_line_vars, start=1):
        _make_line_editor(candidate, index, row_vars, title=f"Line {index}")
    ttk.Label(
        candidate,
        textvariable=app.potential_candidate_context_var,
        style="WhitePanel.TLabel",
        wraplength=480,
    ).grid(row=4, column=0, columnspan=4, sticky="w", padx=4, pady=(7, 2))
    ttk.Button(
        candidate,
        text="Preview Difference (No State Change)",
        style="Accent.TButton",
        command=app.compare_potential_roll,
    ).grid(row=5, column=0, columnspan=4, sticky="ew", padx=4, pady=(8, 2))
    app.potential_record_reroll_button = ttk.Button(
        candidate,
        textvariable=app.potential_record_reroll_button_var,
        command=app.accept_potential_roll,
    )
    app.potential_record_reroll_button.grid(row=6, column=0, columnspan=4, sticky="ew", padx=4, pady=2)
    app.potential_save_review_button = ttk.Button(
        candidate,
        text="Save Corrected as Current",
        command=app.save_corrected_current_potential,
        state="disabled",
    )
    app.potential_save_review_button.grid(row=7, column=0, columnspan=4, sticky="ew", padx=4, pady=2)

    result_outer, result = app._make_maple_section(body, "Roll Decision")
    result_outer.pack(fill="x", padx=18, pady=8)
    result_card = tk.Frame(result, background="#26384d", padx=18, pady=14)
    result_card.pack(fill="x", padx=3, pady=3)
    app.potential_result_title_label = tk.Label(
        result_card,
        textvariable=app.potential_result_title_var,
        background="#26384d",
        foreground="#d7ff45",
        font=("TkDefaultFont", 16, "bold"),
    )
    app.potential_result_title_label.pack(anchor="w")
    tk.Label(
        result_card,
        textvariable=app.potential_result_detail_var,
        background="#26384d",
        foreground="#ffffff",
        justify="left",
        wraplength=1100,
    ).pack(anchor="w", pady=(6, 0))
    odds = tk.Frame(result, background="#ffffff", padx=8, pady=8)
    odds.pack(fill="x")
    ttk.Label(odds, textvariable=app.potential_odds_var, style="WhitePanel.TLabel", wraplength=1100).pack(anchor="w")
    ttk.Label(
        odds,
        text=(
            "The decision is made before cubing: reroll or stop. After a reroll is detected, that result is automatically "
            "treated as the active current Potential because the previous result can no longer be restored. Exact tables "
            "show both upside and downside risk; incomplete tables fall back to observed session data and headroom."
        ),
        style="WhitePanel.TLabel",
        wraplength=1100,
    ).pack(anchor="w", pady=(5, 0))
    stopping_outer, stopping = app._make_maple_section(body, "Configured-Rate Stopping Guide")
    stopping_outer.pack(fill="x", padx=18, pady=8)
    ttk.Label(
        stopping,
        textvariable=app.potential_stopping_rules_var,
        style="WhitePanel.TLabel",
        justify="left",
        wraplength=1100,
    ).pack(anchor="w", padx=4, pady=(2, 5))
    ttk.Label(
        stopping,
        textvariable=app.potential_rank_aware_plan_var,
        style="WhitePanel.TLabel",
        justify="left",
        wraplength=1100,
    ).pack(anchor="w", padx=4, pady=(2, 4))

    _load_selected_slot(app)


def _line_vars_to_models(rows: Sequence[Dict[str, tk.StringVar]], parse_number: Callable[..., float], prefix: str) -> List[PotentialLine]:
    lines: List[PotentialLine] = []
    for index, row in enumerate(rows, start=1):
        stat_name = row["stat"].get().strip()
        value = parse_number(row["value"].get(), field_name=f"{prefix} line {index}")
        if stat_name not in POTENTIAL_OPTIONS:
            raise ValueError(f"{prefix} line {index} has an unknown Potential option.")
        unit_var = row.get("unit")
        unit = _unit_value(unit_var.get()) if unit_var is not None else ""
        lines.append(PotentialLine(stat_name, float(value), unit))
    return lines


def _serialize_line(line: PotentialLine) -> Dict[str, object]:
    return {"stat": line.stat_name, "value": line.value, "unit": line.unit}


def _deserialize_lines(value: object) -> List[PotentialLine]:
    result: List[PotentialLine] = []
    if isinstance(value, list):
        for item in value[:3]:
            if not isinstance(item, dict):
                continue
            stat = str(item.get("stat", "Damage"))
            try:
                number = float(item.get("value", 0.0))
            except (TypeError, ValueError):
                number = 0.0
            if stat in POTENTIAL_OPTIONS:
                result.append(PotentialLine(stat, number, str(item.get("unit", ""))))
    while len(result) < 3:
        result.append(PotentialLine("Damage", 0.0, POTENTIAL_UNIT_PERCENT))
    return result


def _set_row_from_line(row: Dict[str, tk.StringVar], line: PotentialLine) -> None:
    row["stat"].set(line.stat_name)
    row["value"].set(f"{line.value:g}")
    unit_var = row.get("unit")
    if unit_var is not None:
        unit_var.set(_unit_label(line.unit))


def _store_selected_slot(app) -> None:
    slot = app.potential_selected_slot_var.get()
    if slot not in app.potential_slots_state:
        return
    state = app.potential_slots_state[slot]
    state["rarity"] = app.potential_current_rarity_var.get()
    state["progress"] = app.potential_current_progress_var.get()
    state["progress_total"] = app.potential_current_progress_total_var.get()
    status_var = getattr(app, "potential_slot_status_var", None)
    status = status_var.get() if status_var is not None else str(state.get("slot_status", "Auto"))
    state["slot_status"] = status if status in SLOT_STATUS_OPTIONS else "Auto"
    state["lines"] = [
        _serialize_line(line)
        for line in _line_vars_to_models(app.potential_current_line_vars, lambda value, **_: float(str(value).replace(",", "")), "Current Potential")
    ]


def _switch_slot(app) -> None:
    stop_auto_monitor(app)
    previous = getattr(app, "_potential_loaded_slot", None)
    if previous and previous in app.potential_slots_state:
        # Save from the previous slot without relying on the newly changed selector.
        current_selected = app.potential_selected_slot_var.get()
        state = app.potential_slots_state[previous]
        state["rarity"] = app.potential_current_rarity_var.get()
        state["progress"] = app.potential_current_progress_var.get()
        state["progress_total"] = app.potential_current_progress_total_var.get()
        status_var = getattr(app, "potential_slot_status_var", None)
        status = status_var.get() if status_var is not None else str(state.get("slot_status", "Auto"))
        state["slot_status"] = status if status in SLOT_STATUS_OPTIONS else "Auto"
        state["lines"] = [
            _serialize_line(line)
            for line in _line_vars_to_models(app.potential_current_line_vars, lambda value, **_: float(str(value).replace(",", "")), "Current Potential")
        ]
    _load_selected_slot(app)


def _load_selected_slot(app) -> None:
    slot = app.potential_selected_slot_var.get()
    if slot not in app.potential_slots_state:
        return
    app._potential_loaded_slot = slot
    state = app.potential_slots_state[slot]
    app.potential_loading_state = True
    try:
        app.potential_current_rarity_var.set(str(state.get("rarity", "Rare")))
        app.potential_current_progress_var.set(str(state.get("progress", "0")))
        app.potential_current_progress_total_var.set(str(state.get("progress_total", "60")))
        status = str(state.get("slot_status", "Auto"))
        app.potential_slot_status_var.set(status if status in SLOT_STATUS_OPTIONS else "Auto")
        lines = _deserialize_lines(state.get("lines", []))
        for row, line in zip(app.potential_current_line_vars, lines):
            _set_row_from_line(row, line)
    finally:
        app.potential_loading_state = False
    special = SLOT_SPECIAL_OPTIONS.get(slot)
    eligible, eligibility_reason = slot_eligibility(state)
    status_text = "included in priority" if eligible else f"excluded from priority: {eligibility_reason}"
    special_text = f"Slot-exclusive target: {special}." if special else "No verified slot-exclusive option is loaded for this slot yet."
    rate_profile = getattr(app, "potential_rate_profile", PotentialRateProfile())
    rarity = str(state.get("rarity", "Rare"))
    if rate_profile.has_complete_table(slot, rarity):
        rate_text = f"Exact configured odds are available for {rarity}."
    else:
        missing = rate_profile.missing_lines(slot, rarity)
        details = ", ".join(
            f"line {line} ({rate_profile.section_reason(slot, rarity, line)})" for line in missing
        )
        rate_text = (
            f"RATE DATA WARNING: exact odds are unavailable for {slot} {rarity}; "
            f"missing {details or 'lines 1–3'}. Collect this Option Rates section after the slot/rank is available."
        )
    app.potential_slot_note_var.set(f"{special_text} Current status: {status_text}. {rate_text}")
    app.potential_last_candidate_signature = ""
    app.potential_last_comparison = None
    app.potential_exact_odds_text = ""
    _update_observed_odds(app)
    _schedule_priority_refresh(app)



def _rebuild_rate_profile(app) -> None:
    bundled = getattr(app, "potential_bundled_rate_profile", PotentialRateProfile())
    imported = getattr(app, "potential_imported_rate_profile", PotentialRateProfile())
    app.potential_rate_profile = merge_profiles(bundled, imported)
    app.potential_rate_analysis_cache = {}


def load_bundled_configured_rates(app, path: Path) -> None:
    """Load the packaged configured-rate baseline without storing it in each account."""
    try:
        bundled = load_rate_profile(Path(path))
    except Exception as exc:
        bundled = PotentialRateProfile(notes=f"Bundled configured-rate profile could not be loaded: {exc}")
    app.potential_bundled_rate_profile = bundled
    if not hasattr(app, "potential_imported_rate_profile"):
        app.potential_imported_rate_profile = PotentialRateProfile()
    _rebuild_rate_profile(app)
    _update_rate_status(app)

def _update_rate_status(app) -> None:
    variable = getattr(app, "potential_rate_status_var", None)
    if variable is None:
        return
    profile = getattr(app, "potential_rate_profile", PotentialRateProfile())
    completed = profile.completed_tables()
    outcomes = profile.outcome_count()
    if outcomes <= 0:
        variable.set(
            "Configured Option Rates: no profile loaded. Import JSON/CSV to enable exact next-roll and cube-budget odds."
        )
        return
    source = profile.source or "configured-rate import"
    captured = f" • captured {profile.captured_at}" if profile.captured_at else ""
    entirely_missing = [
        slot for slot in EQUIPMENT_SLOTS
        if not any(profile.distribution(slot, rarity, line) for rarity in POTENTIAL_RARITIES for line in (1, 2, 3))
    ]
    partial = []
    for slot in EQUIPMENT_SLOTS:
        for rarity in POTENTIAL_RARITIES:
            missing = profile.missing_lines(slot, rarity)
            if missing and len(missing) < 3:
                partial.append(f"{slot} {rarity} line(s) {', '.join(map(str, missing))}")
    warning_parts = []
    if entirely_missing:
        warning_parts.append("No collected rates yet: " + ", ".join(entirely_missing) + ".")
    if partial:
        warning_parts.append("Incomplete: " + "; ".join(partial[:5]) + ("…" if len(partial) > 5 else "") + ".")
    variable.set(
        f"Configured Option Rates: {completed}/{len(EQUIPMENT_SLOTS) * len(POTENTIAL_RARITIES)} complete "
        f"slot/rarity table(s), {outcomes} outcomes • {source}{captured}. "
        "Exact analysis activates only where lines 1, 2, and 3 are complete. "
        + " ".join(warning_parts)
    )


def import_configured_rates(app) -> None:
    path = filedialog.askopenfilename(
        parent=app,
        title="Import configured Potential Option Rates",
        filetypes=(("Rate profiles", "*.json *.csv"), ("JSON", "*.json"), ("CSV", "*.csv"), ("All files", "*.*")),
    )
    if not path:
        return
    try:
        incoming = load_rate_profile(Path(path))
        app.potential_imported_rate_profile = merge_profiles(
            getattr(app, "potential_imported_rate_profile", PotentialRateProfile()),
            incoming,
        )
        _rebuild_rate_profile(app)
        _update_rate_status(app)
        refresh = getattr(app, "refresh_potential_priority", None)
        if callable(refresh):
            refresh()
        messagebox.showinfo(
            "Configured rates imported",
            f"Loaded {incoming.completed_tables()} complete slot/rarity table(s) and "
            f"{incoming.outcome_count()} outcomes. Existing tables with matching slot, rarity, and line were replaced.",
            parent=app,
        )
    except Exception as exc:
        messagebox.showerror("Configured-rate import failed", str(exc), parent=app)


def export_rate_template(app) -> None:
    slot = app.potential_selected_slot_var.get()
    rarity = app.potential_current_rarity_var.get()
    path = filedialog.asksaveasfilename(
        parent=app,
        title="Export configured-rate CSV template",
        defaultextension=".csv",
        initialfile=f"potential_rates_{slot.replace(' ', '_').lower()}_{rarity.lower()}.csv",
        filetypes=(("CSV", "*.csv"), ("All files", "*.*")),
    )
    if not path:
        return
    try:
        Path(path).write_text(empty_csv_template(slot, rarity), encoding="utf-8")
        messagebox.showinfo(
            "Rate template exported",
            "Replace the placeholder rows with every configured outcome from Option Rates for lines 1, 2, and 3. "
            "Each line distribution must total 100% before it can be imported.",
            parent=app,
        )
    except Exception as exc:
        messagebox.showerror("Rate template export failed", str(exc), parent=app)


def export_configured_rates(app) -> None:
    profile = getattr(app, "potential_rate_profile", PotentialRateProfile())
    if profile.outcome_count() <= 0:
        messagebox.showinfo("No configured rates", "There is no loaded configured-rate profile to export.", parent=app)
        return
    path = filedialog.asksaveasfilename(
        parent=app,
        title="Export loaded configured rates",
        defaultextension=".json",
        initialfile="maplestory_idle_potential_configured_rates.json",
        filetypes=(("JSON", "*.json"), ("All files", "*.*")),
    )
    if not path:
        return
    try:
        save_rate_profile(Path(path), profile)
    except Exception as exc:
        messagebox.showerror("Configured-rate export failed", str(exc), parent=app)


def clear_configured_rates(app) -> None:
    profile = getattr(app, "potential_rate_profile", PotentialRateProfile())
    if profile.outcome_count() <= 0:
        return
    if not messagebox.askyesno(
        "Clear configured rates",
        "Remove account-imported Potential rate overrides and return to the bundled collected rates? Saved Potential rolls are not affected.",
        parent=app,
    ):
        return
    app.potential_imported_rate_profile = PotentialRateProfile()
    _rebuild_rate_profile(app)
    _update_rate_status(app)
    refresh = getattr(app, "refresh_potential_priority", None)
    if callable(refresh):
        refresh()


def collect_state(app) -> Dict[str, object]:
    _store_selected_slot(app)
    capture = None
    if app.potential_capture_region is not None:
        capture = {
            "x1": app.potential_capture_region.x1,
            "y1": app.potential_capture_region.y1,
            "x2": app.potential_capture_region.x2,
            "y2": app.potential_capture_region.y2,
            "source_width": app.potential_capture_region.source_width,
            "source_height": app.potential_capture_region.source_height,
        }
    return {
        "selected_slot": app.potential_selected_slot_var.get(),
        "cubes": app.potential_cubes_var.get(),
        "minimum_gain": app.potential_min_gain_var.get(),
        "auto_deduct": bool(app.potential_auto_deduct_var.get()),
        "capture_region": capture,
        "slots": copy.deepcopy(app.potential_slots_state),
        "configured_rate_profile": rate_profile_to_dict(getattr(app, "potential_imported_rate_profile", PotentialRateProfile())),
    }


def apply_state(app, data: object) -> None:
    # Equipment enhancement is shared account state. Loading an older account or
    # creating a new one must clear the previously open account rather than leak
    # its Potential rolls into the new session.
    # Preserve the StringVar objects already bound to the visible labels.
    # Replacing them here made refreshes update invisible variables.
    app.potential_priority_title_var.set("SCAN CURRENT POTENTIALS TO BUILD A PRIORITY LIST")
    for variable in app.potential_priority_rows_vars:
        variable.set("—")
    app.potential_priority_note_var.set(
        "The ranking uses saved current-set value, verified slot-special headroom, rank progress, and observed rolls."
    )
    stop_auto_monitor(app)
    app.potential_loading_state = True
    app.potential_slots_state = {slot: _default_slot_state() for slot in EQUIPMENT_SLOTS}
    app.potential_imported_rate_profile = PotentialRateProfile()
    _rebuild_rate_profile(app)
    app.potential_exact_odds_text = ""
    _update_rate_status(app)
    app.potential_capture_region = None
    app.potential_capture_status_var.set("Capture region not calibrated")
    app.potential_cubes_var.set("0")
    app.potential_min_gain_var.set("0.25")
    app.potential_auto_deduct_var.set(True)
    app.potential_auto_scan_var.set(False)
    app.potential_auto_scan_button_var.set("Start Auto Scan")
    app.potential_monitor_status_var.set("Auto scan is off")
    app._potential_loaded_slot = None
    if not isinstance(data, dict):
        app.potential_selected_slot_var.set("Cape")
        app.potential_loading_state = False
        _load_selected_slot(app)
        _schedule_priority_refresh(app, 20)
        return
    slots = data.get("slots")
    if isinstance(slots, dict):
        for slot in EQUIPMENT_SLOTS:
            source = slots.get(slot)
            if isinstance(source, dict):
                merged = _default_slot_state()
                merged.update(copy.deepcopy(source))
                raw_lines = source.get("lines", [])
                legacy_unitless_lines = bool(
                    isinstance(raw_lines, list)
                    and any(isinstance(item, dict) and "unit" not in item for item in raw_lines)
                )
                migrated_lines = _deserialize_lines(raw_lines)
                merged["lines"] = [_serialize_line(line) for line in migrated_lines]
                if legacy_unitless_lines:
                    # Versions through 2.8.2 could not distinguish INT 6% from
                    # INT 6. Historical roll comparisons and signatures are
                    # therefore unsafe after migration.
                    merged["observed_rolls"] = 0
                    merged["observed_improvements"] = 0
                    merged["observed_signatures"] = []
                if "configured" not in source:
                    merged["configured"] = bool(
                        isinstance(raw_lines, list)
                        and any(
                            isinstance(item, dict)
                            and str(item.get("value", "0")).strip() not in {"", "0", "0.0"}
                            for item in raw_lines
                        )
                    )
                status = str(merged.get("slot_status", "Auto"))
                merged["slot_status"] = status if status in SLOT_STATUS_OPTIONS else "Auto"
                app.potential_slots_state[slot] = merged
    if "cubes" in data:
        app.potential_cubes_var.set(str(data["cubes"]))
    if "minimum_gain" in data:
        app.potential_min_gain_var.set(str(data["minimum_gain"]))
    if "auto_deduct" in data:
        app.potential_auto_deduct_var.set(bool(data["auto_deduct"]))
    capture = data.get("capture_region")
    if isinstance(capture, dict):
        try:
            app.potential_capture_region = CaptureRegion(
                x1=float(capture["x1"]),
                y1=float(capture["y1"]),
                x2=float(capture["x2"]),
                y2=float(capture["y2"]),
                source_width=int(capture["source_width"]),
                source_height=int(capture["source_height"]),
            )
            app.potential_capture_status_var.set("Capture region loaded from this account")
        except (KeyError, TypeError, ValueError):
            app.potential_capture_region = None
    rate_data = data.get("configured_rate_profile")
    if isinstance(rate_data, dict):
        try:
            app.potential_imported_rate_profile = rate_profile_from_dict(rate_data)
        except Exception as exc:
            app.potential_imported_rate_profile = PotentialRateProfile(
                notes=f"Saved configured-rate profile could not be loaded: {exc}"
            )
    _rebuild_rate_profile(app)
    _update_rate_status(app)
    selected = str(data.get("selected_slot", "Cape"))
    if selected not in EQUIPMENT_SLOTS:
        selected = "Cape"
    app.potential_selected_slot_var.set(selected)
    app.potential_loading_state = False
    _load_selected_slot(app)
    _schedule_priority_refresh(app, 20)


def _prepare_capture_panel(image: Image.Image, region: CaptureRegion) -> Image.Image:
    rough = crop_region(image, region)
    normalized, warnings, bounds = normalize_potential_panel(rough)
    if bounds is None:
        raise ValueError(warnings[0] if warnings else "Could not locate the Potential card. Recalibrate it.")
    return normalized


def calibrate_capture(app, *, image: Optional[Image.Image] = None) -> bool:
    if image is None:
        choice = messagebox.askyesnocancel(
            "Potential capture region",
            "Capture the current screen now?\n\nChoose No to calibrate from a saved screenshot instead.",
            parent=app,
        )
        if choice is None:
            return False
        if choice:
            try:
                image = capture_full_screen()
            except Exception as exc:
                messagebox.showerror("Screen capture failed", str(exc), parent=app)
                return False
        else:
            path = filedialog.askopenfilename(
                parent=app,
                title="Choose a screenshot containing the active Potential card",
                filetypes=(("PNG/JPEG images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")),
            )
            if not path:
                return False
            image = Image.open(path).convert("RGB")
    dialog = CaptureRegionDialog(app, image)
    app.wait_window(dialog)
    if dialog.result is None:
        return False
    try:
        normalized = _prepare_capture_panel(image, dialog.result)
    except Exception as exc:
        messagebox.showerror(
            "Potential card not detected",
            f"{exc}\n\nSelect the complete active Potential Options card, including the left label and outer border.",
            parent=app,
        )
        return False
    preview = PotentialCalibrationPreviewDialog(app, normalized)
    app.wait_window(preview)
    if not preview.accepted:
        app.potential_capture_status_var.set("Calibration was not saved. Retry and include the complete Potential card.")
        return False
    app.potential_capture_region = dialog.result
    nx1, ny1, nx2, ny2 = dialog.result.normalized()
    app.potential_capture_status_var.set(
        f"Potential card calibration saved and localized successfully "
        f"({(nx2 - nx1) * 100:.1f}% × {(ny2 - ny1) * 100:.1f}% approximate screen region)."
    )
    return True


def _set_review_button_state(app, enabled: bool) -> None:
    button = getattr(app, "potential_save_review_button", None)
    if button is not None:
        try:
            button.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass


def _set_reroll_button_state(app, enabled: bool, text: str = "Record Entered Reroll as Current") -> None:
    variable = getattr(app, "potential_record_reroll_button_var", None)
    if variable is not None:
        variable.set(text)
    button = getattr(app, "potential_record_reroll_button", None)
    if button is not None:
        try:
            button.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass


def _fill_candidate(
    app,
    result: PotentialOCRResult,
    *,
    context: str = "manual_entry",
    review_reason: str = "",
) -> None:
    if result.rarity:
        app.potential_candidate_rarity_var.set(result.rarity)
    if result.progress_total:
        app.potential_candidate_progress_var.set(str(result.progress))
        app.potential_candidate_progress_total_var.set(str(result.progress_total))
    for row, line in zip(app.potential_candidate_line_vars, result.lines):
        _set_row_from_line(row, line)
    app.potential_candidate_origin = context
    if context == "current_review":
        app.potential_candidate_context_var.set(
            "CURRENT SCAN REVIEW — correct any OCR mistakes, then press Save Corrected as Current."
        )
        _set_review_button_state(app, True)
        _set_reroll_button_state(app, False)
    elif context == "reroll_review":
        app.potential_candidate_context_var.set(
            "REROLL OCR REVIEW — this result is already active in game and the previous roll is gone. "
            "Correct the fields, then record the corrected reroll as current."
        )
        _set_review_button_state(app, False)
        _set_reroll_button_state(app, True, "Record Corrected Reroll as Current")
    elif context == "committed_reroll":
        app.potential_candidate_context_var.set(
            "LAST DETECTED REROLL — already saved as the active current Potential."
        )
        _set_review_button_state(app, False)
        _set_reroll_button_state(app, True, "Record Edited Reroll as Current")
    else:
        app.potential_candidate_context_var.set(
            "Detected reroll / manual entry — an actual cube permanently replaces the previous result."
        )
        _set_review_button_state(app, False)
        _set_reroll_button_state(app, True, "Record Entered Reroll as Current")
    warning = " ".join(result.warnings)
    confidence_label = "high" if result.confidence >= 0.86 else "medium" if result.confidence >= 0.70 else "low"
    details = (
        f"OCR read completed ({confidence_label} confidence, {result.confidence * 100:.0f}%). "
        "Review the values before recording a corrected result."
    )
    if review_reason:
        details += f" {review_reason}"
    if warning:
        details += f" {warning}"
    app.potential_capture_status_var.set(details)


def _ocr_result_signature(result: PotentialOCRResult) -> str:
    parts = [result.rarity, f"{result.progress}/{result.progress_total}"]
    parts.extend(f"{line.stat_name}:{line.unit}:{line.value:.8g}" for line in result.lines)
    return "|".join(parts)


def _fill_current(app, result: PotentialOCRResult) -> None:
    if result.rarity:
        app.potential_current_rarity_var.set(result.rarity)
    if result.progress_total:
        app.potential_current_progress_var.set(str(result.progress))
        app.potential_current_progress_total_var.set(str(result.progress_total))
    for row, line in zip(app.potential_current_line_vars, result.lines):
        _set_row_from_line(row, line)


def _clear_candidate(app) -> None:
    app.potential_candidate_rarity_var.set(app.potential_current_rarity_var.get())
    app.potential_candidate_progress_var.set(app.potential_current_progress_var.get())
    app.potential_candidate_progress_total_var.set(app.potential_current_progress_total_var.get())
    for row in app.potential_candidate_line_vars:
        _set_row_from_line(row, PotentialLine("Damage", 0.0, POTENTIAL_UNIT_PERCENT))
    app.potential_last_candidate_signature = ""
    app.potential_last_comparison = None
    app.potential_candidate_origin = "manual_entry"
    app.potential_pending_previous_snapshot = None
    app.potential_pending_reroll_cube_deducted = False
    if hasattr(app, "potential_candidate_context_var"):
        app.potential_candidate_context_var.set(
            "Detected reroll / manual entry — an actual cube permanently replaces the previous result."
        )
    _set_review_button_state(app, False)
    _set_reroll_button_state(app, True, "Record Entered Reroll as Current")


def apply_scanned_current(app, result: PotentialOCRResult) -> None:
    """Save one OCR result as the selected slot's baseline without counting a reroll."""
    if not result.complete:
        raise ValueError("Potential OCR did not read a rarity and all three current lines.")
    _fill_current(app, result)
    slot = app.potential_selected_slot_var.get()
    state = app.potential_slots_state[slot]
    state["configured"] = True
    if str(state.get("slot_status", "Auto")) == "Locked":
        state["slot_status"] = "Auto"
        if hasattr(app, "potential_slot_status_var"):
            app.potential_slot_status_var.set("Auto")
    state["observed_rolls"] = 0
    state["observed_improvements"] = 0
    state["observed_signatures"] = []
    state["reroll_history"] = []
    app.potential_pending_previous_snapshot = None
    app.potential_pending_reroll_cube_deducted = False
    _store_selected_slot(app)
    _clear_candidate(app)
    signature = _ocr_result_signature(result)
    app.potential_monitor_last_result_signature = signature
    confidence_label = "high" if result.confidence >= 0.86 else "medium" if result.confidence >= 0.70 else "low"
    warning = " ".join(result.warnings)
    app.potential_capture_status_var.set(
        f"Saved current Potential for {slot} ({confidence_label} OCR confidence, {result.confidence * 100:.0f}%). "
        "No cube was deducted and no reroll observation was recorded."
        + (f" {warning}" if warning else "")
    )
    app.potential_result_title_var.set("CURRENT POTENTIAL SCANNED")
    app.potential_result_detail_var.set(
        f"The visible three-line set is now the saved baseline for {slot}. "
        "Open another equipment slot and repeat, or start automatic scanning before rerolling this slot. "
        "Before cubing, use the risk panel to decide whether the current result is worth risking."
    )
    _update_observed_odds(app)
    _schedule_priority_refresh(app, 20)


def save_corrected_current(app, *, parse_number: Callable[..., float]) -> bool:
    """Save manually corrected Current Scan Review fields as the baseline."""
    if getattr(app, "potential_candidate_origin", "") != "current_review":
        messagebox.showinfo(
            "No current scan to review",
            "Use Scan Current Potential first. This button is only for a current scan that needs OCR correction.",
            parent=app,
        )
        return False
    try:
        lines = _line_vars_to_models(app.potential_candidate_line_vars, parse_number, "Reviewed current Potential")
        rarity = app.potential_candidate_rarity_var.get().strip()
        if rarity not in POTENTIAL_RARITIES:
            raise ValueError("Select the current Potential rarity.")
        progress = int(parse_number(app.potential_candidate_progress_var.get(), field_name="Current Potential progress"))
        progress_total = int(parse_number(app.potential_candidate_progress_total_var.get(), field_name="Current Potential progress total"))
        if progress < 0 or progress_total < 0:
            raise ValueError("Potential rank progress cannot be negative.")
        result = PotentialOCRResult(
            rarity=rarity,
            progress=progress,
            progress_total=progress_total,
            lines=tuple(lines),
            raw_text="Corrected current-scan review",
            warnings=("Saved after manual OCR review.",),
            line_confidences=(1.0, 1.0, 1.0),
            confidence=1.0,
        )
        apply_scanned_current(app, result)
        app.potential_result_title_var.set("CORRECTED CURRENT POTENTIAL SAVED")
        app.potential_result_detail_var.set(
            "The corrected three-line set is now the saved current baseline. No cube was deducted and no reroll was recorded."
        )
        _schedule_priority_refresh(app, 20)
        return True
    except Exception as exc:
        messagebox.showerror("Current Potential review", str(exc), parent=app)
        return False


def _snapshot_current(app, parse_number: Callable[..., float]) -> Dict[str, object]:
    return {
        "rarity": app.potential_current_rarity_var.get(),
        "progress": app.potential_current_progress_var.get(),
        "progress_total": app.potential_current_progress_total_var.get(),
        "lines": _line_vars_to_models(app.potential_current_line_vars, parse_number, "Current Potential"),
    }


def _deduct_reroll_cube(app, parse_number: Callable[..., float]) -> bool:
    if not app.potential_auto_deduct_var.get():
        return False
    try:
        cubes = int(parse_number(app.potential_cubes_var.get(), field_name="Cubes available"))
        app.potential_cubes_var.set(str(max(0, cubes - 1)))
        return True
    except Exception:
        return False


def _selected_post_reroll_action(
    app,
    *,
    profile,
    displayed_stats,
    current_lines: Sequence[PotentialLine],
    main_stat: str,
    score_fn,
) -> str:
    slot = app.potential_selected_slot_var.get()
    rarity = app.potential_current_rarity_var.get()
    rate_profile = getattr(app, "potential_rate_profile", PotentialRateProfile())
    if not rate_profile.has_complete_table(slot, rarity):
        return "Exact stop/continue odds are unavailable for this slot and rarity; do not treat the headroom estimate as a safe reroll recommendation."
    try:
        cubes = max(0, int(float(app.potential_cubes_var.get().replace(",", ""))))
        minimum_gain = max(0.0, float(app.potential_min_gain_var.get().replace(",", "")))
        progress = int(float(app.potential_current_progress_var.get() or 0))
        progress_total = int(float(app.potential_current_progress_total_var.get() or 0))
        analysis = analyze_configured_rates(
            displayed_stats,
            profile.target,
            slot=slot,
            rarity=rarity,
            current_lines=current_lines,
            minimum_gain_pct=minimum_gain,
            cubes=cubes,
            main_stat_name=main_stat,
            score_fn=score_fn,
            profile=rate_profile,
            progress=progress,
            progress_total=progress_total,
            include_rank_aware=True,
        )
    except Exception as exc:
        return f"Could not calculate the next stop/continue decision: {exc}"

    if cubes <= 0:
        action = "STOP FOR NOW — no cubes remain."
    elif analysis.optimal_policy_available:
        if analysis.optimal_should_reroll:
            action = (
                "CONTINUE ROLLING — the finite-budget optimal stopping policy has positive modeled value. "
                f"Expected final change from rerolling is {analysis.optimal_reroll_value_gain_pct:+.3f}%."
            )
        elif analysis.optimal_cubes_to_positive_value > cubes:
            action = (
                f"STOP FOR NOW / SAVE TO ABOUT {analysis.optimal_cubes_to_positive_value} CUBES — "
                "the policy is not positive at the present budget."
            )
        else:
            action = "STOP ROLLING THIS SLOT — retaining the active roll has higher modeled value than continuing."
        return (
            f"{action} If you force another reroll and then follow the policy: "
            f"{analysis.optimal_chance_end_better * 100:.1f}% end better, "
            f"{analysis.optimal_chance_end_worse * 100:.1f}% end worse. "
            f"Next-roll raw risk is {analysis.better_probability * 100:.1f}% better / "
            f"{analysis.worse_probability * 100:.1f}% worse."
        )

    if analysis.expected_final_gain_with_budget <= 0.0:
        action = "STOP ROLLING THIS SLOT — the available fallback calculation has non-positive final value."
    elif analysis.chance_with_budget < 0.35 and analysis.cubes_for_50pct_success > cubes:
        action = f"STOP FOR NOW / SAVE TO ABOUT {analysis.cubes_for_50pct_success} CUBES — the current session is low probability."
    else:
        action = "CONTINUE WITH CAUTION — full optimal stopping is unavailable, but the fallback session value is positive."
    return (
        f"{action} Next reroll: {analysis.better_probability * 100:.1f}% better, "
        f"{analysis.worse_probability * 100:.1f}% worse; expected immediate change "
        f"{analysis.expected_net_gain_per_cube:+.3f}%."
    )

def _commit_candidate_as_current(
    app,
    *,
    parse_number: Callable[..., float],
    score_fn: Callable[[object, object], float],
    class_main_stat: Dict[str, str],
    previous_snapshot: Optional[Dict[str, object]] = None,
    cube_already_deducted: bool = False,
    record_observation: bool = True,
) -> bool:
    """Record a reroll as the active state; the previous roll is not recoverable."""
    try:
        profile = app.collect_profile()
        displayed_stats = _potential_stats(app, profile)
        previous = previous_snapshot or _snapshot_current(app, parse_number)
        previous_lines = list(previous.get("lines", []))
        candidate = _line_vars_to_models(app.potential_candidate_line_vars, parse_number, "Detected reroll")
        minimum_gain = max(0.0, parse_number(app.potential_min_gain_var.get(), field_name="Minimum improvement"))
        main_stat = class_main_stat.get(profile.stats.character_class, "")
        comparison = compare_rolls(
            displayed_stats,
            profile.target,
            previous_lines,
            candidate,
            main_stat,
            score_fn,
        )
        updated_stats, update_warnings = stats_after_replacing_roll(
            displayed_stats,
            previous_lines,
            candidate,
            main_stat,
        )
        if not cube_already_deducted:
            _deduct_reroll_cube(app, parse_number)

        slot = app.potential_selected_slot_var.get()
        state = app.potential_slots_state[slot]
        candidate_rarity = app.potential_candidate_rarity_var.get()
        signature = roll_signature(candidate_rarity, candidate)
        qualifies = comparison.gain_pct >= minimum_gain - 1e-12
        if record_observation:
            state["observed_rolls"] = int(state.get("observed_rolls", 0)) + 1
            if qualifies:
                state["observed_improvements"] = int(state.get("observed_improvements", 0)) + 1
            signatures = list(state.get("observed_signatures", []))
            signatures.append(signature)
            state["observed_signatures"] = signatures[-500:]

        history = list(state.get("reroll_history", []))
        history.append({
            "previous_rarity": str(previous.get("rarity", "")),
            "previous_lines": [_serialize_line(line) for line in previous_lines],
            "new_rarity": candidate_rarity,
            "new_lines": [_serialize_line(line) for line in candidate],
            "gain_pct": comparison.gain_pct,
        })
        state["reroll_history"] = history[-50:]

        for current_row, line in zip(app.potential_current_line_vars, candidate):
            _set_row_from_line(current_row, line)
        app.potential_current_rarity_var.set(candidate_rarity)
        app.potential_current_progress_var.set(app.potential_candidate_progress_var.get())
        app.potential_current_progress_total_var.set(app.potential_candidate_progress_total_var.get())
        state["configured"] = True
        _store_selected_slot(app)
        app.potential_effective_stats_override = updated_stats
        app.potential_last_candidate_signature = signature
        app.potential_last_comparison = comparison
        app.potential_pending_previous_snapshot = None
        app.potential_pending_reroll_cube_deducted = False
        app.potential_candidate_origin = "committed_reroll"
        app.potential_candidate_context_var.set(
            "LAST DETECTED REROLL — already saved as the active current Potential."
        )
        _set_review_button_state(app, False)
        _set_reroll_button_state(app, False, "Reroll Already Recorded")

        if qualifies:
            title = "NEW CURRENT — STOPPING TARGET REACHED"
        elif comparison.gain_pct > 0.0:
            title = "NEW CURRENT — SMALL IMPROVEMENT"
        elif comparison.gain_pct < 0.0:
            title = "NEW CURRENT — VALUE DECREASED"
        else:
            title = "NEW CURRENT — APPROXIMATELY EQUAL"
        next_action = _selected_post_reroll_action(
            app,
            profile=profile,
            displayed_stats=updated_stats,
            current_lines=candidate,
            main_stat=main_stat,
            score_fn=score_fn,
        )
        details = [
            f"This reroll is now active and is estimated at {comparison.gain_pct:+.3f}% versus the immediately previous roll.",
            "The previous roll is no longer available in game; it is retained only in session history.",
            next_action,
            f"Modeled lines: previous {comparison.modeled_current_lines}/3; current {comparison.modeled_candidate_lines}/3.",
        ]
        warnings = tuple(dict.fromkeys(comparison.warnings + update_warnings))
        if warnings:
            details.append("Unmodeled/utility lines: " + " ".join(warnings))
        details.append("The planner advanced its internal modeled stats for this session. Resync Character Stats after the cubing session for permanent accuracy.")
        app.potential_result_title_var.set(title)
        app.potential_result_detail_var.set("\n".join(details))
        _update_observed_odds(app)
        _schedule_priority_refresh(app, 20)
        return True
    except Exception as exc:
        messagebox.showerror("Record reroll", str(exc), parent=app)
        return False


def _begin_reroll_review(
    app,
    result: PotentialOCRResult,
    *,
    parse_number: Callable[..., float],
    deduct_cube: bool,
    reason: str,
) -> None:
    try:
        app.potential_pending_previous_snapshot = _snapshot_current(app, parse_number)
    except Exception:
        app.potential_pending_previous_snapshot = None
    app.potential_pending_reroll_cube_deducted = bool(deduct_cube and _deduct_reroll_cube(app, parse_number))
    _fill_candidate(app, result, context="reroll_review", review_reason=reason)
    app.potential_result_title_var.set("REROLL OCR REVIEW — OLD ROLL UNAVAILABLE")
    app.potential_result_detail_var.set(
        "The game has already replaced the previous Potential. Correct the detected fields, then press "
        "Record Corrected Reroll as Current. The optimizer will not pretend the previous roll can be restored."
    )


def process_current_image(
    app,
    image,
    *,
    executable,
    tessdata,
    parse_number,
    score_fn,
    class_main_stat: Dict[str, str],
    start_auto_scan: bool = False,
) -> bool:
    """OCR and save the visible current Potential, optionally starting monitoring from that exact frame."""
    stop_auto_monitor(app)
    images = list(image) if isinstance(image, (list, tuple)) else [image]
    if not images:
        raise ValueError("No screen captures were provided.")
    if app.potential_capture_region is None:
        if not calibrate_capture(app, image=images[0]):
            return False
    assert app.potential_capture_region is not None
    cropped_images = [_prepare_capture_panel(frame, app.potential_capture_region) for frame in images]
    if len(cropped_images) >= 2:
        result = read_potential_consensus(
            cropped_images,
            executable,
            tessdata,
            equipment_slot=app.potential_selected_slot_var.get(),
            expected_rarity="",
        )
    else:
        result = read_potential_image(
            cropped_images[0],
            executable,
            tessdata,
            equipment_slot=app.potential_selected_slot_var.get(),
            expected_rarity="",
        )
    if not result.complete or result.confidence < 0.62:
        reasons = []
        if not result.rarity:
            reasons.append("rarity was not recognized")
        if len(result.lines) != 3:
            reasons.append(f"only {len(result.lines)} of 3 lines were recognized")
        if result.confidence < 0.62:
            reasons.append(f"confidence was {result.confidence * 100:.0f}%")
        reason_text = "; ".join(reasons) or "the OCR result needs confirmation"
        _fill_candidate(app, result, context="current_review", review_reason=f"Not saved automatically because {reason_text}.")
        app.potential_result_title_var.set("CURRENT SCAN REVIEW")
        app.potential_result_detail_var.set(
            "This is still a current-Potential scan, not a reroll. Correct the review fields and press "
            "Save Corrected as Current. No cube was deducted and no reroll was recorded."
        )
        return False
    apply_scanned_current(app, result)
    fingerprint = region_fingerprint(cropped_images[-1])
    app.potential_monitor_baseline_fingerprint = fingerprint
    if start_auto_scan:
        start_auto_monitor(
            app,
            executable=executable,
            tessdata=tessdata,
            parse_number=parse_number,
            score_fn=score_fn,
            class_main_stat=class_main_stat,
            baseline_fingerprint=fingerprint,
            baseline_signature=_ocr_result_signature(result),
        )
    return True


def apply_current_ocr_result(
    app,
    result: PotentialOCRResult,
    cropped_image: Image.Image,
    *,
    executable,
    tessdata,
    parse_number,
    score_fn,
    class_main_stat: Dict[str, str],
    start_auto_scan: bool = False,
) -> bool:
    """Apply a background OCR result on the Tk main thread."""
    if not result.complete or result.confidence < 0.62:
        reasons = []
        if not result.rarity:
            reasons.append("rarity was not recognized")
        if len(result.lines) != 3:
            reasons.append(f"only {len(result.lines)} of 3 lines were recognized")
        if result.confidence < 0.62:
            reasons.append(f"confidence was {result.confidence * 100:.0f}%")
        reason_text = "; ".join(reasons) or "the OCR result needs confirmation"
        _fill_candidate(app, result, context="current_review", review_reason=f"Not saved automatically because {reason_text}.")
        app.potential_result_title_var.set("CURRENT SCAN REVIEW")
        app.potential_result_detail_var.set(
            "This is still a current-Potential scan, not a reroll. Correct the review fields and press "
            "Save Corrected as Current. No cube was deducted and no reroll was recorded."
        )
        return False
    apply_scanned_current(app, result)
    fingerprint = region_fingerprint(cropped_image)
    app.potential_monitor_baseline_fingerprint = fingerprint
    if start_auto_scan:
        start_auto_monitor(
            app,
            executable=executable,
            tessdata=tessdata,
            parse_number=parse_number,
            score_fn=score_fn,
            class_main_stat=class_main_stat,
            baseline_fingerprint=fingerprint,
            baseline_signature=_ocr_result_signature(result),
        )
    return True


def apply_new_ocr_result(
    app,
    result: PotentialOCRResult,
    *,
    parse_number,
    score_fn,
    class_main_stat: Dict[str, str],
    deduct_cube: bool,
    record_observation: bool,
) -> bool:
    """Apply a detected reroll; reliable reads immediately become current."""
    _fill_candidate(app, result, context="manual_entry")
    if not result.complete or result.confidence < 0.62:
        _begin_reroll_review(
            app,
            result,
            parse_number=parse_number,
            deduct_cube=deduct_cube,
            reason=(
                f"OCR confidence was {result.confidence * 100:.0f}% or one or more fields were missing. "
                "Automatic scanning pauses until this active result is corrected."
            ),
        )
        return False
    previous = _snapshot_current(app, parse_number)
    cube_deducted = bool(deduct_cube and _deduct_reroll_cube(app, parse_number))
    return _commit_candidate_as_current(
        app,
        parse_number=parse_number,
        score_fn=score_fn,
        class_main_stat=class_main_stat,
        previous_snapshot=previous,
        cube_already_deducted=cube_deducted,
        record_observation=record_observation,
    )


def process_image(
    app,
    image,
    *,
    executable,
    tessdata,
    parse_number,
    score_fn,
    class_main_stat: Dict[str, str],
    deduct_cube: bool,
    record_observation: bool,
) -> None:
    images = list(image) if isinstance(image, (list, tuple)) else [image]
    if not images:
        return
    if app.potential_capture_region is None:
        if not calibrate_capture(app, image=images[0]):
            return
    assert app.potential_capture_region is not None
    try:
        cropped_images = [_prepare_capture_panel(frame, app.potential_capture_region) for frame in images]
        if len(cropped_images) >= 2:
            result = read_potential_consensus(
                cropped_images,
                executable,
                tessdata,
                equipment_slot=app.potential_selected_slot_var.get(),
                expected_rarity=app.potential_current_rarity_var.get(),
            )
        else:
            result = read_potential_image(
                cropped_images[0],
                executable,
                tessdata,
                equipment_slot=app.potential_selected_slot_var.get(),
                expected_rarity=app.potential_current_rarity_var.get(),
            )
    except Exception as exc:
        messagebox.showerror("Potential OCR failed", str(exc), parent=app)
        return
    apply_new_ocr_result(
        app,
        result,
        parse_number=parse_number,
        score_fn=score_fn,
        class_main_stat=class_main_stat,
        deduct_cube=deduct_cube,
        record_observation=record_observation,
    )


def compare_candidate(
    app,
    *,
    parse_number: Callable[..., float],
    score_fn: Callable[[object, object], float],
    class_main_stat: Dict[str, str],
    record_observation: bool = False,
) -> None:
    """Preview a difference only; it never implies the old roll can be restored."""
    try:
        profile = app.collect_profile()
        displayed_stats = _potential_stats(app, profile)
        previous_snapshot = getattr(app, "potential_pending_previous_snapshot", None)
        current = (
            list(previous_snapshot.get("lines", []))
            if isinstance(previous_snapshot, dict)
            else _line_vars_to_models(app.potential_current_line_vars, parse_number, "Current Potential")
        )
        candidate = _line_vars_to_models(app.potential_candidate_line_vars, parse_number, "Detected reroll")
        minimum_gain = parse_number(app.potential_min_gain_var.get(), field_name="Minimum improvement")
        if minimum_gain < 0:
            raise ValueError("Minimum improvement cannot be negative.")
        main_stat = class_main_stat.get(profile.stats.character_class, "")
        comparison = compare_rolls(
            displayed_stats,
            profile.target,
            current,
            candidate,
            main_stat,
            score_fn,
        )
        app.potential_last_comparison = comparison
        app.potential_last_candidate_signature = roll_signature(app.potential_candidate_rarity_var.get(), candidate)
        qualifies = comparison.gain_pct >= minimum_gain - 1e-12
        if qualifies:
            title = "REROLL PREVIEW — STOPPING TARGET REACHED"
            intro = f"Estimated {comparison.gain_pct:+.3f}% versus the immediately previous roll."
        elif comparison.gain_pct > 0:
            title = "REROLL PREVIEW — SMALL IMPROVEMENT"
            intro = (
                f"Estimated {comparison.gain_pct:+.3f}% improvement, below the "
                f"{minimum_gain:g}% stopping threshold."
            )
        elif comparison.gain_pct < 0:
            title = "REROLL PREVIEW — WORSE RESULT"
            intro = f"Estimated {comparison.gain_pct:.3f}% versus the immediately previous roll."
        else:
            title = "REROLL PREVIEW — APPROXIMATELY EQUAL"
            intro = "The entered three-line result is approximately equal to the immediately previous roll."
        details = [
            intro,
            "This preview does not preserve the previous roll. Once a cube is used, the detected result is the active current Potential.",
            f"Modeled lines: previous {comparison.modeled_current_lines}/3; entered {comparison.modeled_candidate_lines}/3.",
        ]
        if comparison.warnings:
            details.append("Unmodeled/utility lines: " + " ".join(comparison.warnings))
        if getattr(app, "potential_candidate_origin", "") == "reroll_review":
            details.append("Correct the OCR fields, then press Record Corrected Reroll as Current.")
        else:
            details.append("Press Record Entered Reroll as Current only when this reroll has actually occurred in game.")
        app.potential_result_title_var.set(title)
        app.potential_result_detail_var.set("\n".join(details))
    except Exception as exc:
        messagebox.showerror("Potential comparison", str(exc), parent=app)


def save_current(app) -> None:
    _store_selected_slot(app)
    slot = app.potential_selected_slot_var.get()
    app.potential_slots_state[slot]["configured"] = True
    app.potential_capture_status_var.set(f"Saved current Potential for {slot}.")
    _schedule_priority_refresh(app, 20)


def accept_candidate(
    app,
    *,
    parse_number: Callable[..., float],
    score_fn: Callable[[object, object], float],
    class_main_stat: Dict[str, str],
) -> None:
    if getattr(app, "potential_candidate_origin", "") == "current_review":
        messagebox.showinfo(
            "Current scan review",
            "Use Save Corrected as Current for an initial current-Potential scan.",
            parent=app,
        )
        return
    if getattr(app, "potential_candidate_origin", "") == "committed_reroll":
        messagebox.showinfo(
            "Reroll already recorded",
            "This detected reroll is already the active current Potential. Edit the Current Active Potential panel to correct it.",
            parent=app,
        )
        return
    pending = getattr(app, "potential_pending_previous_snapshot", None)
    cube_deducted = bool(getattr(app, "potential_pending_reroll_cube_deducted", False))
    _commit_candidate_as_current(
        app,
        parse_number=parse_number,
        score_fn=score_fn,
        class_main_stat=class_main_stat,
        previous_snapshot=pending,
        cube_already_deducted=cube_deducted,
        record_observation=True,
    )


def reset_history(app) -> None:
    slot = app.potential_selected_slot_var.get()
    state = app.potential_slots_state[slot]
    state["configured"] = True
    state["observed_rolls"] = 0
    state["observed_improvements"] = 0
    state["observed_signatures"] = []
    app.potential_last_candidate_signature = ""
    _update_observed_odds(app)


def _update_observed_odds(app) -> None:
    slot = app.potential_selected_slot_var.get()
    state = app.potential_slots_state.get(slot, {})
    trials = int(state.get("observed_rolls", 0))
    successes = int(state.get("observed_improvements", 0))
    try:
        cubes = max(0, int(float(app.potential_cubes_var.get().replace(",", ""))))
    except Exception:
        cubes = 0
    exact_text = str(getattr(app, "potential_exact_odds_text", "") or "").strip()
    if trials == 0:
        observed = "Observed session rerolls: none recorded yet."
    else:
        p = successes / trials
        low, high = wilson_interval(successes, trials)
        chance = chance_with_budget(p, cubes)
        reliability = "very limited" if trials < 10 else "early" if trials < 30 else "developing" if trials < 100 else "stronger"
        observed = (
            f"Observed immediate-step improvement rate: {successes}/{trials} ({p * 100:.1f}%; 95% interval {low * 100:.1f}–{high * 100:.1f}%). "
            f"Treating those step-to-step results as a rough sample, chance within {cubes} remaining cube(s): {chance * 100:.1f}%. Sample confidence is {reliability}."
        )
    app.potential_odds_var.set(f"{exact_text}\n{observed}" if exact_text else observed)

# ---------------------------------------------------------------------------
# Equipment-wide priority and automatic stable-region monitoring
# ---------------------------------------------------------------------------


def _format_expected_cubes(value: float) -> str:
    if not math.isfinite(value):
        return "never at this threshold"
    if value < 10:
        return f"{value:.1f}"
    return f"{value:.0f}"


def _format_condition(condition) -> str:
    lines = "/".join(str(number) for number in condition.line_numbers) or "any"
    return (
        f"{condition.stat_name} ≥ {condition.display_value} (line {lines}; "
        f"covers {condition.success_coverage * 100:.1f}% of acceptable rolls; "
        f"{condition.precision * 100:.1f}% of rolls triggering it are acceptable)"
    )


def _format_exact_outcome(outcome) -> str:
    lines = " + ".join(f"{line.stat_name} {line.display_value}" for line in outcome.lines)
    return f"{lines} — {outcome.gain_pct:+.2f}% estimated gain; exact roll chance {outcome.probability * 100:.4f}%"


def _set_exact_selected_guidance(app, exact_priorities, exact_by_slot, cubes: int, guidance_analysis=None) -> None:
    selected = app.potential_selected_slot_var.get()
    analysis = guidance_analysis or exact_by_slot.get(selected)
    if analysis is None:
        app.potential_exact_odds_text = ""
        app.potential_stopping_rules_var.set(
            "No exact stopping guide is available for this selected slot/rank. "
            "Collect all three Option Rates tables or select a slot with complete bundled coverage."
        )
        app.potential_rank_aware_plan_var.set(
            "Rank-aware cube planning is unavailable because this slot/rank does not have a complete configured-rate table."
        )
        _update_observed_odds(app)
        return

    top = exact_priorities[0] if exact_priorities else None
    top_slot = top.slot if top is not None else selected
    policy_available = bool(getattr(analysis, "optimal_policy_available", False))
    should_reroll = bool(getattr(analysis, "optimal_should_reroll", False))
    save_to = int(getattr(analysis, "optimal_cubes_to_positive_value", 0) or 0)

    if cubes <= 0:
        action = "STOP FOR NOW — no cubes remain."
    elif policy_available and not should_reroll:
        if top is not None and top_slot != selected and top.expected_final_gain_with_budget > 0.0:
            action = f"STOP THIS SLOT / MOVE TO {top_slot.upper()} — risking the selected roll is not worthwhile at this budget."
        elif save_to > cubes:
            action = (
                f"STOP FOR NOW / SAVE TO ABOUT {save_to} CUBES — the finite-budget stopping policy first becomes "
                "positive at that budget. Saving does not change the odds of an individual cube."
            )
        else:
            action = "STOP ROLLING THIS SLOT — retaining the active result has higher modeled value than risking it."
    elif policy_available and should_reroll:
        action = "ROLL THIS SLOT — rerolling and following the Stop/Continue policy has positive expected final value."
    elif analysis.expected_final_gain_with_budget <= 0.0:
        action = "STOP ROLLING THIS SLOT — the available exact-risk fallback has non-positive expected final value."
    elif selected != top_slot:
        action = f"STOP / MOVE TO {top_slot.upper()} — that slot has the better modeled irreversible-session value."
    else:
        action = "ROLL THIS SLOT — exact rates show positive modeled session value, but the full optimal policy is unavailable."

    warning = ""
    if analysis.modeled_probability_mass < 0.999:
        warning = (
            f" Only {analysis.modeled_probability_mass * 100:.1f}% of result probability is fully modeled for direct damage; "
            "utility options may change the true decision."
        )

    rank_text = ""
    if analysis.next_rarity:
        rank_text = (
            f" Rank-up toward {analysis.next_rarity}: {analysis.rank_up_probability_per_cube * 100:.3f}% early chance per cube, "
            f"{analysis.chance_to_rank_up_with_budget * 100:.1f}% chance within this budget, "
            f"guaranteed in at most {analysis.cubes_to_guaranteed_rank_up} cube(s)."
        )
        if analysis.next_rarity_success_probability <= 0.0:
            rank_text += " Next-rarity outcome odds are unavailable because that table has not been collected."

    immediate = (
        f"NEXT IRREVERSIBLE REROLL ({selected}, {analysis.rarity}): "
        f"{analysis.better_probability * 100:.2f}% better, {analysis.equal_probability * 100:.2f}% approximately equal, "
        f"{analysis.worse_probability * 100:.2f}% worse; severe loss (−5% or more) "
        f"{analysis.severe_loss_probability * 100:.2f}%. Expected immediate change: "
        f"{analysis.expected_net_gain_per_cube:+.4f}%; median result: {analysis.median_gain_pct:+.3f}%. "
    )
    threshold = (
        f"A result at least {analysis.minimum_gain_pct:g}% better appears on "
        f"{analysis.success_probability * 100:.3f}% of current-rarity rolls; fixed-rarity chance within {cubes} cube(s): "
        f"{analysis.chance_with_budget * 100:.1f}%. "
    )
    if policy_available:
        policy = (
            f"OPTIMAL STOPPING POLICY: if you choose to reroll and then stop/continue optimally, modeled expected final "
            f"change is {analysis.optimal_reroll_value_gain_pct:+.3f}%; chance to end better "
            f"{analysis.optimal_chance_end_better * 100:.1f}%, equal {analysis.optimal_chance_end_equal * 100:.1f}%, "
            f"worse {analysis.optimal_chance_end_worse * 100:.1f}%. {action}"
        )
    else:
        policy = f"OPTIMAL STOPPING POLICY UNAVAILABLE: {analysis.optimal_policy_note or 'future-rarity coverage is incomplete.'} {action}"
    app.potential_exact_odds_text = immediate + threshold + policy + rank_text + warning

    conditions = tuple(getattr(analysis, "stopping_conditions", ()))
    exact_outcomes = tuple(getattr(analysis, "top_exact_outcomes", ()))
    if conditions:
        condition_lines = "\n".join(
            f"{index}. {_format_condition(condition)}"
            for index, condition in enumerate(conditions, start=1)
        )
        coverage_mass = getattr(analysis, "stopping_condition_coverage", 0.0)
        coverage = coverage_mass / analysis.success_probability if analysis.success_probability > 0.0 else 0.0
        stopping_text = (
            "SUGGESTED PREFERRED-OPTION WATCHLIST\n"
            f"{condition_lines}\n"
            f"Together these alerts cover about {coverage * 100:.1f}% of rolls satisfying the full "
            f"{analysis.minimum_gain_pct:g}% threshold. They only tell you to look at the roll. The old result is already gone, "
            "so let the automatic complete-roll Stop/Continue checker decide whether to reroll again."
        )
    else:
        stopping_text = (
            "No single option cleanly identifies the desirable complete results at this threshold. "
            "Use automatic OCR and the complete-roll Stop/Continue recommendation after every reroll."
        )
    if exact_outcomes:
        examples = "\n".join(
            f"{index}. {_format_exact_outcome(outcome)}"
            for index, outcome in enumerate(exact_outcomes, start=1)
        )
        stopping_text += "\n\nREPRESENTATIVE HIGH-VALUE COMPLETE RESULTS\n" + examples
    app.potential_stopping_rules_var.set(stopping_text)

    if policy_available:
        stop_threshold = getattr(analysis, "optimal_next_stop_threshold_gain_pct", math.nan)
        threshold_text = (
            "On a non-rank-up next roll, the policy will recalculate from the newly active result."
            if not math.isfinite(stop_threshold)
            else f"With the remaining budget, a non-rank-up next result around {stop_threshold:+.3f}% or better versus the present roll is worth stopping on immediately; weaker results are candidates to reroll again."
        )
        app.potential_rank_aware_plan_var.set(
            f"FINITE-BUDGET IRREVERSIBLE PLAN: {threshold_text} The policy includes early and guaranteed rank-up branches. "
            f"{analysis.optimal_policy_note}"
        )
    else:
        rank_aware_chance = getattr(analysis, "rank_aware_chance_with_budget", analysis.chance_with_budget)
        app.potential_rank_aware_plan_var.set(
            f"RANK-AWARE THRESHOLD FALLBACK: estimated chance of reaching the selected threshold within {cubes} cube(s) is "
            f"{rank_aware_chance * 100:.1f}%. This is not a complete Stop/Continue policy because future-rate coverage is incomplete."
        )
    _update_observed_odds(app)

def refresh_priority(
    app,
    *,
    parse_number: Callable[..., float],
    score_fn: Callable[[object, object], float],
    class_main_stat: Dict[str, str],
) -> None:
    try:
        _store_selected_slot(app)
        profile = app.collect_profile()
        displayed_stats = _potential_stats(app, profile)
        main_stat = class_main_stat.get(profile.stats.character_class, "")
        cubes = max(0, int(parse_number(app.potential_cubes_var.get(), field_name="Cubes available")))
        minimum_gain = float(parse_number(app.potential_min_gain_var.get(), field_name="Minimum improvement"))
        if minimum_gain < 0:
            raise ValueError("Minimum improvement cannot be negative.")

        eligible: List[str] = []
        excluded: List[Tuple[str, str]] = []
        for slot, state in app.potential_slots_state.items():
            is_eligible, reason = slot_eligibility(state)
            if is_eligible:
                eligible.append(slot)
            else:
                excluded.append((slot, reason))

        rate_profile = getattr(app, "potential_rate_profile", PotentialRateProfile())
        exact_priorities = rank_slots_by_configured_rates(
            displayed_stats,
            profile.target,
            app.potential_slots_state,
            minimum_gain_pct=minimum_gain,
            cubes=cubes,
            main_stat_name=main_stat,
            score_fn=score_fn,
            profile=rate_profile,
            eligibility_fn=slot_eligibility,
        )
        exact_by_slot = {item.slot: item for item in exact_priorities}
        guidance_analysis = None
        selected_slot = app.potential_selected_slot_var.get()
        selected_state = app.potential_slots_state.get(selected_slot, {})
        selected_rarity = str(selected_state.get("rarity", "Rare"))
        if (
            selected_slot in eligible
            and rate_profile.has_complete_table(selected_slot, selected_rarity)
        ):
            try:
                selected_progress = int(float(selected_state.get("progress", 0) or 0))
                selected_total = int(float(selected_state.get("progress_total", 0) or 0))
            except (TypeError, ValueError):
                selected_progress = selected_total = 0
            guidance_analysis = analyze_configured_rates(
                displayed_stats,
                profile.target,
                slot=selected_slot,
                rarity=selected_rarity,
                current_lines=_deserialize_lines(selected_state.get("lines", [])),
                minimum_gain_pct=minimum_gain,
                cubes=cubes,
                main_stat_name=main_stat,
                score_fn=score_fn,
                profile=rate_profile,
                progress=selected_progress,
                progress_total=selected_total,
                include_guidance=True,
                include_rank_aware=True,
            )

        if exact_priorities:
            top = exact_priorities[0]
            if top.expected_final_gain_with_budget <= 0.0:
                app.potential_priority_title_var.set("STOP — CURRENT ROLLS ARE TOO RISKY")
            elif top.recommendation == "PUSH RANK-UP" and top.next_rarity:
                app.potential_priority_title_var.set(f"PUSH {top.slot.upper()} TO {top.next_rarity.upper()}")
            elif top.recommendation == "SAVE FOR 50% SESSION":
                app.potential_priority_title_var.set(
                    f"SAVE TO {top.cubes_for_50pct_success} CUBES, THEN RECHECK {top.slot.upper()}"
                )
            else:
                app.potential_priority_title_var.set(f"LOWEST MODELED RISK/REWARD TARGET: {top.slot}")
            for index, variable in enumerate(app.potential_priority_rows_vars):
                if index >= len(exact_priorities):
                    variable.set("—")
                    continue
                item = exact_priorities[index]
                expected = _format_expected_cubes(item.expected_cubes_to_success)
                rank_summary = ""
                if item.next_rarity:
                    rank_summary = (
                        f" • rank-up {item.chance_to_rank_up_with_budget * 100:.1f}% within budget"
                        f" / guarantee ≤{item.cubes_to_guaranteed_rank_up}"
                    )
                save_summary = (
                    f" • 50% session ≈{item.cubes_for_50pct_success} cubes"
                    if item.cubes_for_50pct_success > 0
                    else ""
                )
                variable.set(
                    f"{index + 1}. {item.slot} ({item.rarity}) — {item.recommendation}\n"
                    f"   Next reroll: {item.better_probability * 100:.1f}% better / {item.worse_probability * 100:.1f}% worse • "
                    f"immediate EV {item.expected_net_gain_per_cube:+.3f}% • threshold within {cubes}: "
                    f"{item.chance_with_budget * 100:.1f}% • session final EV {item.expected_final_gain_with_budget:+.3f}% • "
                    f"end-worse risk {item.chance_end_worse_with_budget * 100:.1f}%"
                    f"{rank_summary}{save_summary}"
                )
            missing_exact = [
                slot for slot in eligible
                if not rate_profile.has_complete_table(slot, str(app.potential_slots_state[slot].get("rarity", "Rare")))
            ]
            diagnostics = [
                f"Exact configured-rate analysis covers {len(exact_priorities)} of {len(eligible)} eligible slot(s).",
                "The ranking includes the downside of irreversible rerolls and orders slots by modeled final session value, not positive outcomes alone.",
                "Current-rarity improvement odds and rank-up odds are shown separately; the selected-slot panel performs the full finite-budget Stop/Continue calculation.",
                "A Save recommendation means the current budget is not yet attractive; waiting does not change any individual cube's probability.",
            ]
            if missing_exact:
                diagnostics.append("Missing complete rates for: " + ", ".join(missing_exact) + ".")
            app.potential_priority_note_var.set(" ".join(diagnostics))
            _set_exact_selected_guidance(
                app,
                exact_priorities,
                exact_by_slot,
                cubes,
                guidance_analysis=guidance_analysis,
            )
            return

        # No applicable complete configured table: retain the transparent
        # headroom estimator rather than fabricating exact rates.
        app.potential_exact_odds_text = ""
        app.potential_stopping_rules_var.set(
            "No exact stopping guide is available for the selected slot/rank because its configured-rate table is incomplete."
        )
        app.potential_rank_aware_plan_var.set(
            "Rank-aware planning requires complete line 1, line 2, and line 3 Option Rates for the selected slot/rank."
        )
        priorities = rank_equipment_slots(
            displayed_stats,
            profile.target,
            app.potential_slots_state,
            main_stat,
            score_fn,
        )
        if not priorities:
            app.potential_priority_title_var.set("NO ELIGIBLE POTENTIAL SLOTS YET")
            for variable in app.potential_priority_rows_vars:
                variable.set("—")
            exclusion_preview = "; ".join(f"{slot}: {reason}" for slot, reason in excluded[:5])
            app.potential_priority_note_var.set(
                f"0 eligible slots; {len(excluded)} excluded. "
                "Scan and save a current Potential, or mark an available slot Unlocked. "
                + (f"Examples: {exclusion_preview}." if exclusion_preview else "")
            )
            _update_observed_odds(app)
            return

        app.potential_priority_title_var.set(f"CUBE THIS NEXT (HEADROOM): {priorities[0].slot}")
        for index, variable in enumerate(app.potential_priority_rows_vars):
            if index >= len(priorities):
                variable.set("—")
                continue
            item = priorities[index]
            special = ""
            if item.special_option and item.special_value > 0:
                special = f" • {item.special_option} target {item.special_value:g}"
            variable.set(
                f"{index + 1}. {item.slot} — current modeled contribution {item.current_gain_pct:+.2f}%"
                f"{special}\n   {item.reason} [{item.confidence}]"
            )

        locked_names = [slot for slot, reason in excluded if reason == "marked locked"]
        incomplete_names = [slot for slot, reason in excluded if "incomplete" in reason or "no current" in reason]
        auto_zero_names = [slot for slot, reason in excluded if "all three values are zero" in reason]
        diagnostics = [f"{len(eligible)} eligible slot(s); {len(excluded)} excluded."]
        if locked_names:
            diagnostics.append("Locked: " + ", ".join(locked_names) + ".")
        if auto_zero_names:
            diagnostics.append("Auto-ignored as not unlocked: " + ", ".join(auto_zero_names) + ".")
        if incomplete_names:
            diagnostics.append("Incomplete: " + ", ".join(incomplete_names) + ".")
        if len(eligible) < 3:
            diagnostics.append("Scan more available equipment slots before treating this as a complete equipment-wide recommendation.")
        diagnostics.append(
            "No complete configured-rate table applies to the saved slot rarities, so this is a headroom estimate. "
            "Import configured Option Rates to unlock exact irreversible-reroll risk and Stop/Continue guidance."
        )
        app.potential_priority_note_var.set(" ".join(diagnostics))
        _update_observed_odds(app)
    except Exception as exc:
        app.potential_exact_odds_text = ""
        app.potential_priority_title_var.set("COULD NOT CALCULATE EQUIPMENT PRIORITY")
        app.potential_priority_rows_vars[0].set(str(exc))
        for variable in app.potential_priority_rows_vars[1:]:
            variable.set("—")
        app.potential_priority_note_var.set(
            "The priority calculation failed visibly rather than leaving the panel blank. Review the error above."
        )
        _update_observed_odds(app)

def _current_monitor_result_signature(app) -> str:
    try:
        lines = [
            PotentialLine(
                row["stat"].get(),
                float(row["value"].get().replace(",", "")),
                _unit_value(row.get("unit").get()) if row.get("unit") is not None else "",
            )
            for row in app.potential_current_line_vars
        ]
    except Exception:
        lines = []
    result = PotentialOCRResult(
        rarity=app.potential_current_rarity_var.get(),
        progress=int(float(app.potential_current_progress_var.get() or 0)),
        progress_total=int(float(app.potential_current_progress_total_var.get() or 0)),
        lines=tuple(lines),
        raw_text="",
    )
    return _ocr_result_signature(result)


def stop_auto_monitor(app) -> None:
    if not hasattr(app, "potential_monitor_running"):
        return
    app.potential_monitor_generation += 1
    app.potential_monitor_running = False
    app.potential_monitor_busy = False
    app.potential_auto_scan_var.set(False)
    app.potential_auto_scan_button_var.set("Start Auto Scan")
    app.potential_monitor_status_var.set("Auto scan is off")
    after_id = getattr(app, "potential_monitor_after_id", None)
    if after_id:
        try:
            app.after_cancel(after_id)
        except Exception:
            pass
    app.potential_monitor_after_id = None


def _set_manual_ocr_buttons(app, enabled: bool) -> None:
    state = "normal" if enabled else "disabled"
    for name in (
        "potential_scan_current_button",
        "potential_scan_current_auto_button",
        "potential_read_live_button",
    ):
        button = getattr(app, name, None)
        if button is not None:
            try:
                button.configure(state=state)
            except Exception:
                pass


def start_manual_live_ocr(
    app,
    *,
    mode: str,
    executable,
    tessdata,
    parse_number,
    score_fn,
    class_main_stat,
) -> None:
    """Capture and OCR without blocking Tk; fast results avoid consensus work."""
    if getattr(app, "potential_manual_ocr_running", False):
        app.potential_capture_status_var.set("A Potential read is already in progress.")
        return
    if app.potential_capture_region is None:
        if not calibrate_capture(app):
            return
    if mode in {"current", "current_auto"}:
        stop_auto_monitor(app)
    app.potential_manual_ocr_generation += 1
    generation = app.potential_manual_ocr_generation
    app.potential_manual_ocr_running = True
    _set_manual_ocr_buttons(app, False)
    app.potential_capture_status_var.set(
        "Reading the Potential panel in the background… clean panels normally finish after one four-pass OCR read."
    )
    region = app.potential_capture_region
    slot = app.potential_selected_slot_var.get()
    expected_rarity = "" if mode in {"current", "current_auto"} else app.potential_current_rarity_var.get()
    started = time.monotonic()

    def worker():
        try:
            if region is None:
                raise RuntimeError("Capture region was cleared.")
            first_screen = capture_full_screen()
            first_crop = _prepare_capture_panel(first_screen, region)
            fast = read_potential_image_fast(
                first_crop,
                executable,
                tessdata,
                equipment_slot=slot,
                expected_rarity=expected_rarity,
            )
            path = "fast"
            result = fast
            final_crop = first_crop
            if not potential_result_is_reliable(fast):
                path = "verified"
                first_full = read_potential_image(
                    first_crop,
                    executable,
                    tessdata,
                    equipment_slot=slot,
                    expected_rarity=expected_rarity,
                )
                result = first_full
                if not potential_result_is_reliable(first_full, threshold=0.80):
                    time.sleep(0.12)
                    second_screen = capture_full_screen()
                    second_crop = _prepare_capture_panel(second_screen, region)
                    second_full = read_potential_image(
                        second_crop,
                        executable,
                        tessdata,
                        equipment_slot=slot,
                        expected_rarity=expected_rarity,
                    )
                    result = consensus_potential_results([first_full, second_full])
                    final_crop = second_crop
                    if not potential_result_is_reliable(result, threshold=0.72):
                        time.sleep(0.12)
                        third_screen = capture_full_screen()
                        third_crop = _prepare_capture_panel(third_screen, region)
                        third_full = read_potential_image(
                            third_crop,
                            executable,
                            tessdata,
                            equipment_slot=slot,
                            expected_rarity=expected_rarity,
                        )
                        result = consensus_potential_results([first_full, second_full, third_full])
                        final_crop = third_crop
            payload = (generation, mode, result, final_crop, path, time.monotonic() - started, "")
        except Exception as exc:
            payload = (generation, mode, None, None, "", time.monotonic() - started, str(exc))
        app.potential_manual_ocr_queue.put(payload)

    threading.Thread(target=worker, daemon=True, name="potential-manual-ocr").start()
    app.potential_manual_ocr_after_id = app.after(80, lambda: _collect_manual_live_ocr(app, executable, tessdata, parse_number, score_fn, class_main_stat))


def _collect_manual_live_ocr(app, executable, tessdata, parse_number, score_fn, class_main_stat) -> None:
    try:
        payload = app.potential_manual_ocr_queue.get_nowait()
    except Exception:
        app.potential_manual_ocr_after_id = app.after(80, lambda: _collect_manual_live_ocr(app, executable, tessdata, parse_number, score_fn, class_main_stat))
        return
    generation, mode, result, cropped, path, elapsed, error = payload
    if generation != app.potential_manual_ocr_generation:
        return
    app.potential_manual_ocr_running = False
    app.potential_manual_ocr_after_id = None
    _set_manual_ocr_buttons(app, True)
    if error:
        app.potential_capture_status_var.set(f"Potential OCR failed after {elapsed:.1f}s.")
        messagebox.showerror("Potential OCR", error, parent=app)
        return
    app.potential_capture_status_var.set(
        f"Potential read completed in {elapsed:.1f}s using the {path} OCR path."
    )
    if result is None or cropped is None:
        return
    if mode in {"current", "current_auto"}:
        saved = apply_current_ocr_result(
            app,
            result,
            cropped,
            executable=executable,
            tessdata=tessdata,
            parse_number=parse_number,
            score_fn=score_fn,
            class_main_stat=class_main_stat,
            start_auto_scan=mode == "current_auto",
        )
        if saved:
            _schedule_priority_refresh(app, 20)
    else:
        apply_new_ocr_result(
            app,
            result,
            parse_number=parse_number,
            score_fn=score_fn,
            class_main_stat=class_main_stat,
            deduct_cube=True,
            record_observation=True,
        )


def toggle_auto_monitor(
    app,
    *,
    executable,
    tessdata,
    parse_number,
    score_fn,
    class_main_stat,
) -> None:
    if app.potential_monitor_running:
        stop_auto_monitor(app)
        return
    if app.potential_capture_region is None:
        messagebox.showinfo(
            "Calibrate first",
            "Calibrate the Potential capture box before starting automatic scanning.",
            parent=app,
        )
        return
    start_auto_monitor(
        app,
        executable=executable,
        tessdata=tessdata,
        parse_number=parse_number,
        score_fn=score_fn,
        class_main_stat=class_main_stat,
    )


def start_auto_monitor(
    app,
    *,
    executable,
    tessdata,
    parse_number,
    score_fn,
    class_main_stat,
    baseline_fingerprint: bytes = b"",
    baseline_signature: str = "",
) -> None:
    """Start stable-region monitoring, optionally from a frame already scanned as current."""
    stop_auto_monitor(app)
    if app.potential_capture_region is None:
        raise RuntimeError("Calibrate the Potential capture box before starting automatic scanning.")
    app.potential_monitor_generation += 1
    app.potential_monitor_running = True
    app.potential_monitor_busy = False
    app.potential_auto_scan_var.set(True)
    app.potential_auto_scan_button_var.set("Stop Auto Scan")
    app.potential_monitor_baseline_fingerprint = baseline_fingerprint
    app.potential_monitor_pending_fingerprint = b""
    app.potential_monitor_pending_image = None
    app.potential_monitor_stable_frames = 0
    app.potential_monitor_stable_images = []
    app.potential_monitor_last_result_signature = baseline_signature or _current_monitor_result_signature(app)
    app.potential_monitor_dependencies = {
        "executable": executable,
        "tessdata": tessdata,
        "parse_number": parse_number,
        "score_fn": score_fn,
        "class_main_stat": class_main_stat,
    }
    app.potential_monitor_queue = __import__("queue").Queue()
    if baseline_fingerprint:
        app.potential_monitor_status_var.set(
            "Current Potential saved and auto scan is ready. Reroll in game; the next stable changed result will be read automatically."
        )
    else:
        app.potential_monitor_status_var.set(
            "Auto scan is starting. Leave the game on the selected Potential screen; the first stable image becomes the baseline."
        )
    _schedule_monitor_capture(app, 50)


def _schedule_monitor_capture(app, delay_ms: int = 950) -> None:
    if not app.potential_monitor_running:
        return
    app.potential_monitor_after_id = app.after(delay_ms, lambda: _start_monitor_capture(app))


def _start_monitor_capture(app) -> None:
    if not app.potential_monitor_running or app.potential_monitor_busy:
        _schedule_monitor_capture(app, 250)
        return
    app.potential_monitor_busy = True
    generation = app.potential_monitor_generation
    region = app.potential_capture_region

    def worker():
        try:
            image = capture_full_screen()
            if region is None:
                raise RuntimeError("Capture region was cleared.")
            cropped = _prepare_capture_panel(image, region)
            payload = ("capture", generation, cropped, region_fingerprint(cropped), "")
        except Exception as exc:
            payload = ("capture", generation, None, b"", str(exc))
        app.potential_monitor_queue.put(payload)

    threading.Thread(target=worker, daemon=True, name="potential-screen-monitor").start()
    app.potential_monitor_after_id = app.after(80, lambda: _collect_monitor_result(app))


def _collect_monitor_result(app) -> None:
    if not app.potential_monitor_running:
        return
    try:
        payload = app.potential_monitor_queue.get_nowait()
    except Exception:
        app.potential_monitor_after_id = app.after(80, lambda: _collect_monitor_result(app))
        return
    kind, generation, value, fingerprint, error = payload
    if generation != app.potential_monitor_generation:
        return
    app.potential_monitor_busy = False
    if error:
        app.potential_monitor_status_var.set(f"Auto scan capture failed: {error}. Retrying…")
        _schedule_monitor_capture(app, 1600)
        return
    if kind == "ocr":
        _handle_monitor_ocr(app, value, fingerprint)
        return
    _handle_monitor_capture(app, value, fingerprint)


def _handle_monitor_capture(app, cropped: Image.Image, fingerprint: bytes) -> None:
    if not app.potential_monitor_baseline_fingerprint:
        app.potential_monitor_baseline_fingerprint = fingerprint
        # Require three stable frames and OCR agreement before recording a reroll.
        app.potential_monitor_status_var.set(
            "Auto scan ready. Waiting for the Potential box to change and agree across three stable captures."
        )
        _schedule_monitor_capture(app)
        return

    changed = fingerprint_distance(app.potential_monitor_baseline_fingerprint, fingerprint)
    if changed < 3.0:
        app.potential_monitor_pending_fingerprint = b""
        app.potential_monitor_pending_image = None
        app.potential_monitor_stable_frames = 0
        app.potential_monitor_stable_images = []
        _schedule_monitor_capture(app)
        return

    if (
        app.potential_monitor_pending_fingerprint
        and fingerprint_distance(app.potential_monitor_pending_fingerprint, fingerprint) <= 2.2
    ):
        app.potential_monitor_stable_frames += 1
        app.potential_monitor_pending_image = cropped
        app.potential_monitor_pending_fingerprint = fingerprint
        app.potential_monitor_stable_images.append(cropped.copy())
    else:
        app.potential_monitor_pending_fingerprint = fingerprint
        app.potential_monitor_pending_image = cropped
        app.potential_monitor_stable_frames = 1
        app.potential_monitor_stable_images = [cropped.copy()]

    if app.potential_monitor_stable_frames < 3:
        app.potential_monitor_status_var.set(
            f"Potential box changed; waiting for stable-capture agreement ({app.potential_monitor_stable_frames}/3)…"
        )
        _schedule_monitor_capture(app, 600)
        return

    app.potential_monitor_status_var.set("Stable new Potential detected; trying the fast OCR path…")
    app.potential_monitor_busy = True
    generation = app.potential_monitor_generation
    stable_images = list(app.potential_monitor_stable_images[-3:])
    stable_fingerprint = app.potential_monitor_pending_fingerprint
    dependencies = app.potential_monitor_dependencies
    slot = app.potential_selected_slot_var.get()
    rarity = app.potential_current_rarity_var.get()

    def worker():
        try:
            result = read_potential_staged(
                stable_images,
                dependencies["executable"],
                dependencies["tessdata"],
                equipment_slot=slot,
                expected_rarity=rarity,
            )
            payload = ("ocr", generation, result, stable_fingerprint, "")
        except Exception as exc:
            payload = ("ocr", generation, None, stable_fingerprint, str(exc))
        app.potential_monitor_queue.put(payload)

    threading.Thread(target=worker, daemon=True, name="potential-ocr-monitor").start()
    app.potential_monitor_after_id = app.after(80, lambda: _collect_monitor_result(app))


def _handle_monitor_ocr(app, result: Optional[PotentialOCRResult], fingerprint: bytes) -> None:
    app.potential_monitor_baseline_fingerprint = fingerprint
    app.potential_monitor_pending_fingerprint = b""
    app.potential_monitor_pending_image = None
    app.potential_monitor_stable_frames = 0
    app.potential_monitor_stable_images = []
    if result is None:
        app.potential_monitor_status_var.set("Auto scan could not read the stable result. Use Read New Roll or recalibrate.")
        _schedule_monitor_capture(app, 1300)
        return
    dependencies = app.potential_monitor_dependencies
    signature = _ocr_result_signature(result)
    if signature == app.potential_monitor_last_result_signature:
        app.potential_monitor_status_var.set(
            "The box changed, but the parsed Potential result did not. Ignored as cursor/UI movement."
        )
        _schedule_monitor_capture(app)
        return
    app.potential_monitor_last_result_signature = signature
    if not result.complete or result.confidence < 0.62:
        # The reroll already occurred in game, so preserve the previous state for
        # comparison, deduct the cube once, and pause monitoring until corrected.
        stop_auto_monitor(app)
        _begin_reroll_review(
            app,
            result,
            parse_number=dependencies["parse_number"],
            deduct_cube=True,
            reason=(
                f"Auto scan detected a changed result but OCR confidence was only {result.confidence * 100:.0f}%. "
                "Monitoring was paused to prevent a later reroll from overwriting this unresolved active state."
            ),
        )
        app.potential_monitor_status_var.set(
            "Auto scan paused: correct the active reroll and record it as current, then restart auto scan."
        )
        return

    _fill_candidate(app, result, context="manual_entry")
    previous = _snapshot_current(app, dependencies["parse_number"])
    cube_deducted = _deduct_reroll_cube(app, dependencies["parse_number"])
    committed = _commit_candidate_as_current(
        app,
        parse_number=dependencies["parse_number"],
        score_fn=dependencies["score_fn"],
        class_main_stat=dependencies["class_main_stat"],
        previous_snapshot=previous,
        cube_already_deducted=cube_deducted,
        record_observation=True,
    )
    if committed:
        app.potential_monitor_status_var.set(
            f"New active reroll recorded automatically ({result.confidence * 100:.0f}% OCR confidence). "
            "The previous result is history only; the Stop/Continue recommendation was recalculated."
        )
    _schedule_monitor_capture(app, 1100)

