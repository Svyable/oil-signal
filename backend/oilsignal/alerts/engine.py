from __future__ import annotations

import json
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from oilsignal.alerts.rules import MetricField, Operator, ThresholdRule
from oilsignal.analytics.petroleum import SeriesSnapshot, build_snapshot
from oilsignal.models import Observation


class MatchMode(StrEnum):
    ALL = "all"
    ANY = "any"


class ConditionEvaluation(BaseModel):
    rule_id: str
    series_id: str
    field: MetricField
    operator: Operator
    threshold: float
    value: float | None
    matched: bool
    as_of: date | None


class AlertPolicy(BaseModel):
    policy_id: str
    name: str
    message: str
    mode: MatchMode = MatchMode.ALL
    conditions: list[ThresholdRule] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_condition_ids(self) -> AlertPolicy:
        ids = [condition.rule_id for condition in self.conditions]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate condition IDs in policy {self.policy_id}: {duplicates}")
        return self

    def evaluate(self, snapshots: dict[str, SeriesSnapshot]) -> PolicyEvaluation:
        condition_results: list[ConditionEvaluation] = []
        for condition in self.conditions:
            snapshot = snapshots.get(condition.series_id)
            value = condition.read_value(snapshot) if snapshot else None
            condition_results.append(
                ConditionEvaluation(
                    rule_id=condition.rule_id,
                    series_id=condition.series_id,
                    field=condition.field,
                    operator=condition.operator,
                    threshold=condition.threshold,
                    value=value,
                    matched=condition.matches(snapshot) if snapshot else False,
                    as_of=snapshot.as_of if snapshot else None,
                )
            )
        matches = [result.matched for result in condition_results]
        matched = all(matches) if self.mode == MatchMode.ALL else any(matches)
        dates = [result.as_of for result in condition_results if result.as_of is not None]
        return PolicyEvaluation(
            policy_id=self.policy_id,
            name=self.name,
            message=self.message,
            mode=self.mode,
            matched=matched,
            as_of=max(dates) if dates else None,
            conditions=condition_results,
        )


class PolicyEvaluation(BaseModel):
    policy_id: str
    name: str
    message: str
    mode: MatchMode
    matched: bool
    as_of: date | None
    conditions: list[ConditionEvaluation]


class AlertPolicySet(BaseModel):
    version: int = 1
    policies: list[AlertPolicy] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_policy_ids(self) -> AlertPolicySet:
        ids = [policy.policy_id for policy in self.policies]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate alert policy IDs: {duplicates}")
        return self

    @classmethod
    def load(cls, path: Path) -> AlertPolicySet:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


class AlertEvaluationResult(BaseModel):
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evaluations: list[PolicyEvaluation]
    triggered: list[PolicyEvaluation]


def evaluate_policies(
    observations: list[Observation],
    policy_set: AlertPolicySet,
) -> AlertEvaluationResult:
    series_ids = {
        condition.series_id
        for policy in policy_set.policies
        for condition in policy.conditions
    }
    snapshots: dict[str, SeriesSnapshot] = {}
    for series_id in series_ids:
        try:
            snapshots[series_id] = build_snapshot(observations, series_id)
        except ValueError:
            continue

    evaluations = [policy.evaluate(snapshots) for policy in policy_set.policies]
    return AlertEvaluationResult(
        evaluations=evaluations,
        triggered=[evaluation for evaluation in evaluations if evaluation.matched],
    )
