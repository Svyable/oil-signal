from datetime import date

from oilsignal.models import (
    CalculationTrace,
    Citation,
    Claim,
    ClaimKind,
    Frequency,
    Observation,
)

SOURCE = "https://api.eia.gov/v2/petroleum/example"


def test_observation_accepts_typed_petroleum_fact() -> None:
    observation = Observation(
        series_id="PET.WCESTUS1.W",
        metric="stocks",
        product="crude_oil",
        frequency=Frequency.WEEKLY,
        unit="thousand barrels",
        observation_date=date(2026, 8, 21),
        value=418_200,
        source_url=SOURCE,
        raw_hash="abc123",
    )
    assert observation.geography == "US"
    assert observation.value == 418_200


def test_calculation_citation_is_linked_to_trace() -> None:
    trace = CalculationTrace(
        operation="week_over_week",
        expression="current - prior",
        input_series_ids=["PET.WCESTUS1.W"],
        input_observation_dates=[date(2026, 8, 21), date(2026, 8, 14)],
        inputs={"current": 418_200, "prior": 416_700},
        result=1_500,
        unit="thousand barrels",
    )
    claim = Claim(
        text="U.S. crude stocks increased by 1,500 thousand barrels week over week.",
        kind=ClaimKind.NUMERIC,
        citations=[
            Citation(
                source_url=SOURCE,
                series_id="PET.WCESTUS1.W",
                observation_date=date(2026, 8, 21),
            )
        ],
        calculation=trace,
    )
    assert claim.citations[0].calculation_id == trace.calculation_id
