"""Streamlit dashboard — Used PC Price Analysis + ML Predictions.

Launch with::

    uv run streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import polars as pl
import streamlit as st
from supabase import Client, create_client

from src.dashboard.components.charts import (
    ACCENT_COLORS,
    MODEL_QUERY_MAP,
    fmt_yen,
    render_all_models_trend,
    render_distribution_chart,
    render_feature_importance_chart,
    render_prediction_vs_actual_chart,
    render_trend_chart,
)
from src.dashboard.components.tables import (
    render_listings_table,
    render_predictions_table,
    render_stat_cards,
)

logger = logging.getLogger(__name__)

# ── Page config (must be the first Streamlit call) ────────────────────────────
st.set_page_config(
    page_title="Used PC Price Analyzer",
    page_icon="💻",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
    background-color: #0d0d0d;
    color: #e0e0e0;
  }

  section[data-testid="stSidebar"] {
    background-color: #111111;
    border-right: 1px solid #2a2a2a;
  }
  section[data-testid="stSidebar"] * {
    color: #c0c0c0 !important;
  }

  .main .block-container {
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 1400px;
  }

  .model-header {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #888;
    border-top: 1px solid #2a2a2a;
    padding-top: 2rem;
    margin-top: 2rem;
    margin-bottom: 0.25rem;
  }
  .model-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2rem;
    font-weight: 600;
    color: #000000;
    margin-bottom: 0.1rem;
    letter-spacing: -0.02em;
  }
  .model-subtitle {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: #555;
    margin-bottom: 1.5rem;
  }

  .stat-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 1px;
    background-color: #1e1e1e;
    border: 1px solid #1e1e1e;
    margin-bottom: 2rem;
  }
  .stat-card {
    background-color: #111;
    padding: 1rem 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .stat-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #555;
  }
  .stat-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.3rem;
    font-weight: 600;
    color: #f0f0f0;
  }
  .stat-unit {
    font-size: 0.7rem;
    color: #555;
  }

  .section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #444;
    margin-bottom: 0.5rem;
    margin-top: 1.5rem;
  }

  .stDataFrame {
    border: 1px solid #1e1e1e !important;
  }

  .app-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #444;
    margin-bottom: 0.2rem;
  }
  .app-name {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.6rem;
    font-weight: 600;
    color: #e0e0e0;
    margin-bottom: 1.5rem;
    letter-spacing: -0.02em;
  }

  .no-data {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: #444;
    padding: 2rem 0;
    border-top: 1px solid #1e1e1e;
    border-bottom: 1px solid #1e1e1e;
    text-align: center;
    margin: 1rem 0;
  }
</style>
""",
    unsafe_allow_html=True,
)


