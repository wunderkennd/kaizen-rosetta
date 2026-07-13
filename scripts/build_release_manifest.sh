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
local_descriptor_file="${root}/dist/rosetta-descriptor.binpb"
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
if [[ ! -s "${local_descriptor_file}" ]]; then
  printf '%s\n' 'local descriptor is required' >&2
  exit 1
fi
computed_descriptor_sha256="$(
  shasum -a 256 "${local_descriptor_file}" | awk '{print $1}'
)"
if [[ "${computed_descriptor_sha256}" != "${descriptor_sha256}" ]]; then
  printf '%s\n' 'descriptor digest does not match local descriptor' >&2
  exit 1
fi

temporary_bsr_descriptor=""
bsr_descriptor_file="${BSR_DESCRIPTOR_FILE:-}"
if [[ -z "${bsr_descriptor_file}" ]]; then
  temporary_bsr_descriptor="$(mktemp "${root}/dist/bsr-descriptor.binpb.tmp.XXXXXX")"
  trap 'rm -f -- "${temporary_bsr_descriptor}"' EXIT
  buf build \
    "buf.build/kaizen/rosetta:${BSR_MODULE_COMMIT}" \
    --as-file-descriptor-set \
    -o "${temporary_bsr_descriptor}"
  bsr_descriptor_file="${temporary_bsr_descriptor}"
fi
if [[ ! -s "${bsr_descriptor_file}" ]]; then
  printf '%s\n' 'BSR descriptor is required' >&2
  exit 1
fi
if ! cmp -s -- "${local_descriptor_file}" "${bsr_descriptor_file}"; then
  printf '%s\n' 'BSR descriptor does not match local descriptor' >&2
  exit 1
fi
rm -f -- "${temporary_bsr_descriptor}"
trap - EXIT

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
  "tools/"
  "Justfile"
  "README.md"
  "docs/"
  ".github/"
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
temporary_sdk_metadata=""
trap 'rm -f -- "${temporary_output}" "${temporary_sdk_metadata}"' EXIT
sdk_metadata_file="${BSR_SDK_METADATA_FILE:-}"
if [[ -z "${sdk_metadata_file}" ]]; then
  temporary_sdk_metadata="$(mktemp "${manifest_output}.sdks.XXXXXX")"
  sdk_metadata_file="${temporary_sdk_metadata}"
  python3 "${root}/scripts/resolve_generated_sdks.py" \
    --buf-gen "${root}/buf.gen.yaml" \
    --module buf.build/kaizen/rosetta \
    --commit "${BSR_MODULE_COMMIT}" \
    --output "${sdk_metadata_file}"
fi
if [[ ! -s "${sdk_metadata_file}" ]]; then
  printf '%s\n' 'generated SDK metadata is required' >&2
  exit 1
fi
sdk_verification_file="${BSR_SDK_VERIFICATION_FILE:-}"
if [[ -z "${sdk_verification_file}" ]] || [[ ! -s "${sdk_verification_file}" ]]; then
  printf '%s\n' 'BSR_SDK_VERIFICATION_FILE is required' >&2
  exit 1
fi
python3 - \
  "${root}/buf.gen.yaml" \
  "${temporary_output}" \
  "${BSR_MODULE_COMMIT}" \
  "${buf_cli_version}" \
  "${descriptor_sha256}" \
  "${git_commit}" \
  "${sdk_metadata_file}" \
  "${sdk_verification_file}" <<'PY'
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
sdk_metadata_path = Path(sys.argv[7])
sdk_verification_path = Path(sys.argv[8])
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

try:
    sdk_metadata = json.loads(sdk_metadata_path.read_text())
except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"invalid generated SDK metadata: {error}") from error
if not isinstance(sdk_metadata, dict):
    raise SystemExit("generated SDK metadata must be an object")
if sdk_metadata.get("moduleCommit") != bsr_module_commit:
    raise SystemExit("generated SDK metadata module commit mismatch")
sdk_entries = sdk_metadata.get("sdks")
if not isinstance(sdk_entries, list):
    raise SystemExit("generated SDK metadata sdks must be an array")

pins = {generator["name"]: generator for generator in generators}
sdk_by_generator = {}
seen_coordinates = set()

retired_path = configuration.parent / "tools/release/retired-generators.json"
try:
    retired_generators = json.loads(retired_path.read_text())
except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"invalid retired generator metadata: {error}") from error
if not isinstance(retired_generators, list):
    raise SystemExit("retired generator metadata must be an array")
