MAPLESTORY IDLE COMPANION OPTIMIZER 2.6.9
============================================================

OVERVIEW
--------
This is a local Python/Tkinter optimizer for MapleStory: Idle RPG companion
teams. It exhaustively evaluates every valid team made from the companion pages
you own, using the character statistics and target assumptions entered for the
active build.

Version 2.0 reorganizes the program around one shared account with multiple
content builds. It also adds robustness analysis for uncertain inputs, Main
companion comparison modes, result explanations, readiness checks, and a
next-level companion upgrade planner.

No pip packages are required for the optimizer engine itself. Packaged releases
bundle Python, Pillow, the English Tesseract OCR runtime, portraits, background,
help images, and other assets. Running directly from source still requires the
local Python/Tk/Pillow/Tesseract development dependencies described below.

WHAT CHANGED IN 2.6.9
---------------------
- Fixed the companion role/equip chooser opening for only a split second on
  affected Linux/Tk window managers.
- The native role menu is now posted after the badge's initiating mouse click
  has fully completed, preventing that same click's release event from
  immediately dismissing the menu.
- Rapid repeated badge clicks cancel the pending popup before scheduling a new
  one, preventing overlapping role menus.
- Corrected the role menu foreground color so its choices remain readable on
  the light popup background.
- Added a regression test for delayed role-menu scheduling and cancellation.
- The packaged startup smoke test now performs an actual role-menu press, release,
  selection, and cleanup cycle on both native build runners.
- No optimizer formulas, account data, or save-file fields changed.

WHAT CHANGED IN 2.6.8
---------------------
- Fixed the packaged Linux startup crash caused by Pillow dynamically importing
  PIL._tkinter_finder after PyInstaller analysis had completed.
- The PyInstaller specification now explicitly bundles PIL._tkinter_finder and
  PIL._imagingtk for both Windows and Linux releases.
- Decorative gradient widgets now fall back to flat Tk controls if the Pillow/Tk
  bridge fails unexpectedly, so a cosmetic rendering problem cannot crash startup.
- Both the one-folder and single-file programs are now launched automatically
  after every build with a packaging smoke-test flag. A release build fails if
  the complete Tk/Pillow interface cannot be constructed.
- Linux GitHub builds now use Xvfb for the packaged GUI startup check. Windows
  builds run the same check on the native Windows runner.
- Added publish_release.sh to each complete source package. Running it validates
  and locally tests the Linux build, commits and pushes the version, then pushes
  the matching tag that makes GitHub build and publish both platform files.
- No optimizer formulas, account data, or save-file fields changed.

WHAT CHANGED IN 2.6.7
---------------------
- Added a GitHub Actions release pipeline that builds native Windows x86_64
  and Linux x86_64 packages from the same tagged source.
- Manual workflow runs create downloadable test artifacts without publishing a
  release. Pushing a matching version tag, such as v2.6.7, builds both systems
  and publishes the files to a GitHub Release automatically.
- Added release-metadata validation so the Git tag, application version,
  executable names, README, and Windows version information cannot silently
  disagree.
- Windows version metadata is generated from APP_VERSION instead of requiring
  several manual edits for every release.
- Build outputs are now packaged into upload-ready single-file and one-folder
  archives with per-platform SHA-256 checksum files.
- Added repository setup and future-release instructions for running the entire
  process from Linux through GitHub-hosted Windows and Linux runners.
- OCR binaries are staged on the temporary build runner rather than stored in
  the source repository.
- No optimizer formulas, account data, or save-file fields changed.

WHAT CHANGED IN 2.6.6
---------------------
- Added release-ready PyInstaller specifications and separate Windows/Linux
  build scripts. Each script creates an easy-to-test one-folder build first and
  then the final single-file build.
- Added a Fire/Poison Arch Mage Legendary application icon in PNG and multi-size
  Windows ICO formats. The icon is applied both to the packaged executable and
  the running Tk application.
- Screenshot OCR now prefers a Tesseract runtime bundled inside the application,
  including English language data, and falls back to a system installation only
  for development copies. Testers do not need to install Tesseract.
