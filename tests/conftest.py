from __future__ import annotations

import polars as pl
import pytest


@pytest.fixture
def sample_rakuten_row() -> dict:
    """Minimal Rakuten API item row for tests."""
    return {
        "itemCode": "shop:test-item-001",
        "itemName": "Lenovo ThinkPad L580 Core i5-8250U 8GB SSD256GB Win11",
        "itemCaption": "メモリ8GB SSD256GB Windows11 Pro 15.6インチ",
        "itemPrice": 29800,
        "itemUrl": "https://item.rakuten.co.jp/shop/test",
        "shopName": "TestShop",
        "imageFlag": 1,
    }


@pytest.fixture
def sample_raw_df(sample_rakuten_row) -> pl.DataFrame:
    """Single-row Polars DataFrame matching Rakuten API output."""
    return pl.DataFrame([sample_rakuten_row])
