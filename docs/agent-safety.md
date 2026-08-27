# Agent safety and scope

OilSignal is decision-support software for petroleum fundamentals. Version 1 intentionally excludes trade execution, personalized investment recommendations, and price predictions.

## Hard rules

- A market claim must have at least one structured citation.
- A derived numerical claim must link its citations to a `CalculationTrace`.
- Model output is never written directly into a validated report without conversion to typed claims and validation.
- Deterministic reports remain available when no LLM is configured.
- Missing data produces an explicit error or omitted section, not a fabricated value.
- Synthetic fixtures are clearly development/test data and must not be presented as current EIA observations.

## Model boundary

The optional OpenAI-compatible client is an explanation component. It may help select or summarize retrieved evidence, but deterministic tools own the calculations. A production LLM workflow should require structured output containing claim text plus citation/calculation identifiers, then run the same validator used by deterministic reports.

## Not trading advice

The application should display a decision-support disclaimer in the UI and generated reports. Do not add automated order placement, portfolio sizing, price targets, or “buy/sell” recommendation features to the core agent.

## Security

API keys belong in environment variables or an external secret manager. Do not persist secrets into Parquet provenance, report JSON, logs, fixtures, or browser bundles. Private connectors should apply least-privilege credentials and retention controls appropriate to customer data.
