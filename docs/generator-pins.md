# Generator pins

Rosetta pins every remote code generator by released version and BSR revision
so local builds and release artifacts do not change when a plugin publishes a
new release or rebuild.

Go consumers receive BSR-generated module coordinates from the remote pins
below. Rust v1 deliberately does not add a remote generator to `buf.gen.yaml`:
it consumes an immutable schema export from a pinned BSR module commit through
locked Cargo `build.rs` generation. Its Rust 1.88.0, `connectrpc` 0.7.0,
`connectrpc-build` 0.7.0, `buffa` 0.7.1, and `buffa-types` 0.7.1 pins are
consumer-compatibility pins recorded in Cargo files, not entries in
`buf.gen.yaml`. This asymmetry remains in force until the BSR-generated Cargo
adoption trigger in
[`ADR 0003`](decisions/0003-rust-contract-distribution.md) is satisfied.

## Selected releases

Selection date: 2026-07-12. Each selection is the newest non-prerelease
version available from the Buf Schema Registry on that date, except that the
Google Python generators are the newest releases compatible with the pinned
`protobuf==6.33.6` contract-test runtime. The `remote` and `revision` columns
together are the immutable generator reference used in `buf.gen.yaml`.

| Generator | `remote` | Revision | BSR container image digest |
|---|---|---:|---|
| Protobuf Go | `buf.build/protocolbuffers/go:v1.36.11` | 1 | `sha256:0eecce1e016da605b2a607c9e5459bb75edaf279a6309c10caaa7b01377aebac` |
| ConnectRPC Go | `buf.build/connectrpc/go:v1.20.0` | 1 | `sha256:b185f000f74573410701819bd670cd21a3f2d1cd8e458bce1c7c5d7b16148b88` |
| Protobuf ES | `buf.build/bufbuild/es:v2.12.1` | 1 | `sha256:ecd4620a9d29e5f2a2eabce87c1672ebcbc42d3e84318c844088f01a88c5c80e` |
| Protobuf Python | `buf.build/protocolbuffers/python:v33.5` | 1 | `sha256:687a411e4b169b1d4cb4be24a703f689ea10bff532a7e6b28286fe261b51be96` |
| Protobuf Python type stubs | `buf.build/protocolbuffers/pyi:v33.5` | 1 | `sha256:39e1001832bb09729eb09e4895a4a96985942ac0936ff6b8fac8ba620d686e03` |
| ConnectRPC Python | `buf.build/connectrpc/py:v0.11.0` | 1 | `sha256:1fe7ff5ff02d387a81bb96f2bc459f2d0ac4a275c270d96092f1594a1404d6c8` |

## Discovery and verification

Buf CLI 1.66.0's `buf registry plugin info` command addresses Buf check
plugins, not the curated `protoc` plugins used by `buf generate`, and returns
`failed_precondition` for these generator names. Pins were therefore resolved
from the BSR's authoritative
`buf.alpha.registry.v1alpha1.PluginCurationService/GetLatestCuratedPlugin`
Connect API. Its response includes the semver-sorted release list, revisions,
creation time, and container image digest. The public plugin catalog pages at
`https://buf.build/<owner>/<plugin>` identify the same curated generators.

Every selected version and revision was fetched and executed by a clean
`buf generate`. Two clean generations were compared by sorted file path and
SHA-256 digest and produced identical manifests. Generated code remains build
output under `gen/`; it is not committed.

Go and TypeScript generation include imported schema dependencies so the local
compiler gates cover complete self-contained generated trees, including
Protovalidate descriptors. `just generated-contracts` uses clean temporary
workspaces and pinned Go 1.26.1, Node.js 25.2.1, npm 11.6.2, TypeScript 5.9.3,
Connect 1.20.0, Go protobuf 1.36.11, and Protobuf-ES 2.12.1. The scripts fail
closed on a missing generated tree, missing tool, unexpected tool version, or
any compiler failure and clean all temporary modules and package installs.

Release manifests resolve each pin against the supplied immutable module
commit with authenticated `buf registry sdk info` calls. They record the exact
Go module, npm package, or Python distribution coordinate and resolved version,
or an explicit `unavailable` publication status when the BSR does not publish
a packaged SDK for that plugin. Publication never implies usability. A separate
required verification record may mark a published SDK usable only after its
exact coordinate and version compile or import successfully. Published but
broken SDKs retain their real coordinate and version with `usable: false` and a
failure reason. Missing, mismatched, duplicated, unverified, or
commit-inconsistent metadata fails the release.

