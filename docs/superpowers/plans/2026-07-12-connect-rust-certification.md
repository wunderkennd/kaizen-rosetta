# Connect-Rust Compatibility Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve tracking issue #3 by deciding the Rust distribution policy (#4), certifying a reproducible Connect-Rust consumer canary (#5), binding that canary to release evidence (#6), and either completing or explicitly deferring the optional Go/Rust adapter consolidation (#7).

**Architecture:** Keep Rosetta producer-owned and runtime-neutral. A small Rust canary exports one immutable BSR module commit into a temporary directory, runs `connectrpc-build` against the complete schema tree with a locked Cargo graph, verifies audience wire vectors and representative RPC shapes, and emits a deterministic consumer-compatibility evidence document. The release-manifest builder validates that document into a new `consumerCompatibility` section; existing BSR-generated SDK records remain unchanged.

**Tech Stack:** Buf CLI 1.66.0, Bash, Python 3.11 `unittest`, Just 1.46.0, Rust/Cargo 1.88.0, Connect-Rust 0.7.0, `connectrpc-build` 0.7.0, Buffa/Buffa Types 0.7.1, Serde JSON, RFC 8785 canonicalization.

## Global Constraints

- Implement in dependency order: #4, #5, #6, then optional #7; close #3 only after the child-issue audit passes.
- Preserve ADR-0001: Rosetta owns schemas, compatibility policy, generated-contract verification, descriptors, and release evidence; consumers own handlers, authentication, middleware, TLS, retries, limits, telemetry, deployment, performance, and domain bridges.
- Use `buf.build/kaizen/rosetta:045c39860c9c40178a3a1ed3088c218f` as the fixed CI certification baseline; its descriptor SHA-256 is `077c2d8d31c41bcdac5bc97ed1e6407dfdae95a80e0d86712c960b997dc254fa`.
- The recommended #4 decision is the consumer-aligned Cargo `build.rs` model with Rust 1.88.0, `connectrpc`/`connectrpc-build` 0.7.0, and `buffa`/`buffa-types` 0.7.1. Record Connect-Rust/Buffa 0.8.1 as an evaluated upgrade, not part of initial certification.
- Treat all 0.x minor upgrades as compatibility reviews: update the ADR, direct version pins, `Cargo.lock`, canary fixtures, and evidence schema in one reviewed change.
- Do not add a Rust remote plugin to `buf.gen.yaml` or a Rust entry to `generatedSdks` unless the #4 HITL decision selects a BSR-generated Cargo SDK that exposes the Buffa/Connect-Rust interface.
- Generate from an immutable BSR reference into a temporary directory. Never copy Rosetta-owned `.proto` files into a consumer fixture or commit generated Rust output.
- Run Cargo with `--locked`; direct runtime/codegen/message dependencies use exact `=` pins and the committed lockfile binds the complete transitive graph.
- Keep existing Go, TypeScript, Python, descriptor, breaking-change, and release-manifest behavior green.

---

## File Structure

### Policy and documentation

- Create `docs/decisions/0003-rust-contract-distribution.md`: selected near-term Rust distribution interface, exact versions/MSRV, 0.x policy, ownership boundary, and BSR Cargo adoption trigger.
- Modify `README.md`: intentionally asymmetric Go/Rust consumption guidance and local commands.
- Modify `docs/generator-pins.md`: Rust consumer pins and why they are not BSR generator pins.
- Modify `docs/architecture_overview.md`: producer certification versus consumer runtime ownership.
- Modify `scripts/test_repository_governance.py`: executable checks for the decision boundary.

### Rust canary

- Create `rust-toolchain.toml`: exact repository Rust channel `1.88.0` with minimal components.
- Create `tools/compatibility/rust/Cargo.toml`: isolated canary package with exact direct pins.
- Create `tools/compatibility/rust/Cargo.lock`: complete reproducible dependency graph.
- Create `tools/compatibility/rust/build.rs`: discover every exported `.proto`, generate Buffa messages and Connect traits, and fail on an empty tree.
- Create `tools/compatibility/rust/src/lib.rs`: include the complete generated package tree.
- Create `tools/compatibility/rust/tests/audience_wire.rs`: binary Protobuf and canonical ProtoJSON conformance.
- Create `tools/compatibility/rust/tests/service_shapes.rs`: unary and server-streaming generated-interface checks.
- Create `scripts/verify_rust_contracts.sh`: immutable export, descriptor verification, locked clean build/test, and evidence production.
- Create `scripts/write_rust_compatibility_evidence.py`: deterministic passed-evidence writer.
- Create `scripts/test_verify_rust_contracts.py`: missing-tool, version-drift, export, generation, compiler, and lockfile failure tests.
- Modify `Justfile`: focused `rust-contracts` recipe and deterministic test registration.
- Modify `.github/workflows/ci.yml`: install exact Rust toolchain and run the fixed-baseline canary.

### Release evidence

