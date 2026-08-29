from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

from pydantic import BaseModel, Field, HttpUrl

from oilsignal.freshness import DatasetFreshness
from oilsignal.models import CalculationTrace, Claim, ClaimKind, Observation, Report
from oilsignal.reports.delta import WeeklyPetroleumDelta
from oilsignal.reports.facts import FACT_PRODUCT_SPECS, FactProductSpec, SeriesFactBrief
from oilsignal.reports.specialized import (
    CrudeBalanceWatch,
    DistillateSupplyRiskBrief,
    RefineryUtilizationWatch,
)
from oilsignal.reports.weekly import WeeklyPetroleumBrief

EVIDENCE_SCHEMA_VERSION = "1.0"
CATALOG_SCHEMA_VERSION = "1.0"


class AgentPrice(BaseModel):
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    unit: str = "evidence_pack"
    enforcement: str = "external"


class AgentProduct(BaseModel):
    sku: str
    name: str
    description: str
    product_kind: str = "brief"
    series_id: str | None = None
    method: str = "GET"
    state_path: str
    evidence_path: str
    quote_path: str
    response_media_type: str = "application/json"
    metering_unit: str = "evidence_pack"
    freshness_policy: str = "fail_closed_wpsr"
    cache_semantics: str = "etag_by_evidence_sha256"
    evidence_guarantees: list[str]
    price: AgentPrice | None = None


class AgentCatalog(BaseModel):
    schema_version: str = CATALOG_SCHEMA_VERSION
    service: str = "OilSignal"
    description: str = (
        "Deterministic U.S. petroleum intelligence products, including briefs, weekly "
        "change deltas, and single-series facts, with cited evidence, calculation traces, "
        "raw-source hashes, and cache-stable fingerprints."
    )
    openapi_path: str = "/openapi.json"
    discovery_path: str = "/.well-known/oilsignal-agent.json"
    products: list[AgentProduct]


class AgentQuote(BaseModel):
    schema_version: str = CATALOG_SCHEMA_VERSION
    sku: str
    available_for_purchase: bool
    price: AgentPrice | None = None
    fulfillment_path: str
    payment_enforcement: str
    payment_protocols: list[str] = Field(default_factory=list)


class EvidenceObservation(BaseModel):
    series_id: str
    metric: str
    product: str
    geography: str
    frequency: str
    unit: str
    observation_date: str
    value: float
    source_url: HttpUrl
    raw_hash: str


class EvidenceCalculation(BaseModel):
    fingerprint: str
    operation: str
    expression: str
    input_series_ids: list[str]
    input_observation_dates: list[str]
    inputs: dict[str, float]
    result: float
    unit: str


class EvidenceCitation(BaseModel):
    source: str
    source_url: HttpUrl
    series_id: str
    observation_date: str
    raw_hash: str
    calculation_fingerprint: str | None = None


class EvidenceClaim(BaseModel):
    fingerprint: str
    text: str
    kind: ClaimKind
    citations: list[EvidenceCitation]
    calculation: EvidenceCalculation | None = None


class EvidencePack(BaseModel):
    schema_version: str = EVIDENCE_SCHEMA_VERSION
    sku: str
    metering_unit: str = "evidence_pack"
    report_type: str
    title: str
    as_of: str
    generated_at: datetime
    data_source: str | None = None
    source_fetched_at: datetime | None = None
    freshness: DatasetFreshness
    claims: list[EvidenceClaim]
    observations: list[EvidenceObservation]
    evidence_sha256: str


@dataclass(frozen=True)
class _ProductDefinition:
    sku: str
    name: str
    description: str
    builder: Callable[[list[Observation]], Report]
    product_kind: str = "brief"
    series_id: str | None = None


def _fact_builder(spec: FactProductSpec) -> Callable[[list[Observation]], Report]:
    def build(observations: list[Observation]) -> Report:
        return SeriesFactBrief(spec).build(observations)

    return build


