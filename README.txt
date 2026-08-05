MAPLESTORY IDLE COMPANION OPTIMIZER 3.0.0
============================================================

OVERVIEW
--------
This is a local Python/Tkinter optimizer for MapleStory: Idle RPG companion
teams, Hero Power/Ability decisions, and Equipment Potential rolls. It uses the
character statistics and target assumptions entered for the active build to
compare complete configurations rather than isolated stat lines.

Version 2.0 reorganizes the program around one shared account with multiple
content builds. It also adds robustness analysis for uncertain inputs, Main
companion comparison modes, result explanations, readiness checks, and a
next-level companion upgrade planner.

No pip packages are required for the optimizer engine itself. Packaged releases
bundle Python, Pillow, the English Tesseract OCR runtime, portraits, background,
help images, and other assets. Running directly from source still requires the
local Python/Tk/Pillow/Tesseract development dependencies described below.

WHAT CHANGED IN 3.0.0
---------------------
- Renamed the release to 3.0.0 without changing optimizer calculations, user
  interface behavior, account compatibility, OCR behavior, or bundled rate data.
- Removed the accumulated standalone per-version update-note files from the
  source repository. Release history remains consolidated in this README and in
  GitHub's automatically generated release notes.
- Updated the publishing helper to delete legacy versioned note files from an
  existing checkout before committing, so extracting this package over the
  current repository removes already-tracked copies on the next push.
- Added repository validation and ignore rules that prevent new files such as
  FEATURE_NAME_3.0.1.txt, README_3.0.1.txt, or GITHUB_RELEASES_3.0.1.txt from
  being committed accidentally.
- Removed the standalone versioned README copy from GitHub release assets. The
  Windows/Linux program, diagnostic one-folder archive, and checksums remain.

WHAT CHANGED IN 2.8.9
---------------------
- Corrected the Potential reroll workflow to match the game: using a cube
  permanently replaces the previous three-line result. A reliably OCR-read
  reroll now becomes the active current Potential immediately; the old result
  is retained only in session history and is never offered as a selectable
  "Keep Current" outcome.
- Low-confidence rerolls now pause automatic monitoring in an explicit active-
  result review state. Correcting the OCR records that already-active result;
  it does not pretend the pre-cube roll can be restored or deduct a second cube.
- Added next-reroll downside reporting: better/equal/worse probabilities, severe
  loss probability, expected immediate net change, and median complete-roll
  change. Equipment ranking now includes the downside of the final active failed
  roll instead of ranking only by positive upside.
- Added a finite-budget optimal stopping solver. After every irreversible roll,
  it compares the value of stopping with the expected value of continuing with
  the remaining cubes, including configured early/guaranteed rarity transitions.
  It can recommend ROLL, STOP, MOVE TO ANOTHER SLOT, or SAVE TO A LARGER BUDGET.
- Added end-of-session outcomes under that policy: expected final damage change
  plus the probabilities of ending better, approximately equal, or worse than
  the active starting Potential. The policy is risk-neutral and labels utility
  options that are still unmodeled for direct damage.
- Reworked Potential capture calibration to accept an approximate box around the
  full card, automatically locate the charcoal Potential panel inside it,
  normalize the panel to stable OCR geometry, and show a header/three-line
  calibration overlay before saving. The same normalization is used by current
  scans, manual reroll reads, screenshots, fingerprints, and automatic scanning.
- Added regression coverage for irreversible session ranking, finite-budget
  stopping behavior, save-until-positive guidance, and approximate-region panel
  localization.

WHAT CHANGED IN 2.8.8
---------------------
- Replaced the bundled Potential probability profile with the corrected in-game
  export. Hat Epic now has complete Slot 1/2/3 rates, and Shoes Rare line 2 is
  accepted as complete because its collected outcomes total exactly 100%.
- Exact configured-rate coverage now includes 54 equipment-slot/rarity tables
  and 4,184 normalized outcomes. Entirely uncollected equipment slots continue
  to show visible rate-data warnings rather than borrowing another slot's odds.
- Added a configured-rate stopping guide for the selected equipment slot. It
  identifies up to three high-value preferred-option watch conditions, reports
  how much of the acceptable-roll probability they cover, and shows how often a
  triggered condition actually corresponds to an acceptable complete roll.
- Added three representative complete three-line stopping outcomes with their
  configured exact probability and estimated gain. These are examples rather
  than a claim that only those exact rolls should be accepted.
