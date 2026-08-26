from pathlib import Path

from fastapi.testclient import TestClient
from oilsignal.alerts.engine import (
    AlertPolicy,
    AlertPolicySet,
    MatchMode,
    evaluate_policies,
)
from oilsignal.alerts.rules import MetricField, Operator, ThresholdRule
from oilsignal.api.app import create_app
from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.storage.datasets import load_latest_observations

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


def _policy_set(utilization_threshold: float = 91.0) -> AlertPolicySet:
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


def test_composite_alert_requires_all_conditions_and_returns_audit_trace(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_latest_observations(data_dir)

    triggered = evaluate_policies(observations, _policy_set())
    not_triggered = evaluate_policies(observations, _policy_set(utilization_threshold=90.0))

    assert len(triggered.triggered) == 1
    assert len(triggered.triggered[0].conditions) == 2
    assert all(condition.matched for condition in triggered.triggered[0].conditions)
    assert not not_triggered.triggered
    assert not_triggered.evaluations[0].conditions[1].value == 90.8


def test_alert_evaluation_api_returns_triggered_policy(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    client = TestClient(create_app(data_dir))

    response = client.post(
        "/api/alerts/evaluate",
        json=_policy_set().model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["triggered"][0]["policy_id"] == "midwest-tightness"
    assert payload["triggered"][0]["conditions"][0]["as_of"] == "2026-08-21"