- Added platform-specific OCR staging. The build computer supplies Tesseract
  once; the staging script gathers the executable, required libraries, English
  data, and TSV configuration for inclusion in the release.
- Added persistent startup, Tk callback, and unhandled-thread crash logs under
  the application's per-user configuration directory.
- Diagnostic bug-report ZIPs now identify frozen/resource/OCR paths and include
  up to three recent crash logs when available.
- Added Windows version metadata and a release smoke-test checklist.
- Expanded the regression suite from 17 to 20 tests. No optimizer formulas,
  account data, or save-file fields changed.

WHAT CHANGED IN 2.6.5
---------------------
- Enlarged the screenshot preparation warning and changed its layout so the
  Don't show again option and Continue/Cancel buttons always retain visible space.
- The dialog now sizes itself to the available display and keeps only the
  explanatory text area flexible on short or heavily scaled screens.
- The warning is built while hidden and then centered, preventing a brief flash
  at the smaller Tk default size.
- No optimizer formulas, account data, or save-file fields changed.

WHAT CHANGED IN 2.6.4
---------------------
- Clicking the Stat Screenshot import button now opens a blocking preparation
  warning before the file picker. It prominently requires Manual combat and all
  temporary buffs/effects to be fully expired before capture.
- The warning explains why incorrect conditions can change the reconstructed
  baseline and final team recommendation.
- Testers can select “Don't show this preparation warning again.” That choice is
  saved as a local UI preference, separate from account/build files.
- The Screenshots page in Help provides a Restore screenshot warning button when
  the warning has been hidden.
- No optimizer formulas, account data, or save-file fields changed.

WHAT CHANGED IN 2.6.3
---------------------
- Corrected the screenshot instructions: switch combat to Manual before
  waiting for all temporary buffs and effects to expire. Remaining on Auto
  can activate skills or companion effects again and contaminate the baseline.
- No optimizer formulas, account data, or save-file fields changed.

WHAT CHANGED IN 2.6.2
---------------------
- Clarified that any preset can supply the screenshot baseline when presets differ
  only by equipped companions, provided the Main and Subs marked in the app are
  exactly the team shown in the captured preset. The recommended team is unchanged;
  Gain is measured against that captured team.
- Added a prominent screenshot-state warning alongside the preset-baseline clarification.
- Enlarged and centered the diagnostic bug-report window so its profile/screenshot
  options and Save Diagnostic ZIP controls are visible at normal desktop sizes.

WHAT CHANGED IN 2.6.1
---------------------
- Clarified that the imported preset supplies the non-companion baseline. If two
  presets differ only in their equipped companion team, either can be imported
  as long as the currently equipped Main and Subs are marked correctly.
- Clarified that presets with different equipment, skills, stat allocations, or
  other non-companion bonuses should be imported separately for accurate team
  ranking.
- Added a bold screenshot-condition warning to the in-app guide.

WHAT CHANGED IN 2.6.0
---------------------
- Replaced the role-badge cycle with an explicit Not equipped / Main / Sub
  chooser that opens beside the portrait. Opening the chooser no longer touches
  the current Main, so a page can be assigned directly as a Sub.
- Replaced About with a page-based Help guide. F1 opens the guide, its left-side
  navigation jumps directly to screenshots, stats, companions, optimization,
  or results, and the screenshot page includes a bundled Expected Stats example.
- Added Report Bug to the header. The local report form exports a diagnostic ZIP
  containing reproduction notes, system/Tk information, an optional account
  snapshot, and an optional application-window screenshot. Nothing is uploaded
  automatically.
- Added Ctrl+Shift+B as a shortcut for the bug-report form.
- Existing accounts, builds, optimization formulas, and save-file format remain
  compatible.

WHAT CHANGED IN 2.5.7
---------------------
- Optimized the exact-search hot path without changing team scores or ordering.
- Cached static Main-companion tie-break rankings instead of rebuilding them for
  every candidate team.