- Added rank-aware cube-budget simulation across early and guaranteed rarity
  increases. The planner now contrasts fixed-rarity session odds with the odds
  after following possible rank transitions through the remaining cube budget.
- The rank-aware simulation tracks first-success timing and explicitly states
  its transition assumption: a cube that raises rarity draws that same result
  from the newly reached rarity's Option Rates.
- Preferred-option targets remain watch conditions, not automatic acceptance
  rules. The automatic complete-roll checker now decides whether to stop or reroll again after the new result becomes active.
- Added regression tests for corrected Hat/Shoes coverage, preferred-condition
  coverage/precision, exact stopping examples, and guaranteed transition-roll
  budget calculations.

WHAT CHANGED IN 2.8.7
---------------------
- Bundled the configured Potential Option Rates collected from the in-game
  Option Rates tables. Exact odds now work automatically for 52 complete
  equipment-slot/rarity tables without requiring a manual import.
- Added visible rate-coverage warnings. Missing unlocked-later equipment slots,
  Hat Epic, and the uncertain Shoes Rare line-2 table are never guessed. The
  selected-slot note and Cube Priority diagnostics identify exactly which rate
  lines still need to be collected.
- Normalized collector artifacts before bundling: Cooldown Reduction is stored
  and displayed in seconds, 0.55/1.55 OCR artifacts are corrected to 0.5s/1.5s,
  Mystic 1,000 flat primary-stat values are restored, and two isolated Rare
  flat-stat zero reads are corrected to 50.
- Added rank-up-aware planning. Each exact-rate result now shows early rank-up
  chance per cube, chance to rank up within the current budget, cubes remaining
  to the guaranteed rank-up, and expected cubes to rank up.
- Added a next-rarity preview when the adjoining rarity table is available. The
  optimizer compares the current saved three-line set against outcomes at the
  next rarity to identify when pushing the rank has better upside.
- Added SAVE TO X CUBES guidance for low-probability sessions. Saving does not
  change the per-cube odds; the recommendation means the current budget is below
  a 50% chance of reaching the configured stopping threshold in one session.
- Added PUSH <SLOT> TO <RARITY> guidance when the current budget can guarantee a
  rank-up and the next-rarity expected upside exceeds the current-rarity return.
- Bundled rates remain separate from account-specific imported overrides.
  Clearing imported rates now returns to the bundled baseline rather than
  deleting the built-in data.
- Added regression tests for bundled coverage, incomplete-table rejection,
  cooldown-second units, corrected OCR artifacts, guaranteed rank-up math, and
  next-rarity odds.

WHAT CHANGED IN 2.8.6
---------------------
- Added a configured-rate Potential probability engine. For every equipment
  slot and rarity with complete line-1, line-2, and line-3 distributions, the
  optimizer enumerates the full three-line outcome space instead of estimating
  from slot headroom or a small personal roll sample.
- Cube Priority can now rank equipment by expected positive damage gain per
  cube. Each exact-rate row shows the next-cube improvement chance, chance
  within the entered cube budget, expected cubes to an accepted result,
  expected damage gain per cube, and average gain when the stopping threshold
  is met.
- The original 2.8.6 Roll/Save guidance was superseded in 2.8.9. The selected-
  slot checker now evaluates irreversible Stop/Continue risk after every OCR-
  read three-line result.
- Added JSON and CSV configured-rate profile import, export, validation, merge,
  and account persistence. A distribution is accepted only when every outcome
  for that slot/rarity/line is present and its probabilities total 100% within
  a narrow display-rounding tolerance.
- Added Export Rate Template and visible coverage diagnostics. Exact analysis
  activates only for complete imported tables; missing tables continue to use
  the transparent headroom fallback rather than fabricated probabilities.
- Exact budget odds currently hold the saved Potential rarity constant. Rank-up
  transitions during a long cube session are deliberately not modeled until
  the exact transition behavior and adjoining rarity tables are both available.
- Added regression tests for profile parsing, probability-total validation,
  exact three-line enumeration, budget odds, expected cubes, expected gain per
  cube, and cross-slot ranking.

WHAT CHANGED IN 2.8.5
---------------------
- Replaced the always-heavy Potential OCR workflow with a staged fast-first
  pipeline. A clean panel now uses one Tesseract pass for the header and one
  pass for each of the three rows, rather than launching every preprocessing
  variant and repeated-capture check unconditionally.
