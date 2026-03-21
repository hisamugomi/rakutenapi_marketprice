"""Tests for src.features.model_extractor."""
import pytest
from src.features.model_extractor import extract_model


@pytest.mark.parametrize("title, expected", [
    # ── ThinkPad ────────────────────────────────────────────────────────────
    (
        "【薄型】Lenovo ThinkPad L580 第8世代 Core i5 8250U 32GB HDD500GB Windows10",
        "ThinkPad L580",
    ),
    (
        "【中古】 Lenovo ThinkPad L390 第8世代 Core i5 8265U 8GB SSD256GB Windows11",
        "ThinkPad L390",
    ),
    (
        "Lenovo ThinkPad L590 Core i5 8265U 16GB SSD 256GB 15.6インチ 中古",
        "ThinkPad L590",
    ),
    (
        "Lenovo 〔中古〕ThinkPad T14s Gen 1 20UJS30F00 AMD Ryzen 5 PRO 4650U",
        "ThinkPad T14s",
    ),
    (
        "Lenovo 〔中古〕ThinkPad X1 Carbon Gen 8 20UAS6U501 Core i7 10610U",
        "ThinkPad X1 Carbon",
    ),
    # ── IdeaPad ─────────────────────────────────────────────────────────────
    (
        "Lenovo 〔中古〕ideapad L3 15ITL6 82HL001BJP（中古1ヶ月保証）",
        "IdeaPad L3",
    ),
    (
        "Lenovo 〔中古〕IdeaPad Slim3 14IRH10 Core i7-13620H 16GB 512GB",
        "IdeaPad Slim3",
    ),
    # ── Dell Latitude ────────────────────────────────────────────────────────
    (
        "【Windows11】DELL Latitude 5590 第8世代 Core i5 8250U 16GB SSD1TB",
        "Latitude 5590",
    ),
    (
        "DELL LATITUDE 5300 2-in-1 訳あり品 Windows11 Core i5 8365U 16GB SSD256GB",
        "Latitude 5300",
    ),
    (
        "DELL 〔中古〕Latitude 5320〔 i5-1145G7 / 8GB / SSD256GB / 13.3inch〕",
        "Latitude 5320",
    ),
    # Legacy e-series — should normalise capitalisation
    (
        "Dell latitude e5400 Core i5 8GB SSD 中古",
        "Latitude E5400",
    ),
    (
        "Dell LATITUDE E5500 Windows10 中古ノートPC",
        "Latitude E5500",
    ),
    # ── Inspiron ─────────────────────────────────────────────────────────────
    (
        "DELL Inspiron 15 3000 Series Core i3 Windows11 中古",
        "Inspiron 15",
    ),
    # ── No match ─────────────────────────────────────────────────────────────
    ("Apple MacBook Pro 13インチ M2チップ 8GB 256GB", None),
    ("中古パソコン HP EliteBook 840 G7 Core i7", None),
    ("完全に別の商品 バッテリー交換済み", None),
])
def test_extract_model(title: str, expected: str | None) -> None:
    assert extract_model(title) == expected
