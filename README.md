# Kaizen Ecosystem Protobuf Schemas

This repository serves as the single source of truth for all Protocol Buffer schemas and architectural documentation across the Kaizen ecosystem.

---

## Ecosystem Documentation Suite

For detailed explanations of ecosystem functionality, microservice details, and end-to-end integration flows:
- **[Ecosystem Architecture Overview](docs/architecture_overview.md)**: Details system topology, value loops, and the master system flow diagram.
- **[Repository & Component Deep Dive](docs/component_deep_dive.md)**: Breaks down the capabilities of `kaizen-experimentation`, `kaizen-accelerator`, `merchandising-apis`, `ATOM Curator Suite`, and `kaizen-rosetta`.
- **[Integration Flows & Message Contracts](docs/integration_flows.md)**: Outlines end-to-end sequence charts for curation publishing, personalized page serving, and closed-loop telemetry ingestion.

---

## Directory Layout

```
kaizen-rosetta/
├── README.md                      # This documentation
├── buf.yaml                       # Buf workspace and linting configuration
├── buf.gen.yaml                   # Centralized multi-language code generation configuration
├── docs/                          # Architectural & Integration Documentation Suite
│   ├── architecture_overview.md   # Overall topology and Mermaid chart
│   ├── component_deep_dive.md     # Deep dive into repository capabilities
│   └── integration_flows.md       # Sequence flows and message pathways
└── proto/                         # Schema root
    ├── experimentation/           # Experimentation, flags, and assignment schemas
    │   ├── analysis/v1/
    │   ├── assignment/v1/
    │   ├── bandit/v1/
    │   ├── common/v1/
    │   ├── flags/v1/
    │   ├── management/v1/
    │   ├── metrics/v1/
    │   └── pipeline/v1/
    ├── recommendation/            # Recommendation and user profile feature schemas
    │   └── v1/
    └── kaizen/protobuf/metadata/     # Curation (merchandising) content metadata schemas
        └── program/v4/
```

---

## Tooling & Command Line Interface

We utilize [Buf](https://buf.build/) to manage, lint, and build our schemas.

### 1. Prerequisite
Ensure `buf` is installed on your local machine:
```bash
brew install bufbuild/buf/buf
```

### 2. Linting Schemas
To verify style guide compliance across all schemas:
```bash
buf lint
```

### 3. Building Schemas
To build the schemas into a unified image format (checking for any import or syntax errors):
```bash
buf build
```

### 4. Generating Client/Server SDKs
To generate code for Go and TypeScript based on the configurations defined in `buf.gen.yaml`:
```bash
buf generate
```
The generated files will be written to `gen/go/` and `gen/ts/`.
