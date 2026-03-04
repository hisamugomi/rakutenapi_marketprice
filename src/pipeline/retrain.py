"""Automated model retraining pipeline."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from src.models.evaluation import mae, mape, r2, rmse
from src.models.price_model import LightGBMPriceModel
from src.models.train import load_training_data

logger = logging.getLogger(__name__)

RANDOM_SEED = 42
TRAIN_RATIO = 0.8
DEFAULT_MODEL_PATH = Path("models/price_model.joblib")
DEFAULT_METRICS_PATH = Path("models/metrics.json")

_RAW_COLS = ["brand", "cpu_gen", "memory", "ssd", "hdd", "display_size", "os", "source"]


class RetrainPipeline:
    """Manages the full model retraining cycle.

    Usage::

        pipeline = RetrainPipeline()
        metrics = pipeline.run(supabase)
        print(metrics)  # {"mae": 1234, "rmse": 2345, ...}
    """

    def __init__(
        self,
        model_path: Path = DEFAULT_MODEL_PATH,
        metrics_path: Path = DEFAULT_METRICS_PATH,
        use_optuna: bool = False,
        n_trials: int = 30,
    ) -> None:
        """Initialise the retraining pipeline.

        Args:
            model_path: Where to save the trained model artifact.
            metrics_path: Where to save the JSON metrics report.
            use_optuna: Whether to run Optuna hyperparameter search before
                training. If False, use default LightGBMPriceModel params.
            n_trials: Number of Optuna trials (only used when use_optuna=True).
        """
        self.model_path = Path(model_path)
        self.metrics_path = Path(metrics_path)
        self.use_optuna = use_optuna
        self.n_trials = n_trials

    def _load_previous_mae(self) -> float | None:
        """Load the MAE from the previous metrics file, if it exists.

        Returns:
            Previous MAE value, or None if no metrics file exists.
        """
        if not self.metrics_path.exists():
            return None
        try:
            with self.metrics_path.open() as f:
                data = json.load(f)
            return float(data["mae"])
        except (KeyError, ValueError, json.JSONDecodeError):
            return None

    def run(self, supabase) -> dict:
        """Full pipeline: load data → (optionally optimize) → train → evaluate → save.

        Args:
            supabase: Authenticated Supabase client (passed through to
                load_training_data).

        Returns:
            dict with keys: model_version, mae, rmse, mape, r2, n_train, n_test,
            improved (bool — True if MAE improved over the previous model).
        """
        # ── Load data ─────────────────────────────────────────────────────────
        df = load_training_data(supabase)
        available = [c for c in _RAW_COLS if c in df.columns]

        n = len(df)
        n_train = int(n * TRAIN_RATIO)
        shuffled = df.sample(fraction=1.0, seed=RANDOM_SEED)
        X_train = shuffled.select(available).head(n_train)
        y_train = shuffled["price"].cast(pl.Int32).head(n_train)
        X_test = shuffled.select(available).tail(n - n_train)
        y_test = shuffled["price"].cast(pl.Int32).tail(n - n_train)

        logger.info("Train: %d rows  Test: %d rows", n_train, n - n_train)

        # ── Select model ──────────────────────────────────────────────────────
        if self.use_optuna:
            from src.models.optimizer import LGBMOptimizer

            logger.info("Running Optuna with %d trials ...", self.n_trials)
            optimizer = LGBMOptimizer(n_trials=self.n_trials)
            optimizer.optimize(X_train, y_train)
            model = optimizer.get_best_model()
        else:
            model = LightGBMPriceModel()

        # ── Fit ───────────────────────────────────────────────────────────────
        model.fit(X_train, y_train)

        # ── Evaluate ──────────────────────────────────────────────────────────
        y_pred = model.predict(X_test)
        mae_val = mae(y_test.cast(pl.Float64), y_pred.cast(pl.Float64))
        rmse_val = rmse(y_test.cast(pl.Float64), y_pred.cast(pl.Float64))
        mape_val = mape(y_test.cast(pl.Float64), y_pred.cast(pl.Float64))
        r2_val = r2(y_test.cast(pl.Float64), y_pred.cast(pl.Float64))

        logger.info(
            "Test metrics — MAE: %.0f  RMSE: %.0f  MAPE: %.2f%%  R²: %.4f",
            mae_val,
            rmse_val,
            mape_val,
            r2_val,
        )

        # ── Compare with previous model ───────────────────────────────────────
        previous_mae = self._load_previous_mae()
        if previous_mae is not None:
            improved = mae_val < previous_mae
            direction = "improved" if improved else "degraded"
            logger.info(
                "Model %s: MAE %.0f → %.0f (delta=%.0f)",
                direction,
                previous_mae,
                mae_val,
                previous_mae - mae_val,
            )
        else:
            logger.info("No previous model found — treating as first run.")
            improved = True

        # ── Save model ────────────────────────────────────────────────────────
        model.save(self.model_path)

        # ── Save metrics ──────────────────────────────────────────────────────
        metrics: dict = {
            "model_version": model.MODEL_VERSION,
            "mae": round(mae_val, 2),
            "rmse": round(rmse_val, 2),
            "mape": round(mape_val, 4),
            "r2": round(r2_val, 6),
            "n_train": n_train,
            "n_test": n - n_train,
            "improved": improved,
            "trained_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with self.metrics_path.open("w") as f:
            json.dump(metrics, f, indent=2)
        logger.info("Metrics saved to %s", self.metrics_path)

        return metrics