- Equip-effects-only searches no longer copy the selected Main companion once
  per candidate team merely to suppress its measured Main bonus.
- Lock-selected-Main mode now generates only combinations containing the locked
  page rather than generating every team and discarding most of them.
- Account and autosave JSON writes now use atomic replacement, reducing the risk
  of a damaged save if a write is interrupted.
- Removed a duplicated GUI method and redundant local import.
- Expanded the regression suite from 14 to 17 tests, including locked-team
  enumeration, neutral-Main scoring, and atomic-save behavior.
- Removed Python and pytest cache files from the distributed package.

WHAT CHANGED IN 2.5.5
---------------------
- Fixed inline companion-level editing closing immediately after the level chip
  was clicked on some Linux/Tk window managers.
- Focus is now applied after the initiating mouse click completes, and click-away
  committing is armed only after the editor has stable focus.

WHAT CHANGED IN 2.5.0
---------------------
- Replaced the four-step workflow tabs with one top-level Companion Optimization
  workspace.
- Character/target inputs occupy the left pane and the portrait companion
  collection occupies the right pane.
- Results and planning share a resizable lower region, so data entry and output
  remain visible without switching workflow tabs.
- Main-companion handling, Main comparison, and upgrade planning now live in a
  compact settings strip above the results.
- Robustness analysis is optional and automatic: enter any minimum/maximum
  range, then Optimize Team runs those scenarios after the exact team search.
  Leave a range blank to skip it.
- The page uses draggable horizontal and vertical dividers, providing a stable
  framework for future top-level Gear Optimization and other optimizer tabs.

WHAT CHANGED IN 2.1.2
---------------------
- Rebuilt the portrait set from one consistently framed sidebar portrait per
  companion instead of mixing square sidebar tiles, wide Sub-companion crops,
  and tiny rank-detail icons.
- The same companion artwork is intentionally reused across its rarity pages;
  rarity is communicated by the card frame and label, matching the game.
- Portraits are now contained inside the image window with padding rather than
  cropped and enlarged to fill it. This prevents clipped hair, oversized faces,
  and inconsistent zoom between ranks.
- All 61 supported companion pages now have a portrait; no placeholder art is
  required in the bundled package.
- Widened the editable level chip to cover the level label captured in the
  source screenshot.

WHAT CHANGED IN 2.1.0 / 2.1.1
-----------------------------
- Replaced the spreadsheet-like companion roster with an in-game-inspired
  portrait grid.
- Each companion has one named row containing its available Common/Rare/Epic/
  Unique/Legendary pages.
- Click a portrait to toggle ownership between grayscale and full color.
- Click the level chip in the portrait corner to edit the page level inline.
- Click the lower-right badge and choose Not equipped, Main, or Sub for the
  active build. Current Subs are displayed as S1-S6; their visual numbering
  does not affect calculations.
- A selected-page inspector shows its effect, calculated value, role, asset
  status, and optional measured Main adjustment.
- Existing account/build JSON files remain compatible.
- The version 2.0.0 header layout is retained: Optimize Team remains in the
  upper-right header and F5 remains available.
- Added the base Pirate/Common page to the roster, using the same verified flat
  Attack curve as the other Common pages.
- Portraits extracted from supplied in-game captures are bundled locally.
  Missing clean portraits use clearly marked rarity-colored placeholders.

WHAT CHANGED IN 2.0.0
---------------------
1. Shared account and multiple builds
   - Class, character level, owned companion pages, companion levels, and total
     companion slots are stored once at the account level.
   - Each build stores its own displayed stats, current equipped team, content
     target, screenshot-review state, Main handling mode, and sensitivity ranges.
   - The header includes New build, Duplicate, Rename, and Delete controls.
   - Optimize Team is available in the upper-right header and with F5.
   - Updating a companion level once updates it for every build.
   - Legacy single-profile JSON files load as one migrated build.

