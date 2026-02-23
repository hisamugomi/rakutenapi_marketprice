---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

NEVER use pandas in this project. Always use Polars.

- Do not `import pandas`. Use `import polars as pl`.
- If a third-party library returns a pandas DataFrame, convert it immediately with `pl.from_pandas(df)`.
- Use Polars lazy evaluation (`.lazy()`, `.collect()`) for datasets over 10k rows.
- Use `.with_columns()` for adding/transforming columns, never assign with `df["col"] = ...`.
- Use `.filter()` not boolean indexing.
- Use `pl.read_csv()`, `pl.read_parquet()`, not pandas equivalents.
