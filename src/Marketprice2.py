import streamlit as st
import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from scipy import stats
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Rakuten Market Price Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
    background-color: #0d0d0d;
    color: #e0e0e0;
  }

  /* Sidebar */
  section[data-testid="stSidebar"] {
    background-color: #111111;
    border-right: 1px solid #2a2a2a;
  }
  section[data-testid="stSidebar"] * {
    color: #c0c0c0 !important;
  }

  /* Main container */
  .main .block-container {
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 1400px;
  }

  /* Model header block */
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
    color: #f0f0f0;
    margin-bottom: 0.1rem;
    letter-spacing: -0.02em;
  }
  .model-subtitle {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: #555;
    margin-bottom: 1.5rem;
  }

  /* Stat cards */
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

  /* Section labels */
  .section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #444;
    margin-bottom: 0.5rem;
    margin-top: 1.5rem;
  }

  /* Dataframe tweaks */
  .stDataFrame {
    border: 1px solid #1e1e1e !important;
  }

  /* App title */
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

  /* No data */
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
""", unsafe_allow_html=True)

# ── Supabase connection ─────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["servicerole"]
    return create_client(url, key)


@st.cache_data(ttl=300)
def fetch_data() -> pl.DataFrame:
    client = get_supabase_client()

    # Paginate — Supabase caps at 1000 rows per request
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        response = (
            client.table("listings_view")
            .select("itemCode, itemName, itemPrice, itemUrl, shopName, brand, cpu, memory, ssd, os, scraped_at, search_query, is_active, source")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not response.data:
            break
        all_rows.extend(response.data)
        if len(response.data) < page_size:
            break
        offset += page_size

    if not all_rows:
        return pl.DataFrame()

    df = pl.DataFrame(all_rows, infer_schema_length=None)

    df = df.with_columns([
        pl.col("itemPrice").cast(pl.Int64, strict=False),
        pl.col("scraped_at").str.to_datetime(strict=False, time_unit="us", time_zone="UTC"),
        pl.col("is_active").cast(pl.Boolean, strict=False),
    ])

    return df


# ── Helpers ─────────────────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="#0d0d0d",
    plot_bgcolor="#111111",
    font=dict(family="IBM Plex Mono, monospace", color="#888", size=11),
    margin=dict(l=50, r=30, t=40, b=50),
    xaxis=dict(
        gridcolor="#1e1e1e",
        linecolor="#2a2a2a",
        tickcolor="#2a2a2a",
        zerolinecolor="#2a2a2a",
    ),
    yaxis=dict(
        gridcolor="#1e1e1e",
        linecolor="#2a2a2a",
        tickcolor="#2a2a2a",
        zerolinecolor="#2a2a2a",
    ),
)

ACCENT_COLORS = {
    # Lenovo
    "Lenovo L390": "#4fc3f7",
    "Lenovo L580": "#81c784",
    "Lenovo L590": "#ffb74d",
    # Dell Latitude
    "Dell Latitude 5300": "#ef9a9a",
    "Dell Latitude 5400": "#f48fb1",
    "Dell Latitude 5490": "#ce93d8",
    "Dell Latitude 5500": "#80cbc4",
    "Dell Latitude 5590": "#bcaaa4",
}

MODEL_QUERY_MAP = {
    # Lenovo
    "Lenovo L390": "L390 -lenovo",
    "Lenovo L580": "L580 -lenovo",
    "Lenovo L590": "L590 -lenovo",
    # Dell Latitude
    "Dell Latitude 5300": "Latitude 5300 -dell",
    "Dell Latitude 5400": "Latitude 5400 -dell",
    "Dell Latitude 5490": "Latitude 5490 -dell",
    "Dell Latitude 5500": "Latitude 5500 -dell",
    "Dell Latitude 5590": "Latitude 5590 -dell",
}

SOURCE_COLORS = {
    "rakuten": "#4fc3f7",
    "pckoubou": "#ce93d8",
}


def fmt_yen(value: float) -> str:
    return f"¥{int(value):,}"


def compute_stats(df: pl.DataFrame) -> dict:
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


def render_stat_cards(s: dict):
    st.markdown(f"""
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">Listings</div>
        <div class="stat-value">{s['count']}<span class="stat-unit"> items</span></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Median</div>
        <div class="stat-value">{fmt_yen(s['median'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Mean</div>
        <div class="stat-value">{fmt_yen(s['mean'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Std Dev</div>
        <div class="stat-value">{fmt_yen(s['std'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">25th pct</div>
        <div class="stat-value">{fmt_yen(s['p25'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">75th pct</div>
        <div class="stat-value">{fmt_yen(s['p75'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Range</div>
        <div class="stat-value">{fmt_yen(s['min'])} <span class="stat-unit">→</span> {fmt_yen(s['max'])}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_trend_chart(df: pl.DataFrame, model: str, color: str):
    """Median price per nightly run + listing count on secondary axis.

    When the dataframe contains multiple sources, renders one median line per
    source using SOURCE_COLORS so Rakuten and PC Koubou can be compared directly.
    """
    if df.is_empty():
        st.markdown('<div class="no-data">— no data —</div>', unsafe_allow_html=True)
        return

    sources_present = df["source"].unique().to_list() if "source" in df.columns else ["rakuten"]
    multi_source = len(sources_present) > 1

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if multi_source:
        # ── Per-source median lines ─────────────────────────────────────────────
        all_counts = []
        all_dates = []

        for src in sorted(sources_present):
            src_color = SOURCE_COLORS.get(src, color)
            src_df = df.filter(pl.col("source") == src)

            trend = (
                src_df.with_columns(pl.col("scraped_at").dt.date().alias("run_date"))
                .group_by("run_date")
                .agg([
                    pl.col("itemPrice").median().alias("median_price"),
                    pl.col("itemPrice").count().alias("listing_count"),
                ])
                .sort("run_date")
                .drop_nulls("median_price")
            )
            if trend.is_empty():
                continue

            dates = trend["run_date"].to_list()
            median_prices = trend["median_price"].to_list()
            counts = trend["listing_count"].to_list()
            all_dates.extend(dates)
            all_counts.extend(counts)

            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=median_prices,
                    name=f"Median ({src})",
                    mode="lines+markers",
                    line=dict(color=src_color, width=2),
                    marker=dict(size=5, color=src_color, line=dict(color="#0d0d0d", width=1)),
                ),
                secondary_y=False,
            )

        # Combined listing count bars
        if all_dates:
            from collections import defaultdict
            count_by_date: dict = defaultdict(int)
            for d, c in zip(all_dates, all_counts):
                count_by_date[d] += c
            sorted_dates = sorted(count_by_date)
            fig.add_trace(
                go.Bar(
                    x=sorted_dates,
                    y=[count_by_date[d] for d in sorted_dates],
                    name="Listing count (total)",
                    marker_color="#1e1e1e",
                    marker_line_color="#2a2a2a",
                    marker_line_width=1,
                    opacity=0.9,
                ),
                secondary_y=True,
            )

    else:
        # ── Single-source behaviour (original) ─────────────────────────────────
        trend = (
            df.with_columns(pl.col("scraped_at").dt.date().alias("run_date"))
            .group_by("run_date")
            .agg([
                pl.col("itemPrice").median().alias("median_price"),
                pl.col("itemPrice").mean().alias("mean_price"),
                pl.col("itemPrice").count().alias("listing_count"),
            ])
            .sort("run_date")
            .drop_nulls("median_price")
        )

        if trend.is_empty():
            st.markdown('<div class="no-data">— insufficient data for trend —</div>', unsafe_allow_html=True)
            return

        dates = trend["run_date"].to_list()
        median_prices = trend["median_price"].to_list()
        mean_prices = trend["mean_price"].to_list()
        counts = trend["listing_count"].to_list()

        fig.add_trace(
            go.Bar(
                x=dates,
                y=counts,
                name="Listing count",
                marker_color="#1e1e1e",
                marker_line_color="#2a2a2a",
                marker_line_width=1,
                opacity=0.9,
            ),
            secondary_y=True,
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=mean_prices,
                name="Mean price",
                mode="lines",
                line=dict(color=color, width=1, dash="dot"),
                opacity=0.4,
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=median_prices,
                name="Median price",
                mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=5, color=color, line=dict(color="#0d0d0d", width=1)),
            ),
            secondary_y=False,
        )

    fig.update_layout(
        **PLOTLY_LAYOUT,
        height=300,
        showlegend=True,
        legend=dict(
            orientation="h",
            x=0, y=1.12,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
    )
    fig.update_yaxes(
        title_text="Price (¥)",
        tickprefix="¥",
        tickformat=",",
        secondary_y=False,
        gridcolor="#1e1e1e",
        linecolor="#2a2a2a",
    )
    fig.update_yaxes(
        title_text="Listings",
        secondary_y=True,
        gridcolor="rgba(0,0,0,0)",
        linecolor="#2a2a2a",
        tickfont=dict(color="#444"),
        title_font=dict(color="#444"),
    )
    fig.update_xaxes(tickformat="%b %d", tickangle=-30)

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_distribution_chart(df: pl.DataFrame, color: str):
    """Histogram + fitted normal curve."""
    prices = df["itemPrice"].drop_nulls().to_numpy()
    if len(prices) < 5:
        st.markdown('<div class="no-data">— insufficient data for distribution —</div>', unsafe_allow_html=True)
        return

    mu, sigma = float(np.mean(prices)), float(np.std(prices))
    x_range = np.linspace(mu - 3.5 * sigma, mu + 3.5 * sigma, 300)
    pdf = stats.norm.pdf(x_range, mu, sigma)
    # Scale PDF to match histogram counts
    bin_count = min(30, max(10, len(prices) // 5))
    bin_width = (prices.max() - prices.min()) / bin_count
    pdf_scaled = pdf * len(prices) * bin_width

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=prices,
        nbinsx=bin_count,
        name="Listings",
        marker_color=color,
        marker_line_color="#0d0d0d",
        marker_line_width=1,
        opacity=0.55,
    ))

    fig.add_trace(go.Scatter(
        x=x_range,
        y=pdf_scaled,
        name=f"Normal fit  μ={fmt_yen(mu)}  σ={fmt_yen(sigma)}",
        mode="lines",
        line=dict(color=color, width=2),
    ))

    # Median line
    fig.add_vline(
        x=float(np.median(prices)),
        line_width=1,
        line_dash="dash",
        line_color="#555",
        annotation_text=f"median {fmt_yen(np.median(prices))}",
        annotation_font=dict(color="#555", size=10, family="IBM Plex Mono"),
        annotation_position="top right",
    )

    fig.update_layout(
        **PLOTLY_LAYOUT,
        height=280,
        showlegend=True,
        legend=dict(
            orientation="h",
            x=0, y=1.12,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        bargap=0.05,
    )
    fig.update_xaxes(tickprefix="¥", tickformat=",")
    fig.update_yaxes(title_text="Count")

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_listings_table(df: pl.DataFrame):
    """Sortable listings table with specs and clickable URLs."""
    cols = ["itemName", "itemPrice", "cpu", "memory", "ssd", "shopName", "scraped_at", "itemUrl", "source"]
    available = [c for c in cols if c in df.columns]
    display = (
        df.select(available)
        .sort("itemPrice", descending=False)
        .with_columns(
            pl.col("itemPrice").map_elements(lambda x: f"¥{x:,}" if x else "—", return_dtype=pl.Utf8).alias("Price"),
            pl.col("scraped_at").dt.strftime("%Y-%m-%d").alias("Scraped"),
        )
    )

    th = "text-align:left; padding:0.5rem 0.75rem; font-family:'IBM Plex Mono',monospace; font-size:0.65rem; letter-spacing:0.12em; text-transform:uppercase; color:#555; font-weight:400;"
    rows_html = ""
    for row in display.iter_rows(named=True):
        url = row.get("itemUrl") or "#"
        rows_html += f"""
        <tr style="border-bottom:1px solid #1a1a1a;">
          <td style="max-width:300px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding:0.4rem 0.75rem;">{row['itemName']}</td>
          <td style="font-family:'IBM Plex Mono',monospace; white-space:nowrap; padding:0.4rem 0.75rem;">{row['Price']}</td>
          <td style="font-family:'IBM Plex Mono',monospace; white-space:nowrap; padding:0.4rem 0.75rem;">{row.get('cpu') or '—'}</td>
          <td style="font-family:'IBM Plex Mono',monospace; white-space:nowrap; padding:0.4rem 0.75rem;">{row.get('memory') or '—'}</td>
          <td style="font-family:'IBM Plex Mono',monospace; white-space:nowrap; padding:0.4rem 0.75rem;">{row.get('ssd') or '—'}</td>
          <td style="white-space:nowrap; padding:0.4rem 0.75rem;">{row.get('shopName') or '—'}</td>
          <td style="font-family:'IBM Plex Mono',monospace; white-space:nowrap; padding:0.4rem 0.75rem;">{row['Scraped'] or '—'}</td>
          <td style="padding:0.4rem 0.75rem;"><a href="{url}" target="_blank" style="color:#4fc3f7; text-decoration:none; font-family:'IBM Plex Mono',monospace; font-size:0.75rem;">↗ open</a></td>
        </tr>"""

    table_html = f"""
    <div style="overflow-x:auto; margin-top:0.5rem;">
      <table style="width:100%; border-collapse:collapse; font-size:0.82rem;">
        <thead>
          <tr style="border-bottom:1px solid #2a2a2a;">
            <th style="{th}">Listing</th>
            <th style="{th}">Price</th>
            <th style="{th}">CPU</th>
            <th style="{th}">RAM</th>
            <th style="{th}">SSD</th>
            <th style="{th}">Shop</th>
            <th style="{th}">Scraped</th>
            <th style="{th}">Link</th>
          </tr>
        </thead>
        <tbody style="color:#c0c0c0;">
          {rows_html}
        </tbody>
      </table>
    </div>"""

    st.markdown(table_html, unsafe_allow_html=True)


def render_all_models_trend(df: pl.DataFrame):
    """One median price line per model on a shared time axis."""
    fig = go.Figure()

    for model, query in MODEL_QUERY_MAP.items():
        color = ACCENT_COLORS[model]
        model_df = df.filter(pl.col("search_query") == query)
        if model_df.is_empty():
            continue

        trend = (
            model_df.with_columns(pl.col("scraped_at").dt.date().alias("run_date"))
            .group_by("run_date")
            .agg(pl.col("itemPrice").median().alias("median_price"))
            .sort("run_date")
            .drop_nulls("median_price")
        )
        if trend.is_empty():
            continue

        fig.add_trace(go.Scatter(
            x=trend["run_date"].to_list(),
            y=trend["median_price"].to_list(),
            name=model,
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=4, color=color),
        ))

    fig.update_layout(
        **PLOTLY_LAYOUT,
        height=420,
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", x=0, y=1.12, font=dict(size=10),
                    bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_yaxes(tickprefix="¥", tickformat=",", title_text="Median Price (¥)",
                     gridcolor="#1e1e1e", linecolor="#2a2a2a")
    fig.update_xaxes(tickformat="%b %d", tickangle=-30)

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Sidebar ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="app-title">Rakuten Market Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div class="app-name">Price Analyzer</div>', unsafe_allow_html=True)

    st.markdown("---")

    # Model selector
    all_models = list(ACCENT_COLORS.keys())
    selected_models = st.multiselect(
        "Models",
        options=all_models,
        default=all_models,
        help="Select which models to display",
    )

    st.markdown("---")

    # Date range
    today = datetime.now(timezone.utc).date()
    default_start = today - timedelta(days=30)

    date_start = st.date_input("From", value=default_start)
    date_end = st.date_input("To", value=today)

    st.markdown("---")

    # Active listings toggle
    active_only = st.checkbox("Active listings only", value=False)

    st.markdown("---")

    # Data source filter
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

    st.markdown(
        '<div style="font-family:\'IBM Plex Mono\',monospace; font-size:0.65rem; color:#333; margin-top:1rem;">'
        'Data refreshes every 5 min<br>Source: Supabase · rakuten_table</div>',
        unsafe_allow_html=True,
    )


# ── Main ─────────────────────────────────────────────────────────────────────────
with st.spinner("Fetching data..."):
    raw_df = fetch_data()

if raw_df.is_empty():
    st.error("No data returned from Supabase. Check your credentials in .streamlit/secrets.toml")
    st.stop()

# Apply date filter
filtered_df = raw_df.filter(
    (pl.col("scraped_at").dt.date() >= date_start) &
    (pl.col("scraped_at").dt.date() <= date_end)
)

if active_only:
    filtered_df = filtered_df.filter(pl.col("is_active") == True)

# Source filter
if selected_sources:
    filtered_df = filtered_df.filter(pl.col("source").is_in(selected_sources))

# Drop nulls on price
filtered_df = filtered_df.filter(pl.col("itemPrice").is_not_null())

# ── Combined all-models trend ────────────────────────────────────────────────────
st.markdown('<div class="section-label">All models — median price trend</div>',
            unsafe_allow_html=True)
render_all_models_trend(filtered_df)

# ── Render per model ─────────────────────────────────────────────────────────────
if not selected_models:
    st.markdown('<div class="no-data">Select at least one model from the sidebar.</div>', unsafe_allow_html=True)
    st.stop()

for model in selected_models:
    color = ACCENT_COLORS[model]
    model_df = filtered_df.filter(pl.col("search_query") == MODEL_QUERY_MAP[model])

    # Model header
    st.markdown(f'<div class="model-header">Model</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="model-title">{model}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="model-subtitle">'
        f'{len(model_df):,} listings · {date_start} → {date_end}'
        f'</div>',
        unsafe_allow_html=True,
    )

    if model_df.is_empty():
        st.markdown('<div class="no-data">— no listings found for this model in the selected date range —</div>', unsafe_allow_html=True)
        continue

    # 1. Stats
    s = compute_stats(model_df)
    if s:
        render_stat_cards(s)

    # 2. Price trend
    st.markdown('<div class="section-label">Price trend over time</div>', unsafe_allow_html=True)
    render_trend_chart(model_df, model, color)

    # 3. Distribution
    st.markdown('<div class="section-label">Price distribution</div>', unsafe_allow_html=True)
    render_distribution_chart(model_df, color)

    # 4. Listings table
    st.markdown('<div class="section-label">Individual listings</div>', unsafe_allow_html=True)
    render_listings_table(model_df)
