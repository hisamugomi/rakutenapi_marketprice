# Context Snapshot
**Saved:** 2026-02-26 (current session)
**Phase:** Phase 2 — ML Pipeline + Scraper Quality
**Branch:** feature/polars-cleanup

## What Was Accomplished
### This session
- Created `src/scrapers/__init__.py` + `src/scrapers/rakuten_filter.py`
  - `filter_rakuten_computers(df)` — two-layer noise filter (genre + keyword)
  - Constants: `COMPUTER_GENRE_IDS`, `NOISE_GENRE_IDS`, `NOISE_KEYWORDS`, `COMPUTER_KEYWORDS`
  - `is_uncertain` column flags mixed-signal rows (both computer + noise kw in unknown genre)
  - stdlib `logging` at INFO with per-run stats
- Created `tests/test_scrapers/test_rakuten_filter.py` — 22 tests all passing (TDD)
- Created `docs/rakuten_filter.md` — usage, extension guide, integration points
- All 27 tests pass, lint clean

### Prior sessions
- Implemented and committed full LightGBM ML pricing pipeline
- Added deps: `lightgbm>=4.3.0`, `scikit-learn>=1.4.0`, `numpy>=1.26.0` (via `uv add`)
- Created `src/models/price_model.py`, `evaluation.py`, `train.py`
- Created `src/pipeline/score.py` — batch scoring entry point
- All previous tests still passing

## Current State
- **Working on:** Nothing in progress — session complete, uncommitted
- **Blocked by:** None
- **Files modified:** src/scrapers/__init__.py, src/scrapers/rakuten_filter.py, tests/test_scrapers/test_rakuten_filter.py, docs/rakuten_filter.md (all new, not yet committed)
- **Tests status:** 27/27 passing (3 harmless sklearn UserWarnings)
- **Lint status:** Clean

## Key Decisions Made
- sklearn Pipeline: `_FeatureParser → _CatEncoder → LGBMRegressor` — prevents data leakage, enables cross_val_score, single joblib artifact
- Native Polars expressions in `_parse_raw_features()` — no `map_elements` UDFs (caused Float32/Float64 conflicts)
- All-null columns handled by `.cast(pl.Utf8)` before string ops (Polars infers Null dtype for all-null lists)
- Categorical encoding: `_CatEncoder` label-encodes brand/os_clean/source to sorted int codes; OOV bucket at predict time
- Training data: query products + price_history separately, join in Polars (supabase-py has no raw SQL JOIN)
- User confirmed: pandas acceptable at library boundaries (sklearn/numpy), not strictly Polars-only everywhere

## Next Steps (Priority Order)
1. Commit: `feat: add rakuten_filter two-layer computer noise filter`
2. Wire `filter_rakuten_computers()` into `src/rakuten_api.py` (separate follow-up per plan)
3. Run actual training: `uv run python -m src.models.train` (needs .env / Streamlit secrets)
4. Run batch scoring: `uv run python -m src.pipeline.score` (needs trained model)
5. Optuna hyperparameter tuning — `src/models/optimizer.py`
6. Survival model — `src/models/survival_model.py` (time-to-sale)
7. Merge feature/polars-cleanup → main

## Open Questions
- Optuna or survival model next?
- When to merge to main?
- Drop `rakuten_table` (backup, 2179 rows)?
- Integrate `src/sofmapscrape.py`?

## Important Notes
- `.streamlit/secrets.toml` and `.env` — NEVER read, edit, or open
- Always `uv add`, never `pip install`; always `uv run`
- `price_history` column is `scraped_at` (NOT `observed_at`)
- `cpu_gen` is TEXT in products table (e.g. "8", "10")
- `/models/` (top-level) gitignored for artifacts; `src/models/` is NOT ignored
- Do NOT merge to main yet

## File Map
```
src/scrapers/__init__.py                      — package marker (new)
src/scrapers/rakuten_filter.py                — filter_rakuten_computers() (new)
tests/test_scrapers/test_rakuten_filter.py    — 22 tests, all passing (new)
docs/rakuten_filter.md                        — usage + extension guide (new)
src/models/price_model.py                     — LightGBMPriceModel (sklearn Pipeline)
src/models/evaluation.py                      — mae/rmse/mape/r2/report
src/models/train.py                           — training entry point
src/pipeline/score.py                         — batch scoring entry point
tests/test_models/test_price_model.py         — 5 unit tests (all passing)
```

## DB State
- products: 788 rows (721 pckoubou + 67 rakuten)
- price_history: growing (scraped_at column)
- price_predictions: empty (populated after first score.py run)
- listings_view: products JOIN price_history for dashboard

## Products Table Schema (actual)
```
id, item_code, source, item_name, item_url, shop_name, search_query,
brand, model, cpu, cpu_gen, memory, ssd, hdd, os, display_size, weight,
bluetooth, webcam, usb_ports, is_active, first_seen_at, last_seen_at
```

## Git Log (recent)
```
36e8d72 feat: implement LightGBM price model with sklearn Pipeline
edd981a feat: add ML pipeline deps and scaffold (lightgbm, sklearn, score.py)
4780a1a fix: improve pckoubou memory extraction coverage 24% → 88%
20e89cf fix: handle missing itemUrl in pckoubou upsert rename
266c5cb refactor: delete dead legacy files, fix lint, add tests scaffold and dev tooling
```
