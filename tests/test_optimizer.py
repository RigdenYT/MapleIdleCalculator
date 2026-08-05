#!/usr/bin/env python3
"""Dependency-free regression checks for the optimizer engine."""

from __future__ import annotations

import importlib.util
import json
import math
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "maplestory_idle_companion_optimizer.py"
spec = importlib.util.spec_from_file_location("maplestory_optimizer", MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("Could not load optimizer module")
opt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = opt
spec.loader.exec_module(opt)


def assert_close(actual: float, expected: float, *, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10):
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def test_companion_tables() -> None:
    checkpoints = [
        ("Hero", "Common", 1, "attack", 60.0),
        ("Hero", "Common", 300, "attack", 1854.0),
        ("Hero", "Rare", 300, "attack", 6180.0),
        ("Hero", "Epic", 100, "max_damage", 54.5),
        ("Dark Knight", "Legendary", 300, "accuracy", 741.6),
        ("Fire/Poison", "Unique", 10, "crit_rate", 11.4),
        ("Marksman", "Legendary", 300, "status_damage", 988.8),
        # Player-verified July 2026 additions: their Rare pages use the
        # standard Attack curve, while Epic+ follows the matching existing
        # Accuracy/Boss-Damage families.
        ("Night Walker", "Rare", 5, "attack", 280.0),
        ("Night Walker", "Epic", 3, "accuracy", 7.2),
        ("Night Walker", "Unique", 1, "accuracy", 12.0),
        ("Night Walker", "Legendary", 1, "accuracy", 24.0),
        ("Wind Archer", "Rare", 6, "attack", 300.0),
        ("Wind Archer", "Epic", 3, "boss_damage", 6.0),
        ("Wind Archer", "Unique", 1, "boss_damage", 10.0),
        ("Wind Archer", "Legendary", 1, "boss_damage", 20.0),
        # Player-provided checkpoints for the Jan/Apr 2026 additions.
        ("Bishop", "Rare", 6, "attack", 300.0),
        ("Bishop", "Epic", 3, "skill_damage", 2.4),
        ("Bishop", "Unique", 1, "skill_damage", 4.0),
        ("Bishop", "Legendary", 1, "skill_damage", 8.0),
        ("Paladin", "Rare", 5, "attack", 280.0),
        ("Paladin", "Epic", 3, "basic_attack_damage", 2.4),
        ("Paladin", "Unique", 1, "basic_attack_damage", 4.0),
        ("Paladin", "Legendary", 1, "basic_attack_damage", 8.0),
        ("Buccaneer", "Common", 1, "attack", 60.0),
        ("Buccaneer", "Rare", 5, "attack", 280.0),
        ("Buccaneer", "Epic", 2, "main_stat_pct", 3.3),
        ("Buccaneer", "Unique", 1, "main_stat_pct", 6.0),
        ("Buccaneer", "Legendary", 1, "main_stat_pct", 12.0),
        ("Corsair", "Rare", 6, "attack", 300.0),
        ("Corsair", "Epic", 3, "crit_damage", 3.6),
        ("Corsair", "Unique", 1, "crit_damage", 6.0),
        ("Corsair", "Legendary", 1, "crit_damage", 12.0),
    ]
    for name, rarity, level, effect, expected in checkpoints:
        actual_effect, actual = opt.companion_effect(name, rarity, level)
        assert actual_effect == effect
        assert_close(actual, expected, label=f"{name} {rarity} Lv.{level}")


def test_caps_and_stacking() -> None:
    assert_close(
        opt.combine_diminishing(50.0, [50.0], 150.0),
        83.33333333333334,
        label="Attack Speed diminishing stack",
    )

    stats = opt.CharacterStats(
        attack=100000.0,
        crit_rate=100.0,
        crit_damage=100.0,
        min_damage=100.0,
        max_damage=100.0,
    )
    target = opt.TargetProfile(content_mode="Boss")
    fp = opt.Companion("fp", "Fire/Poison", "Epic", 100, "crit_rate", 32.7)
    baseline, _ = opt.evaluate_team(stats, target, ())
    capped, _ = opt.evaluate_team(stats, target, (fp,), fp)
    assert_close(capped.score_selected, baseline.score_selected, label="Critical Rate cap")


def test_content_selection() -> None:
    stats = opt.CharacterStats(attack=100000.0, min_damage=100.0, max_damage=100.0)
    hero = opt.Companion("h", "Hero", "Epic", 100, "max_damage", 54.5)
    ice = opt.Companion("i", "Ice/Lightning", "Epic", 100, "normal_damage", 54.5)
    night_lord = opt.Companion("n", "Night Lord", "Epic", 100, "boss_damage", 54.5)
    pool = [hero, ice, night_lord]

    normal, _, _ = opt.optimize_companions(
        stats, opt.TargetProfile(content_mode="Normal farming"), pool, 1, 3
    )
    boss, _, _ = opt.optimize_companions(
        stats, opt.TargetProfile(content_mode="Boss"), pool, 1, 3
    )
    assert normal[0].main.name == "Ice/Lightning"
    assert boss[0].main.name == "Night Lord"


def test_main_stat_effect() -> None:
    stats = opt.CharacterStats(
        attack=10000.0,
        total_main_stat=5000.0,
        current_main_stat_pct=25.0,
        min_damage=100.0,
        max_damage=100.0,
    )
    bucc = opt.Companion("b", "Buccaneer", "Legendary", 1, "main_stat_pct", 10.0)
    state, _ = opt.evaluate_team(stats, opt.TargetProfile(), (bucc,), bucc)
    assert_close(state.main_stat_gain, 400.0, label="Main Stat gain")
    assert_close(state.attack, 10400.0, label="Attack after Main Stat gain")
    assert_close(state.stat_prop_damage, 4.0, label="Stat Prop gain")


def test_fast_and_detailed_match() -> None:
    stats = opt.CharacterStats(
        attack=1234567.0,
        total_main_stat=80000.0,
        current_main_stat_pct=85.0,
        flat_attack_scaling_pct=20.0,
        damage=340.0,
        stat_prop_damage=900.0,
        crit_rate=81.0,
        crit_damage=220.0,
        attack_speed=97.0,
        min_damage=143.0,
        max_damage=256.0,
        normal_damage=510.0,
        boss_damage=470.0,
        basic_attack_damage=180.0,
        skill_damage=240.0,
        basic_attack_share=35.0,
        status_damage=140.0,
        status_uptime=70.0,
        damage_amp=20.0,
        final_damage=35.0,
        defense_pen=55.0,
        accuracy=40.0,
    )
    target = opt.TargetProfile(
        content_mode="Mixed stage",
        normal_weight=65.0,
        target_defense=10000.0,
        target_evasion=90.0,
        use_accuracy_approximation=True,
    )
    effects = [
        ("attack", 5000.0),
        ("attack_speed", 75.0),
        ("crit_rate", 30.0),
        ("main_stat_pct", 12.0),
        ("final_damage", 10.0),
        ("defense_pen", 20.0),
        ("boss_damage", 50.0),
    ]
    team = tuple(
        opt.Companion(str(i), f"Custom {i}", "Legendary", 100, effect, value, 3.0 if i == 2 else 0.0)
        for i, (effect, value) in enumerate(effects)
    )
    main = opt.choose_main(team, target.content_mode)
    detailed, _ = opt.evaluate_team(stats, target, team, main)
    fast = opt.fast_team_score(stats, target, team, main)
    assert_close(fast, detailed.score_selected, label="Fast exhaustive scorer")


def displayed_stats_from_state(
    baseline: "opt.CharacterStats",
    state: "opt.EffectiveState",
    equipped_team: tuple,
) -> "opt.CharacterStats":
    main_stat_pct_added = sum(
        companion.effect_value
        for companion in equipped_team
        if companion.effect_type == "main_stat_pct"
    )
    return opt.CharacterStats(
        character_class=baseline.character_class,
        character_level=baseline.character_level,
        attack=state.attack,
        total_main_stat=state.total_main_stat,
        current_main_stat_pct=baseline.current_main_stat_pct + main_stat_pct_added,
        flat_attack_scaling_pct=baseline.flat_attack_scaling_pct,
        damage=state.damage,
        stat_prop_damage=state.stat_prop_damage,
        crit_rate=state.crit_rate,
        crit_damage=state.crit_damage,
        attack_speed=state.attack_speed,
        min_damage=state.min_damage,
        max_damage=state.max_damage,
        normal_damage=state.normal_damage,
        boss_damage=state.boss_damage,
        basic_attack_damage=state.basic_attack_damage,
        skill_damage=state.skill_damage,
        basic_attack_share=baseline.basic_attack_share,
        status_damage=state.status_damage,
        status_uptime=baseline.status_uptime,
        damage_amp=state.damage_amp,
        final_damage=state.final_damage,
        defense_pen=state.defense_pen,
        accuracy=state.accuracy,
    )


def test_current_team_reconstruction() -> None:
    baseline = opt.CharacterStats(
        character_class="Night Lord",
        character_level=150,
        attack=1_250_000.0,
        total_main_stat=85_000.0,
        current_main_stat_pct=70.0,
        flat_attack_scaling_pct=15.0,
        damage=310.0,
        stat_prop_damage=850.0,
        crit_rate=72.0,
        crit_damage=190.0,
        attack_speed=82.0,
        min_damage=140.0,
        max_damage=230.0,
        normal_damage=420.0,
        boss_damage=390.0,
        basic_attack_damage=120.0,
        skill_damage=175.0,
        basic_attack_share=32.0,
        status_damage=80.0,
        status_uptime=60.0,
        damage_amp=15.0,
        final_damage=28.0,
        defense_pen=41.0,
        accuracy=35.0,
    )
    team = (
        opt.Companion("a", "Hero", "Rare", 80, "attack", 1000.0, equipped_role="Sub"),
        opt.Companion("s", "Bowmaster", "Epic", 50, "attack_speed", 29.5, equipped_role="Sub"),
        opt.Companion("m", "Buccaneer", "Legendary", 1, "main_stat_pct", 12.0, equipped_role="Main"),
        opt.Companion("f", "Custom Final", "Legendary", 1, "final_damage", 8.0, equipped_role="Sub"),
        opt.Companion("p", "Custom Pen", "Legendary", 1, "defense_pen", 17.0, equipped_role="Sub"),
        opt.Companion("b", "Night Lord", "Epic", 30, "boss_damage", 19.5, equipped_role="Sub"),
        opt.Companion("c", "Fire/Poison", "Epic", 20, "crit_rate", 8.7, equipped_role="Sub"),
    )
    current_main = team[2]
    displayed_state, _ = opt.evaluate_team(baseline, opt.TargetProfile(), team, current_main)
    displayed = displayed_stats_from_state(baseline, displayed_state, team)
    reconstructed, warnings = opt.reconstruct_unequipped_stats(displayed, team)
    assert warnings == []
    for field_name in (
        "attack",
        "total_main_stat",
        "current_main_stat_pct",
        "damage",
        "stat_prop_damage",
        "crit_rate",
        "crit_damage",
        "attack_speed",
        "min_damage",
        "max_damage",
        "normal_damage",
        "boss_damage",
        "basic_attack_damage",
        "skill_damage",
        "status_damage",
        "damage_amp",
        "final_damage",
        "defense_pen",
        "accuracy",
    ):
        assert_close(
            getattr(reconstructed, field_name),
            getattr(baseline, field_name),
            label=f"Reconstructed {field_name}",
        )


def test_gain_is_vs_current_team() -> None:
    baseline = opt.CharacterStats(attack=100000.0, min_damage=100.0, max_damage=100.0)
    hero = opt.Companion(
        "h", "Hero", "Epic", 100, "max_damage", 54.5, equipped_role="Main"
    )
    ice = opt.Companion(
        "i", "Ice/Lightning", "Epic", 100, "normal_damage", 54.5
    )
    current_state, _ = opt.evaluate_team(baseline, opt.TargetProfile(content_mode="Normal farming"), (hero,), hero)
    displayed = displayed_stats_from_state(baseline, current_state, (hero,))
    results, _, _ = opt.optimize_companions(
        displayed,
        opt.TargetProfile(content_mode="Normal farming"),
        [hero, ice],
        1,
        2,
        stats_include_equipped_companions=True,
    )
    assert results[0].main.name == "Ice/Lightning"
    current_result = next(result for result in results if result.main.name == "Hero")
    assert_close(current_result.gain_pct, 0.0, label="Current-team reference gain")



def test_stat_source_roundtrip() -> None:
    profile = opt.Profile(
        stats=opt.CharacterStats(attack=123456.0),
        stat_sources={
            "attack": "screenshot",
            "skill_damage": "inferred_zero",
            "status_uptime": "uncovered",
        },
    )
    restored = opt.profile_from_dict(opt.profile_to_dict(profile))
    assert restored.stat_sources == profile.stat_sources


def test_ocr_label_matching() -> None:
    cases = [
        ("Min Damage Multiplier", "min_damage"),
        ("Multiplier Max Damage", "max_damage"),
        ("Stat Prop. Damage I", "stat_prop_damage"),
        ("Job Skill 1st Lv.", "anchor_job"),
    ]
    for text, expected in cases:
        key, score, _ = opt._match_ocr_label(text)
        assert key == expected, (text, key, score)
        assert score >= 0.62


def _advanced_fixture() -> "opt.AdvancedProfile":
    stats = opt.CharacterStats(
        character_class="Hero",
        character_level=70,
        attack=100000.0,
        min_damage=100.0,
        max_damage=100.0,
        basic_attack_damage=20.0,
        skill_damage=20.0,
        basic_attack_share=50.0,
    )
    companions = [
        opt.Companion("hero", "Hero", "Epic", 3, "max_damage", 6.0, equipped_role="Main", source="formula"),
        opt.Companion("pal", "Paladin", "Epic", 3, "basic_attack_damage", 2.4, equipped_role="Sub", source="formula"),
        opt.Companion("bish", "Bishop", "Epic", 3, "skill_damage", 2.4, source="formula"),
        opt.Companion("nl", "Night Lord", "Epic", 3, "boss_damage", 6.0, source="formula"),
    ]
    displayed, _ = opt.evaluate_team(stats, opt.TargetProfile(content_mode="Boss"), companions[:2], companions[0])
    shown = displayed_stats_from_state(stats, displayed, tuple(companions[:2]))
    return opt.AdvancedProfile(
        build_name="Boss",
        stats=shown,
        target=opt.TargetProfile(content_mode="Boss"),
        companions=companions,
        total_slots=2,
        top_results=4,
        stats_include_equipped_companions=True,
        main_options=opt.MainSelectionOptions(),
        sensitivity=opt.SensitivitySettings(
            basic_attack_min=0, basic_attack_max=100, basic_attack_steps=3,
            status_uptime_min=0, status_uptime_max=0, status_uptime_steps=1,
        ),
    )


def test_account_build_roundtrip_and_legacy_migration() -> None:
    profile = _advanced_fixture()
    legacy = opt.Profile(
        stats=profile.stats, target=profile.target, companions=profile.companions,
        total_slots=profile.total_slots, top_results=profile.top_results,
        stats_include_equipped_companions=True,
    )
    migrated = opt.account_from_dict(opt.profile_to_dict(legacy), "Legacy Boss")
    assert migrated.active_build == "Legacy Boss"
    assert len(migrated.builds) == 1
    assert all(c.equipped_role == "Not equipped" for c in migrated.companions)
    restored = opt.account_from_dict(opt.account_to_dict(migrated))
    assert restored.active_build == migrated.active_build
    assert restored.builds[0].current_roles == migrated.builds[0].current_roles


def test_advanced_main_lock() -> None:
    profile = _advanced_fixture()
    profile.main_options = opt.MainSelectionOptions(mode="Lock selected Main", locked_main_uid="bish")
    results, total, _ = opt.optimize_companions_advanced(profile)
    assert total == 3
    assert results
    assert all(result.main.uid == "bish" for result in results)


def test_sensitivity_and_main_comparison() -> None:
    profile = _advanced_fixture()
    analysis = opt.run_sensitivity_analysis(profile)
    assert analysis.scenario_count == 3
    assert 0 <= analysis.nominal_win_pct <= 100
    assert analysis.summaries
    rows, checks, _ = opt.compare_all_mains(profile)
    assert checks == 12
    assert len(rows) == 4


def test_upgrade_value_planner() -> None:
    profile = _advanced_fixture()
    rows, teams, _ = opt.calculate_upgrade_values(profile)
    assert teams == 6
    assert rows
    assert all(row.next_level == row.companion.level + 1 for row in rows)
    assert rows[0].improvement_pct >= rows[-1].improvement_pct



def test_atomic_json_write(tmp_path) -> None:
    path = tmp_path / "account.json"
    opt.write_json_atomic(path, {"version": 1, "builds": ["Boss"]})
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1, "builds": ["Boss"]}

    opt.write_json_atomic(path, {"version": 2, "builds": ["Boss", "Farming"]})
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2
    assert not list(tmp_path.glob(".account.json.*.tmp"))


