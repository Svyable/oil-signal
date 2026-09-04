# OilSignal go-to-market playbook

This document turns the product architecture into a commercial learning plan. The goal is not to maximize feature breadth before launch. The goal is to find a repeatable buyer, decision, workflow, and willingness-to-pay signal while preserving OilSignal's evidence-first positioning.

## Positioning

**Category:** evidence-first petroleum decision support.

**Core promise:** turn public U.S. petroleum fundamentals into fast, auditable inputs for procurement, supply, research, and automated workflows.

**Differentiation:** OilSignal does not ask the buyer to trust a black-box narrative. Numeric claims are tied to source observations, deterministic calculations, freshness state, raw-source hashes, and stable evidence identity.

**Boundary:** do not market OilSignal as a price-prediction engine, trading system, proprietary data feed, or automated execution product.

## Initial market wedge

The best early wedge is a recurring weekly decision with visible manual effort and a short feedback loop. Weekly petroleum releases create that cadence naturally.

Prioritize prospects where at least one person currently:

- copies numbers across multiple sources or spreadsheets after the weekly release;
- writes or forwards a weekly fundamentals summary;
- checks PADD 2 distillate, refinery utilization, crude flows, or product supplied repeatedly;
- needs to defend the source of a number to a manager, client, or downstream system;
- is experimenting with an internal agent that needs petroleum facts with provenance.

Avoid broad “market intelligence platform” sales language in the first motion. Lead with one repeated decision and one measurable workflow.

## ICP priority

### Tier 1 — downstream fuel operator

Roles:

- head of supply / procurement;
- fuel buyer;
- regional marketer;
- terminal or distribution operations;
- treasury/procurement analyst.

Pain hypothesis:

> “We already have the public data, but assembling the weekly read, checking whether it is current, and tracing numbers back to source still costs time and creates review friction.”

Best entry offer: **Downstream Supply Risk**.

Land with a narrow PADD 2 distillate + refinery + demand workflow. Expand later into broader weekly briefs, alerts, managed delivery, and team collaboration.

### Tier 2 — analyst / consultant

Roles:

- petroleum analyst;
- independent consultant;
- research lead;
- advisory team.

Pain hypothesis:

> “The calculation is not the hard part; repeating it every week, keeping dates aligned, and producing a defensible evidence trail is.”

Best entry offer: **Crude Flow Reconciliation**.

Land with one repeatable balance/reconciliation workflow. Expand into broader research automation, client-ready evidence, and hosted history.

### Tier 3 — agent / automation builder

Roles:

- AI product lead;
- automation engineer;
- data-platform engineer;
- internal tooling team.

Pain hypothesis:

> “We need reliable petroleum facts for software consumption, but do not want to own source monitoring, freshness logic, citation mapping, cache identity, and payment semantics ourselves.”

Best entry offer: **Agent-ready Petroleum Evidence**.

Land with a few small fact or delta SKUs. Expand by SKU count, frequency of fulfillment, private connectors, and managed service requirements.

## Offer ladder

### Offer 0 — open-core proof

Purpose: remove trust friction.

The prospect can self-host OilSignal, inspect the calculations, run the synthetic fixture, and see that the evidence contract is real before any commercial commitment.

Do not treat open core as a free version of every future hosted feature. Treat it as the technical credibility layer and the easiest way for a sophisticated buyer to validate the architecture.

### Offer 1 — founding pilot

Purpose: learn the buyer's true value metric.

Scope:

- one buyer team;
- one operational decision;
- one of the three solution offers;
- a narrow SKU allow-list;
- 2-4 weekly release cycles;
- an explicit baseline and success scorecard;
- manual commercial agreement or design-partner approval;
- scoped pilot credential and audited fulfillment.

The pilot should end with a conversion decision, not an indefinite free trial.

### Offer 2 — hosted team workflow

Purpose: monetize convenience, reliability, and collaboration around the open core.

Candidate paid capabilities:

- managed EIA ingestion and freshness operations;
- persistent history and shared workspaces;
- managed alerts to team destinations;
- saved workflows and scheduled briefs;
- team permissions, SSO, and audit controls;
- private data connectors;
- support, deployment assistance, and operational commitments.

These are natural open-core monetization boundaries because they reduce operational burden rather than hiding the evidence logic.

### Offer 3 — embedded evidence API

Purpose: monetize machine consumption.

Use the existing SKU, quote, state, ETag, manifest, signature, and HTTP 402 contracts. Prefer value metrics based on changed evidence fulfillment or explicit SKU consumption rather than charging for unchanged polling.

### Offer 4 — enterprise deployment

Purpose: serve buyers with infrastructure, security, or data-boundary requirements.

Candidate capabilities:

- VPC/private-cloud/on-prem deployment;
- private connectors;
- customer-managed keys/secrets;
- deployment support;
- service commitments;
- enterprise identity and governance.

## Pricing strategy

Do not confuse a technically convenient meter with the buyer's value metric.

Use pricing experiments in this order:

1. **Founding pilot:** fixed commercial agreement for a narrow workflow. Learn what outcome the buyer values before optimizing unit economics.
2. **Embedded agent buyer:** per-SKU or changed-evidence fulfillment pricing can be tested because the product already has stable semantic identity and free unchanged revalidation.
3. **Hosted team:** recurring subscription should primarily reflect team/workflow value, managed operations, collaboration, and support—not the number of public EIA rows stored.
4. **Enterprise:** price deployment, security, private integration, and support requirements separately from evidence-unit pricing.

