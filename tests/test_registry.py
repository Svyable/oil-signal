from pathlib import Path

from oilsignal.data_ingestion.registry import SeriesRegistry

REGISTRY = Path(__file__).parents[1] / "examples" / "eia-series.example.json"


def test_verified_eia_registry_covers_core_report_and_demand_series() -> None:
    registry = SeriesRegistry.load(REGISTRY)
    routes = {spec.canonical_series_id: spec.request.route for spec in registry.series}

    assert routes["PET.CRDUUS.W"] == "seriesid/PET.WCESTUS1.W"
    assert routes["PET.DISTP2.W"] == "seriesid/PET.WDISTP21.W"
    assert routes["PET.UTILUS.W"] == "seriesid/PET.WPULEUS3.W"
    assert routes["PET.JETUS.W"] == "seriesid/PET.WKJSTUS1.W"
    assert routes["PET.CRIMUS.W"] == "seriesid/PET.WCRIMUS2.W"
    assert routes["PET.GASPSUS.W"] == "seriesid/PET.WGFUPUS2.W"
    assert routes["PET.DISTPSUS.W"] == "seriesid/PET.WDIUPUS2.W"
    assert routes["PET.JETPSUS.W"] == "seriesid/PET.WKJUPUS2.W"
    assert routes["PET.TOTALPSUS.W"] == "seriesid/PET.WRPUPUS2.W"
    assert all(spec.release_family == "wpsr" for spec in registry.series)
