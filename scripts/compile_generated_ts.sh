#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
generated="${GENERATED_TS_DIR:-${root}/gen/ts}"
npm_bin="${NPM_BIN:-npm}"
node_bin="${NODE_BIN:-node}"
expected_node_version="${ROSETTA_NODE_VERSION-25.2.1}"
expected_npm_version="${ROSETTA_NPM_VERSION-11.6.2}"
temp_parent="${ROSETTA_COMPILE_TEMP_PARENT:-${TMPDIR:-/tmp}}"

if [[ ! -d "${generated}" ]] || ! find "${generated}" -type f -name '*.ts' -print -quit | grep -q .; then
  printf '%s\n' "generated TypeScript tree is missing or empty: ${generated}" >&2
  exit 1
fi
if ! command -v "${npm_bin}" >/dev/null 2>&1; then
  printf '%s\n' "npm is unavailable: ${npm_bin}" >&2
  exit 1
fi
if ! command -v "${node_bin}" >/dev/null 2>&1; then
  printf '%s\n' "Node.js is unavailable: ${node_bin}" >&2
  exit 1
fi
if [[ -n "${expected_node_version}" ]]; then
  actual_node_version="$(${node_bin} --version)"
  if [[ "${actual_node_version}" != "v${expected_node_version}" ]]; then
    printf 'Node.js version mismatch: expected %s, got %s\n' \
      "${expected_node_version}" "${actual_node_version}" >&2
    exit 1
  fi
fi
if [[ -n "${expected_npm_version}" ]]; then
  actual_npm_version="$(${npm_bin} --version)"
  if [[ "${actual_npm_version}" != "${expected_npm_version}" ]]; then
    printf 'npm version mismatch: expected %s, got %s\n' \
      "${expected_npm_version}" "${actual_npm_version}" >&2
    exit 1
  fi
fi

mkdir -p "${temp_parent}"
workspace="$(mktemp -d "${temp_parent%/}/rosetta-ts-compile.XXXXXX")"
trap 'rm -rf -- "${workspace}"' EXIT
cp -R "${generated}/." "${workspace}/"
cp "${root}/tools/compile/package.json.template" "${workspace}/package.json"
cp "${root}/tools/compile/tsconfig.json.template" "${workspace}/tsconfig.json"
cp "${root}/tools/compile/audience-smoke.ts.template" \
  "${workspace}/audience-smoke.ts"

(
  cd "${workspace}"
  "${npm_bin}" install --ignore-scripts --no-audit --no-fund --package-lock=false
  tsc_bin="${TSC_BIN:-${workspace}/node_modules/.bin/tsc}"
  if [[ ! -x "${tsc_bin}" ]]; then
    printf '%s\n' "TypeScript compiler is unavailable: ${tsc_bin}" >&2
    exit 1
  fi
  "${tsc_bin}" --project tsconfig.json
)
