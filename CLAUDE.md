# Used PC Price Finder — ML Pricing Engine

Python 3.12+ project. We scrape used computer prices from Japanese marketplaces (Rakuten Ichiba API, PC Koubou, etc.), store in Supabase, and build ML models to find optimal resale prices for refurbished PCs. Streamlit dashboard for monitoring.

## Tech Stack

- **Runtime:** Python 3.12+ managed by `uv`
- **Data:** Polars (NOT pandas — always prefer Polars for all dataframe operations)
- **Database:** Supabase (PostgreSQL) via `supabase-py`
- **ML:** LightGBM, scikit-survival, Optuna, SHAP
- **Dashboard:** Streamlit
- **Scraping:** httpx (async), selectolax or beautifulsoup4
- **Testing:** pytest with pytest-asyncio
- **Linting:** ruff

## Commands

```bash
# Environment
uv sync                          # Install/sync all dependencies
uv run python -m pytest tests/   # Run all tests
uv run pytest tests/test_X.py -x # Run single test file, stop on first failure
uv run ruff check src/           # Lint
uv run ruff format src/          # Format
uv run streamlit run src/dashboard/app.py  # Launch dashboard

# Scrapers
uv run python -m src.scrapers.rakuten   # Run Rakuten scraper
uv run python -m src.scrapers.pckoubo   # Run PC Koubou scraper

# ML pipeline
uv run python -m src.models.train       # Train pricing model
uv run python -m src.pipeline.score     # Score new products
```

## Project Structure

```
pc-price-finder/
├── CLAUDE.md
├── pyproject.toml                # uv project config, all deps here (NOT requirements.txt)
├── .env                          # Supabase keys, Rakuten API key (NEVER commit)
├── .claude/
│   ├── context/                  # Auto-saved context snapshots (see Context Protocol below)
│   │   └── latest.md
│   ├── commands/
│   │   ├── save-context.md       # /save-context slash command
│   │   ├── load-context.md       # /load-context slash command
│   │   └── status.md             # /status slash command
│   └── rules/
│       └── polars-only.md        # Enforce Polars over pandas
├── src/
│   ├── __init__.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract BaseScraper class
│   │   ├── rakuten.py            # Rakuten Ichiba API scraper
│   │   ├── pckoubo.py            # PC Koubou web scraper
│   │   └── models.py             # Pydantic models for scraped data
│   ├── database/
│   │   ├── __init__.py
│   │   ├── client.py             # Supabase client singleton
│   │   ├── repository.py         # Data access layer (OOP, typed)
│   │   └── migrations/           # SQL migration files
│   ├── features/
│   │   ├── __init__.py
│   │   ├── builder.py            # Feature engineering pipeline
│   │   ├── cpu_benchmark.py      # CPU → benchmark score mapping
│   │   └── transformers.py       # Individual feature transforms (OOP)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── train.py              # Model training entry point
│   │   ├── price_model.py        # LightGBM price regressor class
│   │   ├── survival_model.py     # Time-to-sale survival model class
│   │   ├── optimizer.py          # Combines both models for optimal price
│   │   └── evaluation.py         # Metrics, SHAP, model comparison
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── score.py              # Batch scoring pipeline
│   │   └── retrain.py            # Retraining pipeline
│   ├── dashboard/
│   │   ├── app.py                # Streamlit main app
│   │   └── components/           # Dashboard UI components
│   └── utils/
│       ├── __init__.py
│       ├── config.py             # Pydantic Settings for env vars
│       └── logging.py            # Structured logging setup
├── tests/
│   ├── conftest.py
│   ├── test_scrapers/
│   ├── test_features/
│   ├── test_models/
│   └── fixtures/                 # Test data (small CSVs, JSON mocks)
├── data/
│   ├── raw/                      # Raw scraper exports (gitignored)
│   ├── processed/                # Feature-engineered datasets (gitignored)
│   └── lookups/                  # CPU benchmarks, brand tiers (committed)
├── models/                       # Saved model artifacts (gitignored)
├── notebooks/                    # Exploration only, NOT production code
└── docs/
    └── project_plan.md           # Full ML project plan and spec
```

## Code Style & Principles

