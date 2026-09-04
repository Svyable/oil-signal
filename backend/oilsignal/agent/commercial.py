from __future__ import annotations

from pydantic import BaseModel, Field

from oilsignal.agent.products import product_exists

COMMERCIAL_SCHEMA_VERSION = "1.0"


class IdealCustomerProfile(BaseModel):
    id: str
    name: str
    buyer_roles: list[str]
    operating_context: str
    trigger_events: list[str]
    value_hypotheses: list[str]


class CommercialSolution(BaseModel):
    id: str
    name: str
    buyer_roles: list[str]
    decision: str
    problem: str
    recommended_skus: list[str]
    quote_paths: list[str]
    delivery_modes: list[str]
    proof_points: list[str]
    pilot_success_metrics: list[str]


class PilotMotion(BaseModel):
    name: str = "Founding customer evidence pilot"
    evaluation_window: str = "2-4 weekly release cycles"
    entry_offer: str = (
        "Start with one operational decision and a narrow set of evidence SKUs, then expand only "
        "after the buyer can measure value."
    )
    phases: list[str] = Field(
        default_factory=lambda: [
            "baseline the current manual workflow and evidence sources",
            "run OilSignal in parallel on the same weekly release cycles",
            "measure speed, auditability, freshness failures, and analyst effort",
            "convert the proven workflow into recurring API, alert, or hosted delivery",
        ]
    )
    success_metrics: list[str] = Field(
        default_factory=lambda: [
            "release-to-decision-support latency",
            "analyst minutes required per weekly release",
            "share of material numeric claims with source-level evidence",
            "number of stale or unverifiable outputs blocked before use",
            "number of recurring downstream workflows automated from the same evidence contract",
        ]
    )


class CommercialCatalog(BaseModel):
    schema_version: str = COMMERCIAL_SCHEMA_VERSION
    service: str = "OilSignal"
    category: str = "evidence-first petroleum decision support"
    positioning: str = (
        "Turn public U.S. petroleum fundamentals into fast, auditable decision support for humans "
        "and software agents without hiding the calculation chain."
    )
    product_catalog_path: str = "/.well-known/oilsignal-agent.json"
    change_manifest_path: str = "/api/agent/manifest"
    openapi_path: str = "/openapi.json"
    ideal_customer_profiles: list[IdealCustomerProfile]
    solutions: list[CommercialSolution]
    pilot: PilotMotion = Field(default_factory=PilotMotion)


def _solution(
    *,
    id: str,
    name: str,
    buyer_roles: list[str],
    decision: str,
    problem: str,
    recommended_skus: list[str],
    delivery_modes: list[str],
    proof_points: list[str],
    pilot_success_metrics: list[str],
) -> CommercialSolution:
    unknown = sorted(sku for sku in recommended_skus if not product_exists(sku))
    if unknown:
        raise ValueError(f"commercial solution {id} references unknown SKUs: {', '.join(unknown)}")
    return CommercialSolution(
        id=id,
        name=name,
        buyer_roles=buyer_roles,
        decision=decision,
        problem=problem,
        recommended_skus=recommended_skus,
        quote_paths=[f"/api/agent/products/{sku}/quote" for sku in recommended_skus],
        delivery_modes=delivery_modes,
        proof_points=proof_points,
        pilot_success_metrics=pilot_success_metrics,
    )