# ── Supabase client ───────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase_client() -> Client:
    """Return a cached Supabase client using Streamlit secrets."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["servicerole"]
    return create_client(url, key)


def _fetch_all(client: Client, table: str, select: str, page_size: int = 1000) -> list[dict]:
    """Paginate through a Supabase table to bypass the 1000-row server cap."""
    rows: list[dict] = []
    offset = 0
    while True:
        resp = client.table(table).select(select).range(offset, offset + page_size - 1).execute()
        rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    return rows


@st.cache_data(ttl=300)
def fetch_listings_data() -> pl.DataFrame:
    """Fetch all listings from listings_view with 5-minute cache."""
    client = get_supabase_client()
    data = _fetch_all(
        client,
        "listings_view",
        "itemCode, itemName, itemPrice, itemUrl, shopName, brand, cpu, memory, ssd, "
        "os, scraped_at, search_query, is_active, source",
    )
    if not data:
        return pl.DataFrame()
    return pl.DataFrame(data, infer_schema_length=None).with_columns(
        pl.col("itemPrice").cast(pl.Int64, strict=False),
        pl.col("scraped_at").str.to_datetime(strict=False, time_unit="us", time_zone="UTC"),
        pl.col("is_active").cast(pl.Boolean, strict=False),
    )


@st.cache_data(ttl=300)
def fetch_predictions_data() -> pl.DataFrame:
    """Fetch price_predictions joined with products from Supabase.

    Returns:
        DataFrame with: product_id, predicted_price, model_version, created_at,
        item_name, itemPrice, source, item_url.
        Returns empty DataFrame if no predictions exist.
    """
    client = get_supabase_client()

    preds_data = _fetch_all(
        client,
        "price_predictions",
        "product_id,predicted_price,model_version,created_at",
    )
    if not preds_data:
        return pl.DataFrame()

    products_data = _fetch_all(
        client,
        "products",
        "id,item_name,source,item_url",
    )
    if not products_data:
        return pl.DataFrame()

    preds = pl.from_dicts(preds_data)
    products = pl.from_dicts(products_data).rename({"id": "product_id"})

    joined = preds.join(products, on="product_id", how="left")

    # Try to enrich with actual prices from listings_view
    listings_data = _fetch_all(client, "listings_view", "itemCode,itemName,itemPrice,source")
    if listings_data:
        listings = pl.from_dicts(listings_data).select(
            pl.col("itemName").alias("item_name"),
            pl.col("itemPrice"),
        )
        # Fuzzy join not available — join on item_name directly
        joined = joined.join(
            listings.unique(subset=["item_name"]),
            on="item_name",
            how="left",
            suffix="_listings",
        )

    return joined


def load_metrics() -> dict | None:
    """Load model metrics from models/metrics.json if it exists."""
    path = Path("models/metrics.json")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def compute_stats(df: pl.DataFrame) -> dict:
    """Compute summary statistics for the price column."""
    prices = df["itemPrice"].drop_nulls()
    if len(prices) == 0:
        return {}
    arr = prices.to_numpy()
    return {
        "count": len(arr),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
    }


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="app-title">Price Analyzer</div>', unsafe_allow_html=True)
    st.markdown('<div class="app-name">市場価格推測サイト</div>', unsafe_allow_html=True)
    st.markdown("---")

    all_models = list(ACCENT_COLORS.keys())
    selected_models = st.multiselect(
        "Models",
        options=all_models,
        default=all_models,
        help="Select which models to display (表示するモデルを選択)",
    )
    st.markdown("---")

    today = datetime.now(timezone.utc).date()
    default_start = today - timedelta(days=30)
    date_start = st.date_input("From", value=default_start)
    date_end = st.date_input("To", value=today)
    st.markdown("---")

    active_only = st.checkbox("Active listings only", value=False)
    st.markdown("---")

    source_options = ["rakuten", "pckoubou"]
    selected_sources = st.multiselect(
        "Data Source",
        options=source_options,
        default=source_options,
        help="Toggle between Rakuten and PC Koubou data",
    )
    st.markdown("---")

    if st.button("↺  Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("**Debug**")
    show_debug = st.checkbox("Show debug info", value=False)


# ── Fetch & filter data ───────────────────────────────────────────────────────
with st.spinner("Fetching data (データを取得中)..."):
    raw_df = fetch_listings_data()

if raw_df.is_empty():
    st.error("No data returned from Supabase. Check your credentials in .streamlit/secrets.toml")
    st.stop()

if show_debug:
    with st.expander("Debug info", expanded=True):
        st.caption(f"Raw rows: **{len(raw_df):,}**")
        if "scraped_at" in raw_df.columns:
            st.caption(f"scraped_at range: {raw_df['scraped_at'].min()} → {raw_df['scraped_at'].max()}")
        if "source" in raw_df.columns:
            st.caption("Rows by source:")
            st.dataframe(raw_df["source"].value_counts().sort("source"), hide_index=True)

filtered_df = raw_df.filter(
    (pl.col("scraped_at").dt.date() >= date_start)
    & (pl.col("scraped_at").dt.date() <= date_end)
)
if active_only:
    filtered_df = filtered_df.filter(pl.col("is_active") == True)  # noqa: E712
if selected_sources:
    filtered_df = filtered_df.filter(pl.col("source").is_in(selected_sources))
filtered_df = filtered_df.filter(pl.col("itemPrice").is_not_null())

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(
    [
        "Market Overview 市場概観",
        "ML Predictions 価格予測",
        "Model Performance モデル評価",
    ]
)

# ── Tab 1: Market Overview ────────────────────────────────────────────────────
with tab1:
    st.markdown(
        '<div class="model-title">All models price trend モデルごとの価格トレンド</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-label">All models price trend モデルごとの価格トレンド</div>',
        unsafe_allow_html=True,
    )
    render_all_models_trend(filtered_df)

    if not selected_models:
        st.markdown(
            '<div class="no-data">Select at least one model from the sidebar.</div>',
            unsafe_allow_html=True,
        )
        st.stop()

    for model in selected_models:
        color = ACCENT_COLORS[model]
        model_df = filtered_df.filter(pl.col("search_query") == MODEL_QUERY_MAP[model])

        st.markdown('<div class="model-header">Model</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="model-title">{model}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="model-subtitle">'
            f'{len(model_df):,} listings · {date_start} → {date_end}'
            f"</div>",
            unsafe_allow_html=True,
        )

        if model_df.is_empty():
            st.markdown(
                "<div class=\"no-data\">— no listings found for this model in the selected date range —</div>",
                unsafe_allow_html=True,
            )
            continue

        s = compute_stats(model_df)
        if s:
            render_stat_cards(s)

        st.markdown('<div class="section-label">Price trend over time 価格トレンド</div>', unsafe_allow_html=True)
        render_trend_chart(model_df, model, color)

        st.markdown('<div class="section-label">Price distribution 価格分散</div>', unsafe_allow_html=True)
        render_distribution_chart(model_df, color)

        st.markdown('<div class="section-label">Individual listings 生データ</div>', unsafe_allow_html=True)
        render_listings_table(model_df)


# ── Tab 2: ML Predictions ─────────────────────────────────────────────────────
with tab2:
    st.markdown("## Price Predictions 価格予測")

    with st.spinner("Loading predictions..."):
        pred_df = fetch_predictions_data()

    if pred_df.is_empty() or "predicted_price" not in pred_df.columns:
        st.info(
            "No predictions yet. Run the ML pipeline first:\n"
            "```\n"
            "uv run python -m src.models.train\n"
            "uv run python -m src.pipeline.score\n"
            "```"
        )
    else:
        has_actual = "itemPrice" in pred_df.columns and pred_df["itemPrice"].drop_nulls().len() > 0

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Products with predictions", f"{len(pred_df):,}")
        with col2:
            avg_pred = pred_df["predicted_price"].cast(pl.Float64).mean()
            st.metric("Avg Predicted Price", fmt_yen(avg_pred) if avg_pred else "—")
        with col3:
            if has_actual:
                avg_actual = pred_df["itemPrice"].cast(pl.Float64).mean()
                st.metric("Avg Actual Price", fmt_yen(avg_actual) if avg_actual else "—")
            else:
                st.metric("Avg Actual Price", "—")
        with col4:
            model_ver = (
                pred_df["model_version"].drop_nulls().head(1).to_list()
                if "model_version" in pred_df.columns
                else []
            )
            st.metric("Model Version", model_ver[0] if model_ver else "—")

        if has_actual:
            st.markdown("### Predicted vs Actual Price")
            render_prediction_vs_actual_chart(pred_df)

            st.markdown("### Best Deals 割安リスト (Model thinks listing is underpriced)")
            render_predictions_table(pred_df)
        else:
            st.markdown("### Predicted Prices (no actual price match available)")
            cols_show = [c for c in ["item_name", "predicted_price", "model_version", "source"] if c in pred_df.columns]
            st.dataframe(pred_df.select(cols_show).head(50), use_container_width=True)


# ── Tab 3: Model Performance ──────────────────────────────────────────────────
with tab3:
    st.markdown("## Model Performance モデル評価")

    metrics = load_metrics()

    if metrics is None:
        st.info(
            "No model trained yet. Run:\n"
            "```\n"
            "uv run python -m src.models.train\n"
            "```"
        )
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Model Version", metrics.get("model_version", "—"))
        with col2:
            trained_at = metrics.get("trained_at", "")
            st.metric("Trained At", trained_at[:10] if trained_at else "—")
        with col3:
            improved = metrics.get("improved")
            st.metric(
                "vs Previous",
                "↑ Improved" if improved is True else ("↓ Degraded" if improved is False else "—"),
            )

        st.markdown("### Evaluation Metrics (test set)")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("MAE", f"¥{metrics.get('mae', 0):,.0f}")
        with c2:
            st.metric("RMSE", f"¥{metrics.get('rmse', 0):,.0f}")
        with c3:
            st.metric("MAPE", f"{metrics.get('mape', 0):.1f}%")
        with c4:
            st.metric("R²", f"{metrics.get('r2', 0):.4f}")

        n_train = metrics.get("n_train", 0)
        n_test = metrics.get("n_test", 0)
        st.caption(f"Trained on {n_train:,} rows · Evaluated on {n_test:,} rows")

        st.markdown("### Feature Importance")
        model_path = Path("models/price_model.joblib")
        if model_path.exists():
            try:
                import joblib

                loaded_model = joblib.load(model_path)
                lgbm_step = loaded_model._pipeline.named_steps["lgbm"]
                feature_names = loaded_model.FEATURE_COLS
                importances = lgbm_step.feature_importances_.tolist()
                render_feature_importance_chart(feature_names, importances)
            except Exception as exc:
                st.warning(f"Could not load model for feature importance: {exc}")
        else:
            st.info("Model file not found at models/price_model.joblib")
