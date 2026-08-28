from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from oilsignal.agent.products import (
    AgentCatalog,
    AgentQuote,
    build_agent_catalog,
    build_evidence_pack,
    product_exists,
    quote_agent_product,
)
from oilsignal.alerts.engine import (
    AlertEvaluationResult,
    AlertPolicySet,
    StatefulAlertEvaluationResult,
    evaluate_policies,
    evaluate_policies_with_state,
)
from oilsignal.analytics.crude_balance import (
    CRUDE_EXPORTS,
    CRUDE_IMPORTS,
    CRUDE_PRODUCTION,
    CRUDE_REFINERY_INPUT,
    build_crude_balance,
)
from oilsignal.analytics.petroleum import build_snapshot
from oilsignal.config import settings
from oilsignal.freshness import (
    DatasetFreshness,
    FreshnessState,
    check_wpsr_freshness,
    require_fresh_wpsr,
)
from oilsignal.models import Citation, Observation, Report
from oilsignal.reports.renderers import render_report
from oilsignal.reports.specialized import (
    CrudeBalanceWatch,
    DistillateSupplyRiskBrief,
    RefineryUtilizationWatch,
)
from oilsignal.reports.weekly import WeeklyPetroleumBrief
from oilsignal.storage.datasets import DataStatus, inspect_data, load_latest_observations


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskResponse(BaseModel):
    answer: str
    evidence: list[Citation]
    mode: str = "deterministic"


class RenderedReport(BaseModel):
    format: str
    content: str


class ReadinessResponse(BaseModel):
    status: str
    data_available: bool
    series_count: int
    observation_count: int
    latest_observation: str | None = None
    latest_fetched_at: str | None = None
    freshness: DatasetFreshness | None = None


def _citation(row: Observation, calculation_id: str | None = None) -> Citation:
    return Citation(
        source_url=row.source_url,
        series_id=row.series_id,
        observation_date=row.observation_date,
        calculation_id=calculation_id,
    )


def _question_series(question: str) -> tuple[str, str]:
    normalized = question.lower()
    demand_intent = any(
        token in normalized
        for token in ("demand", "product supplied", "consumption", "consumed", "usage")
    )
    if demand_intent:
        if any(token in normalized for token in ("gasoline", "motor gas", "gas demand")):
            return "PET.GASPSUS.W", "U.S. finished motor gasoline product supplied"
        if any(token in normalized for token in ("diesel", "distillate")):
            return "PET.DISTPSUS.W", "U.S. distillate product supplied"
        if any(token in normalized for token in ("jet", "aviation")):
            return "PET.JETPSUS.W", "U.S. jet fuel product supplied"
        return "PET.TOTALPSUS.W", "U.S. petroleum products supplied"

    if any(token in normalized for token in ("diesel", "distillate", "midwest", "padd 2")):
        return "PET.DISTP2.W", "PADD 2 distillate stocks"
    if any(token in normalized for token in ("crude production", "field production")):
        return CRUDE_PRODUCTION, "U.S. crude oil field production"
    if any(token in normalized for token in ("crude export", "crude exports")):
        return CRUDE_EXPORTS, "U.S. crude oil exports"
    if any(token in normalized for token in ("refinery input", "refiner input", "crude input")):
        return CRUDE_REFINERY_INPUT, "U.S. refiner net input of crude oil"
    if any(token in normalized for token in ("refinery", "utilization")):
        return "PET.UTILUS.W", "U.S. refinery utilization"
    if any(token in normalized for token in ("gasoline", "motor gas")):
        return "PET.GASUS.W", "U.S. total gasoline stocks"
    if any(token in normalized for token in ("jet", "aviation")):
        return "PET.JETUS.W", "U.S. jet fuel stocks"
    if any(token in normalized for token in ("import", "imports")):
        return CRUDE_IMPORTS, "U.S. crude oil imports"
    return "PET.CRDUUS.W", "U.S. crude oil stocks"