def build_commercial_catalog() -> CommercialCatalog:
    profiles = [
        IdealCustomerProfile(
            id="downstream-operator",
            name="Downstream fuel operator",
            buyer_roles=["fuel procurement", "regional marketing", "terminal operations", "treasury"],
            operating_context=(
                "Teams exposed to weekly changes in gasoline, distillate, refinery, and regional "
                "supply conditions that need an auditable read before making operational decisions."
            ),
            trigger_events=[
                "weekly EIA petroleum release",
                "regional inventory tightness",
                "refinery utilization disruption",
                "procurement or allocation review",
            ],
            value_hypotheses=[
                "reduce time spent assembling weekly fundamentals",
                "make supply-risk discussions traceable to source observations",
                "block stale evidence before it reaches an operational brief",
            ],
        ),
        IdealCustomerProfile(
            id="market-analyst",
            name="Petroleum analyst or consultant",
            buyer_roles=["market analyst", "consultant", "research lead"],
            operating_context=(
                "Analysts who repeatedly reconcile crude flows, inventories, refinery activity, "
                "and demand proxies and need calculations that can be reproduced and cited."
            ),
            trigger_events=[
                "weekly balance review",
                "client briefing",
                "research note preparation",
                "large crude-flow or inventory move",
            ],
            value_hypotheses=[
                "shorten repetitive evidence gathering",
                "make calculations reproducible across analysts and clients",
                "separate modeled reconciliation residuals from unsupported narrative claims",
            ],
        ),
        IdealCustomerProfile(
            id="agent-data-buyer",
            name="Agent or automation builder",
            buyer_roles=["AI product", "automation engineering", "data platform"],
            operating_context=(
                "Software teams that need small, typed petroleum facts or deltas with stable "
                "identity, provenance, cache semantics, and optional machine commerce."
            ),
            trigger_events=[
                "agent tool integration",
                "weekly automated monitoring",
                "evidence cache invalidation",
                "usage-priced data procurement",
            ],
            value_hypotheses=[
                "avoid scraping dashboards or parsing narrative reports",
                "pay only when commercial state and semantic evidence require fulfillment",
                "verify archived evidence independently with source hashes and optional signatures",
            ],
        ),
    ]

    shared_proof = [
        "release-aware freshness checks fail closed for stale live WPSR evidence",
        "numeric claims carry source citations",
        "derived claims carry deterministic calculation traces",
        "cited observations carry raw-source hashes",
    ]

    solutions = [
        _solution(
            id="downstream-supply-risk",
            name="Downstream Supply Risk",
            buyer_roles=["fuel procurement", "regional marketing", "terminal operations", "treasury"],
            decision=(
                "Assess whether weekly inventory, refinery, and demand changes warrant closer "
                "procurement, allocation, or regional supply attention."
            ),
            problem=(
                "Weekly petroleum releases are public but fragmented; teams still spend time "
                "assembling the same facts and defending where each number came from."
            ),
            recommended_skus=[
                "weekly-petroleum-delta",
                "distillate-risk-evidence",
                "fact-padd2-distillate-stocks",
                "fact-us-refinery-utilization",
                "fact-us-distillate-product-supplied",
            ],
            delivery_modes=["JSON API", "cited brief", "alert workflow", "self-hosted automation"],
            proof_points=[*shared_proof, "PADD 2 distillate risk is available as a focused evidence product"],
            pilot_success_metrics=[
                "minutes from release availability to an auditable supply-risk read",
                "manual analyst steps removed from the weekly workflow",
                "share of reviewed claims accepted without separate source lookup",
            ],
        ),
        _solution(
            id="crude-flow-reconciliation",
            name="Crude Flow Reconciliation",
            buyer_roles=["market analyst", "consultant", "research lead"],
            decision=(
                "Explain how crude production, imports, exports, refinery input, and commercial "
                "stock change line up in the current weekly release."
            ),
            problem=(
                "Crude-flow narratives are easy to overstate when component dates, units, or the "
                "unmodeled residual are not explicit."
            ),
            recommended_skus=[
                "crude-balance-evidence",
                "fact-us-crude-production",
                "fact-us-crude-imports",
                "fact-us-crude-exports",
                "fact-us-crude-refinery-input",
                "fact-us-crude-stocks",
            ],
            delivery_modes=["JSON API", "cited brief", "research workflow", "self-hosted automation"],
            proof_points=[
                *shared_proof,
                "the crude balance is labeled as a partial deterministic reconciliation rather than an official EIA identity",
                "the other/adjustment residual remains explicit instead of being explained away",
            ],
            pilot_success_metrics=[
                "time required to reproduce the weekly crude-flow calculation",
                "number of reconciliation steps that remain manual",
                "number of client or internal claims that can be traced directly to calculation inputs",
            ],
        ),
        _solution(
            id="agent-ready-petroleum-evidence",
            name="Agent-ready Petroleum Evidence",
            buyer_roles=["AI product", "automation engineering", "data platform"],
            decision=(
                "Consume only the petroleum facts or deltas an automated workflow needs, with "
                "machine-verifiable state and evidence identity."
            ),
            problem=(
                "Agents should not have to scrape a human dashboard, repurchase unchanged data, "
                "or trust uncited model prose for petroleum fundamentals."
            ),
            recommended_skus=[
                "weekly-petroleum-delta",
                "fact-us-crude-stocks",
                "fact-us-gasoline-stocks",
                "fact-us-distillate-stocks",
                "fact-us-refinery-utilization",
            ],
            delivery_modes=["JSON API", "ETag polling", "catalog manifest", "HTTP 402 gateway"],
            proof_points=[
                *shared_proof,
                "catalog-wide state manifest supports cheap change polling",
                "semantic evidence ETags allow free unchanged-data revalidation before payment verification",
                "optional Ed25519 signatures bind portable evidence identities to an operator key",
            ],
            pilot_success_metrics=[
                "integration time from discovery to first verified evidence fetch",
                "percentage of polling cycles resolved without full evidence transfer",
                "number of manual parsing or provenance steps removed from the consuming agent",
            ],
        ),
    ]
    return CommercialCatalog(ideal_customer_profiles=profiles, solutions=solutions)
