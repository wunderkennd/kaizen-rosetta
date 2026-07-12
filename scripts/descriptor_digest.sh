#!/usr/bin/env bash
set -euo pipefail

mkdir -p dist
buf build --as-file-descriptor-set -o dist/rosetta-descriptor.binpb
shasum -a 256 dist/rosetta-descriptor.binpb \
  | awk '{print $1}' \
  > dist/rosetta-descriptor.sha256
