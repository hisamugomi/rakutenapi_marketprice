"""
extract_specs.py
================
High-performance computer spec extractor powered by Rust/Cython libraries.

Libraries used
--------------
- polars       (Rust)        — lazy DataFrame engine, zero-copy columnar ops
- pyarrow      (C++)         — Arrow schema + Parquet I/O
- regex        (PCRE2 / C)   — full Unicode regex, faster than stdlib re
- rapidfuzz    (C++)         — fuzzy brand/model normalisation
- orjson       (Rust)        — fastest Python JSON serialiser

Setup (one-time, via uv)
------------------------
    uv pip install polars pyarrow regex rapidfuzz orjson

Or with plain pip:
    pip install polars pyarrow regex rapidfuzz orjson

Usage
-----
    import polars as pl
    from extract_specs import extract_specs

    df = pl.read_csv("items.csv")                     # or pl.from_pandas(...)
    specs = extract_specs(df, text_col="combined")
    specs.write_parquet("specs.parquet")              # fast via pyarrow
    print(specs)
"""

from __future__ import annotations

import sys
from typing import Any, Optional

# ── polars (Rust DataFrame engine) ──────────────────────────────────────────
try:
    import polars as pl
    _HAS_POLARS = True
except ImportError:
    _HAS_POLARS = False
    import pandas as _pd  # noqa: F401  (fallback)

# ── regex (PCRE2 via C extension — drop-in stdlib re replacement) ────────────
try:
    import regex as re
    _HAS_REGEX = True
except ImportError:
    import re  # type: ignore[no-redef]
    _HAS_REGEX = False

# ── rapidfuzz (C++ fuzzy matching) ───────────────────────────────────────────
try:
    from rapidfuzz import fuzz as _rfuzz
    from rapidfuzz import process as _rfprocess
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False

# ── orjson (Rust JSON serialiser) ────────────────────────────────────────────
try:
    import orjson
    _HAS_ORJSON = True
except ImportError:
    import json as _json  # noqa: F401  (fallback)
    _HAS_ORJSON = False

# ── pyarrow (C++ columnar / Parquet) ─────────────────────────────────────────
try:
    import pyarrow.parquet as pq
    _HAS_ARROW = True
except ImportError:
    _HAS_ARROW = False


# ---------------------------------------------------------------------------
# Known brands / model families — used by regex + rapidfuzz normaliser
# ---------------------------------------------------------------------------
_BRANDS = [
    "Lenovo", "Dell", "HP", "Hewlett-Packard", "ASUS", "Acer",
    "Toshiba", "Fujitsu", "Panasonic", "NEC", "Sony", "Microsoft",
    "Apple", "MSI", "Samsung", "Dynabook", "Sharp",
]

_MODEL_FAMILIES = [
    "ThinkPad", "IdeaPad", "Latitude", "Inspiron", "XPS", "Optiplex",
    "EliteBook", "ProBook", "ZBook", "Spectre", "Envy", "Pavilion",
    "VivoBook", "ZenBook", "TravelMate", "Aspire", "Swift", "Spin",
    "FMV", "LIFEBOOK", "VersaPro", "Let's Note",
]


# ---------------------------------------------------------------------------
# Full-width → half-width normalisation
# (pure Python — avoids a unicodedata import, fast enough for this use-case)
# ---------------------------------------------------------------------------

def _fw2hw(text: str) -> str:
    buf = []
    for ch in text:
        cp = ord(ch)
        if 0xFF01 <= cp <= 0xFF5E:
            buf.append(chr(cp - 0xFEE0))
        elif cp == 0x3000:
            buf.append(' ')
        else:
            buf.append(ch)
    return ''.join(buf)


# ---------------------------------------------------------------------------
# Compiled regex patterns  (compiled ONCE at import — PCRE2 if regex installed)
# ---------------------------------------------------------------------------
_F = re.IGNORECASE | re.UNICODE

