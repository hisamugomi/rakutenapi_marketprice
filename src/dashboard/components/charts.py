"""Reusable Plotly chart components for the dashboard."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import polars as pl
import streamlit as st
from plotly.subplots import make_subplots
from scipy import stats

import plotly.graph_objects as go

# ── Shared constants ───────────────────────────────────────────────────────────

PLOTLY_LAYOUT = dict(
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
    font=dict(family="IBM Plex Mono, monospace", color="#888", size=11),
    margin=dict(l=50, r=30, t=40, b=50),
    xaxis=dict(
        gridcolor="#B4B4B4",
        linecolor="#B4B4B4",
        tickcolor="#B4B4B4",
        zerolinecolor="#B4B4B4",
    ),
    yaxis=dict(
        gridcolor="#bbbbbb",
        linecolor="#B4B4B4",
        tickcolor="#B4B4B4",
        zerolinecolor="#B4B4B4",
    ),
)

ACCENT_COLORS: dict[str, str] = {
    "Lenovo L390": "#4fc3f7",
    "Lenovo L580": "#81c784",
    "Lenovo L590": "#ffb74d",
    "Dell Latitude 5300": "#ef9a9a",
    "Dell Latitude 5400": "#f48fb1",
    "Dell Latitude 5490": "#ce93d8",
    "Dell Latitude 5500": "#80cbc4",
    "Dell Latitude 5590": "#bcaaa4",
}

MODEL_QUERY_MAP: dict[str, str] = {
    "Lenovo L390": "L390 -lenovo",
    "Lenovo L580": "L580 -lenovo",
    "Lenovo L590": "L590 -lenovo",
    "Dell Latitude 5300": "Latitude 5300 -dell",
    "Dell Latitude 5400": "Latitude 5400 -dell",
    "Dell Latitude 5490": "Latitude 5490 -dell",
    "Dell Latitude 5500": "Latitude 5500 -dell",
    "Dell Latitude 5590": "Latitude 5590 -dell",
}

SOURCE_COLORS: dict[str, str] = {
    "rakuten": "#4fc3f7",
    "pckoubou": "#ce93d8",
}


def fmt_yen(value: float) -> str:
    """Format a numeric value as a yen price string."""
    return f"¥{int(value):,}"


# ── Chart components ───────────────────────────────────────────────────────────


def render_trend_chart(df: pl.DataFrame, model: str, color: str) -> None:
    """Median price per nightly run + listing count on secondary axis.

    When the dataframe contains multiple sources, renders one median line per
    source using SOURCE_COLORS so Rakuten and PC Koubou can be compared directly.

    Args:
        df: Filtered listings DataFrame.
        model: Model name (used for display only).
        color: Fallback accent colour hex string.
    """
    if df.is_empty():
        st.markdown('<div class="no-data">— no data —</div>', unsafe_allow_html=True)
        return

    sources_present = df["source"].unique().to_list() if "source" in df.columns else ["rakuten"]
    multi_source = len(sources_present) > 1

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if multi_source:
        all_counts: list[int] = []
        all_dates: list = []

        for src in sorted(sources_present):
            src_color = SOURCE_COLORS.get(src, color)
            src_df = df.filter(pl.col("source") == src)

            trend = (
                src_df.with_columns(pl.col("scraped_at").dt.date().alias("run_date"))
                .group_by("run_date")
                .agg(
                    [
                        pl.col("itemPrice").median().alias("median_price"),
                        pl.col("itemPrice").count().alias("listing_count"),
                    ]
                )
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
                    line=dict(color=src_color, width=4),
                    marker=dict(size=5, color=src_color, line=dict(color="#0d0d0d", width=1)),
                ),
                secondary_y=False,
            )

        if all_dates:
            count_by_date: dict = defaultdict(int)
            for d, c in zip(all_dates, all_counts):
                count_by_date[d] += c
            sorted_dates = sorted(count_by_date)
            fig.add_trace(
                go.Bar(
                    x=sorted_dates,
                    y=[count_by_date[d] for d in sorted_dates],
                    name="Listing count (total)",
                    marker_color="#b3b3b3",
                    marker_line_color="#b3b3b3",
                    marker_line_width=1,
                    opacity=0.9,
                ),
                secondary_y=True,
            )

    else:
        trend = (
            df.with_columns(pl.col("scraped_at").dt.date().alias("run_date"))
            .group_by("run_date")
            .agg(
                [
                    pl.col("itemPrice").median().alias("median_price"),
                    pl.col("itemPrice").mean().alias("mean_price"),
                    pl.col("itemPrice").count().alias("listing_count"),
                ]
            )
            .sort("run_date")
            .drop_nulls("median_price")
        )

        if trend.is_empty():
            st.markdown(
                '<div class="no-data">— insufficient data for trend —</div>',
                unsafe_allow_html=True,
            )
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
                marker_color="#b3b3b3",
                marker_line_color="#2a2a2a",
                marker_line_width=1,
                opacity=0.7,
            ),
            secondary_y=True,
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=mean_prices,
                name="Mean price (平均価格)",
                mode="lines",
                line=dict(color=color, width=3, dash="dot"),
                opacity=0.4,
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=median_prices,
                name="Median price (中央価格)",
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
            x=0,
            y=1.12,
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
        title_text="Listings 搭載数",
        secondary_y=True,
        gridcolor="rgba(0,0,0,0)",
        linecolor="#b4b3b3",
        tickfont=dict(color="#444"),
        title_font=dict(color="#444"),
    )
    fig.update_xaxes(tickformat="%b %d", tickangle=-30)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_distribution_chart(df: pl.DataFrame, color: str) -> None:
    """Histogram + fitted normal curve.

    Args:
        df: Filtered listings DataFrame (must contain ``itemPrice``).
        color: Accent colour hex string.
    """
    prices = df["itemPrice"].drop_nulls().to_numpy()
    if len(prices) < 5:
        st.markdown(
            '<div class="no-data">— insufficient data for distribution —</div>',
            unsafe_allow_html=True,
        )
        return

    mu, sigma = float(np.mean(prices)), float(np.std(prices))
    x_range = np.linspace(mu - 3.5 * sigma, mu + 3.5 * sigma, 300)
    pdf = stats.norm.pdf(x_range, mu, sigma)
    bin_count = min(30, max(10, len(prices) // 5))
    bin_width = (prices.max() - prices.min()) / bin_count
    pdf_scaled = pdf * len(prices) * bin_width

    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=prices,
            nbinsx=bin_count,
            name="Listings",
            marker_color=color,
            marker_line_color="#0d0d0d",
            marker_line_width=1,
            opacity=0.55,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_range,
            y=pdf_scaled,
            name=f"Normal fit  μ={fmt_yen(mu)}  σ={fmt_yen(sigma)}",
            mode="lines",
            line=dict(color=color, width=2),
        )
    )
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
            x=0,
            y=1.12,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        bargap=0.05,
    )
    fig.update_xaxes(tickprefix="¥", tickformat=",")
    fig.update_yaxes(title_text="Count")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_all_models_trend(df: pl.DataFrame) -> None:
    """One median price line per model on a shared time axis.

    Args:
        df: Full filtered listings DataFrame.
    """
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

        fig.add_trace(
            go.Scatter(
                x=trend["run_date"].to_list(),
                y=trend["median_price"].to_list(),
                name=model,
                mode="lines+markers",
                line=dict(color=color, width=3),
                marker=dict(size=4, color=color),
            )
        )

    fig.update_layout(
        **PLOTLY_LAYOUT,
        height=420,
        hovermode="x unified",
        showlegend=True,
        legend=dict(
            orientation="h",
            x=0,
            y=1.12,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    fig.update_yaxes(
        tickprefix="¥",
        tickformat=",",
        title_text="Median Price 中央価格(¥)",
        gridcolor="#b5b5b5",
        linecolor="#2a2a2a",
    )
    fig.update_xaxes(tickformat="%b %d", tickangle=-30)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_prediction_vs_actual_chart(df: pl.DataFrame) -> None:
    """Scatter plot of predicted_price vs actual itemPrice.

    Shows a diagonal identity line (predicted = actual) for reference.
    Points are coloured by source when available.

    Args:
        df: DataFrame with columns: predicted_price, itemPrice,
            item_name (optional), source (optional).
    """
    if df.is_empty() or "predicted_price" not in df.columns or "itemPrice" not in df.columns:
        st.markdown('<div class="no-data">— no prediction data —</div>', unsafe_allow_html=True)
        return

    plot_df = df.filter(
        pl.col("predicted_price").is_not_null() & pl.col("itemPrice").is_not_null()
    )
    if plot_df.is_empty():
        st.markdown('<div class="no-data">— no matched predictions —</div>', unsafe_allow_html=True)
        return

    actual = plot_df["itemPrice"].cast(pl.Float64).to_list()
    predicted = plot_df["predicted_price"].cast(pl.Float64).to_list()
    names = (
        plot_df["item_name"].cast(pl.Utf8).to_list()
        if "item_name" in plot_df.columns
        else [""] * len(actual)
    )
    sources = (
        plot_df["source"].cast(pl.Utf8).fill_null("unknown").to_list()
        if "source" in plot_df.columns
        else ["unknown"] * len(actual)
    )

    fig = go.Figure()

    # ── Identity line ─────────────────────────────────────────────────────────
    price_min = min(min(actual), min(predicted))
    price_max = max(max(actual), max(predicted))
    fig.add_trace(
        go.Scatter(
            x=[price_min, price_max],
            y=[price_min, price_max],
            mode="lines",
            name="predicted = actual",
            line=dict(color="#aaaaaa", width=1, dash="dash"),
            showlegend=True,
        )
    )

    # ── Points per source ─────────────────────────────────────────────────────
    unique_sources = sorted(set(sources))
    for src in unique_sources:
        idx = [i for i, s in enumerate(sources) if s == src]
        src_color = SOURCE_COLORS.get(src, "#888888")
        diff_pcts = [
            round((predicted[i] - actual[i]) / actual[i] * 100, 1) if actual[i] else 0.0
            for i in idx
        ]
        hover = [
            f"{names[i]}<br>Actual: ¥{int(actual[i]):,}<br>"
            f"Predicted: ¥{int(predicted[i]):,}<br>"
            f"Diff: {diff_pcts[j]:+.1f}%"
            for j, i in enumerate(idx)
        ]
        fig.add_trace(
            go.Scatter(
                x=[actual[i] for i in idx],
                y=[predicted[i] for i in idx],
                mode="markers",
                name=src,
                marker=dict(color=src_color, size=7, opacity=0.7),
                text=hover,
                hovertemplate="%{text}<extra></extra>",
            )
        )

    fig.update_layout(
        **PLOTLY_LAYOUT,
        height=420,
        showlegend=True,
        legend=dict(orientation="h", x=0, y=1.12, font=dict(size=10)),
    )
    fig.update_xaxes(tickprefix="¥", tickformat=",", title_text="Actual Price (¥)")
    fig.update_yaxes(tickprefix="¥", tickformat=",", title_text="Predicted Price (¥)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_feature_importance_chart(
    feature_names: list[str], importances: list[float]
) -> None:
    """Horizontal bar chart of LightGBM feature importances, sorted descending.

    Args:
        feature_names: List of feature column names.
        importances: Corresponding importance values from LightGBM.
    """
    if not feature_names or not importances:
        st.markdown('<div class="no-data">— no feature importance data —</div>', unsafe_allow_html=True)
        return

    paired = sorted(zip(importances, feature_names), reverse=True)
    sorted_importances = [p[0] for p in paired]
    sorted_names = [p[1] for p in paired]

    fig = go.Figure(
        go.Bar(
            x=sorted_importances,
            y=sorted_names,
            orientation="h",
            marker_color="#4fc3f7",
            marker_line_color="#0d0d0d",
            marker_line_width=1,
        )
    )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        height=max(250, len(feature_names) * 35),
        showlegend=False,
        yaxis=dict(autorange="reversed"),
    )
    fig.update_xaxes(title_text="Importance (split count)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
