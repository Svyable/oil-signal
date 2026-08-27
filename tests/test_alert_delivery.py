from pathlib import Path

from oilsignal.alerts.delivery import flush_alert_outbox
from oilsignal.alerts.engine import (
    AlertPolicy,
    AlertPolicySet,
    MatchMode,
    evaluate_policies_with_state,
)
from oilsignal.alerts.rules import MetricField, Operator, ThresholdRule
from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.storage.datasets import load_latest_observations
from oilsignal.storage.metadata import get_alert_outbox, list_alert_outbox

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"


class RecordingAdapter:
    name = "recording"

    def __init__(self) -> None:
        self.payloads: list[str] = []

    def send(self, payload_json: str) -> None:
        self.payloads.append(payload_json)


class FlakyAdapter:
    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def send(self, payload_json: str) -> None:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary delivery failure")


def _policy_set() -> AlertPolicySet:
    return AlertPolicySet(
        policies=[
            AlertPolicy(
                policy_id="distillate-low",
                name="Distillate low",
                message="PADD 2 distillate inventory is low",
                mode=MatchMode.ALL,
                conditions=[
                    ThresholdRule(
                        rule_id="inventory-low",
                        series_id="PET.DISTP2.W",
                        field=MetricField.CURRENT,
                        operator=Operator.LT,
                        threshold=27000,
                        message="inventory low",
                    )
                ],
            )
        ]
    )


def test_state_transition_atomically_enqueues_once(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_latest_observations(data_dir)
    metadata_path = data_dir / "metadata.sqlite"

    first = evaluate_policies_with_state(observations, _policy_set(), metadata_path)
    second = evaluate_policies_with_state(observations, _policy_set(), metadata_path)

    assert first.transitions[0].outbox_id is not None
    assert second.transitions[0].outbox_id is None
    rows = list_alert_outbox(metadata_path)
    assert len(rows) == 1
    assert rows[0].status == "pending"
    assert rows[0].policy_id == "distillate-low"


def test_outbox_success_records_delivery_receipt(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_latest_observations(data_dir)
    metadata_path = data_dir / "metadata.sqlite"
    evaluated = evaluate_policies_with_state(observations, _policy_set(), metadata_path)
    outbox_id = evaluated.transitions[0].outbox_id
    assert outbox_id is not None

    adapter = RecordingAdapter()
    receipts = flush_alert_outbox(metadata_path, adapter)

    assert len(receipts) == 1
    assert receipts[0].status == "delivered"
    assert receipts[0].attempts == 1
    assert len(adapter.payloads) == 1
    stored = get_alert_outbox(metadata_path, outbox_id)
    assert stored is not None
    assert stored.status == "delivered"
    assert stored.delivered_at is not None
    assert list_alert_outbox(metadata_path) == []


def test_failed_outbox_delivery_is_retried(data_dir: Path) -> None:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_latest_observations(data_dir)
    metadata_path = data_dir / "metadata.sqlite"
    evaluated = evaluate_policies_with_state(observations, _policy_set(), metadata_path)
    outbox_id = evaluated.transitions[0].outbox_id
    assert outbox_id is not None

    adapter = FlakyAdapter()
    first = flush_alert_outbox(metadata_path, adapter)
    second = flush_alert_outbox(metadata_path, adapter)

    assert first[0].status == "failed"
    assert first[0].attempts == 1
    assert first[0].error == "temporary delivery failure"
    assert second[0].status == "delivered"
    assert second[0].attempts == 2
    stored = get_alert_outbox(metadata_path, outbox_id)
    assert stored is not None
    assert stored.status == "delivered"
    assert stored.attempts == 2
    assert stored.last_error is None