- Create `scripts/validate_consumer_compatibility.py`: strict Rust evidence parser/validator.
- Create `scripts/test_validate_consumer_compatibility.py`: deterministic positive and negative validation cases.
- Create `tools/release/consumer-compatibility-rust.example.json`: complete documented input shape.
- Modify `scripts/build_release_manifest.sh`: require validated canary evidence and add `consumerCompatibility` without changing `generatedSdks`.
- Modify `scripts/test_build_release_manifest.py`: fixture integration and fail-closed release tests.
- Modify `README.md`: release invocation and manifest field documentation.

### Optional consolidation (#7)

- Create `scripts/compatibility/run.py`: shared `go`, `rust`, and `all` verification interface.
- Create `scripts/compatibility/adapters/go.sh`: existing Go implementation, moved without behavior changes.
- Create `scripts/compatibility/adapters/rust.sh`: Rust canary implementation, moved without changing evidence.
- Modify `scripts/compile_generated_go.sh`: compatibility wrapper preserving the focused entry point.
- Modify `scripts/verify_rust_contracts.sh`: compatibility wrapper preserving the focused entry point.
- Create `scripts/test_contract_compatibility.py`: matrix, adapter-isolation, and language-attributed failure tests.
- Modify `Justfile`: add `contract-compatibility` while retaining `go-contracts` and `rust-contracts`.

---

### Task 1: Decide and document the Rust distribution model (#4, HITL)

**Files:**
- Create: `docs/decisions/0003-rust-contract-distribution.md`
- Modify: `README.md`
- Modify: `docs/generator-pins.md`
- Modify: `docs/architecture_overview.md`
- Test: `scripts/test_repository_governance.py`

**Interfaces:**
- Consumes: ADR-0001 ownership boundary; `kaizen-experimentation` pilot pins (`connectrpc`/`connectrpc-build` 0.7.0, `buffa`/`buffa-types` 0.7.1, edition 2024, MSRV 1.88); upstream Connect-Rust/Buffa 0.8.1; BSR Cargo registry capability.
- Produces: one approved `RustContractDistributionV1` policy used verbatim by Tasks 2-6.

- [ ] **Step 1: Add a failing governance test for the decision record and ownership boundary**

```python
def test_rust_distribution_decision_is_explicit_and_runtime_neutral(self) -> None:
    decision = (ROOT / "docs/decisions/0003-rust-contract-distribution.md").read_text()
    for required in (
        "Cargo build.rs from an immutable BSR export",
        "Rust 1.88.0",
        "connectrpc = 0.7.0",
        "connectrpc-build = 0.7.0",
        "buffa = 0.7.1",
        "buffa-types = 0.7.1",
        "consumer repositories own runtime handlers",
        "BSR-generated Cargo adoption trigger",
    ):
        self.assertIn(required, decision)

    buf_gen = (ROOT / "buf.gen.yaml").read_text()
    self.assertNotIn("connectrpc/rust", buf_gen)
    self.assertNotIn("connect-rust", buf_gen)
```

- [ ] **Step 2: Run the focused test and confirm it fails because ADR-0003 does not exist**

Run: `python3 -m unittest scripts/test_repository_governance.py -v`

Expected: FAIL with `FileNotFoundError` for `docs/decisions/0003-rust-contract-distribution.md`.

- [ ] **Step 3: Hold the HITL decision review using a fixed comparison matrix**

Record these three alternatives in ADR-0003:

| Alternative | Decision | Reason |
|---|---|---|
| Consumer-aligned `connectrpc-build` + Buffa from immutable BSR export | Select for v1 certification | Matches the working consumer pilot and validates the actual Connect-Rust interface without vendoring schemas. |
| BSR Cargo crate from a Prost-oriented community plugin | Reject for v1 | BSR Cargo distribution exists, but a Prost crate does not expose the Buffa types and Connect-Rust traits being certified. |
| Upgrade certification to Connect-Rust/Buffa 0.8.1 immediately | Defer | Upstream 0.8.1 is available, but combining a pre-1.0 migration with first certification would stop the canary from matching the supported consumer. |

The decision section must state:

```text
Rosetta v1 Rust certification uses Cargo build.rs from an immutable BSR export.
The certified baseline is Rust/Cargo 1.88.0, connectrpc 0.7.0,
connectrpc-build 0.7.0, buffa 0.7.1, and buffa-types 0.7.1.
Consumer repositories own runtime handlers, security, middleware, operations,
deployment, performance, and domain bridges.
```

- [ ] **Step 4: Document version and migration policy**

Add these binding rules to ADR-0003:

```text
- Exact direct crate pins and Cargo.lock define one certification line.
- A 0.x minor upgrade is treated as potentially breaking and requires a clean
  canary, corpus replay, generated trait review, and new release evidence.
- Patch upgrades are not automatic; they follow the same locked-canary update.
- Raise MSRV only in the same change that updates rust-toolchain.toml, CI, docs,
  and evidence validation.
- Adopt a BSR-generated Cargo SDK when a curated or approved plugin generates
  the Buffa messages and Connect-Rust client/server traits, publishes immutable
  commit-bound crates, and passes the same canary without build-time schema export.
```

- [ ] **Step 5: Update consumer guidance**

