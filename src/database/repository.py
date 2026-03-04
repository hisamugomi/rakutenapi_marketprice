"""Data access layer — typed Repository classes for each Supabase table.

All methods return ``polars.DataFrame``. Raw SQL is never used in business
logic — all queries go through the supabase-py client.
"""

from __future__ import annotations

import logging

import polars as pl

from src.database.client import get_supabase_client

logger = logging.getLogger(__name__)

_PAGE_SIZE = 1000
_BATCH_SIZE = 500


def _paginate(client, table: str, select: str) -> list[dict]:
    """Fetch all rows from a Supabase table using offset pagination.

    Args:
        client: Authenticated Supabase client.
        table: Table name.
        select: Comma-separated column list for ``select()``.

    Returns:
        List of row dicts.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        resp = (
            client.table(table)
            .select(select)
            .range(offset, offset + _PAGE_SIZE - 1)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return rows


class ProductRepository:
    """Typed data access for the ``products`` table.

    All methods return a ``polars.DataFrame`` — or an empty one if no rows.
    """

    _SELECT = (
        "id,item_code,source,item_name,item_url,shop_name,search_query,"
        "brand,model,cpu,cpu_gen,memory,ssd,hdd,os,display_size,weight,"
        "bluetooth,webcam,usb_ports,is_active,first_seen_at,last_seen_at"
    )

    def __init__(self, client=None) -> None:
        """Initialise repository.

        Args:
            client: Authenticated Supabase client. Uses the singleton from
                :func:`src.database.client.get_supabase_client` if None.
        """
        self._client = client or get_supabase_client()

    def fetch_all(self) -> pl.DataFrame:
        """Fetch all products (paginated).

        Returns:
            DataFrame with all products columns.
        """
        rows = _paginate(self._client, "products", self._SELECT)
        logger.info("ProductRepository.fetch_all: %d rows", len(rows))
        return pl.from_dicts(rows) if rows else pl.DataFrame()

    def fetch_active(self) -> pl.DataFrame:
        """Fetch only active products (is_active=True).

        Returns:
            DataFrame with active products.
        """
        rows: list[dict] = []
        offset = 0
        while True:
            resp = (
                self._client.table("products")
                .select(self._SELECT)
                .eq("is_active", True)
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
            rows.extend(resp.data)
            if len(resp.data) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        logger.info("ProductRepository.fetch_active: %d rows", len(rows))
        return pl.from_dicts(rows) if rows else pl.DataFrame()

    def update_model(self, product_id: str, model_name: str) -> None:
        """Update the ``model`` column for a single product.

        Args:
            product_id: UUID of the product to update.
            model_name: Extracted model name (e.g. "ThinkPad L580").
        """
        self._client.table("products").update({"model": model_name}).eq("id", product_id).execute()
        logger.debug("Updated model=%r for product %s", model_name, product_id)


class PriceRepository:
    """Typed data access for the ``price_history`` table."""

    def __init__(self, client=None) -> None:
        """Initialise repository.

        Args:
            client: Authenticated Supabase client (singleton used if None).
        """
        self._client = client or get_supabase_client()

    def fetch_for_products(self, product_ids: list[str]) -> pl.DataFrame:
        """Fetch price history for a list of product UUIDs.

        Queries in batches of 500 to stay within Supabase URL length limits.

        Args:
            product_ids: List of product UUID strings.

        Returns:
            DataFrame with columns: product_id, price, scraped_at.
        """
        if not product_ids:
            return pl.DataFrame()

        rows: list[dict] = []
        for i in range(0, len(product_ids), _BATCH_SIZE):
            batch = product_ids[i : i + _BATCH_SIZE]
            resp = (
                self._client.table("price_history")
                .select("product_id,price,scraped_at")
                .in_("product_id", batch)
                .gt("price", 0)
                .execute()
            )
            rows.extend(resp.data or [])

        logger.info("PriceRepository.fetch_for_products: %d rows", len(rows))
        return pl.from_dicts(rows) if rows else pl.DataFrame()

    def fetch_latest_per_product(self) -> pl.DataFrame:
        """Fetch the most recent price record per product_id.

        Returns:
            DataFrame with columns: product_id, price, scraped_at — one row
            per product, containing the latest observation.
        """
        rows = _paginate(self._client, "price_history", "product_id,price,scraped_at")
        if not rows:
            return pl.DataFrame()
        df = pl.from_dicts(rows)
        # Keep only the latest scraped_at per product_id
        return (
            df.with_columns(
                pl.col("scraped_at").str.to_datetime(strict=False).alias("scraped_at")
            )
            .sort("scraped_at", descending=True)
            .unique(subset=["product_id"], keep="first")
        )


class PredictionRepository:
    """Typed data access for the ``price_predictions`` table."""

    def __init__(self, client=None) -> None:
        """Initialise repository.

        Args:
            client: Authenticated Supabase client (singleton used if None).
        """
        self._client = client or get_supabase_client()

    def save_predictions(self, records: list[dict]) -> None:
        """Insert price prediction records into Supabase.

        Args:
            records: List of dicts with keys: product_id, predicted_price,
                model_version. Optional keys: confidence, shap_explanation.
        """
        if not records:
            return
        self._client.table("price_predictions").insert(records).execute()
        logger.info("PredictionRepository.save_predictions: inserted %d records", len(records))

    def fetch_latest_per_product(self) -> pl.DataFrame:
        """Fetch the most recent prediction per product_id.

        Returns:
            DataFrame with columns: product_id, predicted_price, model_version,
            created_at — one row per product (latest prediction).
        """
        rows = _paginate(
            self._client,
            "price_predictions",
            "product_id,predicted_price,model_version,created_at",
        )
        if not rows:
            return pl.DataFrame()
        df = pl.from_dicts(rows)
        return (
            df.with_columns(
                pl.col("created_at").str.to_datetime(strict=False).alias("created_at")
            )
            .sort("created_at", descending=True)
            .unique(subset=["product_id"], keep="first")
        )
