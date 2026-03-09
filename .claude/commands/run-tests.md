Run pytest with stop-on-first-failure and short tracebacks.

Usage: /run-tests [optional path or pytest args]

Steps:
1. Run: `uv run pytest $ARGUMENTS -x --tb=short -v`
   - If no arguments given, default to: `uv run pytest tests/ -x --tb=short -v`
2. Report how many tests passed/failed.
3. If any test fails, show the failure message and suggest a fix.
