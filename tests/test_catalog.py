from pathlib import Path

import pytest

from app.catalog import Catalog

CSV = Path(__file__).resolve().parent.parent / "data" / "products.csv"


@pytest.fixture(scope="module")
def catalog():
    return Catalog(str(CSV))


def test_loads_all_products(catalog):
    assert len(catalog.df) == 30


def test_search_respects_max_price(catalog):
    results = catalog.search("winter warm", max_price=100)
    assert results
    assert all(r["price"] <= 100 for r in results)


def test_search_excludes_out_of_stock_by_default(catalog):
    results = catalog.search("cozy", limit=10)
    assert all(r["stock"] > 0 for r in results)
    ids = {r["product_id"] for r in catalog.search("cozy", in_stock_only=False, limit=10)}
    assert "P004" in ids  # out-of-stock slippers appear only when requested


def test_search_category_filter(catalog):
    results = catalog.search("waterproof", category="Footwear")
    assert results and all(r["category"] == "Footwear" for r in results)


def test_no_match_returns_empty(catalog):
    assert catalog.search("zzzzqqq") == []


def test_get_product(catalog):
    assert catalog.get("p001")["name"].startswith("AeroRun")
    assert catalog.get("NOPE") is None
