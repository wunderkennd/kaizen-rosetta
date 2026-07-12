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
    python3 scripts/fix_connectrpc_python_imports.py

python-contracts venv="/tmp/rosetta-test-venv":
    "${PYTHON_TEST_BIN:-python3}" -m venv "{{venv}}"
    "{{venv}}/bin/python" -m pip install -e tests/python
    "{{venv}}/bin/python" -m pytest tests/python -q

descriptor:
    ./scripts/descriptor_digest.sh

release-manifest: descriptor
    ./scripts/build_release_manifest.sh
    python3 -m json.tool dist/release-manifest.json > /dev/null

fixtures:
    python3 scripts/check_fixture_shape.py
    python3 -m unittest scripts/test_check_fixture_shape.py

check:
    buf format --diff --exit-code
    buf lint
    buf build
    python3 scripts/check_fixture_shape.py
    python3 -m unittest scripts/test_check_fixture_shape.py
    python3 -m unittest scripts/test_fix_connectrpc_python_imports.py
    python3 -m unittest scripts/test_build_release_manifest.py
