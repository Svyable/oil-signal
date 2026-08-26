from pathlib import Path

from oilsignal.alerts.rules import MetricField, Operator, ThresholdRule
from oilsignal.analytics.petroleum import build_snapshot
from oilsignal.data_ingestion.fixtures import FixtureIngestor, load_observations

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def test_threshold_rule_fires_on_padd2_weekly_draw(data_dir: Path) -> None:
    result = FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    snapshot = build_snapshot(load_observations(result.parquet_path), "PET.DISTP2.W")
    rule = ThresholdRule(
        rule_id="midwest-distillate-draw",
        series_id="PET.DISTP2.W",
        field=MetricField.WEEK_OVER_WEEK,
        operator=Operator.LT,
        threshold=-500,
        message="PADD 2 distillate draw exceeds 500 thousand barrels.",
    )

    event = rule.evaluate(snapshot)

    assert event is not None
    assert event.value == -700