State in `README.md` and `docs/generator-pins.md` that Go consumes BSR-generated module coordinates while Rust v1 consumes an immutable schema export through locked build-time generation. Make clear that the asymmetry is intentional and that Rust pins are consumer-compatibility pins, not entries in `buf.gen.yaml`.

- [ ] **Step 6: Run documentation/governance tests**

Run: `python3 -m unittest scripts/test_repository_governance.py -v`

Expected: PASS.

- [ ] **Step 7: Commit and close #4**

```bash
git add docs/decisions/0003-rust-contract-distribution.md README.md docs/generator-pins.md docs/architecture_overview.md scripts/test_repository_governance.py
git commit -m "docs: decide Rust contract distribution"
```

Close #4 only after a human approves the selected alternative and exact pin policy.

---

### Task 2: Add the fail-closed Rust generation harness (#5 foundation)

**Files:**
- Create: `rust-toolchain.toml`
- Create: `tools/compatibility/rust/Cargo.toml`
- Create: `tools/compatibility/rust/Cargo.lock`
- Create: `tools/compatibility/rust/build.rs`
- Create: `tools/compatibility/rust/src/lib.rs`
- Create: `scripts/verify_rust_contracts.sh`
- Test: `scripts/test_verify_rust_contracts.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `ROSETTA_RUST_BSR_COMMIT`, `ROSETTA_RUST_DESCRIPTOR_SHA256`, Buf 1.66.0, Rust/Cargo 1.88.0.
- Produces: a clean generated Rust package tree and exit status; no committed generated output.

- [ ] **Step 1: Write failure-path tests first**

Use temporary fake executables, following `scripts/test_compile_generated_sdks.py`. Cover these observable failures:

```python
def test_rejects_missing_cargo(self): ...  # stderr contains "Cargo is unavailable"
def test_rejects_rust_version_drift(self): ...  # stderr contains "Rust version mismatch"
def test_rejects_git_shaped_bsr_commit(self): ...  # requires exactly 32 lowercase hex
def test_propagates_buf_export_failure(self): ...  # fake buf exits 17; script exits 17
def test_rejects_descriptor_mismatch(self): ...  # stderr contains "descriptor SHA-256 mismatch"
def test_propagates_cargo_generation_or_compile_failure(self): ...  # fake cargo exits 23
def test_uses_locked_dependency_resolution(self): ...  # captured argv contains "--locked"
```

- [ ] **Step 2: Run the tests and confirm the missing harness fails**

Run: `python3 -m unittest scripts/test_verify_rust_contracts.py -v`

Expected: FAIL because `scripts/verify_rust_contracts.sh` does not exist.

- [ ] **Step 3: Pin the Rust toolchain and direct crates**

Create `rust-toolchain.toml`:

```toml
[toolchain]
channel = "1.88.0"
profile = "minimal"
components = ["rustfmt"]
```

Create `tools/compatibility/rust/Cargo.toml`:

```toml
[package]
name = "rosetta-connect-rust-canary"
version = "0.1.0"
edition = "2024"
rust-version = "1.88"
publish = false

[dependencies]
buffa = { version = "=0.7.1", features = ["json"] }
buffa-types = { version = "=0.7.1", features = ["json"] }
connectrpc = { version = "=0.7.0", default-features = false, features = ["client", "server"] }
hex = "=0.4.3"
http-body = "=1.0.1"
serde = { version = "=1.0.219", features = ["derive"] }
serde_json = "=1.0.140"
serde_json_canonicalizer = "=0.3.2"

[build-dependencies]
connectrpc-build = "=0.7.0"
walkdir = "=2.5.0"
```

Generate and commit `Cargo.lock` with:

Run: `cargo +1.88.0 generate-lockfile --manifest-path tools/compatibility/rust/Cargo.toml`

Expected: a lockfile whose `connectrpc` and `connectrpc-build` entries are 0.7.0 and whose `buffa` and `buffa-types` entries are 0.7.1.

- [ ] **Step 4: Generate every exported package from `build.rs`**

```rust
use std::{env, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto_root = PathBuf::from(env::var("ROSETTA_PROTO_ROOT")?);
    let mut protos = walkdir::WalkDir::new(&proto_root)
        .into_iter()
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .filter(|entry| entry.file_type().is_file())
        .map(|entry| entry.into_path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "proto"))
        .collect::<Vec<_>>();
    protos.sort();
    if protos.is_empty() {
        return Err("immutable Rosetta export contains no .proto files".into());
    }
    println!("cargo:rerun-if-env-changed=ROSETTA_PROTO_ROOT");
    connectrpc_build::Config::new()
        .files(&protos)
        .includes(&[proto_root])
        .include_file("_connectrpc.rs")
        .compile()?;
    Ok(())
}
```

Create `src/lib.rs`:

```rust
#![allow(clippy::all)]
connectrpc::include_generated!();
```

- [ ] **Step 5: Implement immutable export and descriptor verification**

`scripts/verify_rust_contracts.sh` must:

1. Validate the 32-character BSR commit and 64-character descriptor digest.
2. Require `buf --version == 1.66.0`, `rustc --version` beginning `rustc 1.88.0 `, and `cargo --version` beginning `cargo 1.88.0 `.
3. Create one temporary workspace with `mktemp -d` and clean it with `trap`.
4. Run `buf export "buf.build/kaizen/rosetta:${ROSETTA_RUST_BSR_COMMIT}" --output "$workspace/proto"`.
5. Run `buf build` on the same reference, hash the descriptor, and compare it with `ROSETTA_RUST_DESCRIPTOR_SHA256`.
6. Run Cargo with external output only:

```bash
ROSETTA_PROTO_ROOT="${workspace}/proto" \
ROSETTA_CONFORMANCE_FILE="${root}/conformance/audience/v1/valid.jsonl" \
CARGO_TARGET_DIR="${workspace}/target" \
"${cargo_bin}" test \
  --manifest-path "${root}/tools/compatibility/rust/Cargo.toml" \
  --locked \
  --all-targets
