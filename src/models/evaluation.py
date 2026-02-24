"""Evaluation metrics for the price prediction model."""

from __future__ import annotations

import polars as pl


def mae(y_true: pl.Series, y_pred: pl.Series) -> float:
    """Mean Absolute Error in JPY."""
    return float((y_true.cast(pl.Float64) - y_pred.cast(pl.Float64)).abs().mean())


def rmse(y_true: pl.Series, y_pred: pl.Series) -> float:
    """Root Mean Squared Error in JPY."""
    diff = y_true.cast(pl.Float64) - y_pred.cast(pl.Float64)
    return float((diff**2).mean() ** 0.5)


def mape(y_true: pl.Series, y_pred: pl.Series) -> float:
    """Mean Absolute Percentage Error (%).

    Rows where y_true is zero are excluded to avoid division by zero.
    """
    y_t = y_true.cast(pl.Float64)
    y_p = y_pred.cast(pl.Float64)
    mask = y_t.abs() > 1e-8
    abs_pct = ((y_t - y_p) / y_t).abs()
    filtered = abs_pct.filter(mask)
    if len(filtered) == 0:
        return float("nan")
    return float(filtered.mean() * 100)


def r2(y_true: pl.Series, y_pred: pl.Series) -> float:
    """Coefficient of determination R²."""
    y_t = y_true.cast(pl.Float64)
    y_p = y_pred.cast(pl.Float64)
    ss_res = float(((y_t - y_p) ** 2).sum())
    ss_tot = float(((y_t - y_t.mean()) ** 2).sum())
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return 1.0 - ss_res / ss_tot


def report(model: object, X: pl.DataFrame, y: pl.Series) -> None:
    """Print a formatted metrics table for the given model and data.

    Args:
        model: Any object with a .predict(X) -> pl.Series method.
        X: Feature DataFrame.
        y: Ground-truth price series.
    """
    y_pred = model.predict(X)  # type: ignore[attr-defined]
    print(f"  MAE:  {mae(y, y_pred):>10,.0f} ¥")
    print(f"  RMSE: {rmse(y, y_pred):>10,.0f} ¥")
    print(f"  MAPE: {mape(y, y_pred):>10.2f} %")
    print(f"  R²:   {r2(y, y_pred):>10.4f}")
