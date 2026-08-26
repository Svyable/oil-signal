# Open-core model

OilSignal's community code is Apache-2.0 and should remain useful without a hosted subscription. The business is built around operational reliability and customer-specific integration rather than artificial restrictions in the core.

| Capability | Community core | Commercial opportunity |
|---|---|---|
| Public ingestion | EIA client abstractions, fixtures, normalized Parquet, provenance | Managed pipelines, vendor/private connectors, SLAs |
| Analytics | Transparent petroleum comparisons and rule alerts | Custom geographies, proprietary benchmarks, scenario workflows |
| Agent | Typed tools, cited answers, deterministic templates, local-model compatibility | Hosted model routing, organization knowledge, premium evaluations |
| UI | Local dashboard and evidence view | Team workspaces, RBAC, governance, collaboration |
| Delivery | Console/cron-friendly interfaces | Managed email/Slack/Teams delivery and escalation |
| Deployment | Docker Compose/self-hosting | Managed SaaS, private VPC/on-prem, SSO, support |

## Commercial boundary

Paid components should integrate through documented interfaces, not forks that intentionally degrade the public edition. A self-hosted user must be able to ingest public data, calculate fundamentals, generate cited reports, run local alerts, and use the dashboard without a license key.

## Suggested packaging

- **Community:** Apache-2.0 repository, local storage, public connectors, deterministic reports, local models.
- **Pro:** hosted freshness, scheduling, collaboration, managed alert delivery.
- **Team:** private documents/data connectors, shared workspaces, audit administration.
- **Enterprise:** SSO, private deployment, retention controls, custom sources, SLA/support.
- **Services:** implementation of customer procurement, terminal, delivery, and hedging-report workflows.