- Tightened the normalized row crops so each single-line OCR pass sees only one
  Potential option. On the supplied test panel, the fast path reads Rare 1/60,
  INT 100, Damage 8%, and Max MP 3% in four OCR launches.
- Added confidence-gated fallback behavior. Extra grayscale/threshold passes,
  second and third captures, and consensus are now used only when the first
  result is incomplete, implausible, or low-confidence.
- Moved Scan Current Potential, Scan Current & Start Auto Scan, and Read New
  Roll onto a dedicated background thread. The Tk interface stays responsive
  and displays whether the fast or verified OCR path was used plus elapsed
  time.
- Updated automatic monitoring to try the same staged reader after a changed
  panel stabilizes. Clean rerolls no longer trigger full three-image consensus;
  difficult results retain the defensive validation and review path.
- Added regression coverage proving that the clean fast path uses exactly four
  Tesseract launches and does not invoke the defensive reader.

WHAT CHANGED IN 2.8.4
---------------------
- Reworked Potential OCR label matching so a plain or slightly noisy Damage
  read cannot be silently expanded into Boss Monster Damage. Compound damage
  options now require their distinguishing words, such as Boss, Critical,
  Final, Normal, Basic, or Skill.
- Added decimal-preserving value OCR and rarity-aware plausibility checks. When
  a tiny decimal is lost, an impossible value such as Rare Damage 45% can be
  recovered as 4.5%; unresolved or conflicting values are sent for review
  rather than being saved automatically.
- Added repeated-capture OCR consensus. Current scans and manual reads compare
  up to three captures, while automatic monitoring waits for three stable
  frames before accepting a new result. Disagreement lowers confidence and
  opens an explicit review workflow.
- Replaced the ambiguous low-confidence fallback with CURRENT SCAN REVIEW and a
  Save Corrected as Current action. Reviewed current scans never deduct a cube
  or count as a reroll.
- Fixed the blank Cube Priority dashboard after creating or loading an account.
  Account loading now preserves the Tk variables already bound to the visible
  labels, then recalculates the ranking immediately.
- Added Slot status controls: Auto, Unlocked, and Locked. Auto ignores an
  unconfigured slot whose three values are all zero; Locked always excludes a
  slot from equipment-wide priority. The dashboard now reports eligible,
  locked, auto-ignored, and incomplete slots instead of failing silently.
- Cube Priority now refreshes after scans, accepted rolls, current-line edits,
  rarity/progress changes, slot-status changes, active-build changes, and
  account loading.
- Added regression coverage for exact Damage matching, missing-decimal
  recovery, multi-capture consensus, locked-slot exclusion, and the priority
  display binding bug.

WHAT CHANGED IN 2.8.3
---------------------
- Fixed a serious Potential data-model bug where STR, DEX, INT, and LUK rolls
  did not preserve whether the value was flat or percentage-based. Values such
  as INT 6% and INT 6 are now distinct in OCR, saved accounts, displays,
  comparisons, auto-scan signatures, observed-roll history, and Cube Priority.
- Added an explicit Flat/% unit selector beside every current and candidate
  Potential line. OCR fills it automatically, while manual entry can choose the
  correct unit for ambiguous options such as primary stats, Attack, Max HP, and
  Max MP.
- Updated the damage model so a matching primary-stat percentage line applies
  through Main Stat %, while a flat line continues to add a fixed amount.
- Added backward-compatible account migration. Legacy unitless primary-stat
  lines default to flat, matching the behavior of versions through 2.8.2.
  Historical observed-roll samples are reset for migrated slots because their
  prior comparisons may have used the wrong unit and their signatures lacked
  unit information.
- Added regression tests proving INT 6%, INT 400, and Damage 8% remain distinct
  through OCR, scoring, signatures, serialization, and legacy migration.

WHAT CHANGED IN 2.8.2
---------------------
- Added a dedicated Scan Current Potential action. It OCRs the visible rarity,
  rank progress, and all three lines directly into the selected equipment
  slot's saved baseline without deducting a cube or recording a reroll.
- Added Scan Current & Start Auto Scan. One click saves the current visible
  roll and starts stable-region monitoring from that exact image, so the next
  settled change is treated as the first reroll rather than as setup.
- Current scans clear stale candidate/comparison data, reset observed odds only
  for the newly established baseline, and refresh the equipment-wide Cube
  Priority ranking immediately.
- Low-confidence or incomplete current scans are placed in the editable New
  Roll fields for review but are not silently saved as the current baseline.
