from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oilsignal.alerts.delivery import (
    ConsoleOutboxDelivery,
    DeliveryPolicy,
    OutboxDeliveryAdapter,
    WebhookOutboxDelivery,
    flush_alert_outbox,
)
from oilsignal.alerts.engine import (
    AlertPolicySet,
    evaluate_policies,
    evaluate_policies_with_state,
)
from oilsignal.config import settings
from oilsignal.data_ingestion.eia import EIAClient
from oilsignal.data_ingestion.live import EIAIngestor
from oilsignal.data_ingestion.registry import SeriesRegistry
from oilsignal.data_ingestion.verification import verify_eia_registry
from oilsignal.freshness import FreshnessState, check_wpsr_freshness, require_fresh_wpsr
from oilsignal.reports.renderers import render_report
from oilsignal.reports.specialized import DistillateSupplyRiskBrief, RefineryUtilizationWatch
from oilsignal.reports.weekly import WeeklyPetroleumBrief
from oilsignal.storage.datasets import inspect_data, load_latest_observations
from oilsignal.storage.metadata import list_alert_dead_letters, requeue_alert_dead_letter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oilsignal")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest-eia", help="ingest a configured EIA series registry")
    ingest.add_argument("--registry", type=Path, required=True)
    ingest.add_argument("--data-dir", type=Path, default=settings.data_dir)

    metadata = subparsers.add_parser("eia-metadata", help="inspect EIA route metadata or facets")
    metadata.add_argument("--route", required=True)
    metadata.add_argument("--facet")

    verify = subparsers.add_parser(
        "eia-verify-registry",
        help="probe every EIA registry route and verify its current source contract",
    )
    verify.add_argument("--registry", type=Path, required=True)
    verify.add_argument("--sample-length", type=int, default=2)
    verify.add_argument(
        "--skip-freshness",
        action="store_true",
        help="verify route/data shape without checking WPSR recency",
    )

    freshness = subparsers.add_parser(
        "freshness",
        help="check the latest dataset against the WPSR release calendar",
    )
    freshness.add_argument("--data-dir", type=Path, default=settings.data_dir)

    report = subparsers.add_parser("report", help="render a deterministic cited report")
    report.add_argument(
        "--type",
        choices=["weekly", "distillate", "refinery-utilization"],
        default="weekly",
    )
    report.add_argument("--format", choices=["markdown", "html", "json"], default="markdown")
    report.add_argument("--data-dir", type=Path, default=settings.data_dir)

    alerts = subparsers.add_parser(
        "alerts-evaluate",
        help="evaluate composite alert policies against the latest dataset",
    )
    alerts.add_argument("--rules", type=Path, required=True)
    alerts.add_argument("--data-dir", type=Path, default=settings.data_dir)
    alerts.add_argument(
        "--stateless",
        action="store_true",
        help="dry-run every matching policy instead of edge-triggered notification state",
    )

    deliver = subparsers.add_parser(
        "alerts-deliver",
        help="drain eligible alert rows with leases, backoff, and dead-lettering",
    )
    deliver.add_argument("--adapter", choices=["console", "webhook"], default="console")
    deliver.add_argument("--webhook-url", help="override OILSIGNAL_ALERT_WEBHOOK_URL")
    deliver.add_argument("--data-dir", type=Path, default=settings.data_dir)
    deliver.add_argument("--limit", type=int, default=100)
    deliver.add_argument("--worker-id")
    deliver.add_argument("--lease-seconds", type=int, default=120)
    deliver.add_argument("--max-attempts", type=int, default=5)
    deliver.add_argument("--base-backoff-seconds", type=int, default=30)
    deliver.add_argument("--max-backoff-seconds", type=int, default=3600)

    dead_letters = subparsers.add_parser(
        "alerts-dead-letters",
        help="list active alert dead letters",
    )
    dead_letters.add_argument("--data-dir", type=Path, default=settings.data_dir)
    dead_letters.add_argument("--limit", type=int, default=100)

    requeue = subparsers.add_parser(
        "alerts-requeue",
        help="requeue a dead-lettered alert with a fresh attempt budget",
    )
    requeue.add_argument("--outbox-id", required=True)
    requeue.add_argument("--data-dir", type=Path, default=settings.data_dir)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ingest-eia":
        return asyncio.run(_ingest_eia(args.registry, args.data_dir))
    if args.command == "eia-metadata":
        return asyncio.run(_eia_metadata(args.route, args.facet))
    if args.command == "eia-verify-registry":
        return asyncio.run(
            _eia_verify_registry(args.registry, args.sample_length, args.skip_freshness)
        )
    if args.command == "freshness":
        return _freshness(args.data_dir)
    if args.command == "report":
        return _report(args.type, args.format, args.data_dir)
    if args.command == "alerts-evaluate":
        return _alerts_evaluate(args.rules, args.data_dir, args.stateless)
    if args.command == "alerts-deliver":
        return _alerts_deliver(
            args.adapter,
            args.webhook_url,
            args.data_dir,
            args.limit,
            args.worker_id,
            args.lease_seconds,
            args.max_attempts,
            args.base_backoff_seconds,
            args.max_backoff_seconds,
        )
    if args.command == "alerts-dead-letters":
        return _alerts_dead_letters(args.data_dir, args.limit)
    if args.command == "alerts-requeue":
        return _alerts_requeue(args.data_dir, args.outbox_id)
    raise RuntimeError(f"unhandled command: {args.command}")


