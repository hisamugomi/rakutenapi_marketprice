"""Parametric survival model for time-to-sale estimation.

Uses a log-normal distribution fitted on observed listing durations.
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from scipy import stats

logger = logging.getLogger(__name__)


class SurvivalModel:
    """Log-normal parametric survival model for used PC listings.

    Estimates time-to-sale (days from first_seen_at to last_seen_at for
    inactive listings). Censored observations (still active) are handled
    by fitting only on completed sales.

    Usage::

        model = SurvivalModel()
        model.fit(df)  # df has first_seen_at, last_seen_at, is_active cols
        median_days = model.predict_median_time()
        prob_sold_30d = model.predict_survival_at(days=30)
    """

    MODEL_VERSION: str = "1.0.0"

    def __init__(self) -> None:
        """Initialise SurvivalModel (unfitted)."""
        self.mu_: float | None = None
        self.sigma_: float | None = None

    def fit(self, df: pl.DataFrame) -> "SurvivalModel":
        """Fit log-normal distribution on completed sales durations.

        Uses rows where is_active=False (sold/removed). Duration =
        last_seen_at - first_seen_at in days.

        Args:
            df: DataFrame with columns: first_seen_at (datetime),
                last_seen_at (datetime), is_active (bool).

        Returns:
            self, for method chaining.

        Raises:
            ValueError: If no completed sales with positive duration are found.
        """
        completed = df.filter(pl.col("is_active") == False)  # noqa: E712
        if completed.is_empty():
            raise ValueError("No completed sales (is_active=False) found in DataFrame.")

        durations = (
            completed.with_columns(
                (
                    (
                        pl.col("last_seen_at").cast(pl.Datetime)
                        - pl.col("first_seen_at").cast(pl.Datetime)
                    )
                    .dt.total_seconds()
                    / 86_400.0
                ).alias("duration_days")
            )
            .filter(pl.col("duration_days") > 0)["duration_days"]
            .to_numpy()
        )

        if len(durations) == 0:
            raise ValueError("No completed sales with duration > 0 found after filtering.")

        # Fit log-normal: scipy returns (s=sigma, loc, scale=exp(mu))
        sigma, _loc, scale = stats.lognorm.fit(durations, floc=0)
        self.mu_ = float(np.log(scale))
        self.sigma_ = float(sigma)

        logger.info(
            "SurvivalModel fitted on %d completed sales: mu=%.3f sigma=%.3f (median=%.1f days)",
            len(durations),
            self.mu_,
            self.sigma_,
            self.predict_median_time(),
        )
        return self

    def _check_fitted(self) -> None:
        """Raise RuntimeError if model has not been fitted yet."""
        if self.mu_ is None or self.sigma_ is None:
            raise RuntimeError("SurvivalModel has not been fitted. Call fit() first.")

    def predict_median_time(self, X: pl.DataFrame | None = None) -> float:
        """Return median time-to-sale in days (population-level, ignoring X).

        Args:
            X: Ignored. Accepted for API consistency with future item-level models.

        Returns:
            Median days-to-sale for the fitted population.
        """
        self._check_fitted()
        return float(np.exp(self.mu_))

    def predict_survival_at(self, days: int) -> float:
        """Return P(listing still active after ``days`` days).

        Args:
            days: Number of days since the listing was first seen.

        Returns:
            Probability (0.0–1.0) of still being listed after ``days`` days.
        """
        self._check_fitted()
        prob_sold = stats.lognorm.cdf(days, s=self.sigma_, scale=np.exp(self.mu_))
        return float(1.0 - prob_sold)

    def price_sensitivity(self, price: float, market_median: float) -> float:
        """Estimate relative sale speed based on price vs market median.

        A listing priced below median sells faster (multiplier < 1.0).
        A listing priced above median sells slower (multiplier > 1.0).
        Uses square-root scaling: ``multiplier = sqrt(price / market_median)``.

        Args:
            price: Listing price in JPY.
            market_median: Market median price for this model/spec in JPY.

        Returns:
            Speed multiplier. < 1.0 means faster sale, > 1.0 means slower.

        Raises:
            ValueError: If market_median is zero or negative.
        """
        if market_median <= 0:
            raise ValueError(f"market_median must be positive, got {market_median}")
        ratio = price / market_median
        return float(ratio**0.5)

    def save(self, path: Path) -> None:
        """Persist the fitted model to disk via joblib.

        Args:
            path: Destination file path (e.g. ``Path("models/survival_model.joblib")``).
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("SurvivalModel saved to %s", path)

    @classmethod
    def load(cls, path: Path) -> "SurvivalModel":
        """Load a previously saved model.

        Args:
            path: Path to the joblib file produced by :meth:`save`.

        Returns:
            Loaded ``SurvivalModel`` instance.

        Raises:
            TypeError: If the loaded object is not a SurvivalModel.
        """
        model = joblib.load(Path(path))
        if not isinstance(model, cls):
            raise TypeError(f"Expected {cls.__name__}, got {type(model).__name__}")
        logger.info("SurvivalModel loaded from %s", path)
        return model
