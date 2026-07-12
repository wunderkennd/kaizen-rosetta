# ADR 0001: Rosetta owns shared schema contracts

- Status: Accepted
- Date: 2026-07-12

## Context

Rosetta is the central registry for schemas shared by Kaizen domain systems. A
schema contract needs a single source of truth, stable compatibility checks,
and reproducible generated artifacts. Runtime behavior and deployment concerns
remain specific to each domain repository.

Without a clear boundary, schema definitions or generated code can drift
between repositories and make compatibility ownership ambiguous.

## Decision

Rosetta owns:

- shared Protocol Buffer schemas and their compatibility policy;
- Buf linting, formatting, build, and breaking-change verification;
- generated client and server artifacts derived from those schemas; and
- immutable file-descriptor sets and their SHA-256 digests.

Domain repositories own:

- service runtimes and business logic;
- deployment, operations, and runtime configuration; and
- adoption of released Rosetta-generated artifacts.

Changes to schema packages, Buf configuration, or schema verification workflows
require review by the owners declared in `.github/CODEOWNERS`. Until dedicated
GitHub organization teams are established in this repository, those paths are
owned by `@wunderkennd`.

The released `buf.build/kaizen/rosetta` module is the permanent compatibility
baseline. CI and local verification compare proposed schema changes against
that released baseline rather than an arbitrary local commit.

The shared local and CI entry points are `just check` for deterministic schema
verification, `just descriptor` for descriptor artifacts, and
`BUF_BREAKING_AGAINST=buf.build/kaizen/rosetta just breaking` for compatibility
against the released module.

## Consequences

- Schema evolution is reviewed and validated centrally.
- Domain repositories consume released contracts instead of redefining them.
- Generated artifacts and descriptor digests can be reproduced from Rosetta.
- A schema change that breaks the released module is rejected unless handled
  through an explicitly approved compatibility migration.
