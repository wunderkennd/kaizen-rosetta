# Kaizen Ecosystem Protobuf Schemas (kaizen-rosetta)

`kaizen-rosetta` is the central registry for shared Protocol Buffer contracts
and their architectural documentation across the **Kaizen & Merchandising
Ecosystem**. Domain systems remain authoritative for contracts explicitly
documented here as external compatibility subsets.

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
    └── kaizen/
        ├── audience/v1/           # Neutral typed audience contracts and diagnostics
        └── protobuf/metadata/     # Reconstructed external metadata contracts
            └── program/v4/        # Temporary external campaign subset; not the source of truth
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

The normal `just check` gate additionally validates all 48 audience fixtures,
the schema-level provenance/finite-double cases, and the production registry
TextProto. The registry must remain version `2026-07-12` with exactly the eight
approved unique keys and complete, type-consistent operator metadata.
Each audience fixture also carries portable binary Protobuf and canonical
ProtoJSON vectors for its rule and context; the language-neutral consumer
round-trip procedure is normative in [`docs/audience_v1.md`](docs/audience_v1.md).

### 4. Code Generation (SDKs)
Rosetta handles centralized Go, TypeScript, and Python client/server SDK code generation:
```bash
just generate
```
This parses the pinned rules inside `buf.gen.yaml`, outputs generated files
locally, and applies the guarded ConnectRPC Python import repair documented in
[`docs/generator-pins.md`](docs/generator-pins.md).

After generation, compile all locally generated packages and typed audience
smokes in clean temporary workspaces:

```bash
just generated-contracts
```

The gate pins Go 1.26.1, Node.js 25.2.1, npm 11.6.2, TypeScript 5.9.3,
`connectrpc.com/connect` 1.20.0, `google.golang.org/protobuf` 1.36.11, and
`@bufbuild/protobuf` 2.12.1 with `@connectrpc/connect` 2.1.2. It never writes `go.mod`, `node_modules`, or
compiler artifacts into `gen/` or the repository.

---

## Generated Target SDKs

 Rosetta is configured with `managed` file options to generate consistent module naming conventions:

1. **Go SDK (`gen/go/`)**:
   - Module Target: `github.com/wunderkennd/kaizen-rosetta/gen/go`
   - Generated using `buf.build/protocolbuffers/go` and `buf.build/connectrpc/go`.
   - Used by: `kaizen-alchemy-go` and `kaizen-experimentation` Go services.
2. **TypeScript SDK (`gen/ts/`)**:
   - Package Target: Protobuf-ES v2 messages and service descriptors for Web and Node Connect clients.
   - Generated using `buf.build/bufbuild/es`; applications use the descriptors with `@connectrpc/connect` v2.
   - Used by: `ATOM Curator Suite` (Vite) and A/B Decision Support Dashboard (Next.js).
3. **Python SDK (`gen/python/`)**:
   - Package Target: Google Protobuf messages, type stubs, and ConnectRPC services.
   - Generated using `buf.build/protocolbuffers/python`, `buf.build/protocolbuffers/pyi`, and `buf.build/connectrpc/py`.
   - Verified by the Python generated-contract smoke tests.

Java is not currently a generated or tested Rosetta SDK target. Add it only
after pinning a Java generator and adding a Java compilation test.

### Rust consumers

Go consumers use BSR-generated module coordinates. Rust v1 intentionally uses
a different distribution path: it consumes an immutable schema export from a
pinned BSR module commit and runs locked build-time generation through Cargo
`build.rs`. Rust services must not copy Rosetta `.proto` files into downstream
repositories.

The Rust 1.88.0 certification line pins `connectrpc` and `connectrpc-build` to
0.7.0 and `buffa` and `buffa-types` to 0.7.1 in the consumer's Cargo files.
Those are consumer-compatibility pins, not remote generator entries in
`buf.gen.yaml`. This Go/Rust asymmetry remains deliberate until the
BSR-generated Cargo adoption trigger in
[`ADR 0003`](docs/decisions/0003-rust-contract-distribution.md) is met.

### Release manifests

After `buf push` returns the immutable BSR module commit for the candidate,
build the descriptor and manifest together:

```bash
BSR_MODULE_COMMIT=<commit-returned-by-buf-push> \
BSR_SDK_VERIFICATION_FILE=<exact-coordinate-verification.json> \
just release-manifest
```

The command writes `dist/release-manifest.json` with the Git commit, descriptor
digest, Buf CLI version, BSR module commit, exact generator pins, and one
generated-SDK record for every generator. Publication and usability are
separate: `publicationStatus` says whether the coordinate was published, while
the required `verification` object records `status`, `usable`, and exact-
coordinate consumer evidence or a failure reason. Published records contain
the exact package coordinate, SDK version, plugin version/revision, ecosystem,
and associated immutable module commit. A plugin without a packaged SDK is
kept as an explicit `unavailable` record with a reason and a `not_applicable`,
unusable verification; it is never omitted or given an invented coordinate.
Coordinates follow the BSR package managers:

- Go: `buf.build/gen/go/kaizen/rosetta/{plugin-owner}/{plugin-name}`
- npm: `@buf/kaizen_rosetta.{plugin-owner}_{plugin-name}`
- Python: `kaizen-rosetta-{plugin-owner}-{plugin-name}`

By default the builder resolves metadata with authenticated
`buf registry sdk info` calls against the supplied immutable commit. Tests inject a deterministic
metadata document through `BSR_SDK_METADATA_FILE`; production releases must
use live BSR resolution. `BSR_SDK_VERIFICATION_FILE` is always required and
must contain one commit-bound verification for every pin. Each verification
repeats and must exactly match the resolved `generator`, `moduleCommit`,
`ecosystem`, `pluginVersion`, and `pluginRevision`; a published SDK must also
repeat its exact `coordinate` and `version`. An unavailable SDK omits
coordinate/version, uses `status: not_applicable` and `usable: false`, and
includes a reason. See
[`tools/release/sdk-verification.example.json`](tools/release/sdk-verification.example.json)
for the published shape. Only a passed
exact-coordinate consumer may set `usable: true`; published but broken SDKs
remain published with `usable: false` and a concrete failure reason. The builder refuses an
empty or Git-shaped BSR commit and never infers a BSR commit from the local Git
revision. Before writing a manifest it builds that exact immutable BSR ref and
requires its descriptor bytes to match the local descriptor and recorded
SHA-256 digest, preventing a valid but unrelated BSR commit from being claimed.
It also refuses staged, unstaged, or untracked release-source changes,
so the descriptor, generator pins, tests, and release documentation are
reproducible from the recorded `gitCommit`. Generated `dist/` and `gen/` output
and `.superpowers/` reports are excluded from that cleanliness gate. The
released baseline used by local and CI unit tests is only a builder fixture; it
is not a release of the current checkout.

---

## Ecosystem Flow Integrity

By publishing messages defined in `kaizen-rosetta`, we ensure transaction integrity across three loops:
1. **Curator Merchandising**: ATOM publishes `kaizen.protobuf.metadata.program` schemas to Kafka campaign topics, consumed by `kaizen-accelerator` and cache-synced in `kaizen-alchemy-go`.
2. **Serving Hotpath**: High-scale API gateways query `recommendationv1.PageRecommendationService` with strict timeouts, bucketed under `experimentation.assignment` rules.
3. **Loop Closure**: User clicks and views are sent to `experimentation.pipeline` endpoint, validated against `event.proto`, and analyzed by CUPED statistic servers to hot-reload LinUCB bandit policies in under an hour.
