#!/usr/bin/env python3
"""Dependency-free regression checks for the optimizer engine."""

from __future__ import annotations

import importlib.util
import json
import math
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
    assert linux_text.count("--packaging-smoke-test") >= 1
    assert windows_text.count("--packaging-smoke-test") >= 2
    assert "xvfb" in workflow_text
