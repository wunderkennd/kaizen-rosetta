#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
bsr_commit="${ROSETTA_RUST_BSR_COMMIT-}"
expected_descriptor_sha256="${ROSETTA_RUST_DESCRIPTOR_SHA256-}"
buf_bin="${BUF_BIN:-buf}"
rustc_bin="${RUSTC_BIN:-rustc}"
cargo_bin="${CARGO_BIN:-cargo}"
evidence_file="${ROSETTA_RUST_EVIDENCE_FILE:-${root}/dist/consumer-compatibility-rust.json}"
evidence_writer="${ROSETTA_RUST_EVIDENCE_WRITER:-${root}/scripts/write_rust_compatibility_evidence.py}"

rm -f -- "${evidence_file}"

if [[ ! "${bsr_commit}" =~ ^[0-9a-f]{32}$ ]]; then
  printf '%s\n' "ROSETTA_RUST_BSR_COMMIT must be exactly 32 lowercase hex characters" >&2
  exit 1
fi
if [[ ! "${expected_descriptor_sha256}" =~ ^[0-9a-f]{64}$ ]]; then
  printf '%s\n' "ROSETTA_RUST_DESCRIPTOR_SHA256 must be exactly 64 lowercase hex characters" >&2
  exit 1
fi

if ! command -v "${cargo_bin}" >/dev/null 2>&1; then
  printf '%s\n' "Cargo is unavailable: ${cargo_bin}" >&2
  exit 1
fi
if ! command -v "${rustc_bin}" >/dev/null 2>&1; then
  printf '%s\n' "Rust compiler is unavailable: ${rustc_bin}" >&2
  exit 1
fi
if ! command -v "${buf_bin}" >/dev/null 2>&1; then
  printf '%s\n' "Buf is unavailable: ${buf_bin}" >&2
  exit 1
fi

actual_cargo_version="$("${cargo_bin}" --version)"
if [[ "${actual_cargo_version}" != "cargo 1.88.0 "* ]]; then
  printf 'Cargo version mismatch: expected cargo 1.88.0, got %s\n' \
    "${actual_cargo_version}" >&2
  exit 1
fi
cargo_version="${actual_cargo_version#cargo }"
cargo_version="${cargo_version%% *}"
actual_rust_version="$("${rustc_bin}" --version)"
if [[ "${actual_rust_version}" != "rustc 1.88.0 "* ]]; then
  printf 'Rust version mismatch: expected rustc 1.88.0, got %s\n' \
    "${actual_rust_version}" >&2
  exit 1
fi
rust_version="${actual_rust_version#rustc }"
rust_version="${rust_version%% *}"
actual_buf_version="$("${buf_bin}" --version)"
if [[ "${actual_buf_version}" != "1.66.0" ]]; then
  printf 'Buf version mismatch: expected 1.66.0, got %s\n' \
    "${actual_buf_version}" >&2
  exit 1
fi

workspace="$(mktemp -d "${TMPDIR:-/tmp}/rosetta-rust-contracts.XXXXXX")"
trap 'rm -rf -- "${workspace}"' EXIT
reference="buf.build/kaizen/rosetta:${bsr_commit}"
descriptor="${workspace}/rosetta-descriptor.binpb"

"${buf_bin}" export "${reference}" --output "${workspace}/proto"
"${buf_bin}" build "${reference}" --as-file-descriptor-set --output "${descriptor}"
actual_descriptor_sha256="$(shasum -a 256 "${descriptor}" | awk '{print $1}')"
if [[ "${actual_descriptor_sha256}" != "${expected_descriptor_sha256}" ]]; then
  printf 'descriptor SHA-256 mismatch: expected %s, got %s\n' \
    "${expected_descriptor_sha256}" "${actual_descriptor_sha256}" >&2
  exit 1
fi

ROSETTA_PROTO_ROOT="${workspace}/proto" \
ROSETTA_CONFORMANCE_FILE="${root}/conformance/audience/v1/valid.jsonl" \
CARGO_TARGET_DIR="${workspace}/target" \
"${cargo_bin}" test \
  --manifest-path "${root}/tools/compatibility/rust/Cargo.toml" \
  --locked \
  --all-targets

"${evidence_writer}" \
  --repository-root "${root}" \
  --manifest "${root}/tools/compatibility/rust/Cargo.toml" \
  --lockfile "${root}/tools/compatibility/rust/Cargo.lock" \
  --output "${evidence_file}" \
  --bsr-module-commit "${bsr_commit}" \
  --descriptor-sha256 "${expected_descriptor_sha256}" \
  --cargo-version "${cargo_version}" \
  --rust-version "${rust_version}" \
  --cargo-bin "${cargo_bin}"