# Brand
_RE_BRAND_FIELD  = re.compile(r'メーカー[名]?\s*[：:]\s*([\w\s]+?)(?:\n|　|,|型番)', _F)
_RE_BRAND_INLINE = re.compile(
    r'\b(' + '|'.join(re.escape(b) for b in _BRANDS) + r')\b', _F)

# Model
_RE_MODEL_FIELD  = re.compile(r'型番\s*[：:]\s*([\w\s\-]+?)(?:\n|　|CPU|メモリ|OS)', _F)
_RE_MODEL_FAMILY = re.compile(
    r'(' + '|'.join(re.escape(m) for m in _MODEL_FAMILIES) + r')\s+([\w\-]+)', _F)

# OS
_RE_OS = re.compile(
    r'(Windows\s*1[01]\s*(?:Pro|Home|Professional)?\s*(?:64bit|32bit)?)', _F)

# CPU — full text
_RE_CPU = re.compile(
    r'(?:intel\s+)?Core[™®]*\s+[i][3579][-\s]\d{4,5}[A-Z]*'
    r'(?:\s*\d+\.\d+\s*(?:GHz|MHz))?(?:\s*[\(（][^\)）\n]{0,30}[\)）])?', _F)
_RE_CPU_JP = re.compile(
    # format A (pckobo): インテル® Core™ i5-10210U プロセッサー
    # format B (rakuten): インテル Core i7 プロセッサー 8550U
    r'インテル[®™]*\s+Core[™®]*\s+[i][3579]'
    r'(?:[-\s]\d{4,5}[A-Z]*(?:\s*プロセッサー?)?'
    r'|\s+プロセッサー?\s+\d{4,5}[A-Z]*)'
    r'(?:\s*[\(（]\s*[^\)）\n]{0,50}[\)）])?', _F)

# CPU generation
_RE_GEN_JP   = re.compile(r'第\s*(\d+)\s*世代')
_RE_GEN_EN   = re.compile(r'(\d+)(?:st|nd|rd|th)\s*[Gg]en', _F)
_RE_GEN_NUM  = re.compile(r'Core[™®]*\s+[i][3579][-\s](\d)\d{3}[A-Z]', _F)

# Memory
_RE_MEM  = re.compile(
    r'(?:メモリ[容量]?\s*[：:（(]?\s*|RAM\s*[：:\s]+|MEM\s*[：:\s]+)(\d+)\s*GB', _F)
_RE_MEM2 = re.compile(r'(\d+)GB\s*\(スロット', _F)
_RE_MEM3 = re.compile(r'DDR[3-5](?:L|LP)?\s+(\d+)\s*GB', _F)  # e.g. DDR4 8GB

# Storage
_RE_SSD  = re.compile(r'(?:新品\s*)?(?:NVMe[式]?\s*)?(?:M\.2\s*)?SSD\s*[：:\s]*(\d+)\s*(GB|TB)', _F)
_RE_SSD2 = re.compile(r'容量[（(]SSD[）)]\s*[：:]\s*(\d+)\s*(GB|TB)', _F)
_RE_SSD3 = re.compile(r'(\d+)\s*(GB|TB)\s*(?:新品\s*)?(?:NVMe[式]?\s*)?(?:M\.2\s*)?SSD', _F)
_RE_HDD  = re.compile(r'HDD\s*[：:\s]*(\d+)\s*(GB|TB)', _F)
_RE_HDD2 = re.compile(r'(\d+)\s*(TB)\s*HDD', _F)

# Display
_RE_DISP  = re.compile(r'(?:ディスプレイ|液晶|画面)[^0-9]*(\d+(?:\.\d+)?)\s*(?:型|インチ|inch)', _F)
_RE_DISP2 = re.compile(r'(\d+(?:\.\d+)?)\s*(?:型|インチ|inch)\s*(?:ワイド|液晶|IPS|TN)', _F)
_RE_DISP3 = re.compile(r'(\d+(?:\.\d+)?)-inch', _F)

