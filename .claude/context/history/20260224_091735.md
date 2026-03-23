# Context Snapshot
**Saved:** 2026-02-24 09:17
**Phase:** Phase 1 complete + Phase 2 ML scaffold done — prepping merge to main
**Branch:** feature/polars-cleanup

## What Was Accomplished This Session
- Fixed pckoubou memory extraction: added `_RE_MEM4` pattern to match slash-separated
  format (`/16GB/`, `/8GB DDR5/`) used in pckoubou item names
- Coverage improved: **24% → 88.3%** (172/721 → 637/721 rows with memory)
- Backfilled 465 existing NULL-memory rows in Supabase via Postgres UPDATE (no re-scrape needed)
- Committed memory fix: `4780a1a fix: improve pckoubou memory extraction coverage 24% → 88%`
- Committed ML agent's work (lightgbm/sklearn deps + src/pipeline/score.py + test scaffolding):
  `edd981a feat: add ML pipeline deps and scaffold (lightgbm, sklearn, score.py)`
- Stashed remaining working tree (`.claude/context/latest.md`) as stash@{0} "context snapshot"
- Attempted `git checkout main && git pull` → user rejected, stopped

## ML Pipeline (built by prior ML agent — committed in edd981a)
- `src/models/price_model.py` — `LightGBMPriceModel` wrapping sklearn Pipeline
- `src/models/evaluation.py` — mae/rmse/mape/r2/report helpers
- `src/models/train.py` — loads Supabase data, 80/20 split, fits, evaluates, saves
- `src/pipeline/score.py` — batch scoring → inserts to price_predictions
- `tests/test_models/test_price_model.py` — 5 unit tests (all passing per ML agent)
- Architecture: sklearn Pipeline `_FeatureParser → _CatEncoder → LGBMRegressor`
- Categorical cols (brand, os_clean, source): label-encoded to integers
- Save/load: joblib.dump/load of the whole LightGBMPriceModel object

## Current State
- **Working on:** Prepping feature/polars-cleanup for merge to main
- **Blocked by:** Pull main (user rejected the checkout — clarify before retrying)
- **Branch:** `feature/polars-cleanup` — 5 commits ahead of `origin/feature/polars-cleanup`
- **Stash:** stash@{0} = "context snapshot" (just .claude/context/latest.md — trivial)
- **Tests:** `tests/test_models/test_price_model.py` has 5 tests; other test dirs are empty scaffolds
- **Lint:** Clean

## Files Modified This Session
- `src/extract_specs_1.py` — added `_RE_MEM4` + added to `_memory()` loop (committed)

## Key Decisions Made
- Memory fix: one regex `_RE_MEM4 = re.compile(r'/(\d+)GB(?:\s+DDR[3-5](?:L|LP)?)?/', _F)`
  — minimal, safe, backward-compatible
- Backfilled DB via direct SQL UPDATE (faster than re-scraping)
- `_VALID = {2,4,6,8,12,16,24,32,48,64}` naturally rejects `/512GB SSD/` false positives

## DB State (Supabase — project rpzmfrfzszjwaswpiijk, ap-south-1)
- `products` — 791 rows (721 pckoubou + 70 rakuten)
- pckoubou memory coverage: **88.3%** (up from 24%)
- pckoubou SSD coverage: ~84%, CPU coverage: ~67%
- rakuten memory coverage: ~37% (low — different format)

## Products Table Schema (confirmed)
```
id, item_code, source, item_name, item_url, shop_name, search_query,
brand, model, cpu, cpu_gen, memory, ssd, hdd, os, display_size, weight,
bluetooth, webcam, usb_ports, is_active, first_seen_at, last_seen_at
```
- `cpu_gen` is TEXT (e.g. "8", "10"), not int
- `price_history` timestamp column is `scraped_at` (not `observed_at`)

## Git Log (feature/polars-cleanup — 5 commits ahead of origin)
```
edd981a feat: add ML pipeline deps and scaffold (lightgbm, sklearn, score.py)
4780a1a fix: improve pckoubou memory extraction coverage 24% → 88%
20e89cf fix: handle missing itemUrl in pckoubou upsert rename
266c5cb refactor: delete dead legacy files, fix lint, add tests scaffold and dev tooling
75103df feat: add ruff + pytest dev deps and dev.py task runner
7e0a516 feat: update dashboard to query products + price_history via listings_view
0ed668c feat: write to products + price_history schema
```

## Next Steps (Priority Order)
1. **Ask user** why `git checkout main` was rejected — is timing/permissions, or manual preference?
2. **Pull main + rebase** — `git checkout main && git pull`, then
   `git checkout feature/polars-cleanup && git rebase main`
3. **Pop the stash** — `git stash pop` (trivial — just context file)
4. **Review ML pipeline** before merging: run `uv run ruff check src/models/ src/pipeline/`
   and `uv run pytest tests/test_models/ -x`
5. **Create PR** — `gh pr create` from feature/polars-cleanup → main
6. **Merge to main** once PR approved
7. **Rakuten memory improvement** — only 37% coverage; investigate item name format
8. **Tests with real HTML** — download HTML fixtures, write actual scraper test assertions
9. **Drop `rakuten_table`** — once confirmed not needed
10. **GitHub Actions** — update workflow to use new schema

## Open Questions
- Why did user reject `git checkout main && git pull`? Clarify before retrying.
- Should `src/sofmapscrape.py` be integrated? Still untracked/orphaned.
- Has ML model been trained yet? `uv run python -m src.models.train` not yet run.

## Important Notes
- `.streamlit/secrets.toml` — NEVER read, edit, or open
- `.env` — NEVER read, edit, or open
- Always `uv add <package>`, never `pip install`
- Always `uv run` to execute scripts
- Prices in Japanese Yen (JPY)
- `rakuten_table` is kept as backup — do NOT drop
- `dev.py` task runner: `uv run python dev.py lint|fix|format|test|check`
- stash@{0} = context snapshot (just .claude/context/latest.md) — pop after pulling main
- stash@{1..4} = old stashes from earlier dev work on main/aiworks — ignore
