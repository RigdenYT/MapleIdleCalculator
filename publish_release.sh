#!/usr/bin/env bash
# Release helper; APP_VERSION remains the source of truth.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

die() {
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

need_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

need_command git
need_command python3


cleanup_legacy_update_notes() {
    python3 - <<'PY_CLEAN_NOTES'
from pathlib import Path
import re

pattern = re.compile(
    r"^[A-Z0-9][A-Z0-9_-]*[-_]\d+\.\d+\.\d+\.txt$",
    re.IGNORECASE,
)
removed = []
for path in sorted(Path(".").iterdir()):
    if path.is_file() and pattern.fullmatch(path.name):
        path.unlink()
        removed.append(path.name)

if removed:
    print("Removed legacy per-version update-note files:")
    for name in removed:
        print(f"  - {name}")
else:
    print("No legacy per-version update-note files were present.")
PY_CLEAN_NOTES
}

[[ -d .git ]] || die "Store publish_release.sh in the root of the Git repository."
cleanup_legacy_update_notes
[[ -f maplestory_idle_companion_optimizer.py ]] || die "Application source was not found."
[[ -f build_tools/release_metadata.py ]] || die "Release metadata tool was not found."
[[ -x build_tools/build_linux.sh ]] || die "build_tools/build_linux.sh is missing or not executable."
[[ -f .github/workflows/build-desktop-releases.yml ]] || die "GitHub release workflow was not found."
[[ -f maple_optimizer/hero_power/data.py ]] || die "Hero Power data module is missing."
[[ -f maple_optimizer/hero_power/models.py ]] || die "Hero Power models module is missing."
[[ -f maple_optimizer/hero_power/engine.py ]] || die "Hero Power engine module is missing."
[[ -f maple_optimizer/hero_power/ui.py ]] || die "Hero Power UI module is missing."
[[ -f maple_optimizer/equipment/data.py ]] || die "Equipment Potential data module is missing."
[[ -f maple_optimizer/equipment/models.py ]] || die "Equipment Potential models module is missing."
[[ -f maple_optimizer/equipment/engine.py ]] || die "Equipment Potential engine module is missing."
[[ -f maple_optimizer/equipment/ocr.py ]] || die "Equipment Potential OCR module is missing."
[[ -f maple_optimizer/equipment/potential_rates.py ]] || die "Equipment Potential configured-rate module is missing."
[[ -f maple_optimizer/equipment/ui.py ]] || die "Equipment Potential UI module is missing."
[[ -f assets/data/maplestory_idle_configured_potential_rates.json ]] || die "Bundled Potential rate data is missing."

workflow_file=".github/workflows/build-desktop-releases.yml"
grep -q 'xvfb' "$workflow_file" || die "The GitHub workflow is stale: Linux Xvfb support is missing. Reinstall the complete release package, including the hidden .github folder."
grep -q 'xauth' "$workflow_file" || die "The GitHub workflow is stale: Linux xauth support is missing."
grep -q -- '--packaging-smoke-test' build_tools/build_linux.sh || die "The Linux build script is stale: packaged startup test is missing."
grep -q -- '--packaging-smoke-test' build_tools/build_windows.bat || die "The Windows build script is stale: packaged startup test is missing."
grep -q 'maple-idle-packaging-smoke-' maplestory_idle_companion_optimizer.py || die "The application source is stale: isolated packaging-test state is missing."
grep -q 'optimize_all_tiers' maple_optimizer/hero_power/engine.py || die "The Hero Power engine is stale: tier progression planner is missing."
grep -q 'analyze_reroll_strategies' maple_optimizer/hero_power/engine.py || die "The Hero Power engine is stale: medal-aware action planner is missing."
grep -q 'ability_reserved_medals_var' maple_optimizer/hero_power/ui.py || die "The Hero Power UI is stale: action-planner budget controls are missing."
grep -q 'hero_plan_chance_var' maple_optimizer/hero_power/ui.py || die "The Hero Power UI is stale: concise action dashboard is missing."
grep -q 'top_three_budget_probability_pct' maple_optimizer/hero_power/engine.py || die "The Hero Power engine is stale: top-three budget probability is missing."
grep -q '_accumulate_stopping_metrics' maple_optimizer/hero_power/engine.py || die "The Hero Power engine is stale: corrected first-success probability accumulation is missing."
grep -q 'top_three_expected_attempts_given_success' maple_optimizer/hero_power/models.py || die "The Hero Power result models are stale: expected top-three timing is missing."
grep -q 'ability_approach_var' maple_optimizer/hero_power/ui.py || die "The Hero Power UI is stale: optimization approach control is missing."
grep -q 'STOP REROLLING IF YOU GET ANY OF THESE' maple_optimizer/hero_power/ui.py || die "The Hero Power UI is stale: explicit stopping rules are missing."
grep -q 'compare_rolls' maple_optimizer/equipment/engine.py || die "The Equipment Potential engine is stale: complete-roll comparison is missing."
grep -q 'read_potential_image' maple_optimizer/equipment/ocr.py || die "The Equipment Potential OCR reader is missing."
grep -q 'Read New Roll' maple_optimizer/equipment/ui.py || die "The Equipment Potential new-roll capture workflow is missing."
grep -q 'Scan Current Potential' maple_optimizer/equipment/ui.py || die "The Equipment Potential current-scan workflow is missing."
grep -q 'Scan Current & Start Auto Scan' maple_optimizer/equipment/ui.py || die "The Equipment Potential combined setup/monitor workflow is missing."
grep -q 'process_current_image' maple_optimizer/equipment/ui.py || die "The Equipment Potential current-scan processor is missing."
grep -q 'Record Entered Reroll as Current' maple_optimizer/equipment/ui.py || die "The Equipment Potential irreversible reroll workflow is missing."
grep -q 'potential_auto_scan_button_var' maple_optimizer/equipment/ui.py || die "The Equipment Potential automatic change monitor is missing."
grep -q 'potential_monitor_stable_frames < 3' maple_optimizer/equipment/ui.py || die "The Equipment Potential three-frame stability guard is missing."
grep -q 'region_fingerprint' maple_optimizer/equipment/ocr.py || die "The Equipment Potential image-change detector is missing."
grep -q 'rank_equipment_slots' maple_optimizer/equipment/engine.py || die "The Equipment Potential cross-slot priority engine is missing."
grep -q 'CUBE THIS NEXT' maple_optimizer/equipment/ui.py || die "The Equipment Potential priority dashboard is missing."
grep -q '"unit": line.unit' maple_optimizer/equipment/ui.py || die "Potential unit-aware save format is missing."
grep -q 'line.stat_name}:{line.unit}' maple_optimizer/equipment/engine.py || die "Potential roll signatures do not preserve flat-versus-percent units."
grep -q 'POTENTIAL_UNIT_PERCENT if percent else POTENTIAL_UNIT_FLAT' maple_optimizer/equipment/ocr.py || die "Potential OCR does not preserve percent symbols."
grep -q 'AMBIGUOUS_UNIT_OPTIONS' maple_optimizer/equipment/models.py || die "Potential primary-stat unit model is missing."
grep -q '_REQUIRED_LABEL_TOKENS' maple_optimizer/equipment/ocr.py || die "Potential OCR token-aware label matching is missing."
grep -q 'Recovered a likely missing decimal' maple_optimizer/equipment/ocr.py || die "Potential OCR decimal recovery is missing."
grep -q 'read_potential_consensus' maple_optimizer/equipment/ocr.py || die "Potential OCR multi-capture consensus is missing."
grep -q 'read_potential_image_fast' maple_optimizer/equipment/ocr.py || die "Potential OCR fast path is missing."
grep -q 'potential_result_is_reliable' maple_optimizer/equipment/ocr.py || die "Potential OCR staged confidence gate is missing."
grep -q 'read_potential_staged' maple_optimizer/equipment/ocr.py || die "Potential OCR adaptive fallback path is missing."
grep -q 'potential-manual-ocr' maple_optimizer/equipment/ui.py || die "Potential manual OCR is not running in a background thread."
grep -q 'analyze_configured_rates' maple_optimizer/equipment/potential_rates.py || die "Potential configured-rate exact enumeration is missing."
grep -q 'rank_slots_by_configured_rates' maple_optimizer/equipment/ui.py || die "Potential exact-rate equipment ranking is missing."
grep -q 'Import Configured Rates' maple_optimizer/equipment/ui.py || die "Potential configured-rate import controls are missing."
grep -q 'NEXT IRREVERSIBLE REROLL' maple_optimizer/equipment/ui.py || die "Potential irreversible-risk guidance is missing."
grep -q 'POTENTIAL_UNIT_SECONDS' maple_optimizer/equipment/models.py || die "Potential seconds-unit support is missing."
grep -q 'load_bundled_configured_rates' maple_optimizer/equipment/ui.py || die "Bundled Potential configured-rate loader is missing."
grep -q 'chance_to_rank_up_with_budget' maple_optimizer/equipment/potential_rates.py || die "Potential rank-up budget analysis is missing."
grep -q 'incomplete_sections' maple_optimizer/equipment/potential_rates.py || die "Potential missing-rate coverage tracking is missing."
grep -q 'SAVE FOR 50% SESSION' maple_optimizer/equipment/potential_rates.py || die "Potential save-for-session recommendation is missing."
grep -q 'PotentialStoppingCondition' maple_optimizer/equipment/potential_rates.py || die "Potential preferred-option stopping conditions are missing."
grep -q '_rank_aware_budget_success' maple_optimizer/equipment/potential_rates.py || die "Potential cross-rarity budget simulation is missing."
grep -q '_optimal_stopping_plan' maple_optimizer/equipment/potential_rates.py || die "Potential irreversible optimal-stopping solver is missing."
grep -q 'optimal_chance_end_worse' maple_optimizer/equipment/potential_rates.py || die "Potential ending-downside metrics are missing."
grep -q 'normalize_potential_panel' maple_optimizer/equipment/ocr.py || die "Potential panel localization/normalization is missing."
grep -q 'PotentialCalibrationPreviewDialog' maple_optimizer/equipment/ui.py || die "Potential calibration preview is missing."
grep -q 'REROLL OCR REVIEW — OLD ROLL UNAVAILABLE' maple_optimizer/equipment/ui.py || die "Potential active-reroll OCR review state is missing."
grep -q 'SUGGESTED PREFERRED-OPTION WATCHLIST' maple_optimizer/equipment/ui.py || die "Potential preferred-option watchlist UI is missing."
grep -q 'FINITE-BUDGET IRREVERSIBLE PLAN' maple_optimizer/equipment/ui.py || die "Potential finite-budget stopping guidance UI is missing."
grep -q 'Save Corrected as Current' maple_optimizer/equipment/ui.py || die "Potential current-scan review workflow is missing."
grep -q 'CURRENT SCAN REVIEW' maple_optimizer/equipment/ui.py || die "Potential current-scan review labeling is missing."
grep -q 'SLOT_STATUS_OPTIONS' maple_optimizer/equipment/data.py || die "Potential slot-status controls are missing."
grep -q 'slot_eligibility' maple_optimizer/equipment/engine.py || die "Potential locked-slot eligibility filter is missing."
grep -q 'NO ELIGIBLE POTENTIAL SLOTS YET' maple_optimizer/equipment/ui.py || die "Potential priority diagnostics are missing."
python3 - <<'PY_PRIORITY_BINDING' || die "Potential priority display variables are still being replaced during account loading."
from pathlib import Path
text = Path('maple_optimizer/equipment/ui.py').read_text(encoding='utf-8')
body = text.split('def apply_state', 1)[1].split('def calibrate_capture', 1)[0]
raise SystemExit(1 if 'tk.StringVar' in body else 0)
PY_PRIORITY_BINDING
python3 - <<'PY' || die "The application source is stale: worker-queue follow-up initialization is missing."
from pathlib import Path
text = Path('maplestory_idle_companion_optimizer.py').read_text(encoding='utf-8')
advanced = text[text.index('class AdvancedOptimizerApp'): ]
method = advanced[advanced.index('    def _poll_worker_queue(self):'):advanced.index('    def _display_sensitivity_result', advanced.index('    def _poll_worker_queue(self):'))]
raise SystemExit(0 if 'auto_followup = False' in method else 1)
PY

branch="$(git branch --show-current)"
[[ "$branch" == "main" ]] || die "Releases must be made from main. Current branch: ${branch:-detached HEAD}"
git remote get-url origin >/dev/null 2>&1 || die "The Git remote named origin is not configured."

printf 'Fetching origin/main and release tags...\n'
git fetch origin main --tags

if ! git merge-base --is-ancestor origin/main HEAD; then
    die "Local main has diverged from origin/main. Resolve the branch before publishing."
fi
if ! git merge-base --is-ancestor HEAD origin/main; then
    die "Local main is behind origin/main. Pull the latest changes before publishing."
fi

printf '\nUpdating and validating release metadata...\n'
python3 build_tools/release_metadata.py --write-windows-version
python3 build_tools/release_metadata.py --check
version="$(python3 build_tools/release_metadata.py --print-version)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Invalid APP_VERSION: $version"
tag="v${version}"

if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    die "Local tag $tag already exists. Increase APP_VERSION for a new release."
fi
if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
    die "Remote tag $tag already exists. Increase APP_VERSION for a new release."
fi

printf '\nBuilding and testing the Linux release locally...\n'
printf 'This includes frozen startup tests for both the one-folder and single-file programs.\n'
./build_tools/build_linux.sh

printf '\nFiles that will be included in the release commit:\n'
git status --short

printf '\nPublishing %s will:\n' "$tag"
printf '  1. Commit all current repository changes as "Release %s"\n' "$version"
printf '  2. Push main to origin\n'
printf '  3. Push tag %s\n' "$tag"
printf '  4. Make GitHub build native Windows and Linux programs\n'
printf '  5. Publish both programs and checksums as a GitHub Release\n\n'

read -r -p "Build and publish $tag now? [y/N] " answer
case "$answer" in
    y|Y|yes|YES|Yes) ;;
    *) printf 'Release cancelled. Nothing was committed, pushed, or tagged.\n'; exit 0 ;;
esac

git add -A
if git diff --cached --quiet; then
    printf '\nNo uncommitted source changes were found; releasing the current commit.\n'
else
    git commit -m "Release $version"
fi

printf '\nPushing main...\n'
git push origin main

printf '\nCreating and pushing %s...\n' "$tag"
git tag -a "$tag" -m "Release $version"
git push origin "$tag"

printf '\n%s was pushed successfully.\n' "$tag"
printf 'GitHub Actions is now building the Windows EXE and Linux executable.\n'
printf 'After both packaged startup tests pass, the workflow will publish the release assets.\n'
