# Ecosystem Integration Flows & Contracts

This document explains the end-to-end sequence flows, messaging pathways, and telemetry routes that link curators, client SDKs, real-time recommendation gateways, and analytical computation systems.

---

## 1. Merchandising & Campaign Curation Flow

This sequence shows how an editorial team schedules a new hero promotion campaign and how it propagates to the personalized serving layers.

The `program.v4` messages currently present in Rosetta model only the temporary
reconstructed external subset needed by this integration. The external program
system remains authoritative; these files are not the final production
campaign source of truth.

```mermaid
sequenceDiagram
    autonumber
    actor Curator as Editorial Team
    participant ATOM as ATOM Curator Suite
    participant DB as Supabase / PG
    participant Promo as content-promotion-go
    participant Sync as dynamic-promotions-rust
    participant Kafka as Kafka Campaign Topic
    participant Recs as kaizen-accelerator

    Curator->>ATOM: Draft Campaign (Banner, Schedule, Target segment)
    ATOM->>ATOM: Validate target against Kaizen Lifecycle schema
    ATOM->>DB: Save Campaign Configuration
    DB-->>ATOM: Confirm Save
    ATOM->>Promo: Trigger Publish Campaign
    Promo->>Sync: Fetch aggregated program metadata
    Sync->>Kafka: Publish serialized CampaignMessage (kaizen.protobuf.metadata.program)
    Kafka-->>Recs: Consume active campaigns & cache locally
```

---

## 2. Non-Exposing Audience Preview Flow

`kaizen.audience.v1` is neutral across authoring and runtime consumers.
Workbench's own audience evaluator can import it to preview an expression for
author feedback, while Experimentation alone owns production assignment,
exposure, metrics, and reward behavior. Preview neither emits nor records
assignments, exposures, metrics, or rewards.

```mermaid
sequenceDiagram
    autonumber
    actor Author as Workbench Author
    participant Preview as Workbench Preview
    participant Evaluator as Workbench Audience Evaluator
    participant Contract as "kaizen.audience.v1 (schema only)"
    participant Experimentation as Experimentation Runtime

    Author->>Preview: Preview expression with observed or synthetic context
    Preview->>Evaluator: Evaluate typed expression for diagnostics
    Note over Evaluator,Contract: Evaluator imports contract types; schema executes nothing
    Evaluator-->>Preview: Match result and portable diagnostics
    Preview-->>Author: Match result and diagnostics
    Note over Preview,Experimentation: Preview emits/records no assignments, exposures, metrics, or rewards
```

Preview provenance must distinguish observed values from explicitly synthetic
values. A preview result is diagnostic only and cannot be promoted into an
assignment, exposure, metric, or reward record.

---

## 3. Real-Time Personalized Page Serving Flow

This sequence shows the hot-path execution when a client SDK requests a personalized home page under A/B test assignment and slate-level contextual bandit ranking.

Unlike preview, this production flow is owned by Experimentation: it applies
runtime audience policy, creates deterministic assignments, and records
exposures and assignment telemetry.

```mermaid
sequenceDiagram
    autonumber
    actor Client as User Mobile App
    participant GW as API Gateway
    participant Recs as kaizen-accelerator (Page Recommender)
    participant Dynamo as DynamoDB Feature Store
    participant M1 as kaizen-experimentation (M1 Assignment)
    participant M4b as kaizen-experimentation (M4b LMAX Bandit)

    Client->>GW: HTTP GET /homepage (with auth context)
    GW->>Recs: Forward Request Page (GetRecommendedPageRequest)
    Recs->>Dynamo: Fetch profile features (GetProfileFeaturesRequest)
    Dynamo-->>Recs: Return watched items & user segment features
    Recs->>M1: Request A/B assignments (GetAssignment)
    M1->>M1: Perform hash-bucketing for active experiments
    alt Experiment is Contextual Slate Bandit
        M1->>M4b: Select item arms (SelectSlateRequest)
        M4b->>M4b: Sample posterior weights on LMAX thread
        M4b-->>M1: Return ranked SlateSelection & marginal probabilities
    end
    M1-->>Recs: Return variant and slate order assignments
    Recs->>Recs: Merge personalized bandit slate with editorial campaigns
    Recs-->>GW: Return fully constructed Page Recommendation
    GW-->>Client: Serve UI Response
```

---

## 4. Closed-Loop Telemetry Ingest & Policy Update Flow

This sequence shows how user interactions propagate through the event pipeline to trigger sequential statistical CUPED calculations, updating real-time policy algorithms.

```mermaid
sequenceDiagram
    autonumber
    actor Client as User Mobile App
    participant M2 as kaizen-experimentation (M2 Event Pipeline)
    participant Kafka as Confluent Kafka Topics
    participant M3 as kaizen-experimentation (M3 Metric Compute / Spark)
    participant M4a as kaizen-experimentation (M4a Stat Analysis)
    participant M5 as kaizen-experimentation (M5 Management)
    participant M4b as kaizen-experimentation (M4b LMAX Bandit)

    Client->>Client: User clicks on bandit-promoted item
    Client->>M2: Stream click telemetry (Validate against event.proto)
    M2->>Kafka: Publish event to 'experiment_clicks' Kafka topic
    M3->>Kafka: Read raw event streams
    M3->>M3: Run Spark/Delta SQL aggregation (Hourly guardrail/Daily metrics)
    M3-->>M4a: Write CUPED variance-reduced metrics to Delta Lake
    M4a->>M4a: Perform sequential frequentist (mSPRT) & Bayesian analysis
    M4a-->>M5: Alert if guardrail metrics are violated
    M4a->>M5: Write updated reward coefficients
    M5->>M5: Recompile policy files & write to RocksDB snapshot
    M5->>M4b: Hot-reload bandit weights on serving thread
```
