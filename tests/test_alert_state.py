from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.alerts.engine import (
    AlertPolicy,
    AlertPolicySet,
    MatchMode,
    evaluate_policies_with_state,
)
from oilsignal.alerts.rules import MetricField, Operator, ThresholdRule
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.storage.datasets import load_latest_observations
from oilsignal.storage.metadata import get_alert_state

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def _policy_set(utilization_threshold: float) -> AlertPolicySet:
    return AlertPolicySet(
        policies=[
            AlertPolicy(
                policy_id="midwest-tightness",
                name="Midwest tightness",
                message="Two-signal supply risk",
                mode=MatchMode.ALL,
                conditions=[
                    ThresholdRule(
                        rule_id="distillate-low",
                        series_id="PET.DISTP2.W",
                        field=MetricField.CURRENT,
                        operator=Operator.LT,
                        threshold=27000,
                        message="distillate low",
                    ),
                    ThresholdRule(
                        rule_id="utilization-low",
                        series_id="PET.UTILUS.W",
                        field=MetricField.CURRENT,
                        operator=Operator.LT,
                        threshold=utilization_threshold,
                        message="utilization low",
                    ),
                ],
            )
        ]
    )


def test_stateful_alert_notifies_once_then_rearms_after_recovery(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_latest_observations(data_dir)
    metadata_path = data_dir / "metadata.sqlite"

    first = evaluate_policies_with_state(observations, _policy_set(91.0), metadata_path)
    repeated = evaluate_policies_with_state(observations, _policy_set(91.0), metadata_path)
    recovered = evaluate_policies_with_state(observations, _policy_set(90.0), metadata_path)
    retriggered = evaluate_policies_with_state(observations, _policy_set(91.0), metadata_path)

    assert [item.policy_id for item in first.notifications] == ["midwest-tightness"]
    assert not repeated.notifications
    assert recovered.transitions[0].recovered is True
    assert [item.policy_id for item in retriggered.notifications] == ["midwest-tightness"]
    state = get_alert_state(metadata_path, "midwest-tightness")
    assert state is not None
    assert state.active is True
    assert state.last_triggered_at is not None


def test_stateful_alert_api_suppresses_duplicate_notification(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir))
    payload = _policy_set(91.0).model_dump(mode="json")

    first = client.post("/api/alerts/evaluate/stateful", json=payload)
    second = client.post("/api/alerts/evaluate/stateful", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(first.json()["notifications"]) == 1
    assert second.json()["notifications"] == []
