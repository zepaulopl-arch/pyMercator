PR: refactor/manifest-human-confirmation

Summary:
- Centralized manifest read/write/update helpers in `src/pymercator/manifest.py`.
- Updated `human_confirmation` and `real_run` to use shared manifest helpers.
- Extracted CLI confirm handler to `src/pymercator/cli_confirm.py` and delegated in `cli.py`.
- Extracted execution handler to `src/pymercator/cli_execution.py` and delegated in `cli.py`.

Why:
- Reduce duplicated manifest file logic and standardize manifest updates.
- Start modularizing a large `cli.py` to improve maintainability and testability.

Testing:
- `python -m ruff check src tests` -> All checks passed
- `python -m pytest -q` -> Full suite previously passed (111 passed, 1 skipped). Focused tests after changes:
  - `tests/test_execution_policy.py`, `tests/test_human_confirmation.py`, `tests/test_cli_confirm.py` -> pass

Next steps to create PR:
1. Add remote (if none): `git remote add origin <git-url>`
2. Push branch: `git push -u origin refactor/manifest-human-confirmation`
3. Open PR on GitHub with title and summary from this file.

Notes:
- I created a local branch and committed changes. I cannot push to remote without repository remote and credentials; run the above commands to publish.
- I can continue extracting other CLI handlers (`context`, `daily`) on request.
