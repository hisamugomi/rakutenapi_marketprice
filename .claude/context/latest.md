# Context Snapshot
**Saved:** 2026-02-21
**Phase:** Phase 1 — Scrapers + Dashboard Working
**Branch:** main

## What Was Accomplished
- `scraper.py` — Rakuten API scraper working end-to-end: fetch → spec extract → Supabase insert
- `src/pckoboscrape.py` — PC Koubou Playwright scraper working, scrapes Lenovo + Dell used laptops
- `src/extract_specs_1.py` — Full spec extractor using polars + regex + rapidfuzz: extracts brand, model, OS, CPU, CPU gen, memory, SSD, HDD, display size, weight, bluetooth, webcam, USB ports
- `src/Marketprice.py` — Full Streamlit dashboard: dark theme, per-model price trend charts (Plotly), price distribution histogram, listings table with clickable URLs, multi-source (Rakuten + PC Koubou) support, sidebar filters (model, date range, source, active-only)
- `pyproject.toml` + `uv.lock` — project dependencies synced via uv
- `.claude_md_files/CLAUDE.md` — updated with hard rule: never read/edit/touch `.env` or `secrets.toml`

## Current State
- **Working on:** Nothing in progress — pipeline is functional end-to-end
- **Blocked by:** None
- **Files modified (uncommitted):** `scraper.py`, `src/Marketprice.py`, `src/extract_specs_1.py`, `src/pckoboscrape.py`
- **Files untracked:** `main.py`, `pyproject.toml`, `uv.lock`, `src/extract_specs.py`, `src/savetosupabase.py`, `src/spec_extractor.py`, `.gitignore`, `.python-version`, `node_modules/`, `package.json`, `package-lock.json`
- **Tests status:** None written yet

## Key Decisions Made
- Using `st.secrets` (Streamlit secrets) for credentials, NOT `.env` directly — secrets live in `.streamlit/secrets.toml`
- Supabase table is `rakuten_table` (not `products` as in original CLAUDE.md spec — schema diverged)
- Flat `src/` structure in use (not the nested `src/scrapers/`, `src/database/` etc. from CLAUDE.md spec) — decision pending on whether to refactor
- PC Koubou uses Playwright (async) with auto-scroll to load all items
- Spec extraction is regex-based (not AI) — fast, no API cost

## Tech Debt / Issues to Fix
- `scraper.py` imports and uses `pandas` (`.empty`, `.apply`, `.to_dict`) — violates polars-only rule; should be pure Polars
- `scraper.py` calls `run_scraper()` at module level — side effect on import, bad pattern; wrap in `if __name__ == "__main__"`
- `src/savetosupabase.py` is mostly commented out / stubbed — unused
- `node_modules/` is untracked and should be gitignored
- No `.gitignore` committed yet (file exists but untracked)
- Directory structure does not match CLAUDE.md spec

## Next Steps (Priority Order)
1. **Commit `.gitignore`** — add `node_modules/`, `*.pkl`, `data/raw/`, `data/processed/`, `.env`, `secrets.toml` entries
2. **Fix `scraper.py`** — remove pandas dependency (pure Polars), move `run_scraper()` call inside `if __name__ == "__main__"`
3. **Decide on directory structure** — keep flat `src/` or refactor to match CLAUDE.md spec (`src/scrapers/`, `src/database/`, etc.)
4. **Write tests** — at minimum for `extract_specs_1.py` (pure function, easy to test)
5. **ML pipeline** — feature engineering → LightGBM price model → Optuna tuning

## Open Questions
- Is the Supabase table schema (`rakuten_table`) final, or should it be renamed/restructured to match CLAUDE.md spec (`products` + `price_history`)?
- Are there more scraper targets beyond Rakuten and PC Koubou?
- What models/laptops should be added to the search queries in `scraper.py`?

## Important Notes
- Credentials are in `.streamlit/secrets.toml` — NEVER read, edit, or open this file
- `.env` — NEVER read, edit, or open this file
- Always use `uv add <package>` not `pip install`
- Always use `uv run` to execute scripts
- Prices are in Japanese Yen (JPY)
- Rakuten API queries use negative keywords e.g. `"L580 -lenovo"` to filter out new items sold by the brand itself
- PC Koubou scraper hits two URLs: used Lenovo notes + used Dell notes
