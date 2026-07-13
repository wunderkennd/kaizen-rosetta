#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
generated="${GENERATED_GO_DIR:-${root}/gen/go}"
go_bin="${GO_BIN:-go}"
expected_go_version="${ROSETTA_GO_VERSION-1.26.1}"
temp_parent="${ROSETTA_COMPILE_TEMP_PARENT:-${TMPDIR:-/tmp}}"

if [[ ! -d "${generated}" ]] || ! find "${generated}" -type f -name '*.go' -print -quit | grep -q .; then
  printf '%s\n' "generated Go tree is missing or empty: ${generated}" >&2
  exit 1
fi
if ! command -v "${go_bin}" >/dev/null 2>&1; then
  printf '%s\n' "Go compiler is unavailable: ${go_bin}" >&2
  exit 1
fi
if [[ -n "${expected_go_version}" ]]; then
  actual_go_version="$(${go_bin} version)"
  if [[ "${actual_go_version}" != *"go${expected_go_version}"* ]]; then
    printf 'Go version mismatch: expected %s, got %s\n' \
      "${expected_go_version}" "${actual_go_version}" >&2
    exit 1
  fi
fi

mkdir -p "${temp_parent}"
workspace="$(mktemp -d "${temp_parent%/}/rosetta-go-compile.XXXXXX")"
trap 'rm -rf -- "${workspace}"' EXIT
cp -R "${generated}/." "${workspace}/"
cp "${root}/tools/compile/go.mod.template" "${workspace}/go.mod"
cp "${root}/tools/compile/audience_compile_test.go.template" \
  "${workspace}/audience_compile_test.go"

(
  cd "${workspace}"
  GOTOOLCHAIN=local "${go_bin}" mod tidy
  GOTOOLCHAIN=local "${go_bin}" test ./...
)