```

- [ ] **Step 6: Ignore only transient output**

Add `/tools/compatibility/rust/target/` to `.gitignore`. Do not ignore `Cargo.lock` or the evidence example.

- [ ] **Step 7: Run failure tests and the clean compile**

Run: `python3 -m unittest scripts/test_verify_rust_contracts.py -v`

Expected: PASS.

Run:

```bash
ROSETTA_RUST_BSR_COMMIT=045c39860c9c40178a3a1ed3088c218f \
ROSETTA_RUST_DESCRIPTOR_SHA256=077c2d8d31c41bcdac5bc97ed1e6407dfdae95a80e0d86712c960b997dc254fa \
scripts/verify_rust_contracts.sh
```

Expected: the entire exported package tree compiles and the temporary target directory is removed.

- [ ] **Step 8: Commit the harness**

```bash
git add rust-toolchain.toml .gitignore tools/compatibility/rust scripts/verify_rust_contracts.sh scripts/test_verify_rust_contracts.py
git commit -m "test: add locked Connect-Rust generation canary"
```

---

### Task 3: Verify audience wire vectors and RPC interface shapes (#5 behavior)

**Files:**
- Create: `tools/compatibility/rust/tests/audience_wire.rs`
- Create: `tools/compatibility/rust/tests/service_shapes.rs`

**Interfaces:**
- Consumes: generated `kaizen::audience::v1` messages and `experimentation::assignment::v1` service constants/traits.
- Produces: the checks `audience-binary`, `audience-protojson`, `unary-interface`, and `server-streaming-interface` for evidence.

- [ ] **Step 1: Add a failing typed binary-vector test**

Define fixture structs for only the wire portion, read all 48 lines from `ROSETTA_CONFORMANCE_FILE`, decode `AudienceRule` and `AudienceContext` with `buffa::Message::decode_from_slice`, and assert semantic re-encoding by decoding the second encoding again:

```rust
fn assert_binary<M>(hex_input: &str)
where
    M: buffa::Message + std::fmt::Debug,
{
    let bytes = hex::decode(hex_input).expect("valid lowercase hex fixture");
    let decoded = M::decode_from_slice(&bytes).expect("Buffa decodes corpus bytes");
    let redecoded = M::decode_from_slice(&decoded.encode_to_vec())
        .expect("Buffa decodes its own output");
    assert_eq!(decoded, redecoded);
}
```

Expected initial result: FAIL until imports and generated package coverage are correct.

- [ ] **Step 2: Add canonical ProtoJSON verification**

For each message:

1. Decode `binaryHex` into the typed message.
2. Convert that typed message to `serde_json::Value`.
3. Canonicalize it with `serde_json_canonicalizer::to_string` and compare byte-for-byte with `canonicalProtoJson`.
4. Parse `canonicalProtoJson` into the same typed message and assert semantic equality with the binary-decoded message.

```rust
fn assert_protojson<M>(binary_hex: &str, canonical_json: &str)
where
    M: buffa::Message
        + serde::Serialize
        + serde::de::DeserializeOwned
        + std::fmt::Debug,
{
    let bytes = hex::decode(binary_hex).unwrap();
    let from_binary = M::decode_from_slice(&bytes).unwrap();
    let value = serde_json::to_value(&from_binary).unwrap();
    assert_eq!(serde_json_canonicalizer::to_string(&value).unwrap(), canonical_json);
    let from_json: M = serde_json::from_str(canonical_json).unwrap();
    assert_eq!(from_json, from_binary);
}
```

- [ ] **Step 3: Add compile-time unary and server-streaming assertions**

Use the generated service specs rather than implementing production handlers:

```rust
use rosetta_connect_rust_canary::experimentation::assignment::v1::{
    AssignmentService,
    AssignmentServiceClient,
    GetAssignmentRequest,
    StreamConfigUpdatesRequest,
    ASSIGNMENT_SERVICE_GET_ASSIGNMENT_SPEC,
    ASSIGNMENT_SERVICE_STREAM_CONFIG_UPDATES_SPEC,
};

fn assert_generated_handler_trait<S: AssignmentService>() {}

fn assert_generated_client_methods<T>(client: &AssignmentServiceClient<T>)
where
    T: connectrpc::client::ClientTransport,
    <T::ResponseBody as http_body::Body>::Error: std::fmt::Display,
{
    let _unary_future = client.get_assignment(GetAssignmentRequest::default());
    let _server_streaming_future =
        client.stream_config_updates(StreamConfigUpdatesRequest::default());
}