# Resolution
# _RE_RES     = re.compile(r'(\d{3,4})[×xｘ×](\d{3,4})', _F)
# _RE_RES_FHD = re.compile(r'フルHD|Full\s*HD|FHD', _F)
# _RE_RES_HD  = re.compile(r'\bHD\b', _F)

# Panel type
# _RE_IPS = re.compile(r'\bIPS\b', _F)
# _RE_TN  = re.compile(r'\bTN\b', _F)

# Weight
_RE_WEIGHT  = re.compile(r'重[さ量][：:\s]*(\d+(?:\.\d+)?)\s*kg', _F)
_RE_WEIGHT2 = re.compile(r'重さ[：:\s]?(\d+(?:\.\d+)?)\s*kg', _F)

# Wireless
# _RE_WIFI1       = re.compile(r'(802\.11\s*[a-z/]{2,8})', _F)
# _RE_WIFI2       = re.compile(r'(Wireless[-\s]AC\s*\d+)', _F)
# _RE_WIFI3       = re.compile(r'\b(ac/a/b/g/n)\b', _F)
# _RE_WIFI_PRESENT = re.compile(r'WiFi|Wi-Fi|無線LAN', _F)

# Bluetooth
_RE_BT_VER     = re.compile(r'Bluetooth\s+(\d+\.\d+)', _F)
_RE_BT_PRESENT = re.compile(r'Bluetooth', _F)

# Webcam
_RE_CAM1       = re.compile(r'(?:Web)?[Cc]amera\s*[：:]\s*([\w\s]+p)', _F)
_RE_CAM2       = re.compile(r'Webカメラ\s*[：:]\s*([\w\s]+)', _F)
_RE_CAM3       = re.compile(r'HD\s*720p|1080p', _F)
_RE_CAM_PRESENT = re.compile(r'Webカメラ|webcam|カメラ搭載', _F)

# USB
_RE_USB30  = re.compile(r'USB\s*3\.0\s*[×x×]\s*(\d+)', _F)
_RE_USB31C = re.compile(r'USB\s*3\.1\s*Type[-\s]?C\s*[×x×]?\s*(\d+)', _F)
_RE_USBC   = re.compile(r'USB\s*(?:Type[-\s]?C|3\.1\s*Type[-\s]?C)', _F)

# Optical drive
# _RE_OPT_NO     = re.compile(r'光学[ドド]ライブ[：:\s]*(?:な[しい]|非搭載|無し|なし)', _F)
# _RE_OPT_YES    = re.compile(r'光学[ドド]ライブ[：:\s]*(DVD|CD|Blu[-\s]?ray)', _F)
# _RE_OPT_DVD_NO = re.compile(r'DVD.*?(?:非搭載|なし|無し)', _F)

# Warranty
# _RE_WAR1 = re.compile(r'保証期間[：:\s]*(\d+年間?|\d+ヶ?月間?)', _F)
# _RE_WAR2 = re.compile(r'(\d+年間?)(?:の)?(?:動作)?保証', _F)
# _RE_WAR3 = re.compile(r'保証[：:\s]*(\d+日間)', _F)

# Office
# _RE_OFF_MS   = re.compile(r'Microsoft\s*Office\s*\d{4}|MS\s*Office\s*\d{4}|Office\s*\d{4}', _F)
# _RE_OFF_WPS  = re.compile(r'WPS\s*Office\s*\d+|WPS\s*Office', _F)
# _RE_OFF_NONE = re.compile(r'オフィスソフト[：:\s]*な[しい]|Officeなし|Office\s*非搭載', _F)

# Tenkey
# _RE_TENKEY = re.compile(r'テンキー|10キー|numpad', _F)


# ---------------------------------------------------------------------------
# Tiny helper
# ---------------------------------------------------------------------------

def _g1(pat: "re.Pattern[str]", text: str) -> Optional[str]:
    """Return group(1) of first match, or None."""
    m = pat.search(text)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Per-field extractors  (each accepts a normalised str, returns str|bool|None)
