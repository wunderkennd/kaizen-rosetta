# Kaizen & Merchandising Ecosystem Architecture Overview

This document provides a high-level architectural view of the Kaizen and Merchandising ecosystem. It details the relationship and integration paths between core machine learning/experimentation engines, content merchandising APIs, and curation suites.

---

## High-Level System Topology

The ecosystem is built around three major loops:
1. **Curator Merchandising Loop (Admin Control)**: Where curators define editorial rows, dynamic promotion rules, allowlists, and key art configurations.
2. **Real-time Serving Loop (Hot-path)**: High-scale, low-latency APIs providing personalized recommendations, slate rankings, and experiment variant assignments.
3. **Closed-loop Ingest & Analytics Loop (Feedback loop)**: Capturing user events (impressions, clicks, watch time), validating schemas, streaming to Delta Lake, and performing sequential statistical CUPED calculations to evaluate performance and update bandit policies.

```mermaid
graph TD
    %% Admin Layer
    subgraph Curator Suite
        ATOM[ATOM Curator Suite React/Vite] -->|Supabase Sync| Supa[(Supabase DB)]
    end

    %% Merchandising API Layer
    subgraph Merchandising Core
        MA_CAM[content-promotion-go] -->|Load Campaigns| Supa
        MA_SYNC[dynamic-promotions-rust] -->|Sync Metadata| Kafka{Confluent Kafka}
    end

    %% Hot-Path Serving
    subgraph Serving Layer
        User[Client SDKs Web/iOS/Android] -->|Fetch Page| Recommender[kaizen-accelerator / Page Recommender]
        Recommender -->|Get Assignments| M1_Assign[kaizen-experimentation / M1 Assignment]
        M1_Assign -->|Get Bandit Arms| M4b_Bandit[kaizen-experimentation / M4b LMAX Bandit Engine]
        Recommender -->|Aggregate Features| Dynamo[(DynamoDB Profile Features)]
    end

    %% Streaming & Feedback
    subgraph Analytics Feedback Loop
        User -->|Telemetry Clicks/Views| M2_Event[kaizen-experimentation / M2 Event Pipeline]
        M2_Event -->|Validate & Stream| Kafka
        Kafka -->|Spark SQL / Delta Lake| M3_Compute[kaizen-experimentation / M3 Metric Compute]
        M3_Compute -->|CUPED / Stats| M4a_Analysis[kaizen-experimentation / M4a Stat Analysis]
        M4a_Analysis -->|Update Policy Config| M5_Mgmt[kaizen-experimentation / M5 Management]
        M5_Mgmt -->|Push RocksDB Policies| M4b_Bandit
    end

    classDef curator fill:#e1f5fe,stroke:#03a9f4,stroke-width:2px;
    classDef serve fill:#e8f5e9,stroke:#4caf50,stroke-width:2px;
    classDef stats fill:#fff3e0,stroke:#ff9800,stroke-width:2px;
    class ATOM,Supa curator;
    class Recommender,M1_Assign,M4b_Bandit,Dynamo serve;
    class M2_Event,M3_Compute,M4a_Analysis,M5_Mgmt stats;
```

---

## Core Product Value Loops

### Shared audience contract and runtime ownership

`kaizen.audience.v1` is a neutral Rosetta contract. It defines portable typed
values, expression structure, operators, and diagnostics without assigning
ownership to Merchandising, Workbench, or Experimentation and without
implementing an evaluator.

Workbench's own audience evaluator may import the same contract for authoring
preview, but the schema itself is not an evaluator and preview is non-exposing.
Preview may use observed or explicitly synthetic inputs and return diagnostics,
but it neither emits nor records assignments, exposures, metrics, or rewards.
Experimentation owns production assignment behavior, including runtime
evaluation policy, deterministic bucketing, variant selection, exposure
recording, metrics, rewards, and assignment telemetry.

The checked-in `kaizen.protobuf.metadata.program.v4` files are a temporary,
reconstructed subset of an external program contract needed for current
integration compilation. They are not the final production campaign model or
the source of truth for campaign authoring. Their upstream provenance and
replacement path must be established before expanding them as a Rosetta-owned
API.

### 1. Curated Merchandising
Curators use the **ATOM Curator Suite** to configure hero banners, promotional carousels, and editorial fallbacks. Current integration builds use the temporary reconstructed `program.v4` subset to describe the external campaign boundary; that subset is not the authoring source of truth. Campaigns are parsed by `content-promotion-go` in `merchandising-apis` and synced down to the hot-path engine (`kaizen-accelerator`) so that promotional material is dynamically woven into user pages alongside personalized rows.

### 2. Real-time Personalization & Slate Bandits
When a user requests a personalized page:
1. The **Page Recommender Service** (`kaizen-accelerator`) aggregates the user's profile features from DynamoDB.
2. It requests A/B testing and bucket assignments from the **M1 Assignment Service** (`kaizen-experimentation`).
3. For slate-level contextual bandit rows, M1 orchestrates with **M4b Bandit Engine** to sample slot posterior weights (using LinUCB/Thompson Sampling) and output an optimized slate selection.
4. The page is synthesized, merged with merchandising promotion constraints, and returned to the user in under 15ms.

### 3. Loop Closure & Bayesian Policy Updates
All user activity produces telemetric logs routed to the **M2 Event Pipeline**. These are streamed through Kafka to Apache Spark (**M3 Metric Computation**) and processed into Delta Lake tables. Periodically, the **M4a Statistical Analysis** engine runs Bayesian and sequential frequentist computations (CUPED variance-reduced mSPRT tests). It feeds updated reward expectations back to the **M5 Management Service**, which re-compiles and pushes optimized policy parameters to the M4b RocksDB policy store, closing the loop.