#[test]
fn generated_service_contains_unary_and_server_streaming_procedures() {
    assert_eq!(
        ASSIGNMENT_SERVICE_GET_ASSIGNMENT_SPEC.stream_type,
        connectrpc::StreamType::Unary,
    );
    assert_eq!(
        ASSIGNMENT_SERVICE_STREAM_CONFIG_UPDATES_SPEC.stream_type,
        connectrpc::StreamType::ServerStream,
    );
}
```

The generic functions are intentionally never invoked: Rust still type-checks the generated handler bound and both generated client calls. The public `Spec.stream_type` fields additionally verify the procedure shapes without introducing a listening server, handler behavior, or domain logic.

- [ ] **Step 4: Run the canary against the immutable baseline**

Run the Task 2 fixed-baseline command.

Expected: PASS across all 48 audience rule/context pairs and both procedure shapes.

- [ ] **Step 5: Commit the compatibility assertions**

```bash
git add tools/compatibility/rust/tests
git commit -m "test: certify Rust audience and RPC compatibility"
```

---

### Task 4: Produce canary evidence and run Rust in Just/CI (#5 completion)

**Files:**
- Create: `scripts/write_rust_compatibility_evidence.py`
- Modify: `scripts/verify_rust_contracts.sh`
- Modify: `scripts/test_verify_rust_contracts.py`
- Modify: `Justfile`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: a successful clean Task 2/3 canary run.
- Produces: `dist/consumer-compatibility-rust.json`, a `rosetta.consumer-compatibility.v1` document containing one `rosetta.consumer-compatibility.rust.v1` record.

- [ ] **Step 1: Add a failing test that no evidence survives failure**

Test that a fake Cargo failure removes any pre-existing evidence file and that success calls the writer only after Cargo exits zero.

- [ ] **Step 2: Write deterministic passed evidence**

The writer must emit exactly this envelope and record shape, with runtime values filled from verified inputs and `cargo metadata --locked`:

```json
{
  "records": [
    {
      "adapter": "connect-rust",
      "bsrModule": "buf.build/kaizen/rosetta",
      "bsrModuleCommit": "045c39860c9c40178a3a1ed3088c218f",
      "canary": "rust-contracts-v1",
      "cargoLockSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "cargoVersion": "1.88.0",
      "checks": [
        "all-generated-packages",
        "audience-binary",
        "audience-protojson",
        "server-streaming-interface",
        "unary-interface"
      ],
      "crateVersions": {
        "buffa": "0.7.1",
        "buffa-types": "0.7.1",
        "connectrpc": "0.7.0",
        "connectrpc-build": "0.7.0"
      },
      "descriptorSha256": "077c2d8d31c41bcdac5bc97ed1e6407dfdae95a80e0d86712c960b997dc254fa",
      "generationMode": "cargo-build-rs-bsr-export",
      "gitCommit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "rustVersion": "1.88.0",
      "schema": "rosetta.consumer-compatibility.rust.v1",
      "status": "passed"
    }
  ],
  "schema": "rosetta.consumer-compatibility.v1"
}
```

The example's repeated `a` and `b` hashes are syntactically valid documentation values. The writer must replace them with `hashlib.sha256(lockfile.read_bytes()).hexdigest()` and `git rev-parse --verify 'HEAD^{commit}'`, respectively. Write through a unique temporary file and `os.replace` it atomically.

- [ ] **Step 3: Add Just entry points**

```just
rust-bsr-commit := env_var_or_default("ROSETTA_RUST_BSR_COMMIT", "045c39860c9c40178a3a1ed3088c218f")
rust-descriptor-sha256 := env_var_or_default("ROSETTA_RUST_DESCRIPTOR_SHA256", "077c2d8d31c41bcdac5bc97ed1e6407dfdae95a80e0d86712c960b997dc254fa")

rust-contracts:
    ROSETTA_RUST_BSR_COMMIT="{{rust-bsr-commit}}" ROSETTA_RUST_DESCRIPTOR_SHA256="{{rust-descriptor-sha256}}" scripts/verify_rust_contracts.sh
```

Register `scripts/test_verify_rust_contracts.py` under `just check`.

- [ ] **Step 4: Add the exact Rust toolchain and canary to CI**

Before the canary, run:

```yaml
- name: Install Rust 1.88.0
  run: rustup toolchain install 1.88.0 --profile minimal

- name: Certify Connect-Rust contracts
  env:
    ROSETTA_RUST_BSR_COMMIT: 045c39860c9c40178a3a1ed3088c218f
    ROSETTA_RUST_DESCRIPTOR_SHA256: 077c2d8d31c41bcdac5bc97ed1e6407dfdae95a80e0d86712c960b997dc254fa
  run: just rust-contracts