2. Sensitivity and confidence analysis
   - Tests ranges of Basic Attack share and Status uptime instead of requiring a
     single perfectly estimated value.
   - Can optionally vary target Defense and Evasion.
   - Exhaustively optimizes each scenario and reports team win frequency,
     nominal-team robustness, maximum regret, and which assumptions matter most.
   - A scenario grid is capped at 250 combinations to keep accidental workloads
     reasonable.

3. Main companion handling
   - Automatic
   - Equip effects only
   - Lock selected Main
   - Prefer damage Main
   - Prefer utility Main
   - Compare every Main locks each owned page in turn and finds its best Sub team.

4. Explanations and swap analysis
   - Results report the gap to the next-ranked team.
   - Each selected companion receives a local removal/swap-cost estimate.
   - The report identifies the best excluded replacement where applicable.
   - Sensitivity robustness is included after running an analysis.

5. Profile readiness checks
   - Flags screenshot conflicts, invalid or incomplete current teams, unreviewed
     assumptions, suspicious Flat Attack scaling, missing Main Stat information,
     disabled Accuracy modeling, and content/stat mismatches.
   - Readiness is shown on the Analysis & Planning tab before optimization.

6. Next-level upgrade planner
   - Raises each owned formula-backed companion page by one level, reoptimizes the
     team, and ranks the resulting modeled improvement.
   - Upgrade values cover equip effects only; copy requirements, rarity-up costs,
     and other resource costs are not yet modeled.

CORE MODEL
----------
The optimizer directly models:
- Flat Attack
- Min/Max Damage Multiplier
- Critical Rate and Critical Damage
- Attack Speed, including diminishing stacking and the modeled 150% cap
- Normal Monster Damage and Boss Monster Damage
- Basic Attack Damage and Skill Damage
- Status Damage with adjustable uptime
- Main Stat %, including modeled Attack and Stat Prop. Damage contribution
- Damage, Damage Amplification, Final Damage, Defense Penetration, and Accuracy
- Normal farming, bossing, mixed stages, and content using neither Normal nor
  Boss Monster Damage

The search is exhaustive for the entered pages, slots, target, formulas, and
selected Main mode. It is not a frame-by-frame combat simulator. Main companion
animations, AI, target count, healing, crowd control, movement, and unmeasured
active skills are not silently converted into invented DPS.

ACCOUNT AND BUILD WORKFLOW
--------------------------
A saved account contains:

Account-level data
- Character class and level
- Owned companion pages and levels
- Total unlocked companion slots

Build-level data
- Displayed character stats
- Current Main and Sub companion arrangement
- Content target and target defenses
- Main handling mode
- Sensitivity ranges
- Screenshot import/review state

Suggested builds include Farming, Chapter Boss, World Boss, Breakthrough, and
Arena. Duplicate a build when two presets share most settings, then import or
edit only the values that differ.

PACKAGED RELEASES AND BUILDING
------------------------------
The source code is shared, but Windows and Linux executables must be built on
their respective operating systems. The build configuration is under
`build_tools/`.

Linux build:
    ./build_tools/build_linux.sh

Windows build:
    build_tools\build_windows.bat

Both scripts:
1. Create an isolated build environment.
2. Install PyInstaller, Pillow, and pytest.
3. Stage the local platform's Tesseract runtime into the application.
4. Run all regression tests.
5. Produce a one-folder build for diagnosis.
6. Produce the final single-file executable.

Read `build_tools/BUILDING_RELEASES.txt` before distributing a beta. Always test
the one-folder version first, especially screenshot import, then test the final
one-file version on a machine/account without Python or Tesseract on PATH.

CRASH LOGS
----------
Unexpected startup, Tk callback, and thread failures are written locally to:

Windows:
    %APPDATA%\MapleStoryIdleOptimizer\crash_logs\

Linux:
    ~/.config/maplestory-idle-optimizer/crash_logs/

The Report Bug tool automatically includes up to three recent crash logs.

FIRST USE
---------
1. Open the in-game Stat Info page for the preset being recorded.
2. Set combat to Manual, then wait until every temporary combat buff has worn off.
3. Keep the current companion team equipped.
4. Enter the visible stats manually or use Import Stat Screenshots….
5. Open Owned Companions. Click each portrait you possess so it changes from
   grayscale to full color, then click its level chip to enter the current level.
