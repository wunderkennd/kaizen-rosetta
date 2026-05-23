# Kaizen Ecosystem Protobuf Schemas (kaizen-rosetta)

`kaizen-rosetta` is the central schema registry and single source of truth for all Protocol Buffer schemas and architectural documentation across the **Kaizen & Merchandising Ecosystem**. 

By utilizing standardized message contracts, `kaizen-rosetta` ensures strong interface compatibility and compile-time safety between curation platforms, serving gateways, real-time bandit services, and closed-loop data processing pipelines.

---

## Ecosystem Documentation Suite

For comprehensive diagrams and architecture breakdowns:
- **[Ecosystem Architecture Overview](docs/architecture_overview.md)**: Details system topologies, core value loops, and the global Mermaid topology.
- **[Repository & Component Deep Dive](docs/component_deep_dive.md)**: Breaks down the capabilities of `kaizen-experimentation`, `kaizen-accelerator`, `merchandising-apis`, `ATOM Curator Suite`, and `kaizen-rosetta`.
- **[Integration Flows & Message Contracts](docs/integration_flows.md)**: Outlines end-to-end sequence charts for curation campaigns, personalized page serving, and telemetry analytics loops.

---

## Protobuf Schema Directory Layout

```
kaizen-rosetta/
├── README.md                      # This documentation
├── buf.yaml                       # Buf workspace and linting configuration (Buf v2)
├── buf.gen.yaml                   # Multi-language code generation configuration
├── docs/                          # Architectural & Integration Documentation
└── proto/                         # Schema Root Directory
    ├── experimentation/           # A/B Testing & Slate Bandit schemas
    │   ├── analysis/v1/           # CUPED, sequential mSPRT, and Bayesian reward configurations
    │   ├── assignment/v1/         # Hash-bucketing variant bucketing & slate routing
    │   ├── bandit/v1/             # Multi-Armed Bandit weights & LinUCB/Thompson sampling parameters
    │   ├── common/v1/             # Shared experimental data types
    │   ├── flags/v1/              # Feature flags metadata
    │   ├── management/v1/         # Experiment administration and policy lifecycle management
    │   ├── metrics/v1/            # Spark/Databricks aggregated metric schemas
    │   └── pipeline/v1/           # Telemetry logging & validation schema (e.g. event.proto)
    │
    ├── recommendation/v1/         # Recommendation & User Feature schemas
    │   ├── domain.proto           # Recommendations slates & item specifications
    │   ├── engine_service.proto   # Candidate re-ranking engine gRPC interface
    │   └── service.proto          # PageRecommendationService client/server interfaces
    │
    └── kaizen/protobuf/metadata/  # Merchandising, Banners & Editorial Curation schemas
        └── program/v4/            # Campaign promotion models, editorial schedules & allowlists
```

---

## Tooling & Command Line Interface

We utilize [Buf (v2)](https://buf.build/) to manage, validate, and compile our schemas.

### Prerequisites
Install the `buf` CLI tool on macOS:
```bash
brew install bufbuild/buf/buf
```

### 1. Linting Schemas
Verify that all schemas conform strictly to system-wide style guides:
```bash
buf lint
```

### 2. Format Schema Files
Auto-format styling, spacing, and indents in all `.proto` files:
```bash
buf format -w
```

### 3. Build & Compile Schemas
Compile the entire Protobuf tree into a unified image format to detect syntax or import errors:
```bash
buf build
```

### 4. Code Generation (SDKs)
rossetta handles centralized, multi-language client/server SDK code generation:
```bash
buf generate
```
This parses the rules inside `buf.gen.yaml` and outputs generated files locally.

---

## Generated Target SDKs

 Rosetta is configured with `managed` file options to generate consistent module naming conventions:

1. **Go SDK (`gen/go/`)**:
   - Module Target: `github.com/wunderkennd/kaizen-rosetta/gen/go`
   - Generated using `buf.build/protocolbuffers/go` and `buf.build/connectrpc/go`.
   - Used by: `kaizen-alchemy-go` and `kaizen-experimentation` Go services.
2. **TypeScript SDK (`gen/ts/`)**:
   - Package Target: ConnectRPC/ES for Web and Node runtime clients.
   - Generated using `buf.build/bufbuild/es` and `buf.build/connectrpc/es`.
   - Used by: `ATOM Curator Suite` (Vite) and A/B Decision Support Dashboard (Next.js).
3. **Java SDK**:
   - Package Namespace: `com.wunderkennd.kaizen.proto.*`
   - Used by: Legacy Spring and WebFlux recommendation layers.

---

## Ecosystem Flow Integrity

By publishing messages defined in `kaizen-rosetta`, we ensure transaction integrity across three loops:
1. **Curator Merchandising**: ATOM publishes `kaizen.protobuf.metadata.program` schemas to Kafka campaign topics, consumed by `kaizen-accelerator` and cache-synced in `kaizen-alchemy-go`.
2. **Serving Hotpath**: High-scale API gateways query `recommendationv1.PageRecommendationService` with strict timeouts, bucketed under `experimentation.assignment` rules.
3. **Loop Closure**: User clicks and views are sent to `experimentation.pipeline` endpoint, validated against `event.proto`, and analyzed by CUPED statistic servers to hot-reload LinUCB bandit policies in under an hour.
