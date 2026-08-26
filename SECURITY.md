# Security policy

## Reporting a vulnerability

Please do not open a public issue for a vulnerability that could expose secrets, customer data, or remote execution. Use GitHub's private vulnerability reporting feature when enabled, or contact the repository owner privately.

Include the affected version/commit, reproduction steps, impact, and any proposed mitigation. Avoid accessing data that is not yours while validating a report.

## Secrets

Never commit EIA keys, model-provider keys, customer connector credentials, or private source URLs. Use environment variables locally and a secret manager in production.

## Data boundary

The community fixture data is synthetic. Operators adding private procurement, terminal, or vendor data should isolate credentials, encrypt storage as required, enforce retention policies, and review what evidence is exposed in generated reports.