seen_retired = set()
for retired in retired_generators:
    if not isinstance(retired, dict):
        raise SystemExit("retired generator entry must be an object")
    if set(retired) != {"name", "version", "revision", "retiredDate", "reason"}:
        raise SystemExit("retired generator entry has invalid fields")
    name = retired["name"]
    if not isinstance(name, str) or re.fullmatch(
        r"buf\.build/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name
    ) is None:
        raise SystemExit("retired generator name is invalid")
    if name in pins:
        raise SystemExit(f"retired generator remains active: {name}")
    if name in seen_retired:
        raise SystemExit(f"duplicate retired generator: {name}")
    seen_retired.add(name)
    if not isinstance(retired["version"], str) or re.fullmatch(
        r"v[0-9]+(?:\.[0-9]+){1,2}", retired["version"]
    ) is None:
        raise SystemExit(f"retired generator version is invalid for {name}")
    if not isinstance(retired["revision"], int) or retired["revision"] < 1:
        raise SystemExit(f"retired generator revision is invalid for {name}")
    if not isinstance(retired["retiredDate"], str) or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", retired["retiredDate"]
    ) is None:
        raise SystemExit(f"retired generator date is invalid for {name}")
    if not isinstance(retired["reason"], str) or not retired["reason"]:
        raise SystemExit(f"retired generator reason is missing for {name}")


def expected_sdk_coordinate(generator):
    owner, plugin = generator.removeprefix("buf.build/").split("/")
    if plugin == "go":
        return "go", f"buf.build/gen/go/kaizen/rosetta/{owner}/{plugin}"
    if plugin == "es":
        return "npm", f"@buf/kaizen_rosetta.{owner}_{plugin}"
    if plugin in {"python", "pyi", "py"}:
        return "python", f"kaizen-rosetta-{owner}-{plugin}"
    raise SystemExit(f"no generated SDK coordinate mapping for {generator}")


for sdk in sdk_entries:
    if not isinstance(sdk, dict):
        raise SystemExit("generated SDK entry must be an object")
    generator = sdk.get("generator")
    if generator not in pins:
        raise SystemExit(f"unexpected generated SDK metadata for {generator!r}")
    if generator in sdk_by_generator:
        raise SystemExit(f"duplicate generated SDK metadata for {generator}")
    pin = pins[generator]
    if sdk.get("moduleCommit") != bsr_module_commit:
        raise SystemExit(f"generated SDK module commit mismatch for {generator}")
    if (
        sdk.get("pluginVersion") != pin["version"]
        or sdk.get("pluginRevision") != pin["revision"]
    ):
        raise SystemExit(f"generated SDK plugin pin mismatch for {generator}")
    expected_ecosystem, expected_coordinate = expected_sdk_coordinate(generator)
    if sdk.get("ecosystem") != expected_ecosystem:
        raise SystemExit(f"generated SDK ecosystem mismatch for {generator}")
    publication_status = sdk.get("publicationStatus")
    if publication_status == "published":
        coordinate = sdk.get("coordinate")
        version = sdk.get("version")
        if not isinstance(coordinate, str) or not coordinate:
            raise SystemExit(f"generated SDK coordinate missing for {generator}")
        if coordinate in seen_coordinates:
            raise SystemExit(f"duplicate generated SDK coordinate {coordinate}")
        seen_coordinates.add(coordinate)
        if coordinate != expected_coordinate:
            raise SystemExit(f"generated SDK coordinate mismatch for {generator}")
        if not isinstance(version, str) or not version:
            raise SystemExit(f"generated SDK version missing for {generator}")
        if bsr_module_commit[:12] not in version:
            raise SystemExit(
                f"generated SDK version/commit association mismatch for {generator}"
            )
        plugin_version = pin["version"]
        revision = pin["revision"]
        if expected_ecosystem == "python":
            version_core = plugin_version.removeprefix("v")
            if version_core.count(".") == 1:
                version_core += ".0"
            associated = version.startswith(f"{version_core}.{revision}.")
        elif expected_ecosystem == "npm":
            associated = version.startswith(
                f"{plugin_version.removeprefix('v')}-"
            ) and version.endswith(f".{revision}")
        else:
            associated = version.startswith(f"{plugin_version}-") and version.endswith(
                f".{revision}"
            )
        if not associated:
            raise SystemExit(
                f"generated SDK version/plugin association mismatch for {generator}"
            )
    elif publication_status == "unavailable":
        if "coordinate" in sdk or "version" in sdk:
            raise SystemExit(
                f"unavailable generated SDK must not claim coordinate/version for {generator}"
            )
        if not isinstance(sdk.get("reason"), str) or not sdk["reason"]:
            raise SystemExit(f"unavailable generated SDK reason missing for {generator}")
    else:
        raise SystemExit(f"invalid generated SDK publication status for {generator}")
    sdk_by_generator[generator] = dict(sdk)

missing_sdks = sorted(set(pins).difference(sdk_by_generator))
if missing_sdks:
    raise SystemExit(f"generated SDK metadata missing for {missing_sdks}")

try:
    verification_metadata = json.loads(sdk_verification_path.read_text())
except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"invalid generated SDK verification: {error}") from error
if not isinstance(verification_metadata, dict):
    raise SystemExit("generated SDK verification must be an object")
if verification_metadata.get("moduleCommit") != bsr_module_commit:
    raise SystemExit("generated SDK verification module commit mismatch")
verification_entries = verification_metadata.get("verifications")
if not isinstance(verification_entries, list):
    raise SystemExit("generated SDK verifications must be an array")