```

- [ ] **Step 5: Verify all pre-existing language gates remain green**

Run:

```bash
just check
just generate
just generated-contracts
just python-contracts
just rust-contracts
```

Expected: all commands PASS; `git status --short` shows no generated Rust or temporary workspace files.

- [ ] **Step 6: Commit and close #5**

```bash
git add scripts/write_rust_compatibility_evidence.py scripts/verify_rust_contracts.sh scripts/test_verify_rust_contracts.py Justfile .github/workflows/ci.yml README.md
git commit -m "ci: certify Connect-Rust consumer contracts"
```

Close #5 after CI proves the fixed immutable baseline and all existing gates pass.

---

### Task 5: Validate Rust consumer-compatibility evidence (#6 foundation)

**Files:**
- Create: `scripts/validate_consumer_compatibility.py`
- Create: `scripts/test_validate_consumer_compatibility.py`
- Create: `tools/release/consumer-compatibility-rust.example.json`
- Modify: `Justfile`

**Interfaces:**
- Consumes: the Task 4 evidence document plus expected BSR commit, descriptor SHA-256, Git commit, and the tracked Cargo lockfile.
- Produces: one normalized Rust record safe for inclusion in `consumerCompatibility`.

- [ ] **Step 1: Write table-driven rejection tests**

Start from a valid one-record document and mutate exactly one field per subtest. Require deterministic errors for:

```python
CASES = {
    "missing": (lambda document: document["records"][0].pop("rustVersion"), "fields mismatch"),
    "stale BSR commit": (lambda document: document["records"][0].__setitem__("bsrModuleCommit", "f" * 32), "BSR commit mismatch"),
    "descriptor mismatch": (lambda document: document["records"][0].__setitem__("descriptorSha256", "f" * 64), "descriptor mismatch"),
    "Git mismatch": (lambda document: document["records"][0].__setitem__("gitCommit", "f" * 40), "Git commit mismatch"),
    "lock mismatch": (lambda document: document["records"][0].__setitem__("cargoLockSha256", "f" * 64), "Cargo.lock digest mismatch"),
    "failed": (lambda document: document["records"][0].__setitem__("status", "failed"), "status must be passed"),
    "wrong canary": (lambda document: document["records"][0].__setitem__("canary", "another-script"), "canary mismatch"),
    "wrong generation mode": (lambda document: document["records"][0].__setitem__("generationMode", "bsr-generated-sdk"), "generation mode mismatch"),
    "crate drift": (lambda document: document["records"][0]["crateVersions"].__setitem__("connectrpc", "0.8.1"), "crate version mismatch"),
    "duplicate": (lambda document: document["records"].append(document["records"][0]), "duplicate Rust evidence"),
}
```

- [ ] **Step 2: Run tests and confirm the validator is missing**

Run: `python3 -m unittest scripts/test_validate_consumer_compatibility.py -v`

Expected: FAIL with import/file-not-found error.

- [ ] **Step 3: Implement an exact-field validator**

Expose a document validator and keep record validation focused:

```python
def validate_document(
    document: dict[str, object],
    *,
    bsr_module_commit: str,
    descriptor_sha256: str,
    git_commit: str,
    cargo_lock_path: Path,
) -> dict[str, object]:
    """Require one unique Rust record and return its normalized value."""

def validate_rust_evidence(
    evidence: dict[str, object],
    *,
    bsr_module_commit: str,
    descriptor_sha256: str,
    git_commit: str,
    cargo_lock_path: Path,
) -> dict[str, object]:
    """Return a normalized passed record or raise ValueError fail-closed."""
