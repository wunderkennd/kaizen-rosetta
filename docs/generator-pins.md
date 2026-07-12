# Generator pins

Rosetta pins every remote code generator by released version and BSR revision
so local builds and release artifacts do not change when a plugin publishes a
new release or rebuild.

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
| ConnectRPC ES | `buf.build/connectrpc/es:v1.6.1` | 2 | `sha256:fa07dc72027009767f5a1105d0838e33b5d67a1efff8412ede5ee58123643668` |
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
