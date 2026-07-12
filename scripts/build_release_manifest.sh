#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${BSR_MODULE_COMMIT:-}" ]]; then
  printf '%s\n' 'BSR_MODULE_COMMIT is required' >&2
  exit 1
fi
if [[ ! "${BSR_MODULE_COMMIT}" =~ ^[0-9a-f]{32}$ ]]; then
  printf '%s\n' \
    'BSR_MODULE_COMMIT must be an immutable 32-character BSR module commit' >&2
  exit 1
fi
if [[ "${BSR_MODULE_COMMIT}" == "00000000000000000000000000000000" ]]; then
  printf '%s\n' 'BSR_MODULE_COMMIT must not be all zeros' >&2
  exit 1
fi

descriptor_digest_file="${root}/dist/rosetta-descriptor.sha256"
descriptor_sha256=""
if [[ -f "${descriptor_digest_file}" ]]; then
  IFS= read -r descriptor_sha256 < "${descriptor_digest_file}" || true
fi
if [[ -z "${descriptor_sha256}" ]]; then
  printf '%s\n' 'descriptor digest is required' >&2
  exit 1
fi
if [[ ! "${descriptor_sha256}" =~ ^[0-9a-f]{64}$ ]]; then
  printf '%s\n' 'descriptor digest must be a lowercase SHA-256 value' >&2
  exit 1
fi
if [[ "${descriptor_sha256}" == \
  "0000000000000000000000000000000000000000000000000000000000000000" ]]; then
  printf '%s\n' 'descriptor digest must not be all zeros' >&2
  exit 1
fi

git_commit="$(git -C "${root}" rev-parse --verify 'HEAD^{commit}' 2>/dev/null || true)"
if [[ -z "${git_commit}" ]]; then
  printf '%s\n' 'Git commit is required' >&2
  exit 1
fi
if [[ ! "${git_commit}" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]]; then
  printf '%s\n' 'Git commit must be a full 40- or 64-character object ID' >&2
  exit 1
fi

release_source_paths=(
  "proto/"
  "buf.yaml"
  "buf.lock"
  "buf.gen.yaml"
  "registry/"
  "conformance/"
  "scripts/"
  "tests/"
  "Justfile"
  "README.md"
  "docs/"
)
release_source_status="$(
  git -C "${root}" status --porcelain=v1 --untracked-files=all \
    -- "${release_source_paths[@]}"
)"
if [[ -n "${release_source_status}" ]]; then
  printf '%s\n' 'release sources must match the recorded Git commit:' >&2
  printf '%s\n' "${release_source_status}" >&2
  exit 1
fi

buf_cli_version="$(buf --version)"
if [[ -z "${buf_cli_version}" ]]; then
  printf '%s\n' 'Buf CLI version is required' >&2
  exit 1
fi

mkdir -p "${root}/dist"
manifest_output="${root}/dist/release-manifest.json"
temporary_output="$(mktemp "${manifest_output}.tmp.XXXXXX")"
trap 'rm -f -- "${temporary_output}"' EXIT
python3 - \
  "${root}/buf.gen.yaml" \
  "${temporary_output}" \
  "${BSR_MODULE_COMMIT}" \
  "${buf_cli_version}" \
  "${descriptor_sha256}" \
  "${git_commit}" <<'PY'
from pathlib import Path
import json
import re
import sys


configuration = Path(sys.argv[1])
output = Path(sys.argv[2])
bsr_module_commit = sys.argv[3]
buf_cli_version = sys.argv[4]
descriptor_sha256 = sys.argv[5]
git_commit = sys.argv[6]
generators = []
plugin_entries = []
current_entry = None
in_plugins = False
plugins_found = False


def record_field(entry, key, value, line_number):
    if key in entry:
        raise SystemExit(f"duplicate generator plugin field {key!r} on line {line_number}")
    if value == "":
        raise SystemExit(f"generator plugin field {key!r} is empty on line {line_number}")
    entry[key] = value


for line_number, line in enumerate(configuration.read_text().splitlines(), start=1):
    if not in_plugins:
        if re.fullmatch(r"plugins:\s*(?:#.*)?", line):
            in_plugins = True
            plugins_found = True
        continue

    if not line.strip() or line.lstrip().startswith("#"):
        continue
    if not line.startswith(" "):
        break

    item_match = re.fullmatch(
        r"  -(?:\s+([A-Za-z_][A-Za-z0-9_]*):\s*(.*))?", line
    )
    if item_match:
        if current_entry is not None:
            plugin_entries.append(current_entry)
        current_entry = {}
        if item_match.group(1) is not None:
            record_field(
                current_entry,
                item_match.group(1),
                item_match.group(2).strip(),
                line_number,
            )
        continue

    field_match = re.fullmatch(
        r"    ([A-Za-z_][A-Za-z0-9_]*):\s*(.*)", line
    )
    if field_match and current_entry is not None:
        record_field(
            current_entry,
            field_match.group(1),
            field_match.group(2).strip(),
            line_number,
        )
        continue

    raise SystemExit(f"unsupported buf.gen.yaml plugin structure on line {line_number}")

if current_entry is not None:
    plugin_entries.append(current_entry)
if not plugins_found or not plugin_entries:
    raise SystemExit("buf.gen.yaml must contain at least one generator plugin")

plugin_kind_fields = {"remote", "local", "protoc_builtin"}
metadata_fields = {
    "revision",
    "out",
    "opt",
    "include_imports",
    "include_wkt",
    "strategy",
}
seen_names = set()

for entry in plugin_entries:
    kinds = plugin_kind_fields.intersection(entry)
    if len(kinds) > 1:
        raise SystemExit("generator plugin must select exactly one kind")
    if not kinds:
        raise SystemExit("unknown generator plugin kind")
    unknown_fields = set(entry).difference(plugin_kind_fields, metadata_fields)
    if unknown_fields:
        unknown = sorted(unknown_fields)[0]
        raise SystemExit(f"unknown generator plugin field {unknown!r}")
    if kinds != {"remote"}:
        raise SystemExit("only remote generator plugins are allowed")

    remote = entry["remote"].strip("'\"")
    remote_match = re.fullmatch(
        r"(buf\.build/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):"
        r"(v[0-9]+(?:\.[0-9]+){1,2})",
        remote,
    )
    if remote_match is None:
        raise SystemExit("generator remote must pin an explicit version")
    name, version = remote_match.groups()
    if name in seen_names:
        raise SystemExit(f"duplicate generator plugin name {name!r}")
    seen_names.add(name)

    revision_text = entry.get("revision")
    if revision_text is None:
        raise SystemExit("generator remote must pin an explicit revision")
    if re.fullmatch(r"[1-9][0-9]*", revision_text) is None:
        raise SystemExit("generator revision must be positive")
    generators.append(
        {"name": name, "version": version, "revision": int(revision_text)}
    )

manifest = {
    "bsrModule": "buf.build/kaizen/rosetta",
    "bsrModuleCommit": bsr_module_commit,
    "bufCliVersion": buf_cli_version,
    "descriptorSha256": descriptor_sha256,
    "generatorPinsDocument": "docs/generator-pins.md",
    "generators": sorted(generators, key=lambda generator: generator["name"]),
    "gitCommit": git_commit,
}
output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
PY
mv -f -- "${temporary_output}" "${manifest_output}"
trap - EXIT