# ---------------------------------------------------------------------------

def _brand(text: str) -> Optional[str]:
    m = _RE_BRAND_FIELD.search(text)
    if m:
        return m.group(1).split()[0]
    m = _RE_BRAND_INLINE.search(text)
    return m.group(1) if m else None


def _model(text: str) -> Optional[str]:
    v = _g1(_RE_MODEL_FIELD, text)
    if v:
        return v.strip()
    m = _RE_MODEL_FAMILY.search(text)
    return f"{m.group(1)} {m.group(2)}".strip() if m else None


def _os(text: str) -> Optional[str]:
    return _g1(_RE_OS, text)


def _cpu(text: str) -> Optional[str]:
    # Try the Japanese full-form first (インテル Core i7...) — cleaner
    m = _RE_CPU_JP.search(text)
    if m:
        v = m.group(0).strip().rstrip(',。　')
        if len(v) > 4:
            return v
    # Fall back to the model-number pattern
    m = _RE_CPU.search(text)
    if m:
        v = m.group(0).strip().rstrip(',。　')
        if len(v) > 4:
            return v
    return None


def _cpu_gen(text: str) -> Optional[str]:
    for pat in (_RE_GEN_JP, _RE_GEN_EN):
        m = pat.search(text)
        if m:
            return m.group(1)
    m = _RE_GEN_NUM.search(text)
    if m:
        return m.group(1)
    # Infer from model number: 8250U → gen 8, 10510U → gen 10
    m = re.search(r'\b(\d{1,2})(\d{3})[UYHQGP]\b', text)
    if m:
        g = int(m.group(1))
        if 1 <= g <= 14:
            return str(g)
    return None


def _memory(text: str) -> Optional[str]:
    _VALID = {2, 4, 6, 8, 12, 16, 24, 32, 48, 64}
    for pat in (_RE_MEM, _RE_MEM2, _RE_MEM3):
        m = pat.search(text)
        if m:
            try:
                size = int(m.group(1))
                if size in _VALID:
                    return f"{size}GB"
            except ValueError:
                pass
    return None


def _storage(text: str) -> tuple[Optional[str], Optional[str]]:
    ssd = None
    for pat in (_RE_SSD, _RE_SSD2, _RE_SSD3):
        m = pat.search(text)
        if m:
            ssd = f"{m.group(1)}{m.group(2).upper()}"
            break
    hdd = None
    for pat in (_RE_HDD, _RE_HDD2):
        m = pat.search(text)
        if m:
            hdd = f"{m.group(1)}{m.group(2).upper()}"
            break
    return ssd, hdd


def _display_size(text: str) -> Optional[str]:
    for pat in (_RE_DISP, _RE_DISP2, _RE_DISP3):
        m = pat.search(text)
        if m:
            try:
                s = float(m.group(1))
                if 10.0 <= s <= 20.0:
                    return f"{s}インチ"
            except ValueError:
                pass
    return None


# def _resolution(text: str) -> Optional[str]:
#     m = _RE_RES.search(text)
#     if m:
#         return f"{m.group(1)}x{m.group(2)}"
#     if _RE_RES_FHD.search(text):
#         return "1920x1080"
#     if _RE_RES_HD.search(text):
#         return "1366x768"
#     return None


# def _panel_type(text: str) -> Optional[str]:
#     if _RE_IPS.search(text):
#         return "IPS"
#     if _RE_TN.search(text):
#         return "TN"
#     return None


def _weight(text: str) -> Optional[str]:
    for pat in (_RE_WEIGHT, _RE_WEIGHT2):
        m = pat.search(text)
        if m:
            try:
                w = float(m.group(1))
                if 0.5 <= w <= 5.0:
                    return f"{w}kg"
            except ValueError:
                pass
    return None


# def _wireless(text: str) -> Optional[str]:
#     for pat in (_RE_WIFI1, _RE_WIFI2, _RE_WIFI3):
#         m = pat.search(text)
#         if m:
#             return m.group(1)
#     return "搭載" if _RE_WIFI_PRESENT.search(text) else None


