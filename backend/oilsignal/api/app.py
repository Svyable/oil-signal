from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from oilsignal.alerts.engine import (
    AlertEvaluationResult,
    AlertPolicySet,
    StatefulAlertEvaluationResult,
    evaluate_policies,
    evaluate_policies_with_state,
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
from oilsignal.reports.specialized import DistillateSupplyRiskBrief, RefineryUtilizationWatch
from oilsignal.reports.weekly import WeeklyPetroleumBrief
from oilsignal.storage.datasets import inspect_data, load_latest_observations


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


def _deterministic_answer(question: str, observations: list[Observation]) -> AskResponse:
    normalized = question.lower()
    if any(token in normalized for token in ("diesel", "distillate", "midwest", "padd 2")):
        series_id = "PET.DISTP2.W"
        label = "PADD 2 distillate stocks"
    elif any(token in normalized for token in ("refinery", "utilization")):
        series_id = "PET.UTILUS.W"
        label = "U.S. refinery utilization"
    else:
        series_id = "PET.CRDUUS.W"
        label = "U.S. crude oil stocks"

    rows = sorted(
        [row for row in observations if row.series_id == series_id],
        key=lambda row: row.observation_date,
    )
    if not rows:
        raise ValueError(f"no evidence available for {series_id}")
    snapshot = build_snapshot(rows, series_id)
    current = rows[-1]
    evidence = [_citation(current)]
    change_text = "No prior observation is available."
    if snapshot.week_over_week:
        prior_date = min(snapshot.week_over_week.input_observation_dates)
        prior = next(row for row in rows if row.observation_date == prior_date)
        evidence = [
            _citation(current, snapshot.week_over_week.calculation_id),
            _citation(prior, snapshot.week_over_week.calculation_id),
        ]
        change = snapshot.week_over_week.result
        direction = "up" if change > 0 else "down" if change < 0 else "unchanged"
        change_text = f"That is {direction} {abs(change):,.1f} {snapshot.unit} week over week."
    answer = (
        f"{label} were {snapshot.current:,.1f} {snapshot.unit} as of "
        f"{snapshot.as_of.isoformat()}. {change_text}"
    )
    return AskResponse(answer=answer, evidence=evidence)


def create_app(data_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="OilSignal API", version="0.2.0")
    app.state.data_dir = data_dir or settings.data_dir
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def current_observations() -> list[Observation]:
        data_status = inspect_data(app.state.data_dir)
        observations = load_latest_observations(app.state.data_dir)
        require_fresh_wpsr(observations, live_eia=data_status.is_live_eia)
        return observations

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
