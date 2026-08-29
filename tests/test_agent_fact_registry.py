import json
from pathlib import Path

from oilsignal.reports.facts import FACT_PRODUCT_SPECS

REGISTRY = Path(__file__).parents[1] / "examples" / "eia-series.example.json"


def test_fact_products_match_maintained_eia_registry() -> None:
    payload = json.loads(REGISTRY.read_text())
    registry_series = {item["canonical_series_id"] for item in payload["series"]}
    fact_series = {spec.series_id for spec in FACT_PRODUCT_SPECS}

    assert fact_series == registry_series
    assert len({spec.sku for spec in FACT_PRODUCT_SPECS}) == len(FACT_PRODUCT_SPECS)
    assert len(fact_series) == len(FACT_PRODUCT_SPECS)