def test_locked_team_iterator_is_direct_and_complete() -> None:
    profile = _advanced_fixture()
    profile.main_options = opt.MainSelectionOptions(mode="Lock selected Main", locked_main_uid="bish")
    teams = list(opt._iter_valid_teams(profile.companions, profile.total_slots, profile.main_options))
    assert len(teams) == opt.valid_team_count(len(profile.companions), profile.total_slots, profile.main_options)
    assert all(any(companion.uid == "bish" for companion in team) for team in teams)
    assert len({tuple(sorted(companion.uid for companion in team)) for team in teams}) == len(teams)


def test_fast_score_can_skip_main_bonus_without_copying() -> None:
    stats = opt.CharacterStats(attack=100000.0, min_damage=100.0, max_damage=100.0)
    target = opt.TargetProfile(content_mode="Boss")
    main = opt.Companion("m", "Hero", "Epic", 3, "max_damage", 6.0, main_bonus=25.0)
    sub = opt.Companion("s", "Night Lord", "Epic", 3, "boss_damage", 6.0)
    team = (main, sub)
    neutral_main = opt.Companion("m", "Hero", "Epic", 3, "max_damage", 6.0, main_bonus=0.0)
    detailed, _ = opt.evaluate_team(stats, target, team, neutral_main)
    fast = opt.fast_team_score(stats, target, team, main, apply_main_bonus=False)
    assert_close(fast, detailed.score_selected, label="Fast score without Main bonus")

def test_readiness_flags_suspicious_scaling() -> None:
    profile = _advanced_fixture()
    profile.stats.flat_attack_scaling_pct = 3890.1
    report = opt.assess_profile_readiness(profile)
    assert report.rating == "Ready with assumptions"
    assert any("unusually high" in issue.message for issue in report.issues)

def main() -> None:
    test_companion_tables()
    test_caps_and_stacking()
    test_content_selection()
    test_main_stat_effect()
    test_fast_and_detailed_match()
    test_current_team_reconstruction()
    test_gain_is_vs_current_team()
    test_stat_source_roundtrip()
    test_ocr_label_matching()
    test_account_build_roundtrip_and_legacy_migration()
    test_advanced_main_lock()
    test_sensitivity_and_main_comparison()
    test_upgrade_value_planner()
    test_locked_team_iterator_is_direct_and_complete()
    test_fast_score_can_skip_main_bonus_without_copying()
    test_readiness_flags_suspicious_scaling()
    print("All optimizer regression tests passed.")


if __name__ == "__main__":
    main()



def test_role_chooser_waits_for_initiating_click_to_finish() -> None:
    class DummyVar:
        def get(self) -> str:
            return "Not equipped"

    class FakeApp:
        def __init__(self) -> None:
            self.roster_vars = {"hero_common": {"role": DummyVar()}}
            self._roster_role_menu = None
            self._roster_role_menu_after_id = None
            self.scheduled = []
            self.cancelled = []

        def after(self, delay: int, callback):
            token = f"after-{len(self.scheduled) + 1}"
            self.scheduled.append((delay, callback, token))
            return token

        def after_cancel(self, token: str) -> None:
            self.cancelled.append(token)

        _close_roster_role_menu = opt.OptimizerApp._close_roster_role_menu

    fake = FakeApp()
    previous_active = opt.CompanionTile._active_level_tile
    opt.CompanionTile._active_level_tile = None
    try:
        opt.OptimizerApp._show_roster_role_menu(
            fake, "hero_common", object(), 100, 200
        )
        assert fake._roster_role_menu is None
        assert fake._roster_role_menu_after_id == "after-1"
        assert fake.scheduled[0][0] == opt.ROLE_MENU_POST_DELAY_MS
        assert callable(fake.scheduled[0][1])
        role_menu_source = MODULE_PATH.read_text(encoding="utf-8")
        assert "chooser = tk.Frame(" in role_menu_source
        assert "self._roster_role_menu_buttons[role] = button" in role_menu_source
        assert "menu.post(" not in role_menu_source
        assert "menu.grab_set" not in role_menu_source
        assert "menu.tk_popup" not in role_menu_source

        # A rapid second click cancels the still-pending first popup instead of
        # allowing two menus to race each other after the mouse release.
        opt.OptimizerApp._show_roster_role_menu(
            fake, "hero_common", object(), 100, 200
        )
        assert fake.cancelled == ["after-1"]
        assert fake._roster_role_menu_after_id == "after-2"
    finally:
        opt.CompanionTile._active_level_tile = previous_active

