from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from oilsignal.analytics.petroleum import build_snapshot
from oilsignal.config import settings
from oilsignal.data_ingestion.fixtures import load_observations
from oilsignal.models import Citation, Observation, Report
from oilsignal.reports.renderers import render_report
from oilsignal.reports.specialized import DistillateSupplyRiskBrief, RefineryUtilizationWatch
from oilsignal.reports.weekly import WeeklyPetroleumBrief


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskResponse(BaseModel):
    answer: str
    evidence: list[Citation]
    mode: str = "deterministic"


class RenderedReport(BaseModel):
    format: str
    content: str


def _latest_parquet(data_dir: Path) -> Path:
    paths = list((data_dir / "parquet").glob("*.parquet"))
    if not paths:
        raise FileNotFoundError("no ingested Parquet data found")
    return max(paths, key=lambda path: path.stat().st_mtime_ns)


def _load_latest(data_dir: Path) -> list[Observation]:
    return load_observations(_latest_parquet(data_dir))


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
    app = FastAPI(title="OilSignal API", version="0.1.0")
    app.state.data_dir = data_dir or settings.data_dir
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/reports/weekly", response_model=Report)
    def weekly_report() -> Report:
        try:
            return WeeklyPetroleumBrief().build(_load_latest(app.state.data_dir))
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/reports/distillate", response_model=Report)
    def distillate_report() -> Report:
        try:
            return DistillateSupplyRiskBrief().build(_load_latest(app.state.data_dir))
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/reports/refinery-utilization", response_model=Report)
    def refinery_report() -> Report:
        try:
            return RefineryUtilizationWatch().build(_load_latest(app.state.data_dir))
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/reports/weekly/render", response_model=RenderedReport)
    def weekly_report_render(format: str = "markdown") -> RenderedReport:
        if format not in {"markdown", "md", "html", "json"}:
            raise HTTPException(status_code=422, detail=f"unsupported report format: {format}")
        try:
            report = WeeklyPetroleumBrief().build(_load_latest(app.state.data_dir))
            return RenderedReport(format=format, content=render_report(report, format))
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/ask", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        try:
            return _deterministic_answer(request.question, _load_latest(app.state.data_dir))
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


app = create_app()