verification_by_generator = {}
for verification in verification_entries:
    if not isinstance(verification, dict):
        raise SystemExit("generated SDK verification entry must be an object")
    generator = verification.get("generator")
    if generator not in pins:
        raise SystemExit(f"unexpected generated SDK verification for {generator!r}")
    if generator in verification_by_generator:
        raise SystemExit(f"duplicate generated SDK verification for {generator}")
    sdk = sdk_by_generator[generator]
    if verification.get("moduleCommit") != sdk["moduleCommit"]:
        raise SystemExit(
            f"generated SDK verification module commit mismatch for {generator}"
        )
    if verification.get("ecosystem") != sdk["ecosystem"]:
        raise SystemExit(
            f"generated SDK verification ecosystem mismatch for {generator}"
        )
    if verification.get("pluginVersion") != sdk["pluginVersion"]:
        raise SystemExit(
            f"generated SDK verification plugin version mismatch for {generator}"
        )
    if verification.get("pluginRevision") != sdk["pluginRevision"]:
        raise SystemExit(
            f"generated SDK verification plugin revision mismatch for {generator}"
        )
    status = verification.get("status")
    usable = verification.get("usable")
    if not isinstance(usable, bool):
        raise SystemExit(f"generated SDK usable flag missing for {generator}")
    publication_status = sdk["publicationStatus"]
    if publication_status == "unavailable":
        if "coordinate" in verification or "version" in verification:
            raise SystemExit(
                "unavailable generated SDK verification must not claim "
                f"coordinate/version for {generator}"
            )
        if status != "not_applicable" or usable:
            raise SystemExit(
                f"unavailable generated SDK verification mismatch for {generator}"
            )
        if not isinstance(verification.get("reason"), str) or not verification["reason"]:
            raise SystemExit(
                f"unavailable generated SDK verification reason missing for {generator}"
            )
        expected_fields = {
            "ecosystem",
            "generator",
            "moduleCommit",
            "pluginRevision",
            "pluginVersion",
            "reason",
            "status",
            "usable",
        }
    else:
        if verification.get("coordinate") != sdk["coordinate"]:
            raise SystemExit(
                f"generated SDK verification coordinate mismatch for {generator}"
            )
        if verification.get("version") != sdk["version"]:
            raise SystemExit(
                f"generated SDK verification version mismatch for {generator}"
            )
    if publication_status != "unavailable" and status == "passed":
        if not usable:
            raise SystemExit(f"passed generated SDK must be usable for {generator}")
        if not isinstance(verification.get("evidence"), str) or not verification["evidence"]:
            raise SystemExit(f"generated SDK verification evidence missing for {generator}")
        if "reason" in verification:
            raise SystemExit(f"passed generated SDK must not include a reason for {generator}")
        expected_fields = {
            "coordinate",
            "ecosystem",
            "evidence",
            "generator",
            "moduleCommit",
            "pluginRevision",
            "pluginVersion",
            "status",
            "usable",
            "version",
        }
    elif publication_status != "unavailable" and status in {"failed", "not_run"}:
        if usable:
            raise SystemExit(f"unverified generated SDK cannot be usable for {generator}")
        if not isinstance(verification.get("reason"), str) or not verification["reason"]:
            raise SystemExit(f"generated SDK verification reason missing for {generator}")
        if "evidence" in verification:
            raise SystemExit(
                f"unusable generated SDK must not include passing evidence for {generator}"
            )
        expected_fields = {
            "coordinate",
            "ecosystem",
            "generator",
            "moduleCommit",
            "pluginRevision",
            "pluginVersion",
            "reason",
            "status",
            "usable",
            "version",
        }
    elif publication_status != "unavailable":
        raise SystemExit(f"invalid generated SDK verification status for {generator}")
    if set(verification) != expected_fields:
        raise SystemExit(
            f"generated SDK verification fields mismatch for {generator}"
        )
    verification_by_generator[generator] = verification

missing_verifications = sorted(set(pins).difference(verification_by_generator))
if missing_verifications:
    raise SystemExit(f"generated SDK verification missing for {missing_verifications}")
for generator, sdk in sdk_by_generator.items():
    sdk["verification"] = verification_by_generator[generator]

manifest = {
    "bsrModule": "buf.build/kaizen/rosetta",
    "bsrModuleCommit": bsr_module_commit,
    "bufCliVersion": buf_cli_version,
    "descriptorSha256": descriptor_sha256,
    "generatorPinsDocument": "docs/generator-pins.md",
    "generators": sorted(generators, key=lambda generator: generator["name"]),
    "generatedSdks": sorted(
        sdk_by_generator.values(), key=lambda sdk: sdk["generator"]
    ),
    "gitCommit": git_commit,
    "retiredGenerators": sorted(
        retired_generators, key=lambda generator: generator["name"]
    ),
}
output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
PY
mv -f -- "${temporary_output}" "${manifest_output}"
rm -f -- "${temporary_sdk_metadata}"
trap - EXIT