def _bluetooth(text: str) -> Optional[str]:
    m = _RE_BT_VER.search(text)
    if m:
        return f"Bluetooth {m.group(1)}"
    return "搭載" if _RE_BT_PRESENT.search(text) else None


def _webcam(text: str) -> Optional[str]:
    for pat in (_RE_CAM1, _RE_CAM2, _RE_CAM3):
        m = pat.search(text)
        if m:
            return m.group(0).strip()
    return "搭載" if _RE_CAM_PRESENT.search(text) else None


def _usb_ports(text: str) -> Optional[str]:
    parts = []
    m = _RE_USB30.search(text)
    if m:
        parts.append(f"USB3.0×{m.group(1)}")
    m = _RE_USB31C.search(text)
    if m:
        parts.append(f"USB3.1 Type-C×{m.group(1)}")
    elif _RE_USBC.search(text):
        parts.append("USB Type-C搭載")
    return ", ".join(parts) if parts else None


# def _optical_drive(text: str) -> Optional[str]:
#     if _RE_OPT_NO.search(text):
#         return "なし"
#     m = _RE_OPT_YES.search(text)
#     if m:
#         return m.group(1)
#     if _RE_OPT_DVD_NO.search(text):
#         return "なし"
#     return None


# def _warranty(text: str) -> Optional[str]:
#     for pat in (_RE_WAR1, _RE_WAR2, _RE_WAR3):
#         v = _g1(pat, text)
#         if v:
#             return v
#     return None


# def _office(text: str) -> Optional[str]:
#     if _RE_OFF_NONE.search(text):
#         return "なし"
#     for pat in (_RE_OFF_MS, _RE_OFF_WPS):
#         m = pat.search(text)
#         if m:
#             return m.group(0).strip()
#     return None


# def _tenkey(text: str) -> bool:
#     return bool(_RE_TENKEY.search(text))


# ---------------------------------------------------------------------------
# rapidfuzz brand normaliser  (C++ — only runs when library is installed)
# ---------------------------------------------------------------------------

