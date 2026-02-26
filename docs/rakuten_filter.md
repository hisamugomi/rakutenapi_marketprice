# Rakuten Computer Filter

`src/scrapers/rakuten_filter.py` — two-layer noise filter for Rakuten Ichiba listings.

## Why it exists

The Rakuten Ichiba API `genreId` field is unreliable:
- Accessories (batteries, bags, adapters) sometimes appear with `genreId=0` (unspecified).
- Bags / cases are occasionally mis-tagged with a computer genre ID.
- Filtering by `genreId` alone produces false negatives (real computers dropped) and false positives (accessories kept).

The filter adds an `is_uncertain` column instead of silently dropping ambiguous rows, so the Streamlit dashboard can flag them for manual review.

## Algorithm

```
if genreId in NOISE_GENRE_IDS          → REJECT
if genreId in COMPUTER_GENRE_IDS:
    has noise keyword                  → REJECT  (mislabelled accessory)
    else                               → KEEP    (is_uncertain=False)
if genreId is unknown (0 / null):
    has noise AND has computer kw      → KEEP    (is_uncertain=True)
    has noise, no computer kw          → REJECT
    else                               → KEEP    (is_uncertain=False)
```

`itemName` only is scanned — `itemCaption` is intentionally excluded to keep the filter fast and avoid over-matching from boilerplate shop text.

## Usage

```python
import polars as pl
from src.scrapers.rakuten_filter import filter_rakuten_computers

# raw_df comes from fetch_rakuten_items() in src/rakuten_api.py
clean_df = filter_rakuten_computers(raw_df)

# Inspect flagged rows
uncertain = clean_df.filter(pl.col("is_uncertain"))
```

The function:
- Requires columns `itemName` (Utf8) and `genreId` (Utf8 or Int64).
- Preserves all other columns untouched.
- Returns the filtered DataFrame **plus** the `is_uncertain` boolean column.
- Logs counts at INFO level (total / noise-genre-rejected / keyword-rejected / uncertain-kept / clean-kept).
- Returns the input unchanged (no crash) if the DataFrame is empty.

## Extending the filter

### Add a new noise genre ID

```python
# src/scrapers/rakuten_filter.py
NOISE_GENRE_IDS: Final[frozenset[str]] = frozenset({"552420", "999999"})
```

Lookup Rakuten genre IDs at: https://webservice.rakuten.co.jp/documentation/ichiba-genre-search

### Add noise keywords

Append to `NOISE_KEYWORDS`. Use Japanese katakana / hiragana exactly as they appear in `itemName`. The regex is case-insensitive for Latin characters but exact-match for CJK.

```python
NOISE_KEYWORDS: Final[tuple[str, ...]] = (
    ...existing keywords...,
    "フィルター",   # screen protector
    "液晶保護",     # screen protector (alternative spelling)
)
```

### Add computer keywords

Append to `COMPUTER_KEYWORDS` to improve precision for the "unknown genre + mixed signals" path:

```python
COMPUTER_KEYWORDS: Final[tuple[str, ...]] = (
    ...existing keywords...,
    "CF-",      # Panasonic Let's note prefix
    "NEC",
)
```

## Integration points

| Location | How to use |
|---|---|
| `src/rakuten_api.py` | Call `filter_rakuten_computers(df)` after `fetch_rakuten_items()` returns |
| `src/dashboard/app.py` | Filter `is_uncertain == True` rows for a "Needs review" section |
| `src/pipeline/score.py` | Skip or down-weight uncertain rows when batch-scoring prices |

## Constants reference

| Constant | Type | Current values |
|---|---|---|
| `COMPUTER_GENRE_IDS` | `frozenset[str]` | `{"100040", "100026"}` |
| `NOISE_GENRE_IDS` | `frozenset[str]` | `{"552420"}` |
| `NOISE_KEYWORDS` | `tuple[str, ...]` | 22 Japanese accessory terms |
| `COMPUTER_KEYWORDS` | `tuple[str, ...]` | 30 brand/OS/CPU/type terms |