- Renamed the manual live fallback to Read New Roll and clarified the manual
  Save Edited Current Lines action.
- Added regression and release guards for the dedicated current-scan workflow,
  no-cube/no-observation behavior, and pre-seeded automatic-scan baseline.

WHAT CHANGED IN 2.8.1
---------------------
- Rebuilt Potential OCR around fixed subregions instead of reading the whole
  panel as one paragraph. Rarity/progress and each of the three option rows are
  read separately with single-line OCR, 4x enlargement, color-aware masks for
  yellow/white/cyan text, threshold fallbacks, fuzzy label correction, numeric
  whitelists, and slot-specific validation.
- Added OCR confidence reporting. Impossible slot-exclusive results and weak
  row matches are flagged instead of being silently treated as trustworthy.
- Added automatic Potential change monitoring. After calibration, Start Auto
  Scan captures only the saved region, establishes a baseline, waits for a
  changed image to remain stable across two captures, then OCRs and compares the
  new roll automatically. Cursor/UI-only changes and duplicate parsed results
  are ignored. Manual Read Live Roll remains available.
- Automatic monitoring does not deduct a cube or record an observed roll when
  OCR is incomplete or low-confidence. The parsed fields are still shown for
  manual correction.
- Added an equipment-wide Cube Priority dashboard. Once current Potential is
  saved for multiple slots, the program ranks the top three slots to improve and
  highlights CUBE THIS NEXT. The transparent headroom ranking combines each
  saved set's modeled contribution, verified slot-exclusive option value at the
  current rarity, rank-up progress, and any observed reroll history.
- Cube Priority is deliberately labeled as a headroom recommendation rather
  than an official expected-gain-per-cube probability because a stable complete
  table of per-option roll weights is not bundled.
- Added verified Potential rank requirements and slot-exclusive values used for
  validation and headroom analysis.
- Added regression tests for image-change fingerprints, impossible slot-option
  rejection, weaker-slot priority, automatic scan/release guards, and backward
  compatibility with saved equipment state.

WHAT CHANGED IN 2.8.0
---------------------
- Added a new Equipment Enhancement top-level tab, beginning with a complete
  three-line Potential roll checker. Current Potential rarity, rank progress,
  and three lines are saved independently for every equipment slot.
- Added one-time capture-region calibration. The user can drag a box around the
  in-game Potential panel on a live screen capture or saved screenshot, and the
  normalized region is saved with the account for repeated reads.
- Added live KDE/Linux-friendly capture using Pillow ImageGrab with a Spectacle
  command-line fallback, plus a Read Screenshot File fallback for environments
  where Wayland prevents direct capture.
- Added local Tesseract OCR for Potential rarity, rank progress, and all three
  option lines. OCR output is normalized against known in-game option labels and
  remains editable before the user accepts a result.
- Added complete-set comparison. Every reroll replaces all three lines, so the
  engine removes the selected slot's saved current lines from the displayed
  character state, applies the three new lines together, and reports the new active result versus the immediately previous roll, then recommends STOP or CONTINUE.
- Added modeled support for flat and percentage Main Stat, flat and percentage
  Attack, Damage, Final Damage, Critical Rate/Damage, Min/Max Damage, Boss and
  Normal Monster Damage, Basic/Skill Damage, Attack Speed, Defense Penetration,
  and Accuracy. Utility or job-specific lines remain visible and are explicitly
  labeled unmodeled rather than assigned invented damage value.
- Added current rarity and rank-progress tracking because the whole Potential
  set can rank up while rerolling. Candidate rarity/progress is read by OCR and
  is recorded as the active result immediately after a reliable reroll read; review is required only when OCR confidence is low.
- Added cube tracking with optional automatic one-cube deduction after each live
  OCR read.
- Added an observed improvement-rate tracker per equipment slot and saved
  baseline. It reports the sample success rate, Wilson confidence interval, and
  the implied chance of at least one improvement within the remaining cube
  budget. It is explicitly empirical, not presented as an official cube-rate
  table, and resets when a new baseline is accepted.
- Added account persistence for all equipment-slot Potential data, capture
  calibration, cube count, minimum improvement threshold, and observed roll
  history. Older accounts load with clean default Equipment Enhancement state.
- Added modular Equipment data, models, engine, OCR, and UI packages under
  maple_optimizer/equipment rather than expanding the main source file further.
- Added regression tests for OCR parsing, complete three-line replacement,
  observed budget probability, account round-tripping, and release guards.