_PRODUCT_DEFINITIONS = (
    _ProductDefinition(
        sku="weekly-petroleum-evidence",
        name="Weekly Petroleum Evidence Pack",
        description=(
            "Broad weekly U.S. petroleum fundamentals packaged as deterministic claims, "
            "calculations, citations, and source hashes."
        ),
        builder=lambda observations: WeeklyPetroleumBrief().build(observations),
    ),
    _ProductDefinition(
        sku="weekly-petroleum-delta",
        name="Weekly Petroleum Delta",
        description=(
            "Current-release week-over-week petroleum changes only, with exact prior/current "
            "citations and deterministic calculation traces."
        ),
        builder=lambda observations: WeeklyPetroleumDelta().build(observations),
        product_kind="delta",
    ),
    _ProductDefinition(
        sku="distillate-risk-evidence",
        name="Distillate Risk Evidence Pack",
        description=(
            "PADD 2 distillate inventory and U.S. distillate product-supplied evidence "
            "for downstream supply-risk agents."
        ),
        builder=lambda observations: DistillateSupplyRiskBrief().build(observations),
    ),
    _ProductDefinition(
        sku="refinery-utilization-evidence",
        name="Refinery Utilization Evidence Pack",
        description=(
            "U.S. refinery utilization evidence with deterministic change calculations "
            "and source-level provenance."
        ),
        builder=lambda observations: RefineryUtilizationWatch().build(observations),
    ),
    _ProductDefinition(
        sku="crude-balance-evidence",
        name="Crude Balance Evidence Pack",
        description=(
            "Partial U.S. crude-flow reconciliation with production, imports, exports, "
            "refinery input, stock change, and adjustment residual evidence."
        ),
        builder=lambda observations: CrudeBalanceWatch().build(observations),
    ),
    *(
        _ProductDefinition(
            sku=spec.sku,
            name=spec.name,
            description=spec.description,
            builder=_fact_builder(spec),
            product_kind="fact",
            series_id=spec.series_id,
        )
        for spec in FACT_PRODUCT_SPECS
    ),
)

_PRODUCT_BY_SKU = {definition.sku: definition for definition in _PRODUCT_DEFINITIONS}


def build_agent_catalog(
    *,
    unit_price_usd: Decimal | None = None,
    currency: str = "USD",
) -> AgentCatalog:
    price = _price(unit_price_usd, currency)
    products = [
        AgentProduct(
            sku=definition.sku,
            name=definition.name,
            description=definition.description,
            product_kind=definition.product_kind,
            series_id=definition.series_id,
            state_path=f"/api/agent/products/{definition.sku}/state",
            evidence_path=f"/api/agent/products/{definition.sku}/evidence",
            quote_path=f"/api/agent/products/{definition.sku}/quote",
            evidence_guarantees=[
                "freshness_checked_before_fulfillment",
                "every_numeric_claim_cited",
                "derived_claims_include_calculation_trace",
                "cited_observations_include_raw_source_hash",
                "evidence_sha256_stable_for_equivalent_evidence",
                *(
                    ["current_event_week_only", "week_over_week_changes_only"]
                    if definition.product_kind == "delta"
                    else []
                ),
                *(["maintained_series_only"] if definition.series_id else []),
            ],
            price=price,
        )
        for definition in _PRODUCT_DEFINITIONS
    ]
    return AgentCatalog(products=products)


def quote_agent_product(
    sku: str,
    *,
    unit_price_usd: Decimal | None = None,
    currency: str = "USD",
) -> AgentQuote:
    definition = _definition(sku)
    price = _price(unit_price_usd, currency)
    return AgentQuote(
        sku=definition.sku,
        available_for_purchase=price is not None,
        price=price,
        fulfillment_path=f"/api/agent/products/{definition.sku}/evidence",
        payment_enforcement="external" if price is not None else "not_configured",
    )


def build_evidence_pack(
    sku: str,
    observations: list[Observation],
    *,
    freshness: DatasetFreshness,
    data_source: str | None,
    source_fetched_at: datetime | None,
    generated_at: datetime | None = None,
) -> EvidencePack:
    definition = _definition(sku)
    report = definition.builder(observations)
    observation_map = {
        (row.series_id, row.observation_date.isoformat()): row for row in observations
    }

    claims: list[EvidenceClaim] = []
    cited_keys: set[tuple[str, str]] = set()
    for claim in report.iter_claims():
        evidence_claim, claim_keys = _evidence_claim(claim, observation_map)
        claims.append(evidence_claim)
        cited_keys.update(claim_keys)

    evidence_observations = [
        _evidence_observation(observation_map[key])
        for key in sorted(cited_keys, key=lambda item: (item[0], item[1]))
    ]
    freshness_semantics = _freshness_semantics(freshness)
    semantic_payload = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "sku": sku,
        "report_type": report.report_type,
        "title": report.title,
        "as_of": report.as_of.isoformat(),
        "data_source": data_source,
        "freshness": freshness_semantics,
        "claims": [claim.model_dump(mode="json") for claim in claims],
        "observations": [row.model_dump(mode="json") for row in evidence_observations],
    }
    digest = _fingerprint(semantic_payload)
    return EvidencePack(
        sku=sku,
        report_type=report.report_type,
        title=report.title,
        as_of=report.as_of.isoformat(),
        generated_at=generated_at or datetime.now(UTC),
        data_source=data_source,
        source_fetched_at=source_fetched_at,
        freshness=freshness,
        claims=claims,
        observations=evidence_observations,
        evidence_sha256=digest,
    )


