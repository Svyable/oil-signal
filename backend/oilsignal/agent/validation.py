from __future__ import annotations

import re

from oilsignal.models import Claim, Report


NUMERIC_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?%?")


class ClaimValidationError(ValueError):
    """Raised when a generated market claim cannot be audited back to evidence."""


def validate_claim(claim: Claim) -> None:
    has_number = bool(NUMERIC_PATTERN.search(claim.text))
    if not claim.citations:
        qualifier = " numerical" if has_number else ""
        raise ClaimValidationError(f"uncited{qualifier} claim: {claim.claim_id}: {claim.text}")

    if claim.calculation:
        calculation_id = claim.calculation.calculation_id
        if not any(citation.calculation_id == calculation_id for citation in claim.citations):
            raise ClaimValidationError(
                f"claim {claim.claim_id} has calculation {calculation_id} without a linked citation"
            )


def validate_report(report: Report) -> Report:
    claims = report.iter_claims()
    if not claims:
        raise ClaimValidationError("report contains no claims")
    for claim in claims:
        validate_claim(claim)
    return report
