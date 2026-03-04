"""Reusable table and stat card components for the dashboard."""

from __future__ import annotations

import polars as pl
import streamlit as st

from src.dashboard.components.charts import fmt_yen

_TH_STYLE = (
    "text-align:left; padding:0.5rem 0.75rem; font-family:'IBM Plex Mono',monospace; "
    "font-size:0.65rem; letter-spacing:0.12em; text-transform:uppercase; "
    "color:#555; font-weight:400;"
)


def render_stat_cards(s: dict) -> None:
    """Render a 7-card statistics grid.

    Args:
        s: Dict with keys: count, mean, median, std, min, max, p25, p75.
    """
    st.markdown(
        f"""
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">Listings 搭載数</div>
        <div class="stat-value">{s['count']}<span class="stat-unit"> items</span></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Median 中央価格</div>
        <div class="stat-value">{fmt_yen(s['median'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Mean 平均価格</div>
        <div class="stat-value">{fmt_yen(s['mean'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">sd 分散</div>
        <div class="stat-value">{fmt_yen(s['std'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">25%</div>
        <div class="stat-value">{fmt_yen(s['p25'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">75%</div>
        <div class="stat-value">{fmt_yen(s['p75'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Range　最小から最大</div>
        <div class="stat-value">{fmt_yen(s['min'])} <span class="stat-unit">→</span> {fmt_yen(s['max'])}</div>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_listings_table(df: pl.DataFrame) -> None:
    """HTML listings table with clickable URLs, sorted by price ascending.

    Args:
        df: Listings DataFrame. Expected columns: itemName, itemPrice, cpu,
            memory, ssd, shopName, scraped_at, itemUrl, source.
    """
    cols = ["itemName", "itemPrice", "cpu", "memory", "ssd", "shopName", "scraped_at", "itemUrl", "source"]
    available = [c for c in cols if c in df.columns]
    display = (
        df.select(available)
        .sort("itemPrice", descending=False)
        .with_columns(
            pl.col("itemPrice")
            .map_elements(lambda x: f"¥{x:,}" if x else "—", return_dtype=pl.Utf8)
            .alias("Price"),
            pl.col("scraped_at").dt.strftime("%Y-%m-%d").alias("Scraped"),
        )
    )

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
            <th style="{_TH_STYLE}">Listing</th>
            <th style="{_TH_STYLE}">Price</th>
            <th style="{_TH_STYLE}">CPU</th>
            <th style="{_TH_STYLE}">RAM</th>
            <th style="{_TH_STYLE}">SSD</th>
            <th style="{_TH_STYLE}">Shop</th>
            <th style="{_TH_STYLE}">Scraped</th>
            <th style="{_TH_STYLE}">Link</th>
          </tr>
        </thead>
        <tbody style="color:#c0c0c0;">
          {rows_html}
        </tbody>
      </table>
    </div>"""

    st.markdown(table_html, unsafe_allow_html=True)


def render_predictions_table(df: pl.DataFrame) -> None:
    """Table showing top 20 best deals: where predicted price > actual.

    Sorted by diff_pct descending (most underpriced first). Includes
    clickable item links.

    Args:
        df: DataFrame with columns: item_name, itemPrice, predicted_price,
            model_version, source, item_url (optional).
    """
    if df.is_empty():
        st.markdown('<div class="no-data">— no predictions available —</div>', unsafe_allow_html=True)
        return

    required = {"item_name", "itemPrice", "predicted_price"}
    if not required.issubset(df.columns):
        st.warning(f"Missing columns for predictions table: {required - set(df.columns)}")
        return

    display = (
        df.filter(pl.col("itemPrice").is_not_null() & pl.col("predicted_price").is_not_null())
        .with_columns(
            (
                (pl.col("predicted_price").cast(pl.Float64) - pl.col("itemPrice").cast(pl.Float64))
                / pl.col("itemPrice").cast(pl.Float64)
                * 100
            )
            .round(1)
            .alias("diff_pct")
        )
        .sort("diff_pct", descending=True)
        .head(20)
    )

    rows_html = ""
    for row in display.iter_rows(named=True):
        url = row.get("item_url") or "#"
        diff = row.get("diff_pct", 0.0) or 0.0
        diff_color = "#81c784" if diff > 0 else "#ef9a9a"
        diff_str = f"{diff:+.1f}%"
        rows_html += f"""
        <tr style="border-bottom:1px solid #1a1a1a;">
          <td style="max-width:280px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding:0.4rem 0.75rem;">{row.get('item_name') or '—'}</td>
          <td style="font-family:'IBM Plex Mono',monospace; white-space:nowrap; padding:0.4rem 0.75rem;">¥{int(row['itemPrice']):,}</td>
          <td style="font-family:'IBM Plex Mono',monospace; white-space:nowrap; padding:0.4rem 0.75rem;">¥{int(row['predicted_price']):,}</td>
          <td style="font-family:'IBM Plex Mono',monospace; white-space:nowrap; padding:0.4rem 0.75rem; color:{diff_color};">{diff_str}</td>
          <td style="white-space:nowrap; padding:0.4rem 0.75rem;">{row.get('source') or '—'}</td>
          <td style="padding:0.4rem 0.75rem;"><a href="{url}" target="_blank" style="color:#4fc3f7; text-decoration:none; font-family:'IBM Plex Mono',monospace; font-size:0.75rem;">↗ open</a></td>
        </tr>"""

    table_html = f"""
    <div style="overflow-x:auto; margin-top:0.5rem;">
      <table style="width:100%; border-collapse:collapse; font-size:0.82rem;">
        <thead>
          <tr style="border-bottom:1px solid #2a2a2a;">
            <th style="{_TH_STYLE}">Listing</th>
            <th style="{_TH_STYLE}">Actual Price</th>
            <th style="{_TH_STYLE}">Predicted</th>
            <th style="{_TH_STYLE}">Diff %</th>
            <th style="{_TH_STYLE}">Source</th>
            <th style="{_TH_STYLE}">Link</th>
          </tr>
        </thead>
        <tbody style="color:#c0c0c0;">
          {rows_html}
        </tbody>
      </table>
    </div>"""

    st.markdown(table_html, unsafe_allow_html=True)
