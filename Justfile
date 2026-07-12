set shell := ["bash", "-euo", "pipefail", "-c"]

format:
    buf format -w

lint:
    buf lint

build:
    buf build

breaking:
    test -n "${BUF_BREAKING_AGAINST:-}"
    buf breaking --against "$BUF_BREAKING_AGAINST"

generate:
    buf generate

descriptor:
    ./scripts/descriptor_digest.sh

fixtures:
    python3 scripts/check_fixture_shape.py

check:
    buf format --diff --exit-code
    buf lint
    buf build
    python3 scripts/check_fixture_shape.py