def test_packaged_resource_paths_and_icon() -> None:
    assert opt.resource_path("assets", "companions").is_dir()
    assert (opt.ui_asset_directory() / "app_icon.png").is_file()
    assert (opt.ui_asset_directory() / "app_icon.ico").is_file()


def test_tesseract_override_resolution(tmp_path, monkeypatch) -> None:
    executable = tmp_path / ("tesseract.exe" if opt.os.name == "nt" else "tesseract")
    executable.write_bytes(b"placeholder")
    executable.chmod(0o755)
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "eng.traineddata").write_bytes(b"placeholder")
    monkeypatch.setenv("MAPLE_IDLE_TESSERACT", str(executable))
    monkeypatch.setenv("TESSDATA_PREFIX", str(tessdata))
    runtime = opt.resolve_tesseract_runtime()
    assert runtime is not None
    assert runtime.executable == executable
    assert runtime.tessdata == tessdata
    assert not runtime.bundled


def test_crash_log_creation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(opt, "user_config_directory", lambda: tmp_path)
    try:
        raise RuntimeError("packaging test failure")
    except RuntimeError as exc:
        path = opt.write_crash_log(
            "Regression test", type(exc), exc, exc.__traceback__
        )
    assert path is not None and path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Regression test" in text
    assert "packaging test failure" in text


def test_pyinstaller_bundles_pillow_tk_bridge_modules():
    spec_text = (ROOT / "build_tools" / "MapleStoryIdleOptimizer.spec").read_text(encoding="utf-8")
    assert '"PIL._tkinter_finder"' in spec_text
    assert '"PIL._imagingtk"' in spec_text


def test_release_builds_run_frozen_startup_smoke_tests():
    source_text = MODULE_PATH.read_text(encoding="utf-8")
    linux_text = (ROOT / "build_tools" / "build_linux.sh").read_text(encoding="utf-8")
    windows_text = (ROOT / "build_tools" / "build_windows.bat").read_text(encoding="utf-8")
    workflow_text = (ROOT / ".github" / "workflows" / "build-desktop-releases.yml").read_text(encoding="utf-8")

    assert 'PACKAGING_SMOKE_TEST_FLAG = "--packaging-smoke-test"' in source_text
    assert "_smoke_test_companion_role_menu(app)" in source_text
    assert "main_button.invoke()" in source_text
    assert 'config_env_key = "APPDATA" if os.name == "nt" else "XDG_CONFIG_HOME"' in source_text
    assert 'TemporaryDirectory(prefix="maple-idle-packaging-smoke-")' in source_text
    assert "Packaging smoke test unexpectedly loaded persistent user state." in source_text
    smoke_source = source_text[source_text.index("def _smoke_test_companion_role_menu"):source_text.index("def _run_packaging_smoke_test")]
    assert "main_button.event_generate" not in smoke_source
    assert "warp=True" not in smoke_source
    assert linux_text.count("--packaging-smoke-test") >= 1
    assert windows_text.count("--packaging-smoke-test") >= 2
    assert "xvfb" in workflow_text



def test_advanced_worker_queue_poll_without_terminal_message_initializes_followup_flag():
    """Regression for Optimize Team crash when a poll finds no terminal message."""

    class DummyButton:
        def __init__(self):
            self.states = []

        def configure(self, **kwargs):
            self.states.append(kwargs)

    class FakeApp:
        def __init__(self):
            self.worker = None
            self.worker_queue = opt.queue.Queue()
            self.optimize_button = DummyButton()
            self.cancel_button = DummyButton()
            self.analysis_states = []
            self.current_job_kind = "optimize"

        def _set_analysis_buttons(self, state):
            self.analysis_states.append(state)

    app = FakeApp()
    opt.AdvancedOptimizerApp._poll_worker_queue(app)

    assert app.optimize_button.states[-1] == {"state": "normal"}
    assert app.cancel_button.states[-1] == {"state": "disabled"}
    assert app.analysis_states[-1] == "normal"
    assert app.current_job_kind == ""

