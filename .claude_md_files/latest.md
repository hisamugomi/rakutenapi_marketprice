# Context Snapshot
**Saved:** [initial setup]
**Phase:** Phase 0 — Project Scaffolding
**Branch:** main

## What Was Accomplished
- Created CLAUDE.md with full project spec
- Created slash commands: /save-context, /load-context, /status
- Created Polars-only rule
- Defined Supabase schema, project structure, and OOP architecture

## Current State
- **Working on:** Initial project setup — need to scaffold directory structure, pyproject.toml, and base classes
- **Blocked by:** None
- **Files modified:** CLAUDE.md, .claude/ directory
- **Tests status:** No tests yet

## Key Decisions Made
- Using `uv` as package manager (fast, modern, replaces pip + venv)
- Using `polars` instead of `pandas` for all data work
- OOP architecture: BaseScraper, BaseModel abstract classes
- Supabase for storage, Streamlit for dashboard
- Context preservation via .claude/context/ snapshots

## Next Steps (Priority Order)
1. Run `uv init` and set up pyproject.toml with all dependencies
2. Scaffold the directory structure (src/, tests/, data/, etc.)
3. Create base classes: BaseScraper, BaseModel, Repository, Config
4. Get Rakuten Ichiba scraper working end-to-end (scrape → Supabase)
5. Get PC Koubou scraper working
6. Build feature engineering pipeline
7. Train initial LightGBM price model
8. Build Streamlit dashboard

## Open Questions
- What Supabase tables already exist? Need to verify schema matches CLAUDE.md
- What Rakuten API endpoints are being used? (search? product detail?)
- Are there other scraper targets beyond Rakuten and PC Koubou?

## Important Notes
- Always use `uv add <package>` not `pip install`
- Always use `uv run` to execute scripts
- Prices are in Japanese Yen (JPY)
- Rakuten API has rate limits — respect them with async throttling