```

Require exact document fields (`records`, `schema`), exactly one unique Rust record, exact record fields, exact five-check sorted list, exact crate map, the schema/canary/adapter constants, `status == "passed"`, and `generationMode == "cargo-build-rs-bsr-export"`. Recompute the lockfile SHA-256 from bytes rather than trusting another input.

- [ ] **Step 4: Add the complete example**

`tools/release/consumer-compatibility-rust.example.json` must use the fixed baseline commit/digest, exact crate/toolchain versions, all checks, and an obvious valid 40-character example Git hash. The README must say production automation replaces the commit/hash slots with canary output.

- [ ] **Step 5: Run validator tests and repository checks**

Run: `python3 -m unittest scripts/test_validate_consumer_compatibility.py -v`

Expected: PASS.

Run: `just check`

Expected: PASS after registering the new test module.

- [ ] **Step 6: Commit the validator**

```bash
git add scripts/validate_consumer_compatibility.py scripts/test_validate_consumer_compatibility.py tools/release/consumer-compatibility-rust.example.json Justfile
git commit -m "test: validate Rust compatibility evidence"
```

---

### Task 6: Bind validated Rust evidence into the release manifest (#6 completion)

**Files:**
- Modify: `scripts/build_release_manifest.sh`
- Modify: `scripts/test_build_release_manifest.py`
- Modify: `README.md`
- Modify: `docs/generator-pins.md`

**Interfaces:**
- Consumes: `ROSETTA_RUST_COMPATIBILITY_FILE` created only by `just rust-contracts` and Task 5 validator.
- Produces: `consumerCompatibility.rust` alongside unchanged `generatedSdks`.

- [ ] **Step 1: Extend release fixtures with valid Rust evidence**

In `make_project`, copy the Rust lockfile fixture, create a valid evidence file, and set:

```python
environment["ROSETTA_RUST_COMPATIBILITY_FILE"] = str(rust_evidence)
```

Update the deterministic expected manifest with:

```python
"consumerCompatibility": {
    "rust": valid_rust_evidence(
        module_commit=BASELINE_BSR_MODULE_COMMIT,
        descriptor_sha256=DESCRIPTOR_SHA256,
        git_commit=git_commit,
        cargo_lock_sha256=fixture_lock_digest,
    )
},
```

- [ ] **Step 2: Add release-builder rejection tests**

Cover missing file, empty file, invalid JSON, missing record, duplicate record, stale BSR commit, stale descriptor, stale Git commit, stale lock digest, wrong toolchain/crates, wrong canary, failed status, and dirty Rust canary source. Also assert the pre-existing `generatedSdks`, `generators`, and `retiredGenerators` values are byte-for-byte unchanged apart from the new sibling section.

- [ ] **Step 3: Run focused tests and confirm they fail**

Run: `python3 -m unittest scripts/test_build_release_manifest.py -v`

Expected: FAIL because the builder does not require or record consumer compatibility.

- [ ] **Step 4: Invoke the validator before manifest assembly**

Require `ROSETTA_RUST_COMPATIBILITY_FILE`, call the Task 5 CLI with the exact release values, and write normalized JSON to a unique temporary file. Pass that file as a new argument to the existing inline Python manifest assembler. Add only:

```python
"consumerCompatibility": {
    "rust": normalized_rust_evidence,
},
```

Do not add a seventh generator, generated SDK, coordinate, or publication status.

- [ ] **Step 5: Make the release recipe run a clean canary first**

Change `release-manifest` so a candidate release uses one BSR commit for descriptor verification, Rust canary generation, SDK resolution, and manifest assembly:

```just
release-manifest: descriptor rust-contracts
    test -s dist/consumer-compatibility-rust.json
    ROSETTA_RUST_COMPATIBILITY_FILE=dist/consumer-compatibility-rust.json ./scripts/build_release_manifest.sh
    python3 -m json.tool dist/release-manifest.json > /dev/null
```

The release invocation supplies `BSR_MODULE_COMMIT` and `ROSETTA_RUST_BSR_COMMIT` with the same candidate commit. Add an explicit equality check so mismatched variables fail before network access.

- [ ] **Step 6: Document release use and evidence meaning**

Update the command:

```bash
test -n "$BSR_MODULE_COMMIT"
test -n "$ROSETTA_RUST_DESCRIPTOR_SHA256"
test -s "$BSR_SDK_VERIFICATION_FILE"
ROSETTA_RUST_BSR_COMMIT="$BSR_MODULE_COMMIT" just release-manifest
```

Explain that `BSR_MODULE_COMMIT` is the exact commit returned by `buf push`, `ROSETTA_RUST_DESCRIPTOR_SHA256` is the digest produced by `just descriptor`, and `BSR_SDK_VERIFICATION_FILE` is the exact-coordinate verification input. The generated manifest stores only validated concrete values.

- [ ] **Step 7: Run the full deterministic and release test suite**

Run:

```bash
python3 -m unittest scripts/test_validate_consumer_compatibility.py -v
python3 -m unittest scripts/test_build_release_manifest.py -v
just check
just rust-contracts
```

Expected: PASS; repeated fixture builds produce byte-identical JSON.

- [ ] **Step 8: Commit and close #6**

```bash
git add scripts/build_release_manifest.sh scripts/test_build_release_manifest.py README.md docs/generator-pins.md Justfile
git commit -m "feat: bind Rust canary to release evidence"
```

Close #6 after a candidate manifest shows the separate Rust record and all fail-closed tests pass.

---

### Task 7: Consolidate Go and Rust compatibility adapters (#7, optional)

**Files:**
- Create: `scripts/compatibility/run.py`
- Create: `scripts/compatibility/adapters/go.sh`
- Create: `scripts/compatibility/adapters/rust.sh`
- Modify: `scripts/compile_generated_go.sh`
- Modify: `scripts/verify_rust_contracts.sh`
- Create: `scripts/test_contract_compatibility.py`
- Modify: `Justfile`
- Modify: `README.md`

**Interfaces:**
- Consumes: focused Go script behavior and the final Rust canary/evidence contract.
- Produces: `python3 scripts/compatibility/run.py {go|rust|all}`; wrappers and evidence remain stable.

- [ ] **Step 1: Apply the optional-slice decision gate**

Proceed only if #5 and #6 are closed, both adapters have duplicated orchestration worth centralizing, and the refactor does not change artifacts, versions, or evidence. Otherwise comment on #7 with this rationale and close it as explicitly deferred:

```text
Deferred after Rust certification: the current two adapters do not yet duplicate
enough policy to justify a shared module. The stable entry points and evidence
schema are documented; reopen when a third adapter or a second duplicated
orchestration rule appears. Deferral does not affect #5 or #6 evidence.
```

- [ ] **Step 2: If proceeding, write failing matrix tests**

Test `go`, `rust`, and `all`; assert execution order is deterministic (`go`, then `rust`), exact exit codes propagate, and errors use `go compatibility failed:` or `rust compatibility failed:`. Build temporary adapter directories with only one adapter to prove the shared runner remains useful after deleting either language.

- [ ] **Step 3: Implement the minimal shared interface**

```python
ADAPTERS = {
    "go": ROOT / "scripts/compatibility/adapters/go.sh",
    "rust": ROOT / "scripts/compatibility/adapters/rust.sh",
}