def product_exists(sku: str) -> bool:
    return sku in _PRODUCT_BY_SKU


def _definition(sku: str) -> _ProductDefinition:
    try:
        return _PRODUCT_BY_SKU[sku]
    except KeyError as exc:
        raise ValueError(f"unknown agent product: {sku}") from exc


def _price(amount: Decimal | None, currency: str) -> AgentPrice | None:
    if amount is None:
        return None
    if amount < 0:
        raise ValueError("agent evidence pack price cannot be negative")
    return AgentPrice(amount=amount, currency=currency.upper())


def _evidence_claim(
    claim: Claim,
    observation_map: dict[tuple[str, str], Observation],
) -> tuple[EvidenceClaim, set[tuple[str, str]]]:
    calculation = _evidence_calculation(claim.calculation) if claim.calculation else None
    cited_keys: set[tuple[str, str]] = set()
    citations: list[EvidenceCitation] = []
    for citation in sorted(
        claim.citations,
        key=lambda item: (item.series_id, item.observation_date.isoformat(), str(item.source_url)),
    ):
        key = (citation.series_id, citation.observation_date.isoformat())
        row = observation_map.get(key)
        if row is None:
            raise ValueError(
                "report citation does not resolve to ingested evidence: "
                f"{citation.series_id} {citation.observation_date.isoformat()}"
            )
        cited_keys.add(key)
        citations.append(
            EvidenceCitation(
                source=citation.source,
                source_url=citation.source_url,
                series_id=citation.series_id,
                observation_date=citation.observation_date.isoformat(),
                raw_hash=row.raw_hash,
                calculation_fingerprint=calculation.fingerprint if calculation else None,
            )
        )

    semantics = {
        "text": claim.text,
        "kind": claim.kind.value,
        "citations": [citation.model_dump(mode="json") for citation in citations],
        "calculation": calculation.model_dump(mode="json") if calculation else None,
    }
    return (
        EvidenceClaim(
            fingerprint=_fingerprint(semantics),
            text=claim.text,
            kind=claim.kind,
            citations=citations,
            calculation=calculation,
        ),
        cited_keys,
    )


def _evidence_calculation(trace: CalculationTrace) -> EvidenceCalculation:
    input_dates = [item.isoformat() for item in trace.input_observation_dates]
    semantics = {
        "operation": trace.operation,
        "expression": trace.expression,
        "input_series_ids": trace.input_series_ids,
        "input_observation_dates": input_dates,
        "inputs": trace.inputs,
        "result": trace.result,
        "unit": trace.unit,
    }
    return EvidenceCalculation(
        fingerprint=_fingerprint(semantics),
        operation=trace.operation,
        expression=trace.expression,
        input_series_ids=trace.input_series_ids,
        input_observation_dates=input_dates,
        inputs=trace.inputs,
        result=trace.result,
        unit=trace.unit,
    )


def _evidence_observation(row: Observation) -> EvidenceObservation:
    return EvidenceObservation(
        series_id=row.series_id,
        metric=row.metric,
        product=row.product,
        geography=row.geography,
        frequency=row.frequency.value,
        unit=row.unit,
        observation_date=row.observation_date.isoformat(),
        value=row.value,
        source_url=row.source_url,
        raw_hash=row.raw_hash,
    )


def _freshness_semantics(freshness: DatasetFreshness) -> dict[str, object]:
    return {
        "status": freshness.status.value,
        "latest_observation": (
            freshness.latest_observation.isoformat() if freshness.latest_observation else None
        ),
        "expected_week_ending": (
            freshness.expected_week_ending.isoformat() if freshness.expected_week_ending else None
        ),
        "stale_series": freshness.stale_series,
        "live_series_count": freshness.live_series_count,
    }


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()
    return sha256(encoded).hexdigest()