WHAT CHANGED IN 2.7.5
---------------------
- Corrected the highlighted top-three budget probability. The planner now
  selects the three displayed outcome categories once at the starting
  Reconfiguration Level and tracks those exact same outcomes through every
  later attempt and level-up. Earlier builds could silently substitute a new
  top three after Reconfiguration Level changed.
- Replaced ad hoc repeated-attempt accumulation with a shared first-success
  calculation that handles changing per-attempt probabilities and costs without
  double-counting. Added brute-force regression comparisons for success chance,
  expected attempts, expected Medal spend, and first-success timing.
- Added expected attempts and expected Medals to obtain one of the displayed
  top-three outcomes, conditional on succeeding within the available budget.
- Added accepted improvement ranges and average improvement beside each of the
  three stopping outcomes. Multi-slot recommendations are explicitly labeled as
  combined results.
- Renamed the primary outcome section to STOP REROLLING IF YOU GET ANY OF THESE
  and added a clear instruction to enter the accepted result and analyze again.
- Added Conservative, Balanced, and Aggressive planning approaches. Conservative
  favors success probability, Balanced favors probability-adjusted value per
  Medal, and Aggressive favors larger accepted improvements.
- Added validation for missing/extra enabled slots, locked disabled slots,
  out-of-range values, tier/stat mismatches, tiers unavailable at the entered
  Reconfiguration Level, impossible level-progress values, and reserves larger
  than the available Medal total.
- The chance display is explicitly labeled as an estimate because public data
  provides exact tier rates but not verified option-type and exact-value weights.
- Preserved the concise result dashboard, modular Hero Power engine, companion
  optimizer behavior, and all existing account compatibility.

WHAT CHANGED IN 2.7.4
---------------------
- Replaced the Ability planner's default wall-of-text result with a concise
  decision dashboard. The three primary cards now show the exact slot or slots
  to reroll, the chance of obtaining one of the three highlighted practical
  outcomes within the usable Medal budget, and the reroll cost/attempt count.
- Added a prominent slot strip that separates REROLL slots from KEEP / LOCK
  slots so the recommended action can be understood without reading the full
  probability report.
- Added three ranked outcome rows. They emphasize the three best practical
  results by probability-adjusted gain, show the minimum acceptable value when
  rerolling one slot, and display both per-attempt likelihood and average
  accepted damage improvement.
- Added explicit top-three probability tracking to the reroll engine. The
  planner now estimates both the first-attempt chance and the chance across the
  current Medal budget while accounting for Reconfiguration Level changes.
- Moved the full strategy comparison, ideal tier report, assumptions, and model
  diagnostics behind a Show detailed analysis button. Detailed data remains
  available but no longer overwhelms the primary decision.
- Added a compact Hero Power next-upgrade callout beneath the Ability action
  plan.
- Preserved all companion optimizer behavior and the 2.7.3 Optimize Team crash
  fix.

WHAT CHANGED IN 2.7.3
---------------------
- Fixed an Optimize Team callback crash introduced by the advanced analysis
  queue handler. Polls that contained only progress updates, or no queued
  message yet, could reach the automatic-sensitivity check before its flag had
  been initialized.
- The follow-up flag is now initialized on every poll and is enabled only after
  a successful completed team search explicitly requests sensitivity analysis.
- Added a regression test that exercises the exact empty/non-terminal worker
  queue path from the submitted Linux crash report.
- No optimizer formulas, companion data, Hero Power calculations, account data,
  or saved-profile formats were changed.

WHAT CHANGED IN 2.7.2
---------------------
- Reframed the Ability planner around an immediate action plan rather than only
  showing the theoretical best complete preset. The report now identifies which
  current slot or slots to reroll next and which remaining slots to lock.
- Added medal-budget controls for reserved Medals, current progress toward the
  next Reconfiguration Level, minimum acceptable damage improvement, and the
  maximum number of slots to compare rerolling at once.
- Added a deterministic probability simulator that compares every one-slot and
  two-slot reroll combination by default. It reports first-attempt success, the
  chance of at least one acceptable improvement within the usable budget,
  expected medals spent when successful, expected accepted gain, and
  probability-adjusted gain per 1,000 Medals.
- Reconfiguration Level progression is modeled during the spending plan. When
  simulated Medal use reaches the published requirement for the next level,
  subsequent attempts use the new tier probabilities and reroll price.
- Added practical keep/reroll classifications for the current preset and
  one-slot-equivalent acceptance thresholds showing the minimum value needed for
  each obtainable option to beat the current preset by the selected amount.
