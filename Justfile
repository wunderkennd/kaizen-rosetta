set shell := ["bash", "-euo", "pipefail", "-c"]

python-bin := env_var_or_default("ROSETTA_PYTHON_BIN", "python3")
tooling-venv := env_var_or_default("ROSETTA_TOOLING_VENV", "/tmp/kaizen-rosetta-tooling-venv")
rust-bsr-commit := env_var_or_default("ROSETTA_RUST_BSR_COMMIT", "045c39860c9c40178a3a1ed3088c218f")
rust-descriptor-sha256 := env_var_or_default("ROSETTA_RUST_DESCRIPTOR_SHA256", "077c2d8d31c41bcdac5bc97ed1e6407dfdae95a80e0d86712c960b997dc254fa")

tooling-sync:
    "{{python-bin}}" -m venv "{{tooling-venv}}"
    "{{tooling-venv}}/bin/python" -m pip install --disable-pip-version-check -q -r tools/python/requirements.lock

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

go-contracts:
    scripts/compile_generated_go.sh

typescript-contracts:
    scripts/compile_generated_ts.sh

generated-contracts:
    scripts/compile_generated_go.sh
    scripts/compile_generated_ts.sh

python-contracts venv="/tmp/rosetta-test-venv":
    "${PYTHON_TEST_BIN:-python3}" -m venv "{{venv}}"
    "{{venv}}/bin/python" -m pip install -e tests/python
    "{{venv}}/bin/python" -m pytest tests/python -q

rust-contracts:
    ROSETTA_RUST_BSR_COMMIT="{{rust-bsr-commit}}" ROSETTA_RUST_DESCRIPTOR_SHA256="{{rust-descriptor-sha256}}" scripts/verify_rust_contracts.sh

descriptor:
    ./scripts/descriptor_digest.sh

release-manifest: descriptor
    ./scripts/build_release_manifest.sh
    python3 -m json.tool dist/release-manifest.json > /dev/null

fixtures: tooling-sync
    "{{tooling-venv}}/bin/python" scripts/check_fixture_shape.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_check_fixture_shape.py
    scripts/check_audience_schema_validation.sh

registry: tooling-sync
    "{{tooling-venv}}/bin/python" scripts/check_registry.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_check_registry.py

check: tooling-sync
    buf format --diff --exit-code
    buf lint
    buf build
    "{{tooling-venv}}/bin/python" scripts/check_fixture_shape.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_check_fixture_shape.py
    scripts/check_audience_schema_validation.sh
    "{{tooling-venv}}/bin/python" scripts/check_registry.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_check_registry.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_fix_connectrpc_python_imports.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_compile_generated_sdks.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_resolve_generated_sdks.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_verify_rust_contracts.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_build_release_manifest.py
    "{{tooling-venv}}/bin/python" -m unittest scripts/test_repository_governance.py