6. Click each page's lower-right role badge and choose exactly one Main and the
   remaining occupied pages as Subs for the active build.
7. Select the target content.
8. Review Profile readiness.
9. Click Optimize Team in the upper-right header, or press F5.

Press F1 for the illustrated in-app guide. Use Report Bug (Ctrl+Shift+B) to
create a local diagnostic ZIP for reproducible tester issues.

The "Displayed stats include current companions" option is enabled by default.
The program reverses the marked current team before evaluating replacements.
Uncheck it only when the entered stats genuinely exclude every companion equip
effect.

COMPANION PORTRAIT GRID
-----------------------
The complete ZIP includes assets/companions with both color and grayscale card
portraits. The program remains usable when the asset folder is missing, but it
falls back to text-only cards; therefore use the complete package for the
intended visual layout.

The bundled clean portraits come from the in-game captures supplied for this
project. Rarity-colored placeholders are deliberately used where no clean rank
portrait was available. Replacing a placeholder later does not change account
files or optimizer results.

SCREENSHOT STAT IMPORT
----------------------
1. Open any preset with the non-companion stats you want modeled. If presets differ only by companions, any one is valid.
2. Set combat to Manual, then wait until every temporary effect has worn off.
3. Open Stat Info and take overlapping screenshots from Attack at the top through
   the job-skill rows at the bottom.
4. Click Import Stat Screenshots… or press Ctrl+I.
5. Select all screenshots from the same stable preset state together.
6. Mark exactly the Main and Subs equipped in the captured preset, then review every proposed value before applying it.

Three screenshots cover the tested 2048x1236 layout. Other UI scales may need
more. Row order may change and zero-valued rows may disappear; the importer
matches labels rather than fixed row coordinates.

Review colors
- Green: read directly from screenshots
- Blue: full section covered and a hidden zero-valued row inferred
- Amber: not covered and still needs manual checking
- Red: conflicting readings that require review

Basic Attack share, Status uptime, Current Main Stat %, and Flat Attack scaling %
are not available in the scrolling Stat Info panel and normally remain amber
until checked manually.

SENSITIVITY ANALYSIS
--------------------
Open 4  Analysis & Planning → Sensitivity & confidence.

Recommended starting ranges when the true values are uncertain:
- Basic Attack share: 30% to 70%, 5 samples
- Status uptime: 0% to 75%, 4 samples

The analysis reports:
- How often each team wins across the tested grid
- Whether the nominal recommendation remains optimal
- Maximum loss from keeping the nominal team in another tested scenario
- Which assumption causes the most team changes

A high win rate and low maximum regret mean an exact manual estimate is unlikely
to be worth the effort. A split result indicates which threshold or input should
be measured more carefully.

MAIN COMPANION MODES
--------------------
Automatic
- Uses measured Main adjustments when supplied; otherwise uses the program's
  content heuristic to break equip-score ties.

Equip effects only
- Ignores Main active adjustments and compares teams only by equip effects.

Lock selected Main
- Keeps one chosen companion as Main and exhaustively optimizes its Sub team.

Prefer damage Main / Prefer utility Main
- Applies a transparent qualitative preference when active-skill simulation is
  incomplete. Equip-effect scoring remains the numerical foundation.

Compare every Main
- Locks each owned page as Main in turn and shows its best possible Sub team.
  This is useful when Main active skills, survivability, or target count matter
  more than a tiny equip-score difference.

UPGRADE VALUE PLANNER
---------------------
Open 4  Analysis & Planning → Upgrade value and choose Calculate next-level
values. Each eligible page is advanced by one level in isolation, after which the
entire team is reoptimized.

The planner does not yet account for:
- Companion copies or duplicate requirements
- Currency/material costs
- Opportunity costs between rarity advancement and ordinary levels
- Active-skill upgrades not represented by the equip-effect formula

