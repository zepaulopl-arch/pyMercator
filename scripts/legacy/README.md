# Legacy operational scripts

Moved on: 2026-06-04

These scripts are preserved for audit/history only. They are not the current
operational entry points.

Current supported scripts:

- `scripts/run_daily_signal.ps1`
- `scripts/run_daily_train.ps1`
- `scripts/run_weekend_full.ps1`

Legacy mapping:

| Legacy script | Replacement |
| --- | --- |
| `run_absolute_tests.ps1` | `run_weekend_full.ps1` |
| `run_daily_operation.ps1` | `run_daily_signal.ps1` |
| `run_daily_profiles.ps1` | `run_daily_train.ps1` |
| `run_initial_full_check.ps1` | `run_weekend_full.ps1` |
| `run_operational_tests.ps1` | `run_weekend_full.ps1` |
| `run_weekly_training.ps1` | `run_weekend_full.ps1` |

Rules for this folder:

- Do not call these scripts from automation.
- Do not delete them until at least one stable operating cycle confirms the
  replacements cover the old workflows.
- If a legacy script contains a still-useful check, move that check into the
  supported scripts or tests before deleting the legacy script.
