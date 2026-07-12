#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

convert_expect_pass() {
  local message_type="$1"
  local payload="$2"
  printf '%s' "${payload}" \
    | buf convert "${root}" \
        --type "${message_type}" \
        --from=-#format=json \
        --to=-#format=binpb \
        --validate \
        >/dev/null
}

convert_expect_fail() {
  local message_type="$1"
  local payload="$2"
  local label="$3"
  if convert_expect_pass "${message_type}" "${payload}" >/dev/null 2>&1; then
    printf 'expected schema validation failure: %s\n' "${label}" >&2
    return 1
  fi
}

for provenance in OBSERVED SYNTHETIC DEFAULT OVERLAY; do
  convert_expect_pass \
    kaizen.audience.v1.AudienceContext \
    "{\"attributes\":{\"country_code\":{\"value\":{\"stringValue\":\"US\"},\"provenance\":\"AUDIENCE_ATTRIBUTE_PROVENANCE_${provenance}\"}},\"registryVersion\":\"2026-07-12\"}"
done

convert_expect_fail \
  kaizen.audience.v1.AudienceContext \
  '{"attributes":{"country_code":{"value":{"stringValue":"US"},"provenance":"AUDIENCE_ATTRIBUTE_PROVENANCE_UNSPECIFIED"}},"registryVersion":"2026-07-12"}' \
  unspecified-provenance

for non_finite in NaN Infinity -Infinity; do
  convert_expect_fail \
    kaizen.audience.v1.AudienceValue \
    "{\"doubleValue\":\"${non_finite}\"}" \
    "double-${non_finite}"
done