def _deterministic_answer(question: str, observations: list[Observation]) -> AskResponse:
    normalized = question.lower()
    if "crude" in normalized and "balance" in normalized:
        balance_snapshot = build_crude_balance(observations)
        trace = balance_snapshot.core_flow_balance
        evidence = [
            _citation(
                next(
                    row
                    for row in observations
                    if row.series_id == series_id
                    and row.observation_date == balance_snapshot.as_of
                ),
                trace.calculation_id,
            )
            for series_id in (
                CRUDE_PRODUCTION,
                CRUDE_IMPORTS,
                CRUDE_EXPORTS,
                CRUDE_REFINERY_INPUT,
            )
        ]
        return AskResponse(
            answer=(
                f"Core crude flow balance was {trace.result:+,.1f} {trace.unit} as of "
                f"{balance_snapshot.as_of.isoformat()}, calculated as production plus imports "
                "minus exports and refinery input. This is a partial deterministic "
                "reconciliation, not an official EIA balance identity."
            ),
            evidence=evidence,
        )

    series_id, label = _question_series(question)
    rows = sorted(
        [row for row in observations if row.series_id == series_id],
        key=lambda row: row.observation_date,
    )
    if not rows:
        raise ValueError(f"no evidence available for {series_id}")
    series_snapshot = build_snapshot(rows, series_id)
    current = rows[-1]
    evidence = [_citation(current)]
    change_text = "No prior observation is available."
    if series_snapshot.week_over_week:
        prior_date = min(series_snapshot.week_over_week.input_observation_dates)
        prior = next(row for row in rows if row.observation_date == prior_date)
        evidence = [
            _citation(current, series_snapshot.week_over_week.calculation_id),
            _citation(prior, series_snapshot.week_over_week.calculation_id),
        ]
        change = series_snapshot.week_over_week.result
        direction = "up" if change > 0 else "down" if change < 0 else "unchanged"
        change_text = (
            f"That is {direction} {abs(change):,.1f} "
            f"{series_snapshot.unit} week over week."
        )
    answer = (
        f"{label} were {series_snapshot.current:,.1f} {series_snapshot.unit} as of "
        f"{series_snapshot.as_of.isoformat()}. {change_text}"
    )
    return AskResponse(answer=answer, evidence=evidence)


def _etag_opaque_value(etag: str) -> str:
    return etag[2:] if etag.startswith("W/") else etag


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    expected = _etag_opaque_value(etag)
    candidates = {item.strip() for item in if_none_match.split(",")}
    return "*" in candidates or any(_etag_opaque_value(item) == expected for item in candidates)


