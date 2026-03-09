Lint and format the codebase using ruff.

Steps:
1. Run: `uv run ruff check src/ tests/`
   - Reports any code issues (unused imports, undefined names, style violations, etc.)
2. Run: `uv run ruff format src/ tests/`
   - Auto-formats code in-place.
3. If ruff check found issues, list them and fix any that are straightforward (unused imports, etc.).
4. Report how many files were reformatted.
