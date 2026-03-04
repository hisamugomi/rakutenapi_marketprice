"""Optuna hyperparameter optimizer for LightGBMPriceModel."""

from __future__ import annotations

import logging

import optuna
import polars as pl
from sklearn.model_selection import cross_val_score

from src.models.price_model import LightGBMPriceModel

logger = logging.getLogger(__name__)

optuna.logging.set_verbosity(optuna.logging.WARNING)


class LGBMOptimizer:
    """Runs an Optuna study to find optimal LightGBM hyperparameters.

    Uses cross-validation (neg_mean_absolute_error) to evaluate each trial.
    After optimization, provides a fitted model with the best params.

    Usage::

        optimizer = LGBMOptimizer(n_trials=50, cv_folds=3)
        best_params = optimizer.optimize(X_train, y_train)
        model = optimizer.get_best_model()
        model.fit(X_train, y_train)
    """

    def __init__(
        self,
        n_trials: int = 50,
        cv_folds: int = 3,
        random_seed: int = 42,
    ) -> None:
        """Initialise the optimizer.

        Args:
            n_trials: Number of Optuna trials to run.
            cv_folds: Number of cross-validation folds for each trial.
            random_seed: Random seed for reproducibility.
        """
        self.n_trials = n_trials
        self.cv_folds = cv_folds
        self.random_seed = random_seed
        self._best_params: dict | None = None
        self._study: optuna.Study | None = None

    def optimize(self, X: pl.DataFrame, y: pl.Series) -> dict:
        """Run Optuna study and return best hyperparameters.

        Tunes: num_leaves, learning_rate, n_estimators, colsample_bytree,
               subsample, min_child_samples.

        Args:
            X: Feature DataFrame (same format as LightGBMPriceModel.fit()).
            y: Price series in JPY.

        Returns:
            dict of best hyperparameters.
        """
        y_np = y.cast(pl.Float32).to_numpy()

        def objective(trial: optuna.Trial) -> float:
            params = {
                "num_leaves": trial.suggest_int("num_leaves", 16, 256),
                "learning_rate": trial.suggest_float("learning_rate", 1e-3, 0.3, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 100, 1000),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
            }
            model = LightGBMPriceModel(lgbm_kwargs=params)
            scores = cross_val_score(
                model.pipeline,
                X,
                y_np,
                cv=self.cv_folds,
                scoring="neg_mean_absolute_error",
            )
            return float(-scores.mean())

        self._study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=self.random_seed),
        )
        self._study.optimize(objective, n_trials=self.n_trials)

        self._best_params = self._study.best_params
        logger.info(
            "Optuna study complete: best MAE=%.0f with params=%s",
            self._study.best_value,
            self._best_params,
        )
        return self._best_params

    def get_best_model(self) -> LightGBMPriceModel:
        """Return LightGBMPriceModel initialized with best params (not yet fitted).

        Returns:
            A fresh LightGBMPriceModel configured with the best hyperparameters
            found during optimization.

        Raises:
            RuntimeError: If optimize() has not been called yet.
        """
        if self._best_params is None:
            raise RuntimeError("Call optimize() before get_best_model().")
        return LightGBMPriceModel(lgbm_kwargs=self._best_params)