### OOP Architecture
- Every scraper inherits from `BaseScraper` (abstract class in `scrapers/base.py`)
- ML models wrap in classes with `.fit()`, `.predict()`, `.save()`, `.load()` interface
- Database access goes through `Repository` classes, never raw SQL in business logic
- Use Pydantic `BaseModel` for all data structures crossing boundaries (API responses, DB records, config)
- Use `@dataclass` for internal-only value objects
- Prefer composition over inheritance beyond the base scraper pattern

### Polars, Not Pandas
- **ALWAYS** use `polars` for dataframe operations. Never import or use `pandas`.
- If a library returns a pandas DataFrame, convert immediately: `pl.from_pandas(df)`
- Use lazy evaluation (`pl.scan_*`, `.lazy()`, `.collect()`) for large datasets
- Chain expressions instead of mutating: `df.with_columns(...)` not `df["col"] = ...`

### Python Style
- Type hints on all function signatures. Use `from __future__ import annotations`.
- Docstrings on all public classes and methods (Google style).
- Use `pathlib.Path` not `os.path`.
- Use `httpx.AsyncClient` for HTTP, not `requests`.
- f-strings for formatting, never `.format()` or `%`.
- Use `structlog` or stdlib `logging`, never `print()` for operational output.
- Errors: define custom exception classes in each module, inherit from a project-level base.

### Testing
- Every new module gets a corresponding test file.
- Use `pytest` fixtures, not setUp/tearDown.
- Mock external APIs (Supabase, Rakuten) at the HTTP layer with `respx` or `pytest-httpx`.
- Test data goes in `tests/fixtures/`, never hardcoded in test files.
- Aim for testing business logic, not mocking everything. Avoid mocks that test nothing useful.

### Git
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Branch naming: `feature/xxx`, `fix/xxx`, `refactor/xxx`
- Never commit `.env`, `data/raw/`, `data/processed/`, `models/*.pkl`

---

## Context Preservation Protocol

**CRITICAL WORKFLOW — Read this carefully.**

After every meaningful work session and before every `/clear`, you MUST save context. This project uses frequent `/clear` to keep the context window clean, but context must not be lost.

### How It Works

1. **Before clearing**, always write a context snapshot to `.claude/context/latest.md`
2. **After clearing**, always read `.claude/context/latest.md` to restore state
3. Context snapshots are also archived with timestamps to `.claude/context/history/`

### Context Snapshot Format

When saving context (either manually or via `/save-context`), write to `.claude/context/latest.md` in this exact format:

```markdown
# Context Snapshot
**Saved:** [timestamp]
**Phase:** [current project phase]
**Branch:** [current git branch]

## What Was Accomplished
- [bullet list of completed work this session]

## Current State
- **Working on:** [specific task in progress]
- **Blocked by:** [any blockers, or "none"]
- **Files modified:** [list of files changed]
- **Tests status:** [passing/failing/not run]

## Key Decisions Made
- [important architectural or design decisions with reasoning]

## Next Steps (Priority Order)
1. [most important next task]
2. [second priority]
3. [third priority]

## Open Questions
- [unresolved questions that need answers]

## Important Notes
- [gotchas, warnings, things to remember]
```

### Rules for Context Saves
- **Auto-save triggers:** Before `/clear`, before switching branches, after completing a major task, after any significant architectural decision
- **Keep it factual:** No fluff, just what happened, what's next, and what matters
- **Include file paths:** Always mention specific files so the next session can jump right in
- **Preserve decisions:** If a design choice was debated, record the decision AND the reasoning

---

## Agent Workflow Protocol

### Before Starting Any Task

1. Read `.claude/context/latest.md` if it exists
2. Run `git status` and `git log --oneline -5` to orient
3. Check if tests pass: `uv run pytest tests/ -x --tb=short`
4. Understand the current state BEFORE making changes

### During Work

- **Plan before coding.** Use Shift+Tab (Plan Mode) for anything touching 2+ files.
- **Work in small increments.** One logical change → test → commit. Not 500 lines then "hope it works."
- **Run tests after every change.** If tests break, fix them before moving on.
- **Stop and ask** if requirements are ambiguous. Don't guess at business logic.

### Guardrails — When to STOP