Keep example per-SKU prices in documentation clearly labeled as configuration examples, not public list prices or a guarantee of future pricing.

## Pilot scorecard

Baseline before the first live cycle:

- current minutes from release availability to finished decision-support output;
- number of manual source lookups;
- number of spreadsheet/copy-paste steps;
- number of people who review or re-check the output;
- current downstream delivery steps;
- known stale-data or version-control failure modes.

Measure during the pilot:

- release-to-output latency;
- analyst minutes per cycle;
- percentage of material numeric claims accepted without separate source lookup;
- stale/unverifiable outputs blocked;
- recurring steps automated;
- number of times the buyer voluntarily uses or forwards the output;
- number of additional workflows the buyer asks to connect.

The strongest conversion signal is not “the demo looked good.” It is the buyer asking for the workflow to keep running, reach more users, or connect to another system.

## Discovery script

Keep discovery operational and specific.

Ask:

- What happens in the first hour after the weekly petroleum release?
- Which numbers do you always check?
- Which regional/product conditions trigger a call or procurement discussion?
- Where do those numbers get copied next?
- Who re-checks the source before acting or publishing?
- What breaks when the release is delayed, revised, or stale?
- Which part of the weekly workflow is repetitive but still requires a trusted human check?
- If this workflow were automated, what evidence would you need before trusting it?

Do not lead with “AI.” Lead with the repeated decision and evidence burden. Introduce the agent-native surface only when automation is relevant to the buyer.

## Demo motion

Use one compact live path:

1. show the public/synthetic evidence structure;
2. show a focused SKU tied to the prospect's decision;
3. show the citation and calculation trace;
4. show stale-data fail-closed behavior conceptually or with a fixture test;
5. show state/ETag polling for machine buyers;
6. show portable signature verification for trust-sensitive buyers;
7. finish on the pilot scorecard, not on a feature tour.

The demo should answer: **“Can I trust this enough to put it into a recurring workflow?”**

## Acquisition motions

### Founder-led outbound

Build a small named-account list around the ICPs above. Personalized outreach should reference the prospect's likely weekly workflow, not generic “AI for oil” language.

A useful outbound structure:

- observation: “Your team likely reviews the same weekly petroleum release every Wednesday cycle.”
- problem: “The public data is available, but the source-checking and recurring write-up remain manual.”
- proof: “OilSignal produces deterministic, source-cited facts/deltas and blocks stale live evidence.”
- ask: “Would a 2-4 release-cycle parallel pilot against one existing workflow be worth testing?”

### Consultant/design-partner channel

Independent consultants and small research teams can be unusually valuable early partners because they experience repetitive evidence work directly and can expose multiple downstream use cases.

Optimize for learning and referenceability, not logo size.

### Open-source credibility

Use the repository as proof of method:

- reproducible fixtures;
- visible calculations;
- offline tests;
- provenance docs;
- source verification;
- evidence signatures;
- clear safety boundaries.

The open source should reduce technical diligence time for a serious buyer.

### Weekly evidence content

A recurring public artifact can demonstrate product quality without turning OilSignal into a prediction newsletter. Publish examples of **how to audit a petroleum claim**, explain a deterministic calculation, or show a synthetic/demo brief structure.

Do not publish synthetic fixture values as current market facts.

## Expansion signals

Expand a customer when one of these happens:

- they ask to monitor more products or regions;
- they ask for delivery into email/chat/operations tooling;
- more than one user needs the same workflow;
- they want history, saved views, or comparison workflows;
- they want a private/internal data source combined with public fundamentals;
- they want an internal agent to consume the same evidence contract;
- they need enterprise identity, deployment, or support controls.

Each signal maps naturally to a hosted/open-core monetization boundary.

## What not to build before evidence of demand

Defer unless a real customer pull appears:

- broad proprietary data acquisition;
- speculative price forecasting;
- automated trading/execution;
- a large CRM/account/billing subsystem for a single pilot;
- dozens of delivery adapters before one destination repeats across customers;
- generic chat features that weaken the deterministic evidence contract;
- regional series added by ID pattern guess rather than verified source definitions.

## 30-day commercialization sprint

### Week 1 — package

- use `COMMERCIAL.md` as the buyer-facing one-pager;
- choose one primary ICP and one secondary ICP;
- prepare one focused demo for each;
- configure a pilot SKU set and scorecard;
- verify the production deployment path and audit trail.

### Week 2 — discover

- run 8-12 buyer conversations;
- record repeated workflow language verbatim;
- rank pains by frequency, urgency, and ability to measure improvement;
- do not add features for one-off requests unless they reveal a broader pattern.

### Week 3 — pilot

- start 1-3 narrow pilots;
- baseline the existing workflow before the first live cycle;
- run in parallel rather than asking the buyer to replace trusted processes immediately;
- capture every integration and trust objection.

### Week 4 — convert or learn

- ask for continuation, expansion, or a paid hosted workflow where value was demonstrated;
- reject vague “interesting” feedback as a conversion signal;
- update packaging based on observed decision/workflow pull;
- prioritize the next product slice from customer evidence, not feature novelty.

## Machine-readable commercial discovery

The configurable runtime server exposes:

```text
GET /.well-known/oilsignal-commercial.json
GET /api/agent/offers
```

The response includes ICPs, solution offers, recommended SKUs, quote paths, proof points, and pilot success metrics. It intentionally contains no hard-coded production list price. Actual commercial terms continue to resolve through per-SKU quote endpoints and the configured payment/pilot policy.
