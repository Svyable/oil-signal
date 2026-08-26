from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from oilsignal.config import settings
from oilsignal.data_ingestion.eia import EIAClient
from oilsignal.data_ingestion.live import EIAIngestor
from oilsignal.data_ingestion.registry import SeriesRegistry
from oilsignal.reports.renderers import render_report
from oilsignal.reports.specialized import DistillateSupplyRiskBrief, RefineryUtilizationWatch
from oilsignal.reports.weekly import WeeklyPetroleumBrief
from oilsignal.storage.datasets import load_latest_observations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oilsignal")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest-eia", help="ingest a configured EIA series registry")
    ingest.add_argument("--registry", type=Path, required=True)
    ingest.add_argument("--data-dir", type=Path, default=settings.data_dir)

    metadata = subparsers.add_parser("eia-metadata", help="inspect EIA route metadata or facets")
    metadata.add_argument("--route", required=True)
    metadata.add_argument("--facet")

    report = subparsers.add_parser("report", help="render a deterministic cited report")
    report.add_argument(
        "--type",
        choices=["weekly", "distillate", "refinery-utilization"],
        default="weekly",
    )
    report.add_argument("--format", choices=["markdown", "html", "json"], default="markdown")
    report.add_argument("--data-dir", type=Path, default=settings.data_dir)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ingest-eia":
        return asyncio.run(_ingest_eia(args.registry, args.data_dir))
    if args.command == "eia-metadata":
        return asyncio.run(_eia_metadata(args.route, args.facet))
    if args.command == "report":
        return _report(args.type, args.format, args.data_dir)
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


def _report(report_type: str, output_format: str, data_dir: Path) -> int:
    builders: dict[str, Any] = {
        "weekly": WeeklyPetroleumBrief(),
        "distillate": DistillateSupplyRiskBrief(),
        "refinery-utilization": RefineryUtilizationWatch(),
    }
    report = builders[report_type].build(load_latest_observations(data_dir))
    print(render_report(report, output_format))
    return 0


def _eia_client() -> EIAClient:
    if not settings.eia_api_key:
        raise SystemExit(
            "OILSIGNAL_EIA_API_KEY is required for live EIA commands; tests and fixtures do not need it"
        )
    return EIAClient(settings.eia_api_key, settings.eia_base_url)