- Added common successful multi-slot roll patterns so a two-slot recommendation
  shows which combined outcomes most often satisfy the stopping rule.
- Added separate comparisons for the most Medal-efficient strategy, the safest
  strategy within the current budget, and the highest-upside successful result.
- Probability estimates clearly distinguish exact published tier rates, costs,
  and level requirements from the currently unverified assumption that option
  types are equally likely within a tier and values are uniformly distributed
  across the displayed range.
- Expanded the modular Hero Power engine and typed result models rather than
  moving the new probability calculations back into the main application file.
- Added regression tests for one-versus-two-slot strategy selection, level-up
  progression during rerolls, practical acceptance thresholds, and deterministic
  simulation output.

WHAT CHANGED IN 2.7.1
---------------------
- Replaced the single focused-tier maximum-roll list with a tier-by-tier Ability
  progression planner covering Normal, Rare, Epic, Unique, Legendary, and
  Mystic in one report.
- Added an editable Unlocked Slots field. Every tier now returns exactly that
  many recommended lines, so the report reflects the player's current Hero
  Power stage rather than assuming a complete seven-slot endgame preset.
- Ability recommendations are optimized as complete sets rather than isolated
  one-line rankings. Duplicate options are allowed, and Attack Speed, Critical
  Rate, Accuracy, and Defense Penetration are recalculated after each selected
  line so diminishing returns and caps can change later picks.
- Every recommended line displays its tier value range, minimum-roll and
  maximum-roll marginal gain, cumulative gain, and the tier probability at the
  entered Reconfiguration Level. Tiers not yet available are clearly marked.
- The focused tier selector remains for reroll-cost planning, but no longer
  limits the recommendation report to one usually unrealistic rarity.
- Began the planned codebase modularization. Hero Power tables, typed result
  models, calculation engine, and Tkinter tab now live under
  maple_optimizer/hero_power instead of being embedded in the main source file.
- Preserved compatibility aliases in the main module so existing account files,
  regression tests, and external imports continue to work.
- Added regression coverage for all-tier N-slot recommendations, duplicate best
  lines, module boundaries, account persistence, and the complete GUI startup.

WHAT CHANGED IN 2.7.0
---------------------
- Added a new Hero Power & Ability tab with the same MapleStory-inspired card,
  color, and module styling as the Companion Optimization workspace.
- Added a synchronized Character Baseline panel. Its entries share the exact
  same variables as the active build, so edits on either tab remain in parity.
- Added manual entry for all six Hero Power enhancement rows, including current
  level, current value, next value, and the Hero Token cost shown in-game.
- Added personalized next-upgrade rankings using modeled damage gain per Hero
  Token. Max HP and Defense remain visible as utility upgrades rather than being
  assigned invented offensive value.
- Added seven Ability slots for current Stage 8 support, with tier, option,
  exact value, enabled state, and lock state for every line.
- Added current-line contribution scoring, target-tier line rankings, exact
  published reroll costs for Reconfiguration Levels 1-20, available-roll
  estimates, and published tier probabilities.
- Added reconstruction of the no-Ability baseline when current Ability lines
  are already included in Character Stats, including correct inverse handling
  for diminishing Attack Speed and Defense Penetration sources.
- Hero Power and Ability planner inputs now save with the account file.
- This first version intentionally leaves exact option/value roll probability
  and a complete automatic Hero Power cost table for later validation.

WHAT CHANGED IN 2.6.10
----------------------
- Replaced the native Tk companion role menu with a persistent in-window role
  chooser. The native menu still entered press-and-hold behavior on affected
  Linux/Tk systems and closed when the badge click was released.
- Main, Sub, and Not equipped are now ordinary buttons that accept a separate
  normal click after the chooser opens; dragging from the badge is unnecessary.
- The chooser remains open until a role is selected, Cancel is pressed, Escape
  is pressed, the badge is opened again, or another area of the app is clicked.
- The packaged startup smoke test verifies that the chooser survives the badge
  release, then activates Main through the button's real Tk command path. It no
  longer depends on synthetic pointer warping, which was unreliable in frozen
  Linux builds even when the button itself worked normally.
- Packaging smoke tests now use a temporary configuration directory and never
  restore or modify the publisher's real account. A full saved companion team
  can no longer make the role test fail because no additional slot is available.
- No optimizer formulas, account data, or save-file fields changed.

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
