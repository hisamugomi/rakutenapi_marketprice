from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import plotly.graph_objects as go
import polars as pl
import streamlit as st
from supabase import Client, create_client

# ── Page config ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PC Market Price Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
    background-color: #0d0d0d;
    color: #e0e0e0;
  }
  section[data-testid="stSidebar"] {
    background-color: #0d0d0d;
    border-right: 1px solid #1e1e1e;
  }
  section[data-testid="stSidebar"] * { color: #999 !important; }
  .main .block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1440px; }

  /* Model cards grid */
  .cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 1px;
    background: #1a1a1a;
    border: 1px solid #1a1a1a;
    margin-bottom: 2.5rem;
  }
  .model-card {
    background: #111;
    padding: 1.25rem 1.5rem;
    cursor: default;
  }
  .mc-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #444;
    margin-bottom: 0.4rem;
  }
  .mc-price {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.6rem;
    font-weight: 600;
    color: #f0f0f0;
    letter-spacing: -0.02em;
    line-height: 1;
    margin-bottom: 0.4rem;
  }
  .mc-change {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
  }
  .mc-change.up   { color: #f4a535; }
  .mc-change.down { color: #4fc3f7; }
  .mc-change.flat { color: #444; }
  .mc-count {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    color: #333;
    margin-top: 0.3rem;
  }

  /* Stat row */
  .stat-row {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 1px;
    background: #1a1a1a;
    border: 1px solid #1a1a1a;
    margin-bottom: 2rem;
  }
  .stat-cell {
    background: #111;
    padding: 1rem 1.25rem;
  }
  .stat-cell.ml { background: #0b1520; border-left: 2px solid #1e4a8a; }
  .stat-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #444;
    margin-bottom: 0.35rem;
  }
  .stat-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.25rem;
    font-weight: 600;
    color: #f0f0f0;
  }
  .stat-val.ml { color: #4a9eff; }
  .stat-val.up   { color: #f4a535; }
  .stat-val.down { color: #4fc3f7; }
  .stat-val.flat { color: #555; }
  .stat-sub {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    color: #333;
    margin-top: 0.2rem;
  }

  /* Section labels */
  .sec-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #333;
    margin-top: 1.75rem;
    margin-bottom: 0.5rem;
  }

  /* Model section header */
  .model-divider { border-top: 1px solid #1a1a1a; margin-top: 3rem; padding-top: 2.5rem; }
  .model-name {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.8rem;
    font-weight: 600;
    color: #f0f0f0;
    letter-spacing: -0.02em;
    margin-bottom: 0.2rem;
  }
  .model-meta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #444;
    margin-bottom: 1.75rem;
  }

  /* App header */
  .app-eyebrow {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #333;
    margin-bottom: 0.15rem;
  }
  .app-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.5rem;
    font-weight: 600;
    color: #ddd;
    letter-spacing: -0.02em;
    margin-bottom: 1.5rem;
  }

  .no-data {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: #333;
    padding: 2rem;
    border: 1px solid #1a1a1a;
    text-align: center;
    margin: 1rem 0;
  }

  /* Hide streamlit branding */
  #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Supabase ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["servicerole"])


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
def fetch_data() -> pl.DataFrame:
    client = get_supabase_client()

    products_data = _fetch_all(
        client, "products",
        "id, item_name, item_url, shop_name, brand, model, "
        "cpu, cpu_gen, memory, ssd, hdd, os, display_size, is_active, source",
    )
    price_data = _fetch_all(
        client, "price_history",
        "product_id, price, scraped_at, source, search_query",
    )

    if not products_data or not price_data:
        return pl.DataFrame()

    products_df = pl.DataFrame(products_data, infer_schema_length=None).with_columns(
        pl.col("is_active").cast(pl.Boolean, strict=False),
    )
    price_df = pl.DataFrame(price_data).with_columns([
        pl.col("price").cast(pl.Int64, strict=False),
        pl.col("scraped_at").str.to_datetime(strict=False, time_unit="us", time_zone="UTC"),
    ])

    df = price_df.join(
        products_df.rename({"id": "product_id", "source": "product_source"}),
        on="product_id",
        how="left",
    )

    df = df.with_columns([
        pl.col("source").fill_null("rakuten"),
        pl.when(pl.col("brand").is_null() | (pl.col("brand") == ""))
          .then(pl.lit("Unknown")).otherwise(pl.col("brand")).alias("brand"),
        pl.when(pl.col("model").is_null() | (pl.col("model") == ""))
          .then(pl.lit("Unknown")).otherwise(pl.col("model")).alias("model"),
    ]).with_columns(
        (pl.col("brand") + " " + pl.col("model")).alias("display_name")
    )

    return df


# ── Helpers ──────────────────────────────────────────────────────────────────────
BASE_LAYOUT: dict = dict(
    paper_bgcolor="#0d0d0d",
    plot_bgcolor="#111111",
    font=dict(family="IBM Plex Mono, monospace", color="#555", size=10),
    margin=dict(l=50, r=30, t=30, b=45),
    xaxis=dict(gridcolor="#161616", linecolor="#1e1e1e", tickcolor="#1e1e1e", zerolinecolor="#1e1e1e"),
    yaxis=dict(gridcolor="#161616", linecolor="#1e1e1e", tickcolor="#1e1e1e", zerolinecolor="#1e1e1e"),
)

SOURCE_COLORS: dict[str, str] = {"rakuten": "#4fc3f7", "pckoubou": "#ce93d8"}

PALETTE: list[str] = [
    "#4fc3f7", "#81c784", "#ffb74d", "#ef9a9a",
    "#ce93d8", "#80cbc4", "#f48fb1", "#bcaaa4",
]


def fmt_yen(v: float) -> str:
    return f"¥{int(v):,}"


def hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def compute_stats(df: pl.DataFrame) -> dict:
    prices = df["price"].drop_nulls()
    if len(prices) == 0:
        return {}
    arr = prices.to_numpy()

    # 7-day change: compare most-recent 7d to previous 7d
    max_ts = df["scraped_at"].max()
    cutoff = max_ts - timedelta(days=7)
    recent_prices = df.filter(pl.col("scraped_at") >= cutoff)["price"].drop_nulls()
    prior_prices  = df.filter(pl.col("scraped_at") < cutoff)["price"].drop_nulls()

    if len(recent_prices) > 0 and len(prior_prices) > 0:
        recent_med = float(recent_prices.median())
        prior_med  = float(prior_prices.median())
        change_7d  = (recent_med - prior_med) / prior_med * 100
    else:
        recent_med = float(np.median(arr))
        change_7d  = None

    return {
        "count":       len(arr),
        "median":      float(np.median(arr)),
        "mean":        float(np.mean(arr)),
        "current_med": recent_med,
        "change_7d":   change_7d,
        "std":         float(np.std(arr)),
        "p25":         float(np.percentile(arr, 25)),
        "p75":         float(np.percentile(arr, 75)),
        "min":         float(np.min(arr)),
        "max":         float(np.max(arr)),
    }


def change_class(pct: float | None) -> str:
    if pct is None:
        return "flat"
    if abs(pct) < 0.5:
        return "flat"
    return "up" if pct > 0 else "down"


def fmt_change(pct: float | None) -> str:
    if pct is None:
        return "—"
    if abs(pct) < 0.5:
        return "→ flat"
    arrow = "↑" if pct > 0 else "↓"
    return f"{arrow} {pct:+.1f}%  /7d"


# ── Render functions ─────────────────────────────────────────────────────────────
def render_model_cards(df: pl.DataFrame, display_names: list[str]) -> None:
    """Quick-glance cards showing current median + 7-day change for each model."""
    cards_html = ""
    for name in display_names:
        model_df = df.filter(pl.col("display_name") == name)
        s = compute_stats(model_df)
        if not s:
            continue
        cls = change_class(s["change_7d"])
        change_str = fmt_change(s["change_7d"])
        cards_html += f"""
        <div class="model-card">
          <div class="mc-label">{name}</div>
          <div class="mc-price">{fmt_yen(s['current_med'])}</div>
          <div class="mc-change {cls}">{change_str}</div>
          <div class="mc-count">{s['count']:,} observations</div>
        </div>"""

    if cards_html:
        st.markdown(f'<div class="cards-grid">{cards_html}</div>', unsafe_allow_html=True)


def render_stat_cards(s: dict, ml_price: float | None = None) -> None:
    cls = change_class(s["change_7d"])
    change_str = fmt_change(s["change_7d"])
    ml_val = fmt_yen(ml_price) if ml_price is not None else "—"

    st.markdown(f"""
    <div class="stat-row">
      <div class="stat-cell">
        <div class="stat-label">Median price</div>
        <div class="stat-val">{fmt_yen(s['median'])}</div>
        <div class="stat-sub">50th percentile</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Mean price</div>
        <div class="stat-val">{fmt_yen(s['mean'])}</div>
        <div class="stat-sub">average listing</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">7-day change</div>
        <div class="stat-val {cls}">{change_str}</div>
        <div class="stat-sub">vs prior 7 days</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Std deviation</div>
        <div class="stat-val">{fmt_yen(s['std'])}</div>
        <div class="stat-sub">price spread</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Typical range</div>
        <div class="stat-val" style="font-size:1rem;">{fmt_yen(s['p25'])} – {fmt_yen(s['p75'])}</div>
        <div class="stat-sub">P25 → P75</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Sample size</div>
        <div class="stat-val">{s['count']:,}</div>
        <div class="stat-sub">price observations</div>
      </div>
      <div class="stat-cell ml">
        <div class="stat-label">ML prediction</div>
        <div class="stat-val ml">{ml_val}</div>
        <div class="stat-sub">coming soon</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_trend_chart(df: pl.DataFrame, color: str) -> None:
    """Price scatter cloud + daily median line + IQR shaded band."""
    if df.is_empty():
        st.markdown('<div class="no-data">no data</div>', unsafe_allow_html=True)
        return

    daily = (
        df.with_columns(pl.col("scraped_at").dt.date().alias("d"))
        .group_by("d")
        .agg([
            pl.col("price").median().alias("med"),
            pl.col("price").mean().alias("mean"),
            pl.col("price").quantile(0.25).alias("p25"),
            pl.col("price").quantile(0.75).alias("p75"),
            pl.col("price").count().alias("n"),
        ])
        .sort("d")
        .drop_nulls("med")
    )

    if daily.is_empty():
        st.markdown('<div class="no-data">insufficient data</div>', unsafe_allow_html=True)
        return

    dates = daily["d"].to_list()
    fig = go.Figure()

    # IQR band
    fig.add_trace(go.Scatter(
        x=dates + dates[::-1],
        y=daily["p75"].to_list() + daily["p25"].to_list()[::-1],
        fill="toself",
        fillcolor=hex_rgba(color, 0.08),
        line=dict(color="rgba(0,0,0,0)"),
        hoverinfo="skip",
        name="P25–P75 range",
        showlegend=True,
    ))

    # Mean line (subtle, dotted)
    fig.add_trace(go.Scatter(
        x=dates,
        y=daily["mean"].to_list(),
        mode="lines",
        line=dict(color=color, width=1.5, dash="dot"),
        opacity=0.45,
        name="Mean",
        hovertemplate="Mean: <b>¥%{y:,.0f}</b><extra></extra>",
    ))

    # Median line
    fig.add_trace(go.Scatter(
        x=dates,
        y=daily["med"].to_list(),
        mode="lines+markers",
        line=dict(color=color, width=2),
        marker=dict(size=4, color=color, line=dict(color="#0d0d0d", width=1)),
        name="Median",
        customdata=daily["n"].to_list(),
        hovertemplate="Median: <b>¥%{y:,.0f}</b>  ·  n=%{customdata}<extra></extra>",
    ))

    layout = {**BASE_LAYOUT, "margin": dict(l=50, r=20, t=20, b=40)}
    fig.update_layout(
        **layout,
        height=260,
        showlegend=True,
        hovermode="x unified",
        legend=dict(orientation="h", x=0, y=1.08, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_yaxes(tickprefix="¥", tickformat=",", gridcolor="#161616", linecolor="#1e1e1e")
    fig.update_xaxes(tickformat="%b %d", tickangle=-20)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_distribution_chart(df: pl.DataFrame, color: str) -> None:
    """Clean histogram with median marker."""
    prices = df["price"].drop_nulls().to_numpy()
    if len(prices) < 5:
        st.markdown('<div class="no-data">insufficient data</div>', unsafe_allow_html=True)
        return

    median_val = float(np.median(prices))
    bin_count = min(40, max(10, len(prices) // 4))

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=prices,
        nbinsx=bin_count,
        name="Listings",
        marker_color=color,
        marker_line_color="#0d0d0d",
        marker_line_width=1,
        opacity=0.6,
        hovertemplate="¥%{x:,.0f}<br>Count: %{y}<extra></extra>",
    ))
    fig.add_vline(
        x=median_val,
        line_width=1.5,
        line_dash="dash",
        line_color="#555",
        annotation_text=f"median  {fmt_yen(median_val)}",
        annotation_font=dict(color="#666", size=10, family="IBM Plex Mono"),
        annotation_position="top right",
    )

    layout = {**BASE_LAYOUT, "margin": dict(l=50, r=20, t=20, b=40)}
    fig.update_layout(**layout, height=220, showlegend=False, bargap=0.04)
    fig.update_xaxes(tickprefix="¥", tickformat=",")
    fig.update_yaxes(title_text="count")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_spec_breakdown(df: pl.DataFrame) -> None:
    """Median price by RAM, CPU gen, and SSD — one bar chart each."""
    spec_configs = [("memory", "RAM"), ("cpu_gen", "CPU Generation"), ("ssd", "SSD")]
    available = [
        (col, label) for col, label in spec_configs
        if col in df.columns and df[col].drop_nulls().n_unique() >= 2
    ]
    if not available:
        st.markdown('<div class="no-data">no spec data available</div>', unsafe_allow_html=True)
        return

    cols = st.columns(len(available))
    for container, (spec_col, label) in zip(cols, available):
        agg = (
            df.filter(pl.col(spec_col).is_not_null())
            .group_by(spec_col)
            .agg([
                pl.col("price").median().alias("median"),
                pl.col("price").count().alias("n"),
            ])
            .sort("median")
        )
        if agg.is_empty():
            continue

        labels = agg[spec_col].cast(pl.Utf8).to_list()
        medians = agg["median"].to_list()
        counts = agg["n"].to_list()

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=labels,
            x=medians,
            orientation="h",
            marker_color="#4fc3f7",
            marker_line_color="#0d0d0d",
            marker_line_width=1,
            opacity=0.7,
            customdata=counts,
            hovertemplate="<b>%{y}</b><br>Median: ¥%{x:,.0f}<br>n = %{customdata}<extra></extra>",
        ))

        bar_layout = {
            **BASE_LAYOUT,
            "margin": dict(l=70, r=60, t=35, b=30),
        }
        fig.update_layout(
            **bar_layout,
            height=max(160, len(agg) * 44 + 60),
            title=dict(text=label, font=dict(size=11, color="#555"), x=0, y=0.98),
            showlegend=False,
        )
        fig.update_xaxes(tickprefix="¥", tickformat=",", title_text=None)
        fig.update_yaxes(tickfont=dict(size=10))
        with container:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_listings_table(df: pl.DataFrame) -> None:
    """Sortable listings table with a vs-median column."""
    median_price = float(df["price"].median())

    wanted = ["item_name", "price", "memory", "cpu", "ssd", "shop_name", "scraped_at", "item_url"]
    select_cols = [c for c in wanted if c in df.columns and c != "item_url"]

    display = (
        df.select(select_cols)
        .with_columns(
            ((pl.col("price") - median_price) / median_price * 100).round(1).alias("vs median %")
        )
        .sort("price")
    )

    col_config: dict = {
        "item_name":    st.column_config.TextColumn("Listing", width="large"),
        "price":        st.column_config.NumberColumn("Price", format="¥%d"),
        "vs median %":  st.column_config.NumberColumn("vs Median", format="%.1f%%", help="% above/below median price for this model"),
        "memory":       st.column_config.TextColumn("RAM"),
        "cpu":          st.column_config.TextColumn("CPU", width="medium"),
        "ssd":          st.column_config.TextColumn("SSD"),
        "shop_name":    st.column_config.TextColumn("Shop"),
        "scraped_at":   st.column_config.DatetimeColumn("Scraped", format="YYYY-MM-DD"),
    }
    if "item_url" in df.columns:
        display = display.with_columns(df.sort("price")["item_url"])
        col_config["item_url"] = st.column_config.LinkColumn("Link", display_text="↗")

    st.dataframe(
        display,
        column_config=col_config,
        hide_index=True,
        use_container_width=True,
    )


def render_overview_trend(df: pl.DataFrame, display_names: list[str]) -> None:
    """All models on one chart — median price over time."""
    fig = go.Figure()
    for i, name in enumerate(display_names):
        color = PALETTE[i % len(PALETTE)]
        trend = (
            df.filter(pl.col("display_name") == name)
            .with_columns(pl.col("scraped_at").dt.date().alias("d"))
            .group_by("d")
            .agg(pl.col("price").median().alias("med"))
            .sort("d")
            .drop_nulls("med")
        )
        if trend.is_empty():
            continue
        fig.add_trace(go.Scatter(
            x=trend["d"].to_list(),
            y=trend["med"].to_list(),
            name=name,
            mode="lines",
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{name}</b><br>%{{x}}<br>¥%{{y:,.0f}}<extra></extra>",
        ))

    fig.update_layout(
        **BASE_LAYOUT,
        height=340,
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", x=0, y=1.06, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_yaxes(tickprefix="¥", tickformat=",", gridcolor="#161616", linecolor="#1e1e1e")
    fig.update_xaxes(tickformat="%b %d", tickangle=-20)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Load ─────────────────────────────────────────────────────────────────────────
with st.spinner(""):
    raw_df = fetch_data()

if raw_df.is_empty():
    st.error("No data from Supabase — check credentials in .streamlit/secrets.toml")
    st.stop()


# ── Sidebar ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="app-eyebrow">PC Market Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div class="app-title">Price Analyzer</div>', unsafe_allow_html=True)

    all_brands = sorted(raw_df["brand"].drop_nulls().unique().to_list())
    selected_brands = st.multiselect("Brand", options=all_brands, default=all_brands)

    scoped = raw_df.filter(pl.col("brand").is_in(selected_brands)) if selected_brands else raw_df
    all_names = sorted(scoped["display_name"].drop_nulls().unique().to_list())
    top_names = (
        scoped.filter(pl.col("display_name").is_not_null())
        .group_by("display_name")
        .agg(pl.len().alias("obs"))
        .sort("obs", descending=True)
        .head(5)["display_name"]
        .to_list()
    )
    selected_names = st.multiselect("Model", options=all_names, default=top_names)

    st.markdown("---")

    today = datetime.now(timezone.utc).date()
    date_start = st.date_input("From", value=today - timedelta(days=30))
    date_end   = st.date_input("To",   value=today)

    st.markdown("---")

    source_opts = sorted(raw_df["source"].drop_nulls().unique().to_list())
    selected_sources = st.multiselect("Source", options=source_opts, default=source_opts)

    active_only = st.checkbox("Active listings only", value=False)

    st.markdown("---")

    if st.button("↺  Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        '<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.6rem;color:#222;margin-top:0.75rem;">'
        'Cache 5 min · products + price_history</div>',
        unsafe_allow_html=True,
    )


# ── Filters ──────────────────────────────────────────────────────────────────────
filtered = raw_df.filter(
    (pl.col("scraped_at").dt.date() >= date_start) &
    (pl.col("scraped_at").dt.date() <= date_end)
)
if selected_sources:
    filtered = filtered.filter(pl.col("source").is_in(selected_sources))
if active_only and "is_active" in filtered.columns:
    filtered = filtered.filter(pl.col("is_active") == True)  # noqa: E712
filtered = filtered.filter(pl.col("price").is_not_null())

if filtered.is_empty() or not selected_names:
    st.markdown('<div class="no-data">No data for the selected filters.</div>', unsafe_allow_html=True)
    st.stop()


# ── Overview ─────────────────────────────────────────────────────────────────────
render_model_cards(filtered, selected_names)

st.markdown('<div class="sec-label">Median price over time — all models</div>', unsafe_allow_html=True)
render_overview_trend(filtered, selected_names)


# ── Per-model ────────────────────────────────────────────────────────────────────
for i, name in enumerate(selected_names):
    color = PALETTE[i % len(PALETTE)]
    mdf = filtered.filter(pl.col("display_name") == name)

    st.markdown('<div class="model-divider">', unsafe_allow_html=True)
    st.markdown(f'<div class="model-name">{name}</div>', unsafe_allow_html=True)

    n_products = mdf["product_id"].drop_nulls().n_unique() if "product_id" in mdf.columns else 0
    st.markdown(
        f'<div class="model-meta">'
        f'{len(mdf):,} price observations · {n_products} unique listings'
        f' · {date_start} → {date_end}'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    if mdf.is_empty():
        st.markdown('<div class="no-data">no data in this range</div>', unsafe_allow_html=True)
        continue

    s = compute_stats(mdf)
    if s:
        render_stat_cards(s, ml_price=None)

    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.markdown('<div class="sec-label">Price trend</div>', unsafe_allow_html=True)
        render_trend_chart(mdf, color)

    with col_r:
        st.markdown('<div class="sec-label">Price distribution</div>', unsafe_allow_html=True)
        render_distribution_chart(mdf, color)

    st.markdown('<div class="sec-label">Price by spec</div>', unsafe_allow_html=True)
    render_spec_breakdown(mdf)

    st.markdown('<div class="sec-label">Listings</div>', unsafe_allow_html=True)
    render_listings_table(mdf)