SAVING, SAVE AS, AND AUTOMATIC RESTORE
-------------------------------------
Save and Save As now write one account JSON containing every build.

- Save overwrites the currently loaded account file.
- Save As creates a new account file and makes it active.
- Load accepts version 2 account files and older single-profile JSON files.
- Older files are migrated into one build; saving writes the new account format.

Automatic restore is stored outside the extracted program folder:

Linux/CachyOS
    ~/.config/maplestory-idle-optimizer/last_session.json

Windows
    %APPDATA%\MapleStoryIdleOptimizer\last_session.json

Replacing the extracted program folder therefore does not normally erase the
last session. Manual JSON backups remain recommended before major updates.

RUNNING ON CACHYOS / ARCH LINUX
-------------------------------
1. Extract the folder.
2. Double-click run_optimizer.sh, or open a terminal in the folder and run:

       ./run_optimizer.sh

If Tkinter is unavailable:

       sudo pacman -S tk

For optional screenshot import:

       sudo pacman -S tesseract tesseract-data-eng python-pillow

You may also run directly:

       python3 maplestory_idle_companion_optimizer.py

RUNNING ON WINDOWS
------------------
1. Install a current Python 3 release and enable Add Python to PATH.
2. Double-click run_optimizer.bat.

For screenshot import, install Tesseract OCR and Pillow and ensure
`tesseract.exe` is available on PATH.

IMPORTANT INPUT DETAILS
-----------------------
- Use values from one stable character state and one preset.
- A missing visible stat row generally means its value is zero when the complete
  section was captured.
- Current Main Stat % means the displayed percentage component, not total INT,
  STR, DEX, or LUK.
- Flat Attack scaling % means the Attack percentage that scales newly added flat
  Attack. Leave it at zero when unknown; do not enter total Attack here.
- Basic Attack share and Status uptime are assumptions unless measured. Use the
  sensitivity analysis rather than pretending they are exact.
- Accuracy/Evasion scoring remains optional and approximate.
- Target Defense and Evasion may be zero when unknown; sensitivity analysis can
  test ranges when those values may affect the recommendation.

BASELINE RECONSTRUCTION
-----------------------
Additive companion effects are removed from the displayed stats. Attack Speed
and Defense Penetration are unstacked using their remaining-cap formulas. Final
Damage is divided out multiplicatively. Main Stat % is reversed from Total Main
Stat and Current Main Stat %, including the modeled Attack and Stat Prop. Damage
attributed to the removed companion effect.

If the displayed values cannot be reconciled with the pages marked Main/Sub, the
program stops with a specific validation error rather than silently using a bad
baseline.

COMPANION DATA NOTES
--------------------
Built-in formulas cover the original roster plus Bishop, Paladin, Buccaneer,
Corsair, Night Walker, and Wind Archer. Player-provided in-game checkpoints are
retained as regression tests. The supplied active-skill descriptions remain in
new_companion_skill_reference.txt for future combat-model work.

KEYBOARD SHORTCUTS
------------------
Ctrl+S         Save account
Ctrl+Shift+S   Save account as
Ctrl+O         Load account or legacy profile
Ctrl+N         New account
Ctrl+I         Import Stat Info screenshots
F5             Optimize active build (same as the upper-right button)
Escape         Cancel an active search or analysis

TESTS
-----
From the extracted folder:

       python3 tests/test_optimizer.py

DATA / MECHANICS REFERENCES
---------------------------
MapleStory: Idle RPG Wiki — Companions
https://idle.maplestorywiki.net/w/Companions

MapleStory: Idle RPG Wiki — Character Stats
https://idle.maplestorywiki.net/w/Character_Stats

Public MapleStory Damage Calculator source/data
https://github.com/djc-0de/Maplestory-Damage-Calculator

This is an independent community modeling tool and is not affiliated with or
endorsed by Nexon.


Portrait framing
----------------
Version 2.1.2 uses one consistently framed in-game sidebar portrait per companion across all rarity pages. The artwork is contained with padding rather than enlarged to fill the tile; rarity remains visible through the program-drawn frame and label.