Verification evidence is self-binding rather than an unstructured assertion.
Every record must exactly repeat the resolved generator, immutable module
commit, ecosystem, plugin version, and plugin revision. Published records also
repeat the exact coordinate and SDK version exercised by the consumer. The
builder rejects stale values in any of those fields. Unavailable records omit
coordinate/version, are `not_applicable` and unusable, and carry a reason. The
complete published input shape is in
`tools/release/sdk-verification.example.json`; release automation replaces all
sample values and supplies one record per active generator.

The release gate also builds `buf.build/kaizen/rosetta:<moduleCommit>` as a file
descriptor set and requires byte identity with the locally generated
descriptor, whose recorded SHA-256 digest is independently recomputed. SDK
resolution and successful exact-coordinate checks therefore cannot attach a
manifest to an unrelated, otherwise valid BSR commit.

ConnectRPC Python v0.11.0 is published but is not directly usable for Rosetta's
nested service packages: its BSR wheel retains the known beyond-top-level
relative import. Its release-manifest verification must remain `failed` and
`usable: false`, naming the defect and the required guarded `just generate`
repair, until a newly pinned generator produces an exact-coordinate wheel that
passes the import smoke without rewriting.

Python messages and type stubs use the official Google Protobuf generators.
ConnectRPC Python uses `protobuf=google`, so its service modules import the
Google-Protobuf-compatible message output rather than a parallel message
runtime.

## Python compatibility constraints

The `v35.1` Python generator emits gencode version `7.35.1`, which the pinned
Google Protobuf runtime `6.33.6` rejects because Python runtimes cannot be
older than their generated code. BSR does not publish a `v33.6` generator, so
`v33.5` revision 1 is the newest published release accepted by that runtime;
its generated headers identify gencode version `6.33.5`. The `python` and
`pyi` plugins enable `include_imports` so the imported
`buf.validate.validate_pb2` module and stub are generated with Rosetta. Buf
does not emit `google/protobuf` runtime sources in this configuration, so the
installed `protobuf==6.33.6` package remains authoritative.

ConnectRPC Python `v0.11.0` has a nested-module import defect in Google
Protobuf mode: for a service in `experimentation/management/v1`, it emits a
same-file import such as `from ....management_service_pb2`, which Python
rejects as beyond the top-level package. The older BSR name
`buf.build/connectrpc/python` has no `v0.11.0` release (its latest is
`v0.10.1`), and `v0.11.0` documents only `protobuf` and `io` generator
options, with no Google import-style override.

`just generate` therefore runs a narrow post-generation repair that derives
each expected sibling `*_pb2.py`, requires exactly one same-file import, and
changes only its excessive leading dots to a single dot. It fails on missing
siblings, zero or multiple candidates, or a remaining beyond-top-level
same-file import. Before it inspects any import, it reconstructs and requires
the exact `Generated from ... DO NOT EDIT` source-path header, the immutable
`protoc-gen-connectrpc-py v0.11.0` header with parameter
`protobuf=google`, and exactly one of each Google binary/JSON codec marker
emitted by that pin. A missing header, different version, different protobuf
mode, or missing/duplicate codec marker fails generation rather than allowing
the workaround to touch unknown output.

Remove this workaround once a newly pinned ConnectRPC Python release emits
valid sibling imports for nested Google Protobuf modules. Updating the pin
without removing or deliberately updating this guard fails closed on its
version header; the permanent guard tests and generated-interface smoke test
are the removal gate.

## Retired generator

`buf.build/connectrpc/es:v1.6.1`, revision 2, was retired on 2026-07-12. It is
a Connect-ES v1 generator and depends on Protobuf-ES v1 output, so it is
incompatible with the active Protobuf-ES v2.12.1 SDK. Connect-ES v2 does not use
a separate `protoc-gen-connect-es`; Protobuf-ES v2 emits service descriptors,
which the TypeScript gate now consumes with pinned `@connectrpc/connect` 2.1.2.
The retired pin remains release history only and must not appear in active
`buf.gen.yaml` pins or active generated-SDK coordinates.