def _normalize_brand(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return raw
    # Exact case-insensitive match first (handles LENOVO → Lenovo, HP → HP, etc.)
    raw_lower = raw.lower()
    for brand in _BRANDS:
        if brand.lower() == raw_lower:
            return brand
    # Fuzzy match for typos / partial names
    if _HAS_RAPIDFUZZ:
        result = _rfprocess.extractOne(
            raw, _BRANDS, scorer=_rfuzz.token_sort_ratio, score_cutoff=70
        )
        return result[0] if result else raw
    return raw


# ---------------------------------------------------------------------------
# Per-row extraction  (called by both polars and pandas paths)
# ---------------------------------------------------------------------------

def _extract_row(raw: str) -> dict[str, Any]:
    text = _fw2hw(str(raw))
    ssd, hdd = _storage(text)
    return {
        "brand":         _normalize_brand(_brand(text)),
        "model":         _model(text),
        "os":            _os(text),
        "cpu":           _cpu(text),
        "cpu_gen":       _cpu_gen(text),
        "memory":        _memory(text),
        "ssd":           ssd,
        "hdd":           hdd,
        "display_size":  _display_size(text),
        # "resolution":    _resolution(text),
        # "panel_type":    _panel_type(text),
        "weight":        _weight(text),
        # "wireless":      _wireless(text),
        "bluetooth":     _bluetooth(text),
        "webcam":        _webcam(text),
        "usb_ports":     _usb_ports(text),
        # "tenkey":        _tenkey(text),
        # "optical_drive": _optical_drive(text),
        # "office":        _office(text),
        # "warranty":      _warranty(text),
    }


# ---------------------------------------------------------------------------
# Polars schema definition  (Utf8 = Arrow LargeUtf8 under the hood)
# ---------------------------------------------------------------------------

if _HAS_POLARS:
    _POLARS_SCHEMA: dict[str, pl.PolarsDataType] = {
        "brand":         pl.Utf8,
        "model":         pl.Utf8,
        "os":            pl.Utf8,
        "cpu":           pl.Utf8,
        "cpu_gen":       pl.Utf8,
        "memory":        pl.Utf8,
        "ssd":           pl.Utf8,
        "hdd":           pl.Utf8,
        "display_size":  pl.Utf8,
        # "resolution":    pl.Utf8,
        # "panel_type":    pl.Utf8,
        "weight":        pl.Utf8,
        # "wireless":      pl.Utf8,
        "bluetooth":     pl.Utf8,
        "webcam":        pl.Utf8,
        "usb_ports":     pl.Utf8,
        # "tenkey":        pl.Boolean,
        # "optical_drive": pl.Utf8,
        # "office":        pl.Utf8,
        # "warranty":      pl.Utf8,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_specs(
    df: "pl.DataFrame | pl.LazyFrame | Any",
    text_col: str = "combined",
    price_col: Optional[str] = "itemPrice",
    name_col: Optional[str] = "itemName",
    *,
    lazy: bool = False,
) -> "pl.DataFrame | pl.LazyFrame | Any":
    """
    Extract hardware specs from product description strings.

    Parameters
    ----------
    df : polars.DataFrame | polars.LazyFrame | pandas.DataFrame
        Input dataframe.  Polars is preferred; pandas is the fallback.
    text_col : str
        Column containing the combined product description text.
    price_col : str | None
        Column holding the item price (numeric).
    name_col : str | None
        Column holding the item title/name.
    lazy : bool
        Return a polars LazyFrame (deferred execution). Ignored for pandas.

    Returns
    -------
    polars.DataFrame | polars.LazyFrame | pandas.DataFrame

    Extracted columns
    -----------------
    item_name, price, brand, model, os, cpu, cpu_gen,
    memory, ssd, hdd, display_size, resolution, panel_type,
    weight, wireless, bluetooth, webcam, usb_ports,
    tenkey, optical_drive, office, warranty
    """
    if _HAS_POLARS:
        return _polars_path(df, text_col, price_col, name_col, lazy)
    return _pandas_path(df, text_col, price_col, name_col)


# ---------------------------------------------------------------------------
# Polars path  (Rust columnar engine)
# ---------------------------------------------------------------------------

def _polars_path(
    df: "pl.DataFrame | pl.LazyFrame",
    text_col: str,
    price_col: Optional[str],
    name_col: Optional[str],
    lazy: bool,
) -> "pl.DataFrame | pl.LazyFrame":
    frame = df.collect() if isinstance(df, pl.LazyFrame) else df

    # Extract specs — this is the CPU-bound step.
    # Swap the list comprehension for a multiprocessing.Pool for large datasets.
    rows: list[dict] = [_extract_row(t) for t in frame[text_col].cast(pl.Utf8).to_list()]

    spec_df = pl.from_dicts(rows, schema=_POLARS_SCHEMA)

    # Prepend identity columns (zero-copy slice from input frame)
    id_cols = {}
    if name_col and name_col in frame.columns:
        id_cols["itemName"] = frame[name_col]
    if price_col and price_col in frame.columns:
        id_cols["itemPrice"] = frame[price_col]
    id_cols["itemCode"] = frame["itemCode"]
    id_cols["genreId"] = frame["genreId"]
    id_cols["shopName"] = frame["shopName"]
    id_cols["is_active"] = frame["is_active"]
    id_cols["scraped_at"] = frame["scraped_at"]
    id_cols["search_query"] = frame["search_query"]
    if "itemUrl" in frame.columns:
        id_cols["itemUrl"] = frame["itemUrl"]
    
    result = (
        pl.concat([pl.DataFrame(id_cols), spec_df], how="horizontal")
        if id_cols
        else spec_df
    )

    return result.lazy() if lazy else result


# ---------------------------------------------------------------------------
# Pandas fallback path
# ---------------------------------------------------------------------------

def _pandas_path(df, text_col, price_col, name_col):
    import pandas as pd
    rows = [_extract_row(str(t)) for t in df[text_col]]
    spec_df = pd.DataFrame(rows)

    prefixes = {}
    if name_col and name_col in df.columns:
        prefixes["item_name"] = df[name_col].values
    if price_col and price_col in df.columns:
        prefixes["price"] = df[price_col].values

    if prefixes:
        prefix_df = pd.DataFrame(prefixes, index=df.index)
        return pd.concat([prefix_df, spec_df.set_index(df.index)], axis=1)
    return spec_df


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def to_parquet(df: "pl.DataFrame", path: str) -> None:
    """
    Write to Parquet with Snappy compression.
    Uses pyarrow (C++) when available, else polars' built-in writer.
    """
    if _HAS_ARROW and _HAS_POLARS:
        pq.write_table(df.to_arrow(), path, compression="snappy")
    elif _HAS_POLARS:
        df.write_parquet(path)
    else:
        raise RuntimeError("polars required for Parquet export")


def to_json(df: "pl.DataFrame | Any", path: str) -> None:
    """
    Write to JSON. Uses orjson (Rust) when available, else stdlib json.
    """
    if _HAS_POLARS and isinstance(df, pl.DataFrame):
        records = df.to_dicts()
    else:
        records = df.to_dict(orient="records")

    if _HAS_ORJSON:
        with open(path, "wb") as fh:
            fh.write(orjson.dumps(records, option=orjson.OPT_INDENT_2))
    else:
        import json
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Library status report
# ---------------------------------------------------------------------------

def lib_info() -> dict[str, str]:
    """Return availability and versions of fast backend libraries."""
    checks = [
        ("polars",    _HAS_POLARS,    "polars",    "Rust DataFrame engine"),
        ("pyarrow",   _HAS_ARROW,     "pyarrow",   "C++ columnar / Parquet I/O"),
        ("regex",     _HAS_REGEX,     "regex",     "PCRE2 Unicode regex (C ext)"),
        ("rapidfuzz", _HAS_RAPIDFUZZ, "rapidfuzz", "C++ fuzzy matching"),
        ("orjson",    _HAS_ORJSON,    "orjson",    "Rust JSON serialiser"),
    ]
    out = {}
    for name, flag, mod_name, desc in checks:
        if flag:
            mod = sys.modules.get(mod_name)
            ver = getattr(mod, "__version__", "installed")
            out[name] = f"{ver}  ({desc})"
        else:
            out[name] = f"NOT INSTALLED  ← uv pip install {name}"
    return out


# ---------------------------------------------------------------------------
# Demo / self-test
# ---------------------------------------------------------------------------

# if __name__ == "__main__":
#     print("── Fast-library status ─────────────────────────────────────")
#     for lib, status in lib_info().items():
#         tick = "✓" if not status.startswith("NOT") else "✗"
#         print(f"  {tick}  {lib:<12}  {status}")
#     print()

#     SAMPLE = [
#         {
#             "itemName": "フルHD 15.6型 Lenovo ThinkPad L580 Core i7 8550U M.2SSD256G メモリ8G",
#             "itemPrice": 36800,
#             "combined": (
#                 "Windows11 Pro 64bit導入済みで第8世代Core i7搭載！ "
#                 "メーカー名 Lenovo 型番 Thinkpad L580 "
#                 "CPU 4コア8スレッド インテル Core i7 プロセッサー 8550U (1.80GHz〜4.00GHz) "
#                 "液晶 15.6型 フルHD IPS液晶 (1,920×1,080ドット) "
#                 "メモリ 8GB  M.2 SSD 256GB "
#                 "Webカメラ HD 720p  Bluetooth 4.1 "
#                 "USB3.0 ×2  USB Type-C x2 "
#                 "OS Windows 11 Pro 64bit  重さ：2.0kg  保証期間1年間"
#             ),
#         },
#         {
#             "itemName": "Lenovo ThinkPad L590 16GB SSD256GB WPS Office 付き Windows11",
#             "itemPrice": 32800,
#             "combined": (
#                 "型番Lenovo ThinkPad L590  CPU第8世代 Core i5 "
#                 "画面15.6インチワイド (1,366x768)  RAMDDR4 16GB  SSD256GB "
#                 "OS Windows 11 Pro 64bit  WPS Office 2 "
#                 "USB 3.0x2  USB 3.1 Type-Cx2  テンキー "
#                 "保証期間：30日間  光学ドライブ非搭載"
#             ),
#         },
#         {
#             "itemName": "ThinkPad L580 Core i5 8250U MEM:16GB SSD:512GB 一年保証",
#             "itemPrice": 31980,
#             "combined": (
#                 "メーカーLenovo シリーズThinkPad L580 "
#                 "メモリ容量16GB  容量（SSD）512GB(新品換装済) "
#                 "CPU intel Core i5 8250U 1.6(〜最大3.4)GHz "
#                 "ディスプレイ15.6型ワイド TN HD(1366×768)  重さ：2.0kg "
#                 "OSWindows11Pro 64bit  保証期間1年間  光学ドライブ非搭載  テンキー"
#             ),
#         },
#         {
#             "itemName": "ThinkPad L580 Core i3 8130U 8GB SSD256GB WPS Office",
#             "itemPrice": 25800,
#             "combined": (
#                 "Lenovo ThinkPad L580  OS Windows11 64ビット "
#                 "第8世代Core i3  WPS Office "
#                 "メモリ（RAM） 8GB  SSD：256GB "
#                 "15.6インチ  TN液晶1366×768ドット "
#                 "無線LAN対応  Bluetooth搭載  保証1年間"
#             ),
#         },
#         {
#             "itemName": "訳有 ThinkPad L580 Core i7-8550U 8GB NVMe SSD512GB Win11",
#             "itemPrice": 16489,
#             "combined": (
#                 "型番：Lenovo ThinkPad L580 "
#                 "CPU：第8世代Core i7-8550U 1.8Ghz、4コア8スレッド "
#                 "爆速NVMe式 SSD 512GB  メモリ：8GB "
#                 "ディスプレイ：15.6インチ 1366 x 768 "
#                 "USB3.0 x2  USB Type-C接続口 x2個 "
#                 "Webカメラ搭載  Bluetooth搭載 "
#                 "OS Windows11 Pro 64bit  テンキー"
#             ),
#         },
#     ]
#     if _HAS_POLARS:
#         df = pl.from_dicts(SAMPLE)
#         print(f"Input : polars DataFrame  shape={df.shape}")
#     else:
#         import pandas as pd
#         df = pd.DataFrame(SAMPLE)
#         print(f"Input : pandas DataFrame  shape={df.shape}")

    # result = extract_specs(df, text_col="combined",
    #                        price_col="itemPrice", name_col="itemName")

    # print()
    # print("── Extracted specs ─────────────────────────────────────────")
    # if _HAS_POLARS:
    #     with pl.Config(tbl_width_chars=200, tbl_rows=20):
    #         print(result)
    # else:
    #     import pandas as pd
    #     pd.set_option("display.max_columns", None)
    #     pd.set_option("display.width", 220)
    #     pd.set_option("display.max_colwidth", 38)
    #     print(result.to_string(index=False))

    # print()
    # print("── First item detail ───────────────────────────────────────")
    # if _HAS_POLARS:
    #     for k, v in result.row(0, named=True).items():
    #         print(f"  {k:<20}: {v}")
    # else:
    #     for col in result.columns:
    #         print(f"  {col:<20}: {result.iloc[0][col]}")

    # print(result)

    # # Uncomment to export:
    # # to_json(result, "specs.json")
    # # to_parquet(result, "specs.parquet")