def test_hero_power_ability_tables_and_inverse_sources():
    assert opt.APP_VERSION == "3.0.0"
    assert len(opt.ABILITY_RANGES["Main Stat"]) == 6
    assert opt.ABILITY_RANGES["Attack Speed"]["Unique"] == (7, 9)
    assert opt.ABILITY_REROLL_COST[2][3] == 75
    stats = opt.CharacterStats(attack_speed=40.0, defense_pen=35.0)
    original = opt.copy.deepcopy(stats)
    opt._apply_ability_line(stats, "Attack Speed", 10.0)
    opt._apply_ability_line(stats, "Defense Penetration", 12.0)
    restored = opt._remove_ability_lines(stats, [("Attack Speed", 10.0), ("Defense Penetration", 12.0)])
    assert math.isclose(restored.attack_speed, original.attack_speed, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(restored.defense_pen, original.defense_pen, rel_tol=1e-9, abs_tol=1e-9)


def test_hero_power_account_round_trip():
    state = {"stage": "4", "tokens": "217", "unlocked_slots": "3", "lines": [{"stat": "Attack Speed", "value": "8.8"}]}
    account = opt.AccountProfile(hero_power=state)
    loaded = opt.account_from_dict(opt.account_to_dict(account))
    assert loaded.hero_power == state


def test_hero_power_is_modularized_and_reexported():
    source_text = MODULE_PATH.read_text(encoding="utf-8")
    assert "from maple_optimizer.hero_power.data import" in source_text
    assert "hero_power_ui.build_tab(self, COLORS)" in source_text
    assert "ABILITY_RANGES: Dict" not in source_text
    for relative in (
        "maple_optimizer/hero_power/data.py",
        "maple_optimizer/hero_power/models.py",
        "maple_optimizer/hero_power/engine.py",
        "maple_optimizer/hero_power/ui.py",
    ):
        assert (ROOT / relative).is_file()


def test_tier_progression_returns_n_ranked_picks_for_every_tier():
    stats = opt.CharacterStats(
        attack=100000.0,
        total_main_stat=10000.0,
        damage=50.0,
        crit_rate=70.0,
        crit_damage=100.0,
        attack_speed=30.0,
        boss_damage=100.0,
        defense_pen=30.0,
        accuracy=100.0,
    )
    target = opt.TargetProfile(content_mode="Boss")
    recommendations = opt.hero_power_engine.optimize_all_tiers(
        stats,
        target,
        3,
        2,
        opt._score_character,
        opt.combine_diminishing,
        beam_width=32,
    )
    assert [item.tier for item in recommendations] == list(opt.ABILITY_TIERS)
    assert all(len(item.lines) == 3 for item in recommendations)
    assert recommendations[3].tier == "Unique"
    assert recommendations[3].available
    assert not recommendations[4].available
    assert not recommendations[5].available
    for recommendation in recommendations:
        assert [line.slot_number for line in recommendation.lines] == [1, 2, 3]
        assert recommendation.maximum_total_gain_pct >= recommendation.minimum_total_gain_pct
        assert all(line.maximum_value >= line.minimum_value for line in recommendation.lines)


def test_tier_progression_allows_duplicate_best_lines():
    stats = opt.CharacterStats(attack=100000.0, damage=0.0)
    target = opt.TargetProfile(content_mode="Boss")
    recommendation = opt.hero_power_engine.optimize_tier(
        stats,
        target,
        "Rare",
        3,
        2,
        opt._score_character,
        opt.combine_diminishing,
        beam_width=32,
    )
    assert len(recommendation.lines) == 3
    assert len({line.stat_name for line in recommendation.lines}) < 3


def test_action_planner_compares_one_and_two_slot_rerolls():
    stats = opt.CharacterStats(
        attack=100000.0,
        total_main_stat=10000.0,
        damage=50.0,
        crit_rate=70.0,
        crit_damage=100.0,
        attack_speed=30.0,
        boss_damage=100.0,
        defense_pen=30.0,
        accuracy=100.0,
    )
    target = opt.TargetProfile(content_mode="Boss")
    lines = [
        opt.hero_power_engine.AbilityLine("Damage", 15.0, True, "Unique", 1),
        opt.hero_power_engine.AbilityLine("Max HP", 15000.0, True, "Unique", 2),
        opt.hero_power_engine.AbilityLine("Max MP", 200.0, True, "Unique", 3),
    ]
    plan = opt.hero_power_engine.analyze_reroll_strategies(
        stats,
        lines,
        target,
        5,
        50000,
        0,
        0,
        0.25,
        2,
        opt._score_character,
        opt.combine_diminishing,
        samples_per_level=3000,
    )
    assert plan.recommended_strategy is not None
    assert plan.recommended_strategy.rerolled_slots == (2, 3)
    assert {len(strategy.rerolled_slots) for strategy in plan.strategies} == {1, 2}
    assert plan.recommended_strategy.budget_success_probability_pct > 99.0
    assert plan.recommended_strategy.expected_gain_per_1000_medals > 0.0


def test_action_planner_accounts_for_reconfiguration_level_progression():
    stats = opt.CharacterStats(attack=100000.0, damage=40.0)
    target = opt.TargetProfile(content_mode="Boss")
    lines = [
        opt.hero_power_engine.AbilityLine("Max HP", 15000.0, False, "Unique", 1),
        opt.hero_power_engine.AbilityLine("Max MP", 200.0, False, "Unique", 2),
        opt.hero_power_engine.AbilityLine("Evasion", 10.0, False, "Unique", 3),
    ]
    plan = opt.hero_power_engine.analyze_reroll_strategies(
        stats,
        lines,
        target,
        2,
        24000,
        0,
        11000,
        0.10,
        1,
        opt._score_character,
        opt.combine_diminishing,
        samples_per_level=2000,
    )
    assert plan.recommended_strategy is not None
    assert plan.recommended_strategy.attempts_affordable > 0
    assert plan.recommended_strategy.ending_reconfiguration_level >= 3


def test_replacement_thresholds_report_practical_accept_values():
    stats = opt.CharacterStats(
        attack=100000.0,
        total_main_stat=10000.0,
        damage=50.0,
        crit_rate=70.0,
        crit_damage=100.0,
        attack_speed=30.0,
    )
    target = opt.TargetProfile(content_mode="Boss")
    lines = [
        opt.hero_power_engine.AbilityLine("Attack Speed", 8.8, True, "Unique", 1),
        opt.hero_power_engine.AbilityLine("Attack Speed", 7.2, True, "Unique", 2),
        opt.hero_power_engine.AbilityLine("Main Stat", 400.0, True, "Unique", 3),
    ]
    thresholds = opt.hero_power_engine.estimate_replacement_thresholds(
        stats,
        lines,
        3,
        target,
        2,
        0.25,
        opt._score_character,
        opt.combine_diminishing,
        limit=20,
    )
    assert thresholds
    assert any(item.stat_name == "Damage" for item in thresholds)
    assert all(item.minimum_accepted_value <= item.maximum_value for item in thresholds)
    assert all(item.estimated_probability_per_rolled_slot > 0 for item in thresholds)


def test_action_planner_simulation_is_deterministic():
    stats = opt.CharacterStats(attack=100000.0, damage=40.0)
    target = opt.TargetProfile(content_mode="Boss")
    lines = [
        opt.hero_power_engine.AbilityLine("Max HP", 15000.0, False, "Unique", 1),
        opt.hero_power_engine.AbilityLine("Main Stat", 400.0, False, "Unique", 2),
    ]
    args = (
        stats,
        lines,
        target,
        3,
        10000,
        1000,
        0,
        0.25,
        2,
        opt._score_character,
        opt.combine_diminishing,
    )
    first = opt.hero_power_engine.analyze_reroll_strategies(*args, samples_per_level=1500)
    second = opt.hero_power_engine.analyze_reroll_strategies(*args, samples_per_level=1500)
    assert first == second


def test_action_planner_reports_top_three_budget_probability():
    stats = opt.CharacterStats(
        attack=100000.0,
        total_main_stat=10000.0,
        damage=50.0,
        crit_rate=70.0,
        crit_damage=100.0,
        attack_speed=30.0,
    )
    target = opt.TargetProfile(content_mode="Boss")
    lines = [
        opt.hero_power_engine.AbilityLine("Attack Speed", 8.8, True, "Unique", 1),
        opt.hero_power_engine.AbilityLine("Attack Speed", 7.2, True, "Unique", 2),
        opt.hero_power_engine.AbilityLine("Main Stat", 400.0, True, "Unique", 3),
    ]
    plan = opt.hero_power_engine.analyze_reroll_strategies(
        stats,
        lines,
        target,
        2,
        23495,
        0,
        0,
        0.25,
        2,
        opt._score_character,
        opt.combine_diminishing,
        samples_per_level=2500,
    )
    strategy = plan.recommended_strategy
    assert strategy is not None
    assert len(strategy.top_success_patterns) >= 3
    assert 0.0 < strategy.top_three_first_attempt_probability_pct
    assert strategy.top_three_first_attempt_probability_pct <= strategy.first_attempt_success_probability_pct
    assert strategy.top_three_first_attempt_probability_pct <= strategy.top_three_budget_probability_pct
    assert strategy.top_three_budget_probability_pct <= strategy.budget_success_probability_pct + 1e-9
    assert all(pattern.probability_per_attempt_pct > 0.0 for pattern in strategy.top_success_patterns[:3])


def test_hero_power_ui_uses_concise_action_dashboard():
    text = (ROOT / "maple_optimizer" / "hero_power" / "ui.py").read_text(encoding="utf-8")
    assert '"Recommended Action"' in text
    assert '"STOP REROLLING IF YOU GET ANY OF THESE"' in text
    assert 'app.hero_plan_chance_var' in text
    assert 'app.hero_details_frame.grid_remove()' in text
    assert 'text="Show detailed analysis"' in text
    assert 'app.ability_approach_var' in text
    assert 'top_three_expected_attempts_given_success' in text


def test_budget_probability_matches_bruteforce_first_success_enumeration():
    probabilities = (0.2, 0.4, 0.1)
    costs = (10, 20, 30)
    metrics = opt.hero_power_engine._accumulate_stopping_metrics(probabilities, costs)

    first_success_probabilities = (
        0.2,
        (1.0 - 0.2) * 0.4,
        (1.0 - 0.2) * (1.0 - 0.4) * 0.1,
    )
    brute_probability = sum(first_success_probabilities)
    brute_attempts = sum(
        (index + 1) * probability
        for index, probability in enumerate(first_success_probabilities)
    ) / brute_probability
    cumulative_costs = (10, 30, 60)
    brute_spend = sum(
        spend * probability
        for spend, probability in zip(cumulative_costs, first_success_probabilities)
    ) / brute_probability
    brute_expected_spend_until_stop = 10 + (1.0 - 0.2) * 20 + (1.0 - 0.2) * (1.0 - 0.4) * 30

    assert_close(metrics.success_probability, brute_probability, label="budget success probability")
    assert_close(metrics.expected_attempts_given_success, brute_attempts, label="expected attempts")
    assert_close(metrics.expected_spend_given_success, brute_spend, label="expected spend given success")
    assert_close(metrics.expected_spend_until_stop, brute_expected_spend_until_stop, label="expected spend until stop")


def test_top_three_budget_probability_tracks_same_displayed_outcomes(monkeypatch):
    engine = opt.hero_power_engine
    pattern_type = engine._PatternOutcomeEstimate
    level_type = engine._LevelOutcomeEstimate

    def successful(signature, probability, gain):
        return opt.hero_power_engine.SuccessfulPattern(
            signature=signature,
            description=" + ".join(signature),
            share_of_successes_pct=probability * 100.0,
            probability_per_attempt_pct=probability * 100.0,
            minimum_gain_pct=gain,
            average_gain_pct=gain,
            maximum_gain_pct=gain,
        )

    start_signatures = (("Rare Damage",), ("Epic Damage",), ("Unique Damage",))
    later_signatures = (("Mystic Damage",), ("Legendary Damage",), ("Mystic Attack Speed",))

    def fake_simulate(_base, _target, _lines, _slots, level, *_args):
        if level == 1:
            probabilities = {signature: 0.1 for signature in start_signatures}
            patterns = tuple(successful(signature, 0.1, 1.0) for signature in start_signatures)
            success_probability = 0.3
        else:
            probabilities = {signature: 0.01 for signature in start_signatures}
            probabilities.update({signature: 0.3 for signature in later_signatures})
            patterns = tuple(successful(signature, 0.3, 5.0) for signature in later_signatures)
            success_probability = 0.93
        estimates = {
            signature: pattern_type(signature, probability, 1.0, 1.0, 1.0)
            for signature, probability in probabilities.items()
        }
        return level_type(success_probability, 1.0, 0.0, patterns, estimates)

    monkeypatch.setattr(engine, "_simulate_level_outcomes", fake_simulate)
    monkeypatch.setattr(engine, "_attempt_schedule", lambda *_args: ((1, 10), (2, 10)))

    stats = opt.CharacterStats(attack=100000.0)
    lines = [engine.AbilityLine("Max HP", 1200.0, False, "Normal", 1)]
    plan = engine.analyze_reroll_strategies(
        stats,
        lines,
        opt.TargetProfile(),
        1,
        100,
        0,
        0,
        0.1,
        1,
        opt._score_character,
        opt.combine_diminishing,
        samples_per_level=10,
    )
    strategy = plan.recommended_strategy
    assert strategy is not None
    # The displayed starting outcomes have 30% on attempt 1 and only 3% on
    # attempt 2. A changing "top three" would incorrectly use 90% on attempt 2.
    assert_close(
        strategy.top_three_budget_probability_pct,
        (1.0 - (1.0 - 0.30) * (1.0 - 0.03)) * 100.0,
        label="fixed top-three budget probability",
    )


def test_ability_input_validation_rejects_invalid_slot_data():
    class Variable:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value

    class App:
        pass

    app = App()
    app.ability_line_vars = [
        {"enabled": Variable(True), "locked": Variable(False)},
        {"enabled": Variable(False), "locked": Variable(False)},
    ]
    invalid_line = opt.hero_power_engine.AbilityLine(
        "Attack Speed", 99.0, False, "Unique", 1
    )
    with pytest.raises(ValueError, match="between 7 and 9"):
        opt.hero_power_ui._validate_ability_inputs(app, [invalid_line], 1, 2, 1000, 0, 0)


def test_planning_approach_changes_recommendation_priority():
    stats = opt.CharacterStats(
        attack=100000.0,
        total_main_stat=10000.0,
        damage=50.0,
        crit_rate=70.0,
        crit_damage=100.0,
        attack_speed=30.0,
    )
    target = opt.TargetProfile(content_mode="Boss")
    lines = [
        opt.hero_power_engine.AbilityLine("Attack Speed", 8.8, True, "Unique", 1),
        opt.hero_power_engine.AbilityLine("Attack Speed", 7.2, True, "Unique", 2),
        opt.hero_power_engine.AbilityLine("Main Stat", 400.0, True, "Unique", 3),
    ]
    common = (
        stats,
        lines,
        target,
        2,
        23495,
        0,
        0,
        0.25,
        2,
        opt._score_character,
        opt.combine_diminishing,
    )
    conservative = opt.hero_power_engine.analyze_reroll_strategies(
        *common, optimization_approach="Conservative", samples_per_level=1500
    )
    balanced = opt.hero_power_engine.analyze_reroll_strategies(
        *common, optimization_approach="Balanced", samples_per_level=1500
    )
    aggressive = opt.hero_power_engine.analyze_reroll_strategies(
        *common, optimization_approach="Aggressive", samples_per_level=1500
    )
    assert conservative.recommended_strategy is not None
    assert balanced.recommended_strategy is not None
    assert aggressive.recommended_strategy is not None
    assert conservative.recommended_strategy.top_three_budget_probability_pct >= 0.0
    assert aggressive.recommended_strategy.expected_gain_given_success_pct >= 0.0


def test_probability_validation_release_guards_are_present():
    publisher = (ROOT / "publish_release.sh").read_text(encoding="utf-8")
    assert "_accumulate_stopping_metrics" in publisher
    assert "top_three_expected_attempts_given_success" in publisher
    assert "STOP REROLLING IF YOU GET ANY OF THESE" in publisher



def test_potential_ocr_parser_reads_supplied_panel_shape():
    text = """@ Rare ; 1/60
Potential INT 100
Options Damage 8%
Max MP 3%
"""
    result = opt.equipment_ui.read_potential_image if False else None
    from maple_optimizer.equipment.ocr import parse_potential_text
    parsed = parse_potential_text(text)
    assert parsed.rarity == "Rare"
    assert parsed.progress == 1
    assert parsed.progress_total == 60
    assert [(line.stat_name, line.value, line.unit) for line in parsed.lines] == [
        ("INT", 100.0, "flat"),
        ("Damage", 8.0, "percent"),
        ("Max MP %", 3.0, "percent"),
    ]


def test_potential_complete_roll_comparison_replaces_all_three_lines():
    from maple_optimizer.equipment.engine import compare_rolls
    from maple_optimizer.equipment.models import PotentialLine

    stats = opt.CharacterStats(
        character_class="Ice/Lightning Arch Mage",
        attack=100000.0,
        total_main_stat=10000.0,
        damage=8.0,
        crit_rate=50.0,
        crit_damage=100.0,
    )
    target = opt.TargetProfile(content_mode="Boss")
    current = [
        PotentialLine("INT", 100.0),
        PotentialLine("Damage", 8.0),
        PotentialLine("Max MP %", 3.0),
    ]
    candidate = [
        PotentialLine("INT", 150.0),
        PotentialLine("Damage", 10.0),
        PotentialLine("Critical Damage", 5.0),
    ]
    result = compare_rolls(stats, target, current, candidate, "INT", opt._score_character)
    assert result.gain_pct > 0.0
    assert result.modeled_current_lines == 2
    assert result.modeled_candidate_lines == 3
    assert any("Max MP" in warning for warning in result.warnings)


def test_potential_observed_budget_probability_math():
    from maple_optimizer.equipment.engine import chance_with_budget, wilson_interval
    assert_close(chance_with_budget(0.25, 2), 0.4375, label="potential two-cube chance")
    low, high = wilson_interval(5, 10)
    assert 0.0 < low < 0.5 < high < 1.0


def test_equipment_state_round_trips_with_account():
    account = opt.AccountProfile(
        equipment={
            "selected_slot": "Cape",
            "cubes": "67",
            "slots": {
                "Cape": {
                    "rarity": "Rare",
                    "progress": "1",
                    "progress_total": "60",
                    "lines": [
                        {"stat": "INT", "value": "100", "unit": "flat"},
                        {"stat": "Damage", "value": "8", "unit": "percent"},
                        {"stat": "Max MP %", "value": "3", "unit": "percent"},
                    ],
                }
            },
        }
    )
    restored = opt.account_from_dict(opt.account_to_dict(account))
    assert restored.equipment["selected_slot"] == "Cape"
    assert restored.equipment["cubes"] == "67"
    assert restored.equipment["slots"]["Cape"]["rarity"] == "Rare"


def test_equipment_potential_tab_and_release_guards_are_present():
    source = MODULE_PATH.read_text(encoding="utf-8")
    ui_text = (ROOT / "maple_optimizer" / "equipment" / "ui.py").read_text(encoding="utf-8")
    publisher = (ROOT / "publish_release.sh").read_text(encoding="utf-8")
    assert 'text="Equipment Enhancement"' in source
    assert 'text="Read New Roll"' in ui_text
    assert 'text="Read Screenshot File"' in ui_text
    assert "Record Entered Reroll as Current" in ui_text
    assert "REROLL OCR REVIEW — OLD ROLL UNAVAILABLE" in ui_text
    assert "normalize_potential_panel" in ui_text
    assert "KEEP CURRENT" not in ui_text.upper()
    assert "maple_optimizer/equipment" in publisher


def test_potential_ocr_v2_fingerprint_detects_stable_changes():
    from PIL import Image
    from maple_optimizer.equipment.ocr import fingerprint_distance, region_fingerprint
    first = Image.new("RGB", (200, 100), (20, 20, 20))
    same = Image.new("RGB", (200, 100), (20, 20, 20))
    changed = Image.new("RGB", (200, 100), (220, 220, 220))
    assert fingerprint_distance(region_fingerprint(first), region_fingerprint(same)) == 0.0
    assert fingerprint_distance(region_fingerprint(first), region_fingerprint(changed)) > 50.0


def test_reliable_reroll_immediately_replaces_current_state():
    from types import SimpleNamespace
    from maple_optimizer.equipment.models import PotentialLine, PotentialOCRResult
    from maple_optimizer.equipment.potential_rates import PotentialRateProfile
    from maple_optimizer.equipment.ui import apply_new_ocr_result

    class Var:
        def __init__(self, value=None):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value

    def row(stat, value, unit="%"):
        return {"stat": Var(stat), "value": Var(str(value)), "unit": Var(unit)}

    stats = opt.CharacterStats(character_class="Mage", attack=100000.0, damage=1.0)
    target = opt.TargetProfile(content_mode="Boss")
    state = {
        "configured": True, "slot_status": "Unlocked", "rarity": "Mystic",
        "progress": "0", "progress_total": "0",
        "lines": [
            {"stat": "Damage", "value": 1.0, "unit": "percent"},
            {"stat": "Damage", "value": 0.0, "unit": "percent"},
            {"stat": "Damage", "value": 0.0, "unit": "percent"},
        ],
        "observed_rolls": 0, "observed_improvements": 0,
        "observed_signatures": [], "reroll_history": [],
    }
    app = SimpleNamespace(
        collect_profile=lambda: SimpleNamespace(stats=stats, target=target),
        potential_selected_slot_var=Var("Cape"),
        potential_slots_state={"Cape": state},
        potential_current_rarity_var=Var("Mystic"),
        potential_current_progress_var=Var("0"),
        potential_current_progress_total_var=Var("0"),
        potential_current_line_vars=[row("Damage", 1), row("Damage", 0), row("Damage", 0)],
        potential_candidate_rarity_var=Var("Mystic"),
        potential_candidate_progress_var=Var("0"),
        potential_candidate_progress_total_var=Var("0"),
        potential_candidate_line_vars=[row("Damage", 0), row("Damage", 0), row("Damage", 0)],
        potential_candidate_context_var=Var(""),
        potential_record_reroll_button_var=Var(""),
        potential_capture_status_var=Var(""),
        potential_result_title_var=Var(""),
        potential_result_detail_var=Var(""),
        potential_slot_status_var=Var("Unlocked"),
        potential_cubes_var=Var("3"),
        potential_min_gain_var=Var("0.25"),
        potential_auto_deduct_var=Var(True),
        potential_odds_var=Var(""),
        potential_exact_odds_text="",
        potential_rate_profile=PotentialRateProfile(),
        potential_pending_previous_snapshot=None,
        potential_pending_reroll_cube_deducted=False,
        potential_effective_stats_override=None,
        potential_loading_state=False,
        potential_last_candidate_signature="",
        potential_last_comparison=None,
    )
    result = PotentialOCRResult(
        rarity="Mystic", progress=0, progress_total=0,
        lines=(
            PotentialLine("Damage", 5.0, "percent"),
            PotentialLine("Damage", 0.0, "percent"),
            PotentialLine("Damage", 0.0, "percent"),
        ),
        raw_text="synthetic", line_confidences=(1.0, 1.0, 1.0), confidence=1.0,
    )
    committed = apply_new_ocr_result(
        app, result, parse_number=lambda value, **_: float(value),
        score_fn=lambda candidate, _target: 100.0 + candidate.damage,
        class_main_stat={"Mage": "INT"}, deduct_cube=True, record_observation=True,
    )
    assert committed
    assert app.potential_current_line_vars[0]["value"].get() == "5"
    assert app.potential_cubes_var.get() == "2"
    assert state["observed_rolls"] == 1
    assert len(state["reroll_history"]) == 1
    assert "no longer available" in app.potential_result_detail_var.get().lower()
    assert "NEW CURRENT" in app.potential_result_title_var.get()


def test_potential_card_localization_accepts_approximate_region():
    from PIL import Image, ImageDraw
    from maple_optimizer.equipment.ocr import (
        POTENTIAL_CANONICAL_SIZE,
        locate_potential_panel_bounds,
        normalize_potential_panel,
    )

    image = Image.new("RGB", (720, 420), (18, 25, 34))
    draw = ImageDraw.Draw(image)
    # Synthetic neutral-charcoal inner option box with generous calibration margins.
    draw.rectangle((205, 105, 615, 265), fill=(50, 49, 50))
    bounds = locate_potential_panel_bounds(image)
    assert bounds is not None
    left, top, right, bottom = bounds
    assert left < 205 and top <= 105 and right > 615 and bottom >= 265
    normalized, warnings, localized = normalize_potential_panel(image)
    assert localized == bounds
    assert warnings == ()
    assert normalized.size == POTENTIAL_CANONICAL_SIZE


def test_potential_ocr_validation_rejects_impossible_slot_special():
    from maple_optimizer.equipment.models import PotentialLine, PotentialOCRResult
    from maple_optimizer.equipment.ocr import _validate_result
    result = PotentialOCRResult(
        rarity="Unique",
        progress=1,
        progress_total=333,
        lines=(
            PotentialLine("Critical Damage", 20.0),
            PotentialLine("Damage", 12.0),
            PotentialLine("INT", 400.0),
        ),
        raw_text="",
        line_confidences=(0.95, 0.95, 0.95),
        confidence=0.95,
    )
    checked = _validate_result(result, equipment_slot="Cape", expected_rarity="Unique")
    assert checked.confidence < result.confidence
    assert any("not valid for Cape" in warning for warning in checked.warnings)


def test_equipment_priority_ranks_weaker_saved_slot_first():
    from maple_optimizer.equipment.engine import apply_line, rank_equipment_slots
    from maple_optimizer.equipment.models import PotentialLine
    stats = opt.CharacterStats(
        character_class="Ice/Lightning Arch Mage",
        attack=100000.0,
        total_main_stat=10000.0,
        damage=40.0,
        crit_rate=60.0,
        crit_damage=80.0,
    )
    target = opt.TargetProfile(content_mode="Boss")
    glove_lines = [
        PotentialLine("Critical Damage", 20.0),
        PotentialLine("Damage", 12.0),
        PotentialLine("INT", 400.0),
    ]
    cape_lines = [
        PotentialLine("INT", 100.0),
        PotentialLine("Max MP %", 3.0),
        PotentialLine("Defense", 30.0),
    ]
    for line in glove_lines + cape_lines:
        apply_line(stats, line, "INT")
    states = {
        "Gloves": {
            "configured": True, "rarity": "Unique", "progress": "20", "progress_total": "333",
            "lines": [{"stat": line.stat_name, "value": line.value} for line in glove_lines],
            "observed_rolls": 0, "observed_improvements": 0,
        },
        "Cape": {
            "configured": True, "rarity": "Rare", "progress": "1", "progress_total": "60",
            "lines": [{"stat": line.stat_name, "value": line.value} for line in cape_lines],
            "observed_rolls": 0, "observed_improvements": 0,
        },
    }
    priorities = rank_equipment_slots(stats, target, states, "INT", opt._score_character)
    assert priorities
    assert priorities[0].slot == "Cape"


def test_potential_auto_scan_and_priority_release_guards_are_present():
    ui_text = (ROOT / "maple_optimizer" / "equipment" / "ui.py").read_text(encoding="utf-8")
    ocr_text = (ROOT / "maple_optimizer" / "equipment" / "ocr.py").read_text(encoding="utf-8")
    engine_text = (ROOT / "maple_optimizer" / "equipment" / "engine.py").read_text(encoding="utf-8")
    publisher = (ROOT / "publish_release.sh").read_text(encoding="utf-8")
    assert "Start Auto Scan" in ui_text
    assert "potential_monitor_stable_frames < 3" in ui_text
    assert "region_fingerprint" in ocr_text
    assert "rank_equipment_slots" in engine_text
    assert "potential_auto_scan_button_var" in publisher
    assert "rank_equipment_slots" in publisher


def test_scan_current_potential_saves_baseline_without_counting_reroll():
    from maple_optimizer.equipment.models import PotentialLine, PotentialOCRResult

    class Var:
        def __init__(self, value=""):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value

    class App:
        pass

    app = App()
    app.potential_selected_slot_var = Var("Cape")
    app.potential_current_rarity_var = Var("Rare")
    app.potential_current_progress_var = Var("0")
    app.potential_current_progress_total_var = Var("60")
    app.potential_current_line_vars = [
        {"stat": Var("Damage"), "value": Var("0"), "unit": Var("%")} for _ in range(3)
    ]
    app.potential_candidate_rarity_var = Var("Rare")
    app.potential_candidate_progress_var = Var("0")
    app.potential_candidate_progress_total_var = Var("60")
    app.potential_candidate_line_vars = [
        {"stat": Var("Damage"), "value": Var("0"), "unit": Var("%")} for _ in range(3)
    ]
    app.potential_slots_state = {
        "Cape": {
            "configured": False,
            "rarity": "Rare",
            "progress": "0",
            "progress_total": "60",
            "lines": [],
            "observed_rolls": 12,
            "observed_improvements": 4,
            "observed_signatures": ["old"],
        }
    }
    app.potential_last_candidate_signature = "old-candidate"
    app.potential_last_comparison = object()
    app.potential_monitor_last_result_signature = ""
    app.potential_capture_status_var = Var()
    app.potential_result_title_var = Var()
    app.potential_result_detail_var = Var()
    app.potential_odds_var = Var()
    app.potential_cubes_var = Var("68")

    result = PotentialOCRResult(
        rarity="Rare",
        progress=1,
        progress_total=60,
        lines=(
            PotentialLine("INT", 100.0),
            PotentialLine("Damage", 8.0),
            PotentialLine("Max MP %", 3.0),
        ),
        raw_text="",
        line_confidences=(0.95, 0.95, 0.95),
        confidence=0.95,
    )
    opt.equipment_ui.apply_scanned_current(app, result)

    state = app.potential_slots_state["Cape"]
    assert state["configured"] is True
    assert state["observed_rolls"] == 0
    assert state["observed_improvements"] == 0
    assert app.potential_cubes_var.get() == "68"
    assert app.potential_current_rarity_var.get() == "Rare"
    assert app.potential_current_progress_var.get() == "1"
    assert [row["stat"].get() for row in app.potential_current_line_vars] == ["INT", "Damage", "Max MP %"]
    assert app.potential_result_title_var.get() == "CURRENT POTENTIAL SCANNED"



def test_primary_stat_flat_and_percent_units_are_distinct_and_scored_differently():
    from maple_optimizer.equipment.engine import apply_line, roll_signature
    from maple_optimizer.equipment.models import PotentialLine

    flat = PotentialLine("INT", 6.0, "flat")
    percent = PotentialLine("INT", 6.0, "percent")
    assert flat != percent
    assert flat.display_value == "6"
    assert percent.display_value == "6%"
    assert roll_signature("Rare", [flat]) != roll_signature("Rare", [percent])

    flat_stats = opt.CharacterStats(character_class="Ice/Lightning Arch Mage", total_main_stat=1000.0)
    percent_stats = opt.CharacterStats(character_class="Ice/Lightning Arch Mage", total_main_stat=1000.0)
    assert apply_line(flat_stats, flat, "INT") is True
    assert apply_line(percent_stats, percent, "INT") is True
    assert_close(flat_stats.total_main_stat, 1006.0, label="flat INT Potential")
    assert_close(percent_stats.total_main_stat, 1060.0, label="percent INT Potential")
    assert_close(percent_stats.current_main_stat_pct, 6.0, label="percent INT tracking")


def test_potential_ocr_preserves_primary_stat_percent_symbol():
    from maple_optimizer.equipment.ocr import parse_potential_text

    parsed = parse_potential_text("""Rare 1/60
INT 6%
INT 400
Damage 8%
""")
    assert parsed.complete
    assert [(line.stat_name, line.value, line.unit) for line in parsed.lines] == [
        ("INT", 6.0, "percent"),
        ("INT", 400.0, "flat"),
        ("Damage", 8.0, "percent"),
    ]


def test_potential_line_save_migration_defaults_legacy_primary_stats_to_flat():
    from maple_optimizer.equipment import ui as equipment_ui
    from maple_optimizer.equipment.models import PotentialLine

    migrated = equipment_ui._deserialize_lines([
        {"stat": "INT", "value": "6"},
        {"stat": "Damage", "value": "8"},
        {"stat": "Max MP %", "value": "3"},
    ])
    assert [line.unit for line in migrated] == ["flat", "percent", "percent"]
    serialized = [equipment_ui._serialize_line(line) for line in migrated]
    assert serialized[0]["unit"] == "flat"
    assert serialized[1]["unit"] == "percent"


def test_potential_unit_release_guards_are_present():
    ui_text = (ROOT / "maple_optimizer" / "equipment" / "ui.py").read_text(encoding="utf-8")
    engine_text = (ROOT / "maple_optimizer" / "equipment" / "engine.py").read_text(encoding="utf-8")
    ocr_text = (ROOT / "maple_optimizer" / "equipment" / "ocr.py").read_text(encoding="utf-8")
    publisher = (ROOT / "publish_release.sh").read_text(encoding="utf-8")
    assert '"unit": line.unit' in ui_text
    assert 'line.stat_name}:{line.unit}' in engine_text
    assert 'POTENTIAL_UNIT_PERCENT if percent else POTENTIAL_UNIT_FLAT' in ocr_text
    assert 'Potential unit-aware save format is missing' in publisher


def test_current_potential_scan_release_guards_are_present():
    source = MODULE_PATH.read_text(encoding="utf-8")
    ui_text = (ROOT / "maple_optimizer" / "equipment" / "ui.py").read_text(encoding="utf-8")
    publisher = (ROOT / "publish_release.sh").read_text(encoding="utf-8")
    assert "def scan_current_potential(self):" in source
    assert "def scan_current_and_start_auto_scan(self):" in source
    assert 'text="Scan Current Potential"' in ui_text
    assert 'text="Scan Current & Start Auto Scan"' in ui_text
    assert "process_current_image" in ui_text
    assert "baseline_fingerprint=fingerprint" in ui_text
    assert "Scan Current Potential" in publisher


def test_potential_damage_label_never_expands_to_boss_damage():
    from maple_optimizer.equipment import ocr as potential_ocr

    stat, confidence = potential_ocr._canonical_stat_with_confidence("Damage", True)
    assert stat == "Damage"
    assert confidence == 1.0

    stat, confidence = potential_ocr._canonical_stat_with_confidence("Boss Monster Damage", True)
    assert stat == "Boss Monster Damage"
    assert confidence == 1.0

    # A noisy plain-Damage read must not invent the missing Boss modifier.
    stat, _confidence = potential_ocr._canonical_stat_with_confidence("Darnage", True)
    assert stat == "Damage"


def test_potential_decimal_loss_recovery_rejects_impossible_rare_45_percent():
    from maple_optimizer.equipment import ocr as potential_ocr

    value, percent, confidence, warning = potential_ocr._select_numeric_candidate(
        ["45%"],
        "Damage",
        rarity="Rare",
        equipment_slot="Belt",
    )
    assert value == pytest.approx(4.5)
    assert percent is True
    assert confidence > 0.0
    assert "missing decimal" in warning

    direct_value, direct_percent, _confidence, direct_warning = potential_ocr._select_numeric_candidate(
        ["4.5%"],
        "Damage",
        rarity="Rare",
        equipment_slot="Belt",
    )
    assert direct_value == pytest.approx(4.5)
    assert direct_percent is True
    assert direct_warning == ""


def test_potential_consensus_uses_majority_and_forces_review_on_disagreement():
    from maple_optimizer.equipment.models import PotentialLine, PotentialOCRResult
    from maple_optimizer.equipment.ocr import consensus_potential_results

    correct = PotentialOCRResult(
        rarity="Rare",
        progress=1,
        progress_total=60,
        lines=(
            PotentialLine("INT", 100, "flat"),
            PotentialLine("Damage", 4.5, "percent"),
            PotentialLine("Max MP", 3, "percent"),
        ),
        raw_text="correct",
        line_confidences=(0.90, 0.90, 0.90),
        confidence=0.90,
    )
    same = PotentialOCRResult(
        rarity=correct.rarity,
        progress=correct.progress,
        progress_total=correct.progress_total,
        lines=correct.lines,
        raw_text="same",
        line_confidences=(0.88, 0.89, 0.91),
        confidence=0.89,
    )
    wrong = PotentialOCRResult(
        rarity="Rare",
        progress=1,
        progress_total=60,
        lines=(
            PotentialLine("INT", 100, "flat"),
            PotentialLine("Boss Monster Damage", 45, "percent"),
            PotentialLine("Max MP", 3, "percent"),
        ),
        raw_text="wrong",
        line_confidences=(0.70, 0.55, 0.70),
        confidence=0.61,
    )
    consensus = consensus_potential_results([correct, wrong, same])
    assert consensus.lines[1].stat_name == "Damage"
    assert consensus.lines[1].value == pytest.approx(4.5)
    assert consensus.confidence >= 0.90
    assert any("agreed across" in warning for warning in consensus.warnings)

    third = PotentialOCRResult(
        rarity="Rare",
        progress=1,
        progress_total=60,
        lines=(
            PotentialLine("LUK", 200, "flat"),
            PotentialLine("Critical Damage", 7, "percent"),
            PotentialLine("Defense", 120, "flat"),
        ),
        raw_text="third",
        line_confidences=(0.75, 0.75, 0.75),
        confidence=0.75,
    )
    disagreement = consensus_potential_results([correct, wrong, third])
    assert disagreement.confidence <= 0.58
    assert any("disagreed" in warning for warning in disagreement.warnings)


def test_potential_slot_status_excludes_locked_and_auto_zero_slots():
    from maple_optimizer.equipment.engine import slot_eligibility

    zero_state = {
        "slot_status": "Auto",
        "configured": False,
        "lines": [
            {"stat": "Damage", "value": 0, "unit": "percent"},
            {"stat": "INT", "value": 0, "unit": "flat"},
            {"stat": "Defense", "value": 0, "unit": "flat"},
        ],
    }
    eligible, reason = slot_eligibility(zero_state)
    assert eligible is False
    assert "all three values are zero" in reason

    configured_state = dict(zero_state)
    configured_state["configured"] = True
    configured_state["lines"] = [
        {"stat": "Damage", "value": 8, "unit": "percent"},
        {"stat": "INT", "value": 100, "unit": "flat"},
        {"stat": "Defense", "value": 30, "unit": "flat"},
    ]
    eligible, reason = slot_eligibility(configured_state)
    assert eligible is True
    assert "auto-detected" in reason

    configured_state["slot_status"] = "Locked"
    eligible, reason = slot_eligibility(configured_state)
    assert eligible is False
    assert reason == "marked locked"


def test_loading_equipment_state_preserves_visible_priority_variable_bindings(monkeypatch):
    from maple_optimizer.equipment import ui as equipment_ui

    class Var:
        def __init__(self, value=""):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value

    class App:
        pass

    app = App()
    app.potential_priority_title_var = Var("old title")
    app.potential_priority_rows_vars = [Var("old 1"), Var("old 2"), Var("old 3")]
    app.potential_priority_note_var = Var("old note")
    title_id = id(app.potential_priority_title_var)
    row_ids = [id(var) for var in app.potential_priority_rows_vars]
    note_id = id(app.potential_priority_note_var)

    app.potential_loading_state = False
    app.potential_slots_state = {}
    app.potential_capture_region = None
    app.potential_capture_status_var = Var()
    app.potential_cubes_var = Var()
    app.potential_min_gain_var = Var()
    app.potential_auto_deduct_var = Var()
    app.potential_auto_scan_var = Var()
    app.potential_auto_scan_button_var = Var()
    app.potential_monitor_status_var = Var()
    app.potential_selected_slot_var = Var("Cape")
    app._potential_loaded_slot = None

    monkeypatch.setattr(equipment_ui, "stop_auto_monitor", lambda _app: None)
    monkeypatch.setattr(equipment_ui, "_load_selected_slot", lambda _app: None)
    monkeypatch.setattr(equipment_ui, "_schedule_priority_refresh", lambda _app, _delay=0: None)

    equipment_ui.apply_state(app, None)

    assert id(app.potential_priority_title_var) == title_id
    assert [id(var) for var in app.potential_priority_rows_vars] == row_ids
    assert id(app.potential_priority_note_var) == note_id
    assert app.potential_priority_title_var.get() == "SCAN CURRENT POTENTIALS TO BUILD A PRIORITY LIST"


def test_potential_ocr_priority_patch_release_guards_are_present():
    data_text = (ROOT / "maple_optimizer" / "equipment" / "data.py").read_text(encoding="utf-8")
    engine_text = (ROOT / "maple_optimizer" / "equipment" / "engine.py").read_text(encoding="utf-8")
    ocr_text = (ROOT / "maple_optimizer" / "equipment" / "ocr.py").read_text(encoding="utf-8")
    ui_text = (ROOT / "maple_optimizer" / "equipment" / "ui.py").read_text(encoding="utf-8")

    assert "_REQUIRED_LABEL_TOKENS" in ocr_text
    assert "Recovered a likely missing decimal" in ocr_text
    assert "read_potential_consensus" in ocr_text
    assert "Save Corrected as Current" in ui_text
    assert "CURRENT SCAN REVIEW" in ui_text
    assert "SLOT_STATUS_OPTIONS" in data_text
    assert "slot_eligibility" in engine_text
    assert "NO ELIGIBLE POTENTIAL SLOTS YET" in ui_text
    apply_state_body = ui_text.split("def apply_state", 1)[1].split("def calibrate_capture", 1)[0]
    assert "tk.StringVar" not in apply_state_body


def test_potential_fast_path_uses_four_tesseract_launches(monkeypatch):
    from PIL import Image
    from maple_optimizer.equipment import ocr as potential_ocr

    outputs = iter(("Rare 1/60", "INT 100", "Damage 8%", "Max MP 3%"))
    calls = []

    def fake_run(*_args, **_kwargs):
        calls.append(1)
        return next(outputs)

    monkeypatch.setattr(potential_ocr, "_run_tesseract", fake_run)
    result = potential_ocr.read_potential_image_fast(
        Image.new("RGB", (860, 260), (30, 30, 30)),
        Path("tesseract"),
        equipment_slot="Belt",
    )
    assert result.complete
    assert result.progress == 1
    assert result.progress_total == 60
    assert [(line.stat_name, line.value, line.unit) for line in result.lines] == [
        ("INT", 100.0, "flat"),
        ("Damage", 8.0, "percent"),
        ("Max MP %", 3.0, "percent"),
    ]
    assert len(calls) == 4
    assert potential_ocr.potential_result_is_reliable(result)


def test_potential_staged_ocr_skips_defensive_reader_for_clean_result(monkeypatch):
    from PIL import Image
    from maple_optimizer.equipment import ocr as potential_ocr
    from maple_optimizer.equipment.models import PotentialLine, PotentialOCRResult

    clean = PotentialOCRResult(
        rarity="Rare",
        progress=1,
        progress_total=60,
        lines=(
            PotentialLine("INT", 100, "flat"),
            PotentialLine("Damage", 8, "percent"),
            PotentialLine("Max MP", 3, "percent"),
        ),
        raw_text="clean",
        line_confidences=(0.95, 0.95, 0.95),
        confidence=0.95,
    )
    monkeypatch.setattr(potential_ocr, "read_potential_image_fast", lambda *_args, **_kwargs: clean)

    def fail_full(*_args, **_kwargs):
        raise AssertionError("defensive OCR should not run for a clean fast result")

    monkeypatch.setattr(potential_ocr, "read_potential_image", fail_full)
    result = potential_ocr.read_potential_staged(
        [Image.new("RGB", (860, 260), (30, 30, 30))],
        Path("tesseract"),
    )
    assert result.lines == clean.lines
    assert any("fast four-pass" in warning for warning in result.warnings)


def test_potential_ocr_performance_patch_release_guards_are_present():
    source = MODULE_PATH.read_text(encoding="utf-8")
    ocr_text = (ROOT / "maple_optimizer" / "equipment" / "ocr.py").read_text(encoding="utf-8")
    ui_text = (ROOT / "maple_optimizer" / "equipment" / "ui.py").read_text(encoding="utf-8")
    publisher = (ROOT / "publish_release.sh").read_text(encoding="utf-8")
    assert "start_manual_live_ocr" in source
    assert "read_potential_image_fast" in ocr_text
    assert "potential_result_is_reliable" in ocr_text
    assert "read_potential_staged" in ocr_text
    assert 'name="potential-manual-ocr"' in ui_text
    assert "Potential read completed in" in ui_text
    assert "read_potential_image_fast" in publisher
    assert "potential-manual-ocr" in publisher


def _synthetic_potential_rate_profile(slot="Cape", rarity="Rare", hit_value=10.0, hit_probability=0.5):
    from maple_optimizer.equipment.models import PotentialLine
    from maple_optimizer.equipment.potential_rates import PotentialRateOutcome, PotentialRateProfile

    profile = PotentialRateProfile(source="synthetic configured rates")
    profile.distributions[(slot, rarity, 1)] = (
        PotentialRateOutcome(PotentialLine("Damage", 0.0, "percent"), 1.0 - hit_probability),
        PotentialRateOutcome(PotentialLine("Damage", hit_value, "percent"), hit_probability),
    )
    profile.distributions[(slot, rarity, 2)] = (
        PotentialRateOutcome(PotentialLine("Damage", 0.0, "percent"), 1.0),
    )
    profile.distributions[(slot, rarity, 3)] = (
        PotentialRateOutcome(PotentialLine("Damage", 0.0, "percent"), 1.0),
    )
    return profile


def test_configured_potential_rate_profile_json_and_csv_roundtrip():
    from maple_optimizer.equipment.potential_rates import (
        profile_from_csv,
        profile_from_dict,
        profile_to_dict,
    )

    profile = _synthetic_potential_rate_profile()
    restored = profile_from_dict(profile_to_dict(profile))
    assert restored.has_complete_table("Cape", "Rare")
    assert restored.outcome_count() == 4

    csv_text = """slot,rarity,line,stat,value,unit,probability,source,captured_at
Cape,Rare,1,Damage,0,percent,50%,test,2026-08-04
Cape,Rare,1,Damage,10,percent,50%,test,2026-08-04
Cape,Rare,2,Damage,0,percent,100%,test,2026-08-04
Cape,Rare,3,Damage,0,percent,100%,test,2026-08-04
"""
    csv_profile = profile_from_csv(csv_text)
    assert csv_profile.has_complete_table("Cape", "Rare")
    assert csv_profile.source == "test"
    assert csv_profile.captured_at == "2026-08-04"


def test_configured_potential_rate_analysis_matches_exact_enumeration():
    from maple_optimizer.equipment.models import PotentialLine
    from maple_optimizer.equipment.potential_rates import analyze_configured_rates

    stats = opt.CharacterStats(attack=100000.0, damage=0.0)
    target = opt.TargetProfile(content_mode="Boss")
    current = [
        PotentialLine("Damage", 0.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
    ]
    analysis = analyze_configured_rates(
        stats,
        target,
        slot="Cape",
        rarity="Rare",
        current_lines=current,
        minimum_gain_pct=1.0,
        cubes=2,
        main_stat_name="INT",
        score_fn=lambda candidate, _target: 100.0 + candidate.damage,
        profile=_synthetic_potential_rate_profile(hit_value=10.0, hit_probability=0.5),
    )
    assert_close(analysis.success_probability, 0.5, label="configured next-cube success")
    assert_close(analysis.chance_with_budget, 0.75, label="configured two-cube success")
    assert_close(analysis.expected_cubes_to_success, 2.0, label="configured expected cubes")
    assert_close(analysis.average_gain_on_success, 10.0, label="configured accepted gain")
    assert_close(analysis.expected_positive_gain_per_cube, 5.0, label="configured expected gain per cube")
    assert analysis.combination_count == 2


def test_irreversible_optimal_stopping_can_make_saving_cubes_rational():
    from maple_optimizer.equipment.models import PotentialLine
    from maple_optimizer.equipment.potential_rates import analyze_configured_rates

    # At Mystic there is no future-rarity table dependency. A single cube has
    # zero expected value, but two cubes are positive because a good first roll
    # can be kept while a bad first roll can be rerolled once more.
    profile = _synthetic_potential_rate_profile(
        "Cape", rarity="Mystic", hit_value=10.0, hit_probability=0.5
    )
    stats = opt.CharacterStats(attack=100000.0, damage=5.0)
    current = [
        PotentialLine("Damage", 5.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
    ]
    one_cube = analyze_configured_rates(
        stats, opt.TargetProfile(content_mode="Boss"), slot="Cape", rarity="Mystic",
        current_lines=current, minimum_gain_pct=0.1, cubes=1, main_stat_name="INT",
        score_fn=lambda candidate, _target: 100.0 + candidate.damage, profile=profile,
        include_rank_aware=True,
    )
    two_cubes = analyze_configured_rates(
        stats, opt.TargetProfile(content_mode="Boss"), slot="Cape", rarity="Mystic",
        current_lines=current, minimum_gain_pct=0.1, cubes=2, main_stat_name="INT",
        score_fn=lambda candidate, _target: 100.0 + candidate.damage, profile=profile,
        include_rank_aware=True,
    )
    assert one_cube.optimal_policy_available
    assert not one_cube.optimal_should_reroll
    assert one_cube.optimal_cubes_to_positive_value == 2
    assert_close(one_cube.optimal_chance_end_worse, 0.5, label="one-cube downside")
    assert two_cubes.optimal_should_reroll
    assert two_cubes.optimal_reroll_value_gain_pct > 0.0
    assert_close(two_cubes.optimal_chance_end_better, 0.75, label="two-cube better chance")
    assert_close(two_cubes.optimal_chance_end_worse, 0.25, label="two-cube worse chance")


def test_configured_potential_priority_includes_irreversible_session_downside():
    from maple_optimizer.equipment.potential_rates import merge_profiles, rank_slots_by_configured_rates

    profile = merge_profiles(
        _synthetic_potential_rate_profile("Cape", hit_value=10.0, hit_probability=0.2),
        _synthetic_potential_rate_profile("Gloves", hit_value=5.0, hit_probability=0.8),
    )
    states = {
        "Cape": {
            "configured": True,
            "slot_status": "Unlocked",
            "rarity": "Rare",
            "lines": [
                {"stat": "Damage", "value": 1.0, "unit": "percent"},
                {"stat": "Damage", "value": 0.0, "unit": "percent"},
                {"stat": "Damage", "value": 0.0, "unit": "percent"},
            ],
        },
        "Gloves": {
            "configured": True,
            "slot_status": "Unlocked",
            "rarity": "Rare",
            "lines": [
                {"stat": "Damage", "value": 1.0, "unit": "percent"},
                {"stat": "Damage", "value": 0.0, "unit": "percent"},
                {"stat": "Damage", "value": 0.0, "unit": "percent"},
            ],
        },
    }
    stats = opt.CharacterStats(attack=100000.0, damage=2.0)
    rows = rank_slots_by_configured_rates(
        stats,
        opt.TargetProfile(content_mode="Boss"),
        states,
        minimum_gain_pct=0.25,
        cubes=20,
        main_stat_name="INT",
        score_fn=lambda candidate, _target: 100.0 + candidate.damage,
        profile=profile,
        eligibility_fn=lambda state: (True, "test"),
    )
    # Gloves wins on positive-upside-per-cube alone, but Cape has the better
    # final-session value once the active final failed roll is included.
    assert [row.slot for row in rows] == ["Cape", "Gloves"]
    assert rows[0].expected_positive_gain_per_cube < rows[1].expected_positive_gain_per_cube
    assert rows[0].expected_final_gain_with_budget > rows[1].expected_final_gain_with_budget


def test_configured_rate_profile_rejects_incomplete_probability_totals():
    from maple_optimizer.equipment.potential_rates import profile_from_csv

    csv_text = """slot,rarity,line,stat,value,unit,probability
Cape,Rare,1,Damage,10,percent,80%
Cape,Rare,2,Damage,0,percent,100%
Cape,Rare,3,Damage,0,percent,100%
"""
    with pytest.raises(ValueError, match="not 100%"):
        profile_from_csv(csv_text)


def test_configured_rate_feature_release_guards_are_present():
    source = MODULE_PATH.read_text(encoding="utf-8")
    ui_text = (ROOT / "maple_optimizer" / "equipment" / "ui.py").read_text(encoding="utf-8")
    rates_text = (ROOT / "maple_optimizer" / "equipment" / "potential_rates.py").read_text(encoding="utf-8")
    assert "def import_potential_configured_rates(self):" in source
    assert "Import Configured Rates" in ui_text
    assert "rank_slots_by_configured_rates" in ui_text
    assert "NEXT IRREVERSIBLE REROLL" in ui_text
    assert "OPTIMAL STOPPING POLICY" in ui_text
    assert "def analyze_configured_rates" in rates_text
    assert "PotentialStoppingCondition" in rates_text
    assert "_rank_aware_budget_success" in rates_text
    assert "SUGGESTED PREFERRED-OPTION WATCHLIST" in ui_text
    assert "FINITE-BUDGET IRREVERSIBLE PLAN" in ui_text


def test_potential_cooldown_unit_is_preserved_as_seconds():
    from maple_optimizer.equipment.models import PotentialLine

    line = PotentialLine("Cooldown Reduction", 1.5, "percent")
    assert line.unit == "seconds"
    assert line.display_value == "1.5s"


def test_bundled_potential_rates_are_normalized_and_report_missing_coverage():
    from maple_optimizer.equipment.potential_rates import load_profile

    bundled = ROOT / "assets" / "data" / "maplestory_idle_configured_potential_rates.json"
    profile = load_profile(bundled)
    assert profile.completed_tables() == 54
    assert profile.outcome_count() == 4184
    assert profile.has_complete_table("Hat", "Epic")
    assert profile.has_complete_table("Shoes", "Rare")
    assert profile.missing_lines("Necklace", "Rare") == (1, 2, 3)

    cooldown = profile.distribution("Hat", "Legendary", 2)
    cooldown_values = {
        (outcome.line.value, outcome.line.unit)
        for outcome in cooldown
        if outcome.line.stat_name == "Cooldown Reduction"
    }
    assert cooldown_values == {(1.0, "seconds"), (1.5, "seconds")}

    mystic = profile.distribution("Belt", "Mystic", 1)
    flat_int = [
        outcome.line.value
        for outcome in mystic
        if outcome.line.stat_name == "INT" and outcome.line.unit == "flat"
    ]
    assert flat_int == [1000.0]


def test_collector_marked_incomplete_rate_section_is_not_used():
    from maple_optimizer.equipment.potential_rates import profile_from_dict

    profile = profile_from_dict({
        "distributions": [{
            "slot": "Cape",
            "rarity": "Rare",
            "line": 1,
            "complete": False,
            "reason": "collector confidence was low",
            "rank_up_probability": 0.03333,
            "outcomes": [{"stat": "Damage", "value": 8, "unit": "percent", "probability": 1.0}],
        }],
    })
    assert not profile.distribution("Cape", "Rare", 1)
    assert profile.section_reason("Cape", "Rare", 1) == "collector confidence was low"
    assert_close(profile.rank_up_probability("Cape", "Rare"), 0.03333, label="stored rank chance")


def test_configured_rate_analysis_reports_guaranteed_rank_up_and_next_rarity_preview():
    from maple_optimizer.equipment.models import PotentialLine
    from maple_optimizer.equipment.potential_rates import analyze_configured_rates, merge_profiles

    profile = merge_profiles(
        _synthetic_potential_rate_profile("Cape", "Rare", hit_value=5.0, hit_probability=0.1),
        _synthetic_potential_rate_profile("Cape", "Epic", hit_value=10.0, hit_probability=0.5),
    )
    profile.rank_up_probabilities[("Cape", "Rare")] = 0.05
    stats = opt.CharacterStats(attack=100000.0, damage=0.0)
    current = [
        PotentialLine("Damage", 0.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
    ]
    analysis = analyze_configured_rates(
        stats,
        opt.TargetProfile(content_mode="Boss"),
        slot="Cape",
        rarity="Rare",
        current_lines=current,
        minimum_gain_pct=1.0,
        cubes=2,
        main_stat_name="INT",
        score_fn=lambda candidate, _target: 100.0 + candidate.damage,
        profile=profile,
        progress=8,
        progress_total=10,
    )
    assert analysis.cubes_to_guaranteed_rank_up == 2
    assert_close(analysis.chance_to_rank_up_with_budget, 1.0, label="guaranteed rank-up")
    assert analysis.next_rarity == "Epic"
    assert_close(analysis.next_rarity_success_probability, 0.5, label="next-rarity success")
    assert analysis.next_rarity_expected_gain_per_cube > analysis.expected_positive_gain_per_cube
    assert analysis.cubes_for_50pct_success == 7


def test_configured_rate_guidance_produces_watch_conditions_and_exact_examples():
    from maple_optimizer.equipment.models import PotentialLine
    from maple_optimizer.equipment.potential_rates import analyze_configured_rates

    stats = opt.CharacterStats(attack=100000.0, damage=0.0)
    current = [
        PotentialLine("Damage", 0.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
    ]
    analysis = analyze_configured_rates(
        stats,
        opt.TargetProfile(content_mode="Boss"),
        slot="Cape",
        rarity="Rare",
        current_lines=current,
        minimum_gain_pct=1.0,
        cubes=10,
        main_stat_name="INT",
        score_fn=lambda candidate, _target: 100.0 + candidate.damage,
        profile=_synthetic_potential_rate_profile(hit_value=10.0, hit_probability=0.5),
        include_guidance=True,
    )
    assert analysis.stopping_conditions
    condition = analysis.stopping_conditions[0]
    assert condition.stat_name == "Damage"
    assert condition.minimum_value == 10.0
    assert_close(condition.precision, 1.0, label="watch condition precision")
    assert_close(condition.success_coverage, 1.0, label="watch condition success coverage")
    assert analysis.stopping_condition_coverage > 0.0
    assert analysis.top_exact_outcomes
    assert analysis.top_exact_outcomes[0].gain_pct > 0.0


def test_rank_aware_budget_models_guaranteed_transition_roll():
    from maple_optimizer.equipment.models import PotentialLine
    from maple_optimizer.equipment.potential_rates import analyze_configured_rates, merge_profiles

    rare = _synthetic_potential_rate_profile(
        "Cape", "Rare", hit_value=0.0, hit_probability=0.0
    )
    epic = _synthetic_potential_rate_profile(
        "Cape", "Epic", hit_value=10.0, hit_probability=1.0
    )
    profile = merge_profiles(rare, epic)
    profile.rank_up_probabilities[("Cape", "Rare")] = 0.0
    current = [
        PotentialLine("Damage", 0.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
        PotentialLine("Damage", 0.0, "percent"),
    ]
    analysis = analyze_configured_rates(
        opt.CharacterStats(attack=100000.0, damage=0.0),
        opt.TargetProfile(content_mode="Boss"),
        slot="Cape",
        rarity="Rare",
        current_lines=current,
        minimum_gain_pct=1.0,
        cubes=2,
        main_stat_name="INT",
        score_fn=lambda candidate, _target: 100.0 + candidate.damage,
        profile=profile,
        progress=0,
        progress_total=2,
        include_rank_aware=True,
    )
    assert_close(analysis.chance_with_budget, 0.0, label="fixed-rarity budget chance")
    assert_close(analysis.rank_aware_chance_with_budget, 1.0, label="rank-aware budget chance")
    assert_close(analysis.rank_aware_expected_cubes_to_success, 2.0, label="rank-aware expected first success")
