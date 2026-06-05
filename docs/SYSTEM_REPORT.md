# pyMercator System Report

Generated: 2026-06-04 22:19:02 -03:00

## Scope

This report records the current operational state after the CLI/script documentation pass, the daily signal panel polish, the script closing improvements, and the autotune audit/engine benchmark work.

Related commits:

- `7048523` Polish daily signal panel
- `56dc58e` Document pyMercator commands
- `efcce4b` Audit autotune and add engine benchmark
- `634f440` Improve operational script summaries
- `0645b37` Add code audit and refactor report

Existing audit artifacts:

- `runtime/code_audit_20260604_141850/code_audit.txt`
- `runtime/code_audit_20260604_141850/code_audit.json`
- `runtime/refactor_report_20260604_165553/refactor_report.txt`

## Successes

- `scripts/run_daily_signal.ps1` now ends with `PYMERCATOR SIGNALS`, showing market header, signal summary, buy/long candidates, sell-short setups, observation candidates, hedge/defense, basket state, final decision, and key files.
- Short setups are visible even when execution is blocked by missing borrow/cost data. They are marked as setup candidates, not automatic sell orders.
- Short execution wording was clarified: `EXEC_READY`, `DATA_BLOCKED`, and `EXECUTION` replace the older ambiguous wording.
- `HEDGE / DEFENSE` makes cash and hedge watch explicit when the long basket is blocked.
- `scripts/run_daily_train.ps1` now closes with `PROFILE SUMMARY`, `SYSTEM CHECKS`, revised `VERDICT`, and `KEY FILES`.
- `scripts/run_weekend_full.ps1` has the same closing structure and reports scenario/pytest status from logs when the run reaches those steps.
- `docs/COMMANDS.md` documents the real argparse command tree and PowerShell scripts.
- `docs/OPERATING.md` reduces the operator routine to three main scripts.
- `scripts/dump_cli_help.ps1` inventories CLI help into `runtime/cli_help_<timestamp>/help_index.txt` and continues when a command is unavailable.
- `train --details` gained autotune audit sections and `train benchmark-engines` exists for experimental comparison without changing default operational engines.
- JSON/CSV/TXT/log/manifest artifacts remained ANSI-free in the daily signal tests.

## Validation

- `python -m pytest tests -q`: `284 passed, 1 skipped in 43.67s`.
- `.\scripts\run_daily_signal.ps1`: exit `0`, runtime `runtime\daily_signal_20260604_220826`.
- `.\scripts\run_daily_signal.ps1`: showed `PYMERCATOR SIGNALS`, `BUY / LONG SIGNALS`, `SELL-SHORT SIGNALS`, `HEDGE / DEFENSE`, `EXECUTION`, and `DATA_BLOCKED`.
- `.\scripts\run_daily_signal.ps1`: no loose `0` lines detected; no ANSI detected in terminal capture; no ANSI detected in runtime artifacts.
- `.\scripts\run_daily_signal.ps1 -Color`: exit `0`, runtime `runtime\daily_signal_20260604_221241`.
- `.\scripts\run_daily_signal.ps1 -Color`: binary capture confirmed ANSI in terminal output; no ANSI detected in runtime artifacts.
- `.\scripts\run_daily_train.ps1`: exit `0`, runtime `runtime\daily_train_20260604_211518`.
- `.\scripts\run_daily_train.ps1`: showed profile summary, system checks as `NOT_RUN`, revised blocker verdict, and key files; no loose `0` lines were visible.
- Previous complete weekend validation: `runtime\weekend_full_20260604_172712`, manifest `OK`, pytest log `281 passed, 1 skipped`, scenario positive checks passed.

## Current Failures And Risks

- A fresh `.\scripts\run_weekend_full.ps1` attempt at `runtime\weekend_full_20260604_212433` exceeded the tool timeout and was manually stopped while running `train --autotune --details`. Its manifest is correctly marked `FAIL`.
- The failed weekend attempt did not reach scenario positive or pytest. This is a runtime-duration risk around autotune, not a pytest failure.
- The tool-timeout run suggests `weekend_full` may need a longer execution window, more aggressive autotune limits, or cache/parallel tuning before it is comfortable as a frequent validation command.
- The command manual is intentionally large because it documents the real CLI tree. It should be regenerated with `scripts/dump_cli_help.ps1` whenever argparse changes.

## Behavior Preserved

- No change was made to D5/D20/D60 horizon semantics.
- No change was made to the weighted observer decision model.
- No change was made to model quality guards or behavior guards.
- No change was made to basket analysis-only behavior.
- No change was made to scenario positive logic.
- Short candidates remain separate from the long basket and do not imply automatic short execution.
- Observation remains observation, not a buy signal.

## Recommended Next Work

- Re-run `.\scripts\run_weekend_full.ps1` in a long enough shell session, or add a bounded quick weekend mode for development validation.
- Profile `train --autotune --details` and decide whether to cache more aggressively, reduce default audit work, or parallelize safe parts.
- Add a CI job that runs pytest and a non-network/non-heavy script smoke test.
- Keep reducing duplicated render code by moving more table/header helpers into the shared terminal renderer.
- Keep `docs/COMMANDS.md` generated from code and make documentation refresh part of release hygiene.