def run(names: list[str]) -> None:
    for name in names:
        result = subprocess.run([str(ADAPTERS[name])], cwd=ROOT, check=False)
        if result.returncode:
            raise SystemExit(f"{name} compatibility failed: exit {result.returncode}")
```

The real CLI must validate choices and translate `all` to the sorted adapter list.

- [ ] **Step 4: Move implementations and preserve wrappers**

Move existing logic without edits into the adapter scripts. Keep old paths as executable wrappers:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/compatibility/adapters/go.sh" "$@"
```

Use the analogous Rust wrapper. The Rust evidence fields, `rust-contracts-v1` canary ID, lock digest, and generated output must remain unchanged.

- [ ] **Step 5: Add shared and focused Just entries**

```just
contract-compatibility:
    python3 scripts/compatibility/run.py all

go-contracts:
    python3 scripts/compatibility/run.py go

rust-contracts:
    python3 scripts/compatibility/run.py rust
```

Keep `generated-contracts` running Go and TypeScript as before; do not silently add a networked Rust export to existing deterministic local generation.

- [ ] **Step 6: Verify the deletion test and unchanged semantics**

Run:

```bash
python3 -m unittest scripts/test_contract_compatibility.py -v
just go-contracts
just rust-contracts
just contract-compatibility
git diff --exit-code -- tools/compatibility/rust/Cargo.lock tools/release/consumer-compatibility-rust.example.json
```

Expected: PASS; failures name the responsible language; focused commands remain available.

- [ ] **Step 7: Commit and close #7**

```bash
git add scripts/compatibility scripts/compile_generated_go.sh scripts/verify_rust_contracts.sh scripts/test_contract_compatibility.py Justfile README.md
git commit -m "refactor: consolidate contract compatibility adapters"
```

Close #7 either with the implementation evidence above or with the explicit deferral rationale from Step 1.

---

### Task 8: Audit and close the tracking issue (#3)

**Files:**
- Modify only if gaps are found: `README.md`, `docs/decisions/0003-rust-contract-distribution.md`, `docs/generator-pins.md`

**Interfaces:**
- Consumes: completed #4, #5, #6, and completed/deferred #7.
- Produces: closure evidence for #3.

- [ ] **Step 1: Run every repository gate from a clean checkout**

```bash
just check
just generate
just generated-contracts
just python-contracts
just descriptor
just rust-contracts
```

If #7 was implemented, also run `just contract-compatibility`.

Expected: every command PASS and `git status --short` contains no generated or temporary artifacts.

- [ ] **Step 2: Inspect the Rust evidence and manifest fixture**

```bash
python3 -m json.tool dist/consumer-compatibility-rust.json
python3 -m unittest scripts/test_build_release_manifest.py -v
```

Confirm the Rust record binds BSR commit, descriptor, Git commit, toolchains, Cargo lock digest, exact crates, generation mode, five passed checks, and the `rust-contracts-v1` canary. Confirm existing generated SDK records are unchanged.

- [ ] **Step 3: Map every #3 acceptance criterion to evidence**

Use this closure checklist:

- Distribution decision and explicit version policy: ADR-0003 and #4.
- Immutable release compile: fixed BSR commit canary and #5 CI run.
- Unary/server-streaming/audience wire compatibility: Rust tests and #5 CI run.
- BSR/descriptor/toolchain/lock/crate binding: manifest `consumerCompatibility.rust` and #6 tests.
- Go compatibility: `just generated-contracts` and, if implemented, `just contract-compatibility`.
- Consumer-owned runtime boundary: ADR-0001, ADR-0003, and absence of runtime handlers.
- #4, #5, #6 closed; #7 closed implemented or explicitly deferred.

- [ ] **Step 4: Close #3**

Post the checklist with links to the merged commits and successful CI run. Close #3 only when every required child issue is closed and #7 has a recorded outcome.

---

## Self-Review Results

- **Spec coverage:** Every acceptance criterion from #3-#7 maps to a task and verification command. Runtime concerns are explicitly excluded.
- **Dependency consistency:** #4 produces the policy/pins used by #5; #5 produces evidence consumed by #6; #7 starts only after #5/#6 semantics are stable.
- **Type/name consistency:** The evidence schema is always `rosetta.consumer-compatibility.rust.v1`, adapter `connect-rust`, canary `rust-contracts-v1`, generation mode `cargo-build-rs-bsr-export`, and manifest path `consumerCompatibility.rust`.
- **Release-model consistency:** Rust remains separate from `generatedSdks`; Go/TypeScript/Python publication and usability evidence stays intact.
- **Optional work:** #7 has two valid resolution paths, and either path satisfies #3 only when the rationale is recorded and #7 is closed.
