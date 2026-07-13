# ADR 0003: Distribute Rust contracts through locked build-time generation

- Status: Accepted
- Date: 2026-07-12

## Context

ADR 0001 makes Rosetta the owner of shared schemas and generated contract
artifacts while leaving runtime behavior with each consuming repository. Rust
certification therefore needs a reproducible way to exercise the same
immutable Rosetta schema revision that does not move handlers or operations
into this repository.

The working `kaizen-experimentation` pilot uses Rust edition 2024, Rust 1.88.0,
Connect-Rust and `connectrpc-build` 0.7.0, and Buffa and `buffa-types` 0.7.1.
Connect-Rust and Buffa 0.8.1 are available upstream. The BSR can also publish
Cargo crates from plugins, but the available Prost-oriented path does not
produce the Buffa messages and Connect-Rust traits that this certification is
intended to prove.

## Decision

Rosetta v1 Rust certification uses Cargo build.rs from an immutable BSR export.
The certified baseline is Rust/Cargo 1.88.0, connectrpc 0.7.0,
connectrpc-build 0.7.0, buffa 0.7.1, and buffa-types 0.7.1.
Consumer repositories own runtime handlers, security, middleware, operations,
deployment, performance, and domain bridges.

The locked direct dependency pins used by the certification consumer are:

```text
connectrpc = 0.7.0
connectrpc-build = 0.7.0
buffa = 0.7.1
buffa-types = 0.7.1
```

Rust edition 2024 is part of the v1 consumer baseline. The ownership boundary
is explicit: consumer repositories own runtime handlers and every other
runtime concern listed above. Rosetta owns the immutable schemas and the
evidence that locked build-time generation can consume them; it does not own a
Rust service runtime.

## Alternatives considered

| Alternative | Decision | Reason |
|---|---|---|
| Consumer-aligned `connectrpc-build` + Buffa from immutable BSR export | Select for v1 certification | Matches the working consumer pilot and validates the actual Connect-Rust interface without vendoring schemas. |
| BSR Cargo crate from a Prost-oriented community plugin | Reject for v1 | BSR Cargo distribution exists, but a Prost crate does not expose the Buffa types and Connect-Rust traits being certified. |
| Upgrade certification to Connect-Rust/Buffa 0.8.1 immediately | Defer | Upstream 0.8.1 is available, but combining a pre-1.0 migration with first certification would stop the canary from matching the supported consumer. |

## Version and migration policy

- Exact direct crate pins and Cargo.lock define one certification line.
- A 0.x minor upgrade is treated as potentially breaking and requires a clean
  canary, corpus replay, generated trait review, and new release evidence.
- Patch upgrades are not automatic; they follow the same locked-canary update.
- Raise MSRV only in the same change that updates rust-toolchain.toml, CI, docs,
  and evidence validation.
- Adopt a BSR-generated Cargo SDK when a curated or approved plugin generates
  the Buffa messages and Connect-Rust client/server traits, publishes immutable
  commit-bound crates, and passes the same canary without build-time schema export.

### BSR-generated Cargo adoption trigger

The final version-policy rule is the adoption trigger. Until every condition in
that rule is satisfied, Rust remains on the consumer-aligned locked `build.rs`
model. A candidate that merely publishes a Prost crate does not satisfy the
trigger.

## Consequences

- The Rust canary certifies the dependency line already used by the supported
  consumer instead of mixing initial certification with a pre-1.0 migration.
- Rust generation starts from a commit-bound BSR export and does not vendor or
  copy Rosetta `.proto` files into consumer repositories.
- Rust crate pins are consumer-compatibility pins. They are not remote plugins
  and do not become entries in `buf.gen.yaml`.
- Go and Rust intentionally use different delivery mechanisms: Go consumes
  BSR-generated module coordinates, while Rust v1 performs locked build-time
  generation from the immutable schema export.
- Moving to Connect-Rust/Buffa 0.8.1, changing MSRV, or adopting BSR Cargo
  distribution requires the evidence defined by this policy.
