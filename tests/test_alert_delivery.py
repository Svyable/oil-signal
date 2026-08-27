from datetime import UTC, datetime, timedelta
from pathlib import Path

from oilsignal.alerts.delivery import DeliveryPolicy, flush_alert_outbox
from oilsignal.alerts.engine import (
    AlertPolicy,
    AlertPolicySet,
    MatchMode,
    evaluate_policies_with_state,
)
from oilsignal.alerts.rules import MetricField, Operator, ThresholdRule
from oilsignal.data_ingestion.fixtures import FixtureIngestor
from oilsignal.storage.datasets import load_latest_observations
from oilsignal.storage.metadata import (
    claim_alert_outbox,
    get_alert_delivery_lease,
    get_alert_outbox,
    list_alert_dead_letters,
    list_alert_outbox,
    requeue_alert_dead_letter,
)

FIXTURE = Path(__file__).parent / "fixtures" / "petroleum_weekly.csv"
T0 = datetime(2026, 8, 27, 13, 0, tzinfo=UTC)


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


class FailingAdapter:
    name = "failing"

    def send(self, payload_json: str) -> None:
        raise RuntimeError("provider unavailable")


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


def _enqueue(data_dir: Path) -> tuple[Path, str]:
    FixtureIngestor(data_dir).ingest_csv(FIXTURE)
    observations = load_latest_observations(data_dir)
    metadata_path = data_dir / "metadata.sqlite"
    evaluated = evaluate_policies_with_state(observations, _policy_set(), metadata_path)
    outbox_id = evaluated.transitions[0].outbox_id
    assert outbox_id is not None
    return metadata_path, outbox_id


def test_state_transition_atomically_enqueues_once(data_dir: Path) -> None:
    metadata_path, _ = _enqueue(data_dir)
    observations = load_latest_observations(data_dir)
    second = evaluate_policies_with_state(observations, _policy_set(), metadata_path)

    assert second.transitions[0].outbox_id is None
    rows = list_alert_outbox(metadata_path)
    assert len(rows) == 1
    assert rows[0].status == "pending"
    assert rows[0].policy_id == "distillate-low"


def test_outbox_success_records_delivery_receipt(data_dir: Path) -> None:
    metadata_path, outbox_id = _enqueue(data_dir)
    adapter = RecordingAdapter()

    receipts = flush_alert_outbox(metadata_path, adapter, worker_id="worker-a", now=T0)

    assert len(receipts) == 1
    assert receipts[0].status == "delivered"
    assert receipts[0].attempts == 1
    assert receipts[0].worker_id == "worker-a"
    assert len(adapter.payloads) == 1
    stored = get_alert_outbox(metadata_path, outbox_id)
    assert stored is not None
    assert stored.status == "delivered"
    assert stored.delivered_at == T0
    assert list_alert_outbox(metadata_path) == []
    assert get_alert_delivery_lease(metadata_path, outbox_id) is None


def test_active_lease_prevents_second_worker_from_claiming_same_row(data_dir: Path) -> None:
    metadata_path, outbox_id = _enqueue(data_dir)
    kwargs = {
        "adapter": "recording",
        "now": T0,
        "lease_seconds": 60,
        "max_attempts": 5,
        "base_backoff_seconds": 0,
        "max_backoff_seconds": 0,
    }

    first = claim_alert_outbox(metadata_path, worker_id="worker-a", **kwargs)
    second = claim_alert_outbox(metadata_path, worker_id="worker-b", **kwargs)

    assert first is not None
    assert first.id == outbox_id
    assert second is None
    lease = get_alert_delivery_lease(metadata_path, outbox_id)
    assert lease is not None
    assert lease.worker_id == "worker-a"


def test_expired_lease_can_be_reclaimed_by_another_worker(data_dir: Path) -> None:
    metadata_path, outbox_id = _enqueue(data_dir)
    first = claim_alert_outbox(
        metadata_path,
        worker_id="worker-a",
        adapter="recording",
        now=T0,
        lease_seconds=60,
        max_attempts=5,
        base_backoff_seconds=0,
        max_backoff_seconds=0,
    )
    assert first is not None

    reclaimed = claim_alert_outbox(
        metadata_path,
        worker_id="worker-b",
        adapter="recording",
        now=T0 + timedelta(seconds=61),
        lease_seconds=60,
        max_attempts=5,
        base_backoff_seconds=0,
        max_backoff_seconds=0,
    )

    assert reclaimed is not None
    assert reclaimed.id == outbox_id
    assert reclaimed.attempts == 2
    lease = get_alert_delivery_lease(metadata_path, outbox_id)
    assert lease is not None
    assert lease.worker_id == "worker-b"


def test_failed_outbox_delivery_waits_for_exponential_backoff(data_dir: Path) -> None:
    metadata_path, outbox_id = _enqueue(data_dir)
    adapter = FlakyAdapter()
    policy = DeliveryPolicy(base_backoff_seconds=60, max_backoff_seconds=600)

    first = flush_alert_outbox(
        metadata_path,
        adapter,
        worker_id="worker-a",
        policy=policy,
        now=T0,
    )
    blocked = flush_alert_outbox(
        metadata_path,
        adapter,
        worker_id="worker-b",
        policy=policy,
        now=T0 + timedelta(seconds=59),
    )
    second = flush_alert_outbox(
        metadata_path,
        adapter,
        worker_id="worker-b",
        policy=policy,
        now=T0 + timedelta(seconds=60),
    )

    assert first[0].status == "failed"
    assert first[0].attempts == 1
    assert first[0].error == "temporary delivery failure"
    assert blocked == []
    assert second[0].status == "delivered"
    assert second[0].attempts == 2
    stored = get_alert_outbox(metadata_path, outbox_id)
    assert stored is not None
    assert stored.status == "delivered"
    assert stored.attempts == 2
    assert stored.last_error is None


def test_exhausted_attempts_move_to_dead_letter_and_can_be_requeued(data_dir: Path) -> None:
    metadata_path, outbox_id = _enqueue(data_dir)
    policy = DeliveryPolicy(
        max_attempts=2,
        base_backoff_seconds=0,
        max_backoff_seconds=0,
    )

    receipts = flush_alert_outbox(
        metadata_path,
        FailingAdapter(),
        worker_id="worker-a",
        policy=policy,
        limit=2,
        now=T0,
    )

    assert [receipt.status for receipt in receipts] == ["failed", "dead_letter"]
    stored = get_alert_outbox(metadata_path, outbox_id)
    assert stored is not None
    assert stored.status == "dead_letter"
    dead_letters = list_alert_dead_letters(metadata_path)
    assert len(dead_letters) == 1
    assert dead_letters[0].outbox_id == outbox_id
    assert dead_letters[0].attempts == 2

    requeued = requeue_alert_dead_letter(
        metadata_path,
        outbox_id=outbox_id,
        now=T0 + timedelta(minutes=1),
    )

    assert requeued.status == "pending"
    assert requeued.attempts == 0
    assert list_alert_dead_letters(metadata_path) == []
    history = list_alert_dead_letters(metadata_path, active_only=False)
    assert len(history) == 1
    assert history[0].requeued_at == T0 + timedelta(minutes=1)

    delivered = flush_alert_outbox(
        metadata_path,
        RecordingAdapter(),
        worker_id="worker-b",
        policy=policy,
        now=T0 + timedelta(minutes=2),
    )
    assert delivered[0].status == "delivered"
