# Repository & Component Deep Dive

This document provides a detailed breakdown of the capabilities, directories, technologies, and internal services within each of the core repositories in the Kaizen & Merchandising ecosystem.

---

## 1. kaizen-experimentation

The experimentation platform is a highly modular, multi-service system written in Rust and Go, designed to serve and evaluate experiments at extreme scale.

### Sub-services Architecture:
- **M1 Assignment Service (Rust)**:
  - High-performance variant allocation using robust hash-bucketing.
  - Handles real-time slate interleaving and routing.
  - Owns production audience evaluation policy, assignment state, and exposure recording; authoring previews do not perform these operations.
  - SLA: p99 latency < 5ms under 50K rps.
- **M2 Event Pipeline (Rust/Go)**:
  - Validates client telemetric logs against strict protobuf schemas.
  - De-duplicates events and streams them to Apache Kafka.
- **M3 Metric Computation Service (Go)**:
  - Orchestrates Databricks and Apache Spark SQL jobs.
  - Accumulates and aggregates raw user activities into daily metrics inside Delta Lake.
- **M4a Statistical Analysis (Rust)**:
  - Runs advanced A/B evaluation algorithms: CUPED variance reduction, sequential testing (mSPRT, GST), Bayesian posterior updates, and surrogate metrics.
- **M4b Bandit Policy Service (Rust)**:
  - Contextual multi-armed bandit policy server (LinUCB, Thompson Sampling, Slate-level factorizations).
  - Uses an LMAX Disruptor-inspired single-thread model.
  - Utilizes RocksDB for transactional crash-only policy updates.
- **M5 Experiment Management (Go)**:
  - CRUD operations for experiment lifecycle configuration and RBAC control.
- **M6 Decision Support UI (TypeScript/Next.js)**:
  - Dashboard displaying experiment performance metrics, Bayesian charts, and guardrail alerts.

---

## 2. kaizen-accelerator

The personalization service provides real-time user-targeted recommendation pages by orchestrating candidate generation, ranking, and profile features.

### Core Capabilities:
- **Page Recommender Service**:
  - Leverages Spring WebFlux / Project Reactor for non-blocking I/O.
  - Dynamically synthesizes the structure of pages from CMS configs and merges personalized slots.
- **Profile Feature Provider**:
  - Pulls, aggregates, and caches user features from feature stores, My List, and Continue Watching databases.
- **Candidate Orchestration**:
  - Re-ranks and deduplicates recommendation candidates using compile-time exhaustive matching in the embedded Rust-based `recommendation-engine` crate.

---

## 3. merchandising-apis

Supports editorial and promotional merchandising services, connecting manual editorial campaigns to automated Kafka streams and client APIs.

### Core Capabilities:
- **dynamic-promotions-rust**:
  - Consumes and aggregates program catalog schemas.
  - Implements the dynamic promotions sync engine to feed catalog changes directly into the personalization pipelines.
- **content-promotion-go**:
  - Manages active merchandising campaigns, banners, and carousels.
  - Persists configurations in Supabase/PostgreSQL databases.
- **Hopper (legacy Java/Go)**:
  - Serves as the legacy gateway to discovery content APIs.

---

## 4. ATOM Curator Suite

A modern curation console that allows editorial teams to schedule campaigns, verify catalog items, and propagate taxonomies.

### Core Capabilities:
- **Campaign Builder & Calendar**:
  - Curators visually plan banner promotions and dynamic target segments on a shared calendar layout.
- **AI Catalog Panel & Taxonomy Propagation**:
  - Interactive tool supporting automated tag generation and bulk taxonomy propagation across content hierarchies.
- **Allowlist & Fallback Panels**:
  - Configures safe fallback items and critical row overrides for personalization failures.

Workbench-style authoring tools may preview neutral `kaizen.audience.v1`
expressions against observed or explicitly synthetic values through their own
audience evaluator. Preview is a non-exposing diagnostic operation: it neither
emits nor records assignments, exposures, metrics, or rewards and does not
mutate Experimentation state. The audience package supplies schema contracts;
it is not a callable evaluator.

---

## 5. kaizen-rosetta (Schemas)

The central schema registry that binds all of the above repositories together.

### Core Capabilities:
- Aggregates Protocol Buffer definitions for A/B testing (`proto/experimentation`), personalization (`proto/recommendation`), and catalog metadata (`proto/kaizen/protobuf/metadata`).
- Owns the neutral `kaizen.audience.v1` contract for typed values, expressions, operators, and diagnostics. Rosetta does not own production evaluation or assignment behavior; Experimentation does.
- Utilizes `buf` to enforce backward compatibility (`buf breaking`) and style consistency (`buf lint`), generating pinned client SDKs for Go, TypeScript, and Python.
- Publishes a descriptor and deterministic release manifest for consumers. Rust consumers pin the released BSR module or descriptor instead of copying protobuf sources.

`proto/kaizen/protobuf/metadata/program/v4` is currently a temporary,
reconstructed subset of an external program contract. It exists to support the
known integration surface and must not be treated as the final production
campaign source of truth or expanded without confirmed upstream provenance.