def create_app(
    data_dir: Path | None = None,
    *,
    agent_unit_price_usd: Decimal | None = None,
) -> FastAPI:
    app = FastAPI(title="OilSignal API", version="0.2.0")
    app.state.data_dir = data_dir or settings.data_dir
    app.state.agent_unit_price_usd = (
        agent_unit_price_usd
        if agent_unit_price_usd is not None
        else settings.agent_evidence_pack_price_usd
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def current_evidence_context() -> tuple[list[Observation], DataStatus, DatasetFreshness]:
        data_status = inspect_data(app.state.data_dir)
        observations = load_latest_observations(app.state.data_dir)
        freshness = require_fresh_wpsr(observations, live_eia=data_status.is_live_eia)
        return observations, data_status, freshness

    def current_observations() -> list[Observation]:
        observations, _, _ = current_evidence_context()
        return observations

    def agent_catalog() -> AgentCatalog:
        return build_agent_catalog(
            unit_price_usd=app.state.agent_unit_price_usd,
            currency=settings.agent_price_currency,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", response_model=ReadinessResponse)
    def readiness(response: Response) -> ReadinessResponse:
        data_status = inspect_data(app.state.data_dir)
        freshness: DatasetFreshness | None = None
        ready = data_status.available
        if data_status.available:
            freshness = check_wpsr_freshness(
                load_latest_observations(app.state.data_dir),
                live_eia=data_status.is_live_eia,
            )
            ready = freshness.status != FreshnessState.STALE
        if not ready:
            response.status_code = 503
        return ReadinessResponse(
            status="ready" if ready else "not_ready",
            data_available=data_status.available,
            series_count=data_status.series_count,
            observation_count=data_status.observation_count,
            latest_observation=(
                data_status.latest_observation.isoformat()
                if data_status.latest_observation
                else None
            ),
            latest_fetched_at=(
                data_status.latest_fetched_at.isoformat() if data_status.latest_fetched_at else None
            ),
            freshness=freshness,
        )

    @app.get("/.well-known/oilsignal-agent.json", response_model=AgentCatalog)
    def agent_discovery() -> AgentCatalog:
        return agent_catalog()

    @app.get("/api/agent/products", response_model=AgentCatalog)
    def agent_products() -> AgentCatalog:
        return agent_catalog()

    @app.get("/api/agent/products/{sku}/quote", response_model=AgentQuote)
    def agent_quote(sku: str) -> AgentQuote:
        if not product_exists(sku):
            raise HTTPException(status_code=404, detail=f"unknown agent product: {sku}")
        return quote_agent_product(
            sku,
            unit_price_usd=app.state.agent_unit_price_usd,
            currency=settings.agent_price_currency,
        )

    @app.get(
        "/api/agent/products/{sku}/evidence",
        response_model=None,
        responses={304: {"description": "Semantic evidence unchanged for supplied ETag"}},
    )
    def agent_evidence(sku: str, request: Request) -> Response:
        if not product_exists(sku):
            raise HTTPException(status_code=404, detail=f"unknown agent product: {sku}")
        try:
            observations, data_status, freshness = current_evidence_context()
            pack = build_evidence_pack(
                sku,
                observations,
                freshness=freshness,
                data_source=data_status.source,
                source_fetched_at=data_status.latest_fetched_at,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        etag = f'W/"sha256:{pack.evidence_sha256}"'
        headers = {
            "ETag": etag,
            "Cache-Control": "private, max-age=0, must-revalidate",
            "X-OilSignal-Evidence-SHA256": pack.evidence_sha256,
            "X-OilSignal-SKU": pack.sku,
        }
        if _etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)
        return JSONResponse(content=pack.model_dump(mode="json"), headers=headers)

    @app.get("/api/reports/weekly", response_model=Report)
    def weekly_report() -> Report:
        try:
            return WeeklyPetroleumBrief().build(current_observations())
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/reports/distillate", response_model=Report)
    def distillate_report() -> Report:
        try:
            return DistillateSupplyRiskBrief().build(current_observations())
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/reports/refinery-utilization", response_model=Report)
    def refinery_report() -> Report:
        try:
            return RefineryUtilizationWatch().build(current_observations())
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/reports/crude-balance", response_model=Report)
    def crude_balance_report() -> Report:
        try:
            return CrudeBalanceWatch().build(current_observations())
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/reports/weekly/render", response_model=RenderedReport)
    def weekly_report_render(format: str = "markdown") -> RenderedReport:
        if format not in {"markdown", "md", "html", "json"}:
            raise HTTPException(status_code=422, detail=f"unsupported report format: {format}")
        try:
            report = WeeklyPetroleumBrief().build(current_observations())
            return RenderedReport(format=format, content=render_report(report, format))
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/alerts/evaluate", response_model=AlertEvaluationResult)
    def alert_evaluation(policy_set: AlertPolicySet) -> AlertEvaluationResult:
        try:
            return evaluate_policies(current_observations(), policy_set)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/alerts/evaluate/stateful", response_model=StatefulAlertEvaluationResult)
    def stateful_alert_evaluation(policy_set: AlertPolicySet) -> StatefulAlertEvaluationResult:
        try:
            return evaluate_policies_with_state(
                current_observations(),
                policy_set,
                app.state.data_dir / "metadata.sqlite",
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/ask", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        try:
            return _deterministic_answer(request.question, current_observations())
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


app = create_app()