**Stop immediately and ask the user if:**
- You're about to change the database schema
- You're about to delete files or significantly refactor an existing working module
- You're unsure whether to use a new library or approach
- A task is taking more than 3 attempts to get right (you may be going in the wrong direction)
- Tests are failing and you don't understand why after 2 fix attempts
- The current approach requires changing more than 5 files (might need a different strategy)

**Never:**
- **Read, edit, or touch `.env` or `secrets.toml` under any circumstances.** These files contain live credentials and must never be opened, modified, or committed. Load config exclusively via `src/utils/config.py` (Pydantic Settings).
- Push to main branch directly
- Install packages outside of `pyproject.toml` (no `pip install`, always `uv add`)
- Use `pandas` (use `polars`)
- Skip writing tests for new functionality
- Make changes to the Supabase schema without explicit user approval

### After Completing a Task

1. Run `uv run ruff check src/ && uv run ruff format src/`
2. Run `uv run pytest tests/ -x`
3. Write a clear commit message
4. Update `.claude/context/latest.md`

---

## Supabase Schema (Current)

```sql
-- Products table
products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,           -- 'rakuten', 'pckoubo', etc.
    source_id TEXT NOT NULL,        -- Original listing ID from source
    title TEXT NOT NULL,
    brand TEXT,
    cpu TEXT,
    cpu_benchmark FLOAT,
    ram_gb INTEGER,
    storage_gb INTEGER,
    storage_type TEXT,              -- 'SSD', 'HDD', 'NVMe'
    screen_size FLOAT,
    os TEXT,
    condition TEXT,                 -- 'A', 'B', 'C', 'Junk'
    listed_price INTEGER,           -- Yen
    scraped_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source, source_id)
)

-- Price history table
price_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid REFERENCES products(id),
    price INTEGER NOT NULL,         -- Yen
    observed_at TIMESTAMPTZ DEFAULT now()
)

-- Model predictions table (created during ML phase)
price_predictions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid REFERENCES products(id),
    predicted_price INTEGER,
    model_version TEXT,
    confidence FLOAT,
    shap_explanation JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
)
```

**IMPORTANT:** If you need to modify this schema, STOP and discuss with the user first. Write migration SQL in `src/database/migrations/` and get approval before running.

---

## Scraper Architecture

All scrapers inherit from:

```python
from abc import ABC, abstractmethod
from src.scrapers.models import ProductListing

class BaseScraper(ABC):
    """Base class for all marketplace scrapers."""

    @abstractmethod
    async def scrape(self, **kwargs) -> list[ProductListing]:
        """Scrape listings and return structured data."""
        ...

    @abstractmethod
    async def scrape_single(self, listing_id: str) -> ProductListing | None:
        """Scrape a single listing by ID."""
        ...

    async def run(self, **kwargs) -> int:
        """Scrape, validate, and upload to Supabase. Returns count of new records."""
        listings = await self.scrape(**kwargs)
        validated = [l for l in listings if l.is_valid()]
        return await self._upload(validated)
```

When adding a new scraper: create `src/scrapers/newsite.py`, inherit from `BaseScraper`, implement the abstract methods, add a test in `tests/test_scrapers/`, then add the run command to this CLAUDE.md.

---

## ML Model Architecture

```python
from abc import ABC, abstractmethod
import polars as pl
from pathlib import Path

class BaseModel(ABC):
    """Base class for all ML models in this project."""

    @abstractmethod
    def fit(self, X: pl.DataFrame, y: pl.Series) -> "BaseModel": ...

    @abstractmethod
    def predict(self, X: pl.DataFrame) -> pl.Series: ...

    def save(self, path: Path) -> None: ...
    def load(cls, path: Path) -> "BaseModel": ...
```

---

## Environment Variables (in .env)

```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=xxx
RAKUTEN_APP_ID=xxx
RAKUTEN_AFFILIATE_ID=xxx  # optional
```

Load with Pydantic Settings, never read `.env` directly:
```python
from src.utils.config import settings
url = settings.supabase_url
```

---

## Current Phase

Check `.claude/context/latest.md` for the current project phase and what to work on next. If that file doesn't exist, the project is in initial setup and the first task is to scaffold the directory structure and get the Rakuten scraper working end-to-end.
