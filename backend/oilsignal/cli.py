from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from oilsignal.alerts.delivery import ConsoleOutboxDelivery, flush_alert_outbox
from oilsignal.alerts.engine import (
    AlertPolicySet,
    evaluate_policies,
    evaluate_policies_with_state,
)
from oilsignal.config import settings
from oilsignal.data_ingestion.eia import EIAClient
from oilsignal.data_ingestion.live import EIAIngestor
from oilsignal.data_ingestion.registry import SeriesRegistry
from oilsignal.freshness import FreshnessState, check_wpsr_freshness, require_fresh_wpsr
from oilsignal.reports.renderers import render_report
from oilsignal.reports.specialized import DistillateSupplyRiskBrief, RefineryUtilizationWatch
from oilsignal.reports.weekly import WeeklyPetroleumBrief
from oilsignal.storage.datasets import inspect_data, load_latest_observations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oilsignal")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest-eia", help="ingest a configured EIA series registry")
    ingest.add_argument("--registry", type=Path, required=True)
    ingest.add_argument("--data-dir", type=Path, default=settings.data_dir)

    metadata = subparsers.add_parser("eia-metadata", help="inspect EIA route metadata or facets")
    metadata.add_argument("--route", required=True)
    metadata.add_argument("--facet")

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
        help="deliver pending alert outbox rows with retry receipts",
    )
    deliver.add_argument("--adapter", choices=["console"], default="console")
    deliver.add_argument("--data-dir", type=Path, default=settings.data_dir)
    deliver.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ingest-eia":
        return asyncio.run(_ingest_eia(args.registry, args.data_dir))
    if args.command == "eia-metadata":
        return asyncio.run(_eia_metadata(args.route, args.facet))
    if args.command == "freshness":
        return _freshness(args.data_dir)
    if args.command == "report":
        return _report(args.type, args.format, args.data_dir)
    if args.command == "alerts-evaluate":
        return _alerts_evaluate(args.rules, args.data_dir, args.stateless)
    if args.command == "alerts-deliver":
        return _alerts_deliver(args.adapter, args.data_dir, args.limit)
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


def _alerts_deliver(adapter_name: str, data_dir: Path, limit: int) -> int:
    if adapter_name != "console":
        raise ValueError(f"unsupported delivery adapter: {adapter_name}")
    receipts = flush_alert_outbox(
        data_dir / "metadata.sqlite",
        ConsoleOutboxDelivery(),
        limit=limit,
    )
    print(json.dumps([receipt.model_dump(mode="json") for receipt in receipts], indent=2))
    return 1 if any(receipt.status == "failed" for receipt in receipts) else 0


def _eia_client() -> EIAClient:
    if not settings.eia_api_key:
        raise SystemExit(
            "OILSIGNAL_EIA_API_KEY is required for live EIA commands; tests and fixtures do not need it"
        )
    return EIAClient(settings.eia_api_key, settings.eia_base_url)
