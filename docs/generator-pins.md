# Generator pins

Rosetta pins every remote code generator by released version and BSR revision
so local builds and release artifacts do not change when a plugin publishes a
new release or rebuild.

## Selected releases

Selection date: 2026-07-12. Each selection is the newest non-prerelease
version available from the Buf Schema Registry on that date. The `remote` and
`revision` columns together are the immutable generator reference used in
`buf.gen.yaml`.

| Generator | `remote` | Revision | BSR container image digest |
|---|---|---:|---|
| Protobuf Go | `buf.build/protocolbuffers/go:v1.36.11` | 1 | `sha256:0eecce1e016da605b2a607c9e5459bb75edaf279a6309c10caaa7b01377aebac` |
| ConnectRPC Go | `buf.build/connectrpc/go:v1.20.0` | 1 | `sha256:b185f000f74573410701819bd670cd21a3f2d1cd8e458bce1c7c5d7b16148b88` |
| Protobuf ES | `buf.build/bufbuild/es:v2.12.1` | 1 | `sha256:ecd4620a9d29e5f2a2eabce87c1672ebcbc42d3e84318c844088f01a88c5c80e` |
| ConnectRPC ES | `buf.build/connectrpc/es:v1.6.1` | 2 | `sha256:fa07dc72027009767f5a1105d0838e33b5d67a1efff8412ede5ee58123643668` |
| Protobuf Python | `buf.build/protocolbuffers/python:v35.1` | 1 | `sha256:eaf9163dcf56764de2236cac5279e3ff726ecaed3c825ad8e4c311d788dba001` |
| Protobuf Python type stubs | `buf.build/protocolbuffers/pyi:v35.1` | 1 | `sha256:1cb29ea5d60502372e1745612eeddd599bd8ba6f1efcf000be2cbe0b9ac7d81e` |
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