async def _ingest_eia(registry_path: Path, data_dir: Path) -> int:
    client = _eia_client()
    registry = SeriesRegistry.load(registry_path)
    result = await EIAIngestor(data_dir, client).ingest_registry(registry)
    print(result.model_dump_json(indent=2))
    return 0


async def _eia_metadata(route: str, facet: str | None) -> int:
    client = _eia_client()
    payload = await client.facet_values(route, facet) if facet else await client.metadata(route)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


async def _eia_verify_registry(
    registry_path: Path,
    sample_length: int,
    skip_freshness: bool,
) -> int:
    result = await verify_eia_registry(
        SeriesRegistry.load(registry_path),
        _eia_client(),
        sample_length=sample_length,
        enforce_freshness=not skip_freshness,
    )
    print(result.model_dump_json(indent=2))
    return 0 if result.ok else 2


def _freshness(data_dir: Path) -> int:
    observations = load_latest_observations(data_dir)
    status = inspect_data(data_dir)
    result = check_wpsr_freshness(observations, live_eia=status.is_live_eia)
    print(result.model_dump_json(indent=2))
    return 2 if result.status == FreshnessState.STALE else 0


def _report(report_type: str, output_format: str, data_dir: Path) -> int:
    builders: dict[str, Any] = {
        "weekly": WeeklyPetroleumBrief(),
        "distillate": DistillateSupplyRiskBrief(),
        "refinery-utilization": RefineryUtilizationWatch(),
    }
    observations = load_latest_observations(data_dir)
    status = inspect_data(data_dir)
    require_fresh_wpsr(observations, live_eia=status.is_live_eia)
    report = builders[report_type].build(observations)
    print(render_report(report, output_format))
    return 0


def _alerts_evaluate(rules_path: Path, data_dir: Path, stateless: bool) -> int:
    policy_set = AlertPolicySet.load(rules_path)
    observations = load_latest_observations(data_dir)
    status = inspect_data(data_dir)
    require_fresh_wpsr(observations, live_eia=status.is_live_eia)
    if stateless:
        result = evaluate_policies(observations, policy_set)
    else:
        result = evaluate_policies_with_state(
            observations,
            policy_set,
            data_dir / "metadata.sqlite",
        )
    print(result.model_dump_json(indent=2))
    return 0


def _alerts_deliver(
    adapter_name: str,
    webhook_url: str | None,
    data_dir: Path,
    limit: int,
    worker_id: str | None,
    lease_seconds: int,
    max_attempts: int,
    base_backoff_seconds: int,
    max_backoff_seconds: int,
) -> int:
    adapter = _build_delivery_adapter(adapter_name, webhook_url)
    policy = DeliveryPolicy(
        lease_seconds=lease_seconds,
        max_attempts=max_attempts,
        base_backoff_seconds=base_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
    )
    receipts = flush_alert_outbox(
        data_dir / "metadata.sqlite",
        adapter,
        limit=limit,
        worker_id=worker_id,
        policy=policy,
    )
    print(json.dumps([receipt.model_dump(mode="json") for receipt in receipts], indent=2))
    bad_statuses = {"failed", "dead_letter", "lease_lost"}
    return 1 if any(receipt.status in bad_statuses for receipt in receipts) else 0


def _build_delivery_adapter(
    adapter_name: str,
    webhook_url: str | None = None,
) -> OutboxDeliveryAdapter:
    if adapter_name == "console":
        return ConsoleOutboxDelivery()
    if adapter_name == "webhook":
        endpoint = webhook_url or settings.alert_webhook_url
        if not endpoint:
            raise SystemExit(
                "webhook delivery requires --webhook-url or OILSIGNAL_ALERT_WEBHOOK_URL"
            )
        bearer_token = (
            settings.alert_webhook_bearer_token.get_secret_value()
            if settings.alert_webhook_bearer_token
            else None
        )
        signing_secret = (
            settings.alert_webhook_signing_secret.get_secret_value()
            if settings.alert_webhook_signing_secret
            else None
        )
        return WebhookOutboxDelivery(
            endpoint,
            bearer_token=bearer_token,
            signing_secret=signing_secret,
            timeout_seconds=settings.alert_webhook_timeout_seconds,
            allow_insecure_http=settings.alert_webhook_allow_insecure_http,
        )
    raise ValueError(f"unsupported delivery adapter: {adapter_name}")


def _alerts_dead_letters(data_dir: Path, limit: int) -> int:
    rows = list_alert_dead_letters(data_dir / "metadata.sqlite", limit=limit)
    print(json.dumps([row.model_dump(mode="json") for row in rows], indent=2))
    return 1 if rows else 0


def _alerts_requeue(data_dir: Path, outbox_id: str) -> int:
    row = requeue_alert_dead_letter(
        data_dir / "metadata.sqlite",
        outbox_id=outbox_id,
        now=datetime.now(UTC),
    )
    print(json.dumps(row.model_dump(mode="json"), indent=2))
    return 0


def _eia_client() -> EIAClient:
    if not settings.eia_api_key:
        raise SystemExit(
            "OILSIGNAL_EIA_API_KEY is required for live EIA commands; tests and fixtures do not need it"
        )
    return EIAClient(settings.eia_api_key, settings.eia_base_url)
