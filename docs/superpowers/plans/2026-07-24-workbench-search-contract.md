# Workbench Search Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the governed `workbench.v1.WorkbenchSearchService` contract required by Rosetta #11, including title-first search, explicit episode expansion, typed safe provenance, executable validation, and generated-language compatibility.

**Architecture:** Add a dedicated additive `workbench/v1/search.proto` that imports the existing audience and Workbench resources rather than extending `PageWorkbenchService`. Rosetta validates transport-safe invariants with Protovalidate annotations and CEL; Workbench remains responsible for authorization, retrieval, ranking, pagination-token implementation, and Slice-A rejection of the reserved episode-search scope.

**Tech Stack:** Buf CLI 1.66.0, Protobuf v3, Protovalidate annotations/runtime 1.0.0, ConnectRPC Python generator 0.11.0, Google Protobuf generator v33.5/runtime 6.33.6, Go 1.26.1, TypeScript 5.9.3, Node.js 25.2.1, Python 3.11, unittest/pytest, Just 1.46.0.

## Global Constraints

- Work from `/Users/kennethsylvain/Prototypes/kaizen/kaizen-rosetta/.worktrees/workbench-search-v1` on `feat/workbench-search-v1-contracts`, based on `origin/main` commit `733510862bbe678107f283394b6ad7fe800821a8`.
- Rosetta owns the wire model. Do not add Workbench runtime, provider selection, SQL/filter construction, Databricks resources, or renderer behavior here.
- Add `WorkbenchSearchService`; do not add methods to `PageWorkbenchService`.
- Reuse `workbench.v1.ResourceKind` and `CraftedHistoryEntry`; do not redefine either.
- Cross-app search/history transport exposes no arbitrary SQL, filter expression, table/index/endpoint name, credential, embedding, model logits, query plan, provider-native payload, or provider-native score.
- `SearchScope` includes `TITLE` and reserved `EPISODE`; Workbench Slice A rejects `EPISODE` at runtime.
- Public bounds are exact: query `1..512` UTF-8 bytes and contains non-whitespace; result limit `1..50`; episode page size `1..100`; IDs `1..256` UTF-8 bytes and contain non-whitespace; request/correlation IDs at most `128` UTF-8 bytes; opaque page tokens at most `2048` UTF-8 bytes; response warnings at most `20`.
- Search results are bounded to `50`, episode results to `100`, retrieval contributions to `2`, and matched-field categories to `3`.
- Fused scores and routing weights are finite and nonnegative; lexical and semantic weights are individually in `[0,1]` and sum to `1.0` within `1e-9`.
- Retrieval contributions use unique lane kinds and one-based ranks. Final result ranks are one-based, unique, and contiguous; Workbench preserves ordered monotonic serialization.
- Request IDs remain optional wire correlation values. Workbench’s trusted-renderer middleware separately requires an `x-request-id` header.
- The currently certified generated-language matrix is Go, TypeScript, and Python. Rust certification remains a separately tracked Rosetta follow-up and is not a blocker for issue #11.
- This change is additive and must pass breaking checks against both `buf.build/kaizen/rosetta` and immutable Workbench baseline `buf.build/kaizen/rosetta:045c39860c9c40178a3a1ed3088c218f`.
- Do not commit `gen/`, `dist/`, virtual environments, or `.superpowers/` execution artifacts.

---

### Task 1: Define the additive Workbench search schema

**Files:**
- Create: `proto/workbench/v1/search.proto`
- Modify: `scripts/test_workbench_schema.py`

**Interfaces:**
- Consumes: `kaizen.audience.v1.AudienceContext`, `workbench.v1.ResourceKind`, and the existing `workbench.v1` package.
- Produces: `WorkbenchSearchService`, `SearchTitlesRequest/Response`, `ListTitleEpisodesRequest/Response`, and all typed search/provenance messages and enums used by generated consumers.

- [ ] **Step 1: Write failing descriptor tests for the new service and closed wire surface**

Extend `scripts/test_workbench_schema.py` with helpers that build one descriptor set per test class and locate `workbench/v1/search.proto`. Add assertions for:

```python
SEARCH_ENUMS = {
    "SearchScope": [
        "SEARCH_SCOPE_UNSPECIFIED",
        "SEARCH_SCOPE_TITLE",
        "SEARCH_SCOPE_EPISODE",
    ],
    "RetrievalLane": [
        "RETRIEVAL_LANE_UNSPECIFIED",
        "RETRIEVAL_LANE_LEXICAL",
        "RETRIEVAL_LANE_SEMANTIC",
    ],
    "RoutingMode": [
        "ROUTING_MODE_UNSPECIFIED",
        "ROUTING_MODE_DISABLED",
        "ROUTING_MODE_HEURISTIC",
        "ROUTING_MODE_MODEL_SHADOW",
        "ROUTING_MODE_MODEL_ACTIVE",
    ],
}

SEARCH_MESSAGES = {
    "SearchTitlesRequest": [
        "query",
        "scope",
        "audience_context",
        "limit",
        "request_id",
        "parent_title_id",
    ],
    "SearchTitlesResponse": [
        "contract_version",
        "results",
        "routing",
        "source",
        "warnings",
        "correlation_id",
    ],
    "ListTitleEpisodesRequest": [
        "parent_title_id",
        "audience_context",
        "page_size",
        "page_token",
        "request_id",
    ],
    "ListTitleEpisodesResponse": [
        "contract_version",
        "episodes",
        "next_page_token",
        "repository_status",
        "warnings",
        "correlation_id",
    ],
}
```

Assert that:

- `WorkbenchSearchService` has exactly `SearchTitles` then `ListTitleEpisodes`;
- the search file depends on `buf/validate/validate.proto`, `kaizen/audience/v1/context.proto`, and `workbench/v1/workbench.proto`;
- `SearchResult.detail` is a required oneof with `title` and `episode`;
- `SearchTitlesRequest` has message-level CEL forbidding `parent_title_id` with `TITLE`;
- `SearchTitlesResponse` has CEL for unique contiguous final ranks;
- `SearchResult.contributions` has CEL uniqueness by lane;
- `RoutingManifest` has CEL for normalized weights and mode-dependent model identity;
- no field name contains `sql`, `filter_expression`, `table`, `index`, `endpoint`, `credential`, `embedding`, `logit`, `query_plan`, `native_score`, or `provider_payload`.

- [ ] **Step 2: Run the descriptor test and verify RED**

Run:

```bash
ROSETTA_TOOLING_VENV=/tmp/kaizen-rosetta-tooling-venv just tooling-sync
/tmp/kaizen-rosetta-tooling-venv/bin/python -m unittest scripts/test_workbench_schema.py -v
```

Expected: FAIL because `workbench/v1/search.proto` and `WorkbenchSearchService` do not exist.

- [ ] **Step 3: Add the schema with fixed enum vocabulary**

Create `proto/workbench/v1/search.proto` with `syntax = "proto3"`, package `workbench.v1`, and the three imports named above.

Define these enums in the listed order:

```protobuf
enum SearchScope {
  SEARCH_SCOPE_UNSPECIFIED = 0;
  SEARCH_SCOPE_TITLE = 1;
  SEARCH_SCOPE_EPISODE = 2;
}

enum RetrievalLane {
  RETRIEVAL_LANE_UNSPECIFIED = 0;
  RETRIEVAL_LANE_LEXICAL = 1;
  RETRIEVAL_LANE_SEMANTIC = 2;
}

enum ExactMatchClass {
  EXACT_MATCH_CLASS_UNSPECIFIED = 0;
  EXACT_MATCH_CLASS_NONE = 1;
  EXACT_MATCH_CLASS_CANONICAL_EXACT = 2;
  EXACT_MATCH_CLASS_ALIAS_EXACT = 3;
  EXACT_MATCH_CLASS_PREFIX = 4;
}

enum MatchedField {
  MATCHED_FIELD_UNSPECIFIED = 0;
  MATCHED_FIELD_CANONICAL_TITLE = 1;
  MATCHED_FIELD_ALIAS = 2;
  MATCHED_FIELD_DESCRIPTION = 3;
}

enum SearchStatus {
  SEARCH_STATUS_UNSPECIFIED = 0;
  SEARCH_STATUS_OK = 1;
  SEARCH_STATUS_EMPTY = 2;
  SEARCH_STATUS_TIMEOUT = 3;
  SEARCH_STATUS_UNAVAILABLE = 4;
  SEARCH_STATUS_INVALID_RESPONSE = 5;
  SEARCH_STATUS_CAPACITY_EXHAUSTED = 6;
  SEARCH_STATUS_PERMISSION_DENIED = 7;
  SEARCH_STATUS_CONFIGURATION_ERROR = 8;
  SEARCH_STATUS_DEGRADED = 9;
}

enum SourceMode {
  SOURCE_MODE_UNSPECIFIED = 0;
  SOURCE_MODE_PRIMARY = 1;
  SOURCE_MODE_SHADOW = 2;
}

enum RoutingMode {
  ROUTING_MODE_UNSPECIFIED = 0;
  ROUTING_MODE_DISABLED = 1;
  ROUTING_MODE_HEURISTIC = 2;
  ROUTING_MODE_MODEL_SHADOW = 3;
  ROUTING_MODE_MODEL_ACTIVE = 4;
}

enum LanguageHint {
  LANGUAGE_HINT_UNSPECIFIED = 0;
  LANGUAGE_HINT_UNKNOWN = 1;
  LANGUAGE_HINT_ENGLISH = 2;
  LANGUAGE_HINT_JAPANESE = 3;
  LANGUAGE_HINT_OTHER = 4;
}

enum ScriptHint {
  SCRIPT_HINT_UNSPECIFIED = 0;
  SCRIPT_HINT_UNKNOWN = 1;
  SCRIPT_HINT_LATIN = 2;
  SCRIPT_HINT_JAPANESE = 3;
  SCRIPT_HINT_MIXED = 4;
  SCRIPT_HINT_OTHER = 5;
}

enum RomajiHint {
  ROMAJI_HINT_UNSPECIFIED = 0;
  ROMAJI_HINT_UNKNOWN = 1;
  ROMAJI_HINT_UNLIKELY = 2;
  ROMAJI_HINT_POSSIBLE = 3;
  ROMAJI_HINT_LIKELY = 4;
}

enum ConfidenceBand {
  CONFIDENCE_BAND_UNSPECIFIED = 0;
  CONFIDENCE_BAND_UNKNOWN = 1;
  CONFIDENCE_BAND_LOW = 2;
  CONFIDENCE_BAND_MEDIUM = 3;
  CONFIDENCE_BAND_HIGH = 4;
}

enum RoutingReasonCode {
  ROUTING_REASON_CODE_UNSPECIFIED = 0;
  ROUTING_REASON_CODE_BALANCED_DEFAULT = 1;
  ROUTING_REASON_CODE_ANALYZER_FAILURE = 2;
  ROUTING_REASON_CODE_CANONICAL_EXACT = 3;
  ROUTING_REASON_CODE_ALIAS_EXACT = 4;
  ROUTING_REASON_CODE_DESCRIPTIVE_QUERY = 5;
  ROUTING_REASON_CODE_ROMAJI_OR_MIXED_SCRIPT = 6;
  ROUTING_REASON_CODE_SINGLE_HEALTHY_LANE = 7;
  ROUTING_REASON_CODE_LOW_CONFIDENCE = 8;
  ROUTING_REASON_CODE_MODEL_SHADOW_ONLY = 9;
  ROUTING_REASON_CODE_MODEL_ACTIVE = 10;
}

enum SearchWarningCode {
  SEARCH_WARNING_CODE_UNSPECIFIED = 0;
  SEARCH_WARNING_CODE_LEXICAL_TIMEOUT = 1;
  SEARCH_WARNING_CODE_LEXICAL_UNAVAILABLE = 2;
  SEARCH_WARNING_CODE_LEXICAL_INVALID_RESPONSE = 3;
  SEARCH_WARNING_CODE_LEXICAL_CAPACITY = 4;
  SEARCH_WARNING_CODE_SEMANTIC_TIMEOUT = 5;
  SEARCH_WARNING_CODE_SEMANTIC_UNAVAILABLE = 6;
  SEARCH_WARNING_CODE_SEMANTIC_INVALID_RESPONSE = 7;
  SEARCH_WARNING_CODE_SEMANTIC_CAPACITY = 8;
  SEARCH_WARNING_CODE_ROUTING_FALLBACK = 9;
  SEARCH_WARNING_CODE_MALFORMED_CANDIDATE_DROPPED = 10;
  SEARCH_WARNING_CODE_PARTIAL_EPISODE_RESULTS = 11;
}
```

- [ ] **Step 4: Add requests, results, provenance, routing, and episode messages**

Define the messages with these exact field numbers and constraints:

```protobuf
message SearchTitlesRequest {
  option (buf.validate.message).cel = {
    id: "search_titles_request.title_forbids_parent"
    message: "parent_title_id is not allowed for title search"
    expression: "this.scope != workbench.v1.SEARCH_SCOPE_TITLE || !has(this.parent_title_id)"
  };

  string query = 1 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 512
    pattern: "\\S"
  }];
  SearchScope scope = 2 [(buf.validate.field).enum = {
    defined_only: true
    not_in: 0
  }];
  kaizen.audience.v1.AudienceContext audience_context = 3 [(buf.validate.field).required = true];
  uint32 limit = 4 [(buf.validate.field).uint32 = {
    gte: 1
    lte: 50
  }];
  string request_id = 5 [(buf.validate.field).string.max_bytes = 128];
  optional string parent_title_id = 6 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 256
    pattern: "\\S"
  }];
}

message TitleSearchDetail {
  bool episode_details_available = 1;
}

message EpisodeSearchDetail {
  string parent_title_id = 1 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 256
    pattern: "\\S"
  }];
  string season_display = 2 [(buf.validate.field).string.max_bytes = 128];
  string episode_display = 3 [(buf.validate.field).string.max_bytes = 128];
}

message RetrievalContribution {
  RetrievalLane lane = 1 [(buf.validate.field).enum = {
    defined_only: true
    not_in: 0
  }];
  uint32 rank = 2 [(buf.validate.field).uint32 = {
    gte: 1
    lte: 1000
  }];
}

message AudienceFilterProvenance {
  string policy_id = 1 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 128
  }];
  string policy_version = 2 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 64
  }];
  string registry_version = 3 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 64
  }];
}

message SearchResult {
  option (buf.validate.message).cel = {
    id: "search_result.detail_matches_resource_kind"
    message: "result detail must match resource kind"
    expression: "(has(this.title) && (this.resource_kind == workbench.v1.RESOURCE_KIND_SERIES || this.resource_kind == workbench.v1.RESOURCE_KIND_MOVIE)) || (has(this.episode) && this.resource_kind == workbench.v1.RESOURCE_KIND_EPISODE)"
  };

  string resource_id = 1 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 256
    pattern: "\\S"
  }];
  ResourceKind resource_kind = 2 [(buf.validate.field).enum = {
    defined_only: true
    not_in: 0
  }];
  oneof detail {
    option (buf.validate.oneof).required = true;
    TitleSearchDetail title = 3;
    EpisodeSearchDetail episode = 4;
  }
  string display_title = 5 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 512
    pattern: "\\S"
  }];
  string description = 6 [(buf.validate.field).string.max_bytes = 2048];
  string image_url = 7 [(buf.validate.field).string.max_bytes = 2048];
  uint32 final_rank = 8 [(buf.validate.field).uint32 = {
    gte: 1
    lte: 50
  }];
  double fused_score = 9 [(buf.validate.field).double = {
    gte: 0
    finite: true
  }];
  ExactMatchClass exact_match_class = 10 [(buf.validate.field).enum = {
    defined_only: true
    not_in: 0
  }];
  repeated RetrievalContribution contributions = 11 [
    (buf.validate.field).repeated = {
      max_items: 2
      items: {required: true}
    },
    (buf.validate.field).cel = {
      id: "search_result.unique_contribution_lanes"
      message: "retrieval contribution lanes must be unique"
      expression: "this.map(contribution, contribution.lane).unique()"
    }
  ];
  repeated MatchedField matched_fields = 12 [(buf.validate.field).repeated = {
    max_items: 3
    unique: true
    items: {
      enum: {
        defined_only: true
        not_in: 0
      }
    }
  }];
  AudienceFilterProvenance audience = 13 [(buf.validate.field).required = true];
}
```

Add:

- `RoutingManifest` fields `mode=1`, `policy_id=2`, `policy_version=3`, optional `model_id=4`, optional `model_version=5`, `language_hint=6`, `script_hint=7`, `romaji_hint=8`, `confidence_band=9`, `lexical_weight=10`, `semantic_weight=11`, `fallback=12`, repeated unique typed `reason_codes=13` (max 10). Require all nonzero enums, finite bounded weights, normalized sum, model identity present only for modes 3/4 and required for modes 3/4, and model ID/version presence to agree.
- `SourceManifest` fields `logical_source_id=1`, `logical_source_version=2`, `document_manifest_version=3`, `manifest_build_id=4`, `mode=5`; bound strings to 128/64/128/128 bytes and require nonblank.
- `LaneManifest` fields `lane=1`, `status=2`, `candidate_count=3`; require nonzero enums and `candidate_count <= 1000`.
- `SearchSourceManifest` fields `source=1` required and `lanes=2` with exactly two required items plus CEL uniqueness by lane.
- `SearchWarning` fields `code=1` required nonzero enum and `message=2` required, nonblank, max 256 bytes.
- `SearchTitlesResponse` fields as listed in Step 1. Bound results/warnings, require routing/source, require nonblank `contract_version`/`correlation_id`, and add CEL:

```protobuf
option (buf.validate.message).cel = {
  id: "search_titles_response.unique_final_ranks"
  message: "final ranks must be unique"
  expression: "this.results.map(result, result.final_rank).unique()"
};
option (buf.validate.message).cel = {
  id: "search_titles_response.contiguous_final_ranks"
  message: "final ranks must be contiguous from one"
  expression: "this.results.all(result, result.final_rank <= uint(this.results.size()))"
};
```

Define `EpisodeResource` with exact fields:

1. `resource_id` required bounded ID;
2. `parent_title_id` required bounded ID;
3. `resource_kind` required `ResourceKind`;
4. `display_title` required, nonblank, max 512 bytes;
5. `season_display` max 128 bytes;
6. `episode_display` max 128 bytes;
7. `image_url` max 2048 bytes;
8. `season_order` uint32;
9. `episode_order` uint32;
10. `release_order` uint64.

Define request/response:

```protobuf
message ListTitleEpisodesRequest {
  string parent_title_id = 1 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 256
    pattern: "\\S"
  }];
  kaizen.audience.v1.AudienceContext audience_context = 2 [(buf.validate.field).required = true];
  uint32 page_size = 3 [(buf.validate.field).uint32 = {
    gte: 1
    lte: 100
  }];
  string page_token = 4 [(buf.validate.field).string.max_bytes = 2048];
  string request_id = 5 [(buf.validate.field).string.max_bytes = 128];
}

message ListTitleEpisodesResponse {
  string contract_version = 1 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 64
  }];
  repeated EpisodeResource episodes = 2 [(buf.validate.field).repeated.max_items = 100];
  string next_page_token = 3 [(buf.validate.field).string.max_bytes = 2048];
  SearchStatus repository_status = 4 [(buf.validate.field).enum = {
    defined_only: true
    not_in: 0
  }];
  repeated SearchWarning warnings = 5 [(buf.validate.field).repeated.max_items = 20];
  string correlation_id = 6 [(buf.validate.field).string = {
    min_bytes: 1
    max_bytes: 128
  }];
}
```

Finish with:

```protobuf
service WorkbenchSearchService {
  rpc SearchTitles(SearchTitlesRequest) returns (SearchTitlesResponse);
  rpc ListTitleEpisodes(ListTitleEpisodesRequest) returns (ListTitleEpisodesResponse);
}
```

- [ ] **Step 5: Format and run the focused schema gate**

Run:

```bash
buf format -w proto/workbench/v1/search.proto
/tmp/kaizen-rosetta-tooling-venv/bin/python -m unittest scripts/test_workbench_schema.py -v
buf lint
buf build
```

Expected: all descriptor tests pass and Buf accepts every standard/CEL validation rule.

- [ ] **Step 6: Commit Task 1**

```bash
git add proto/workbench/v1/search.proto scripts/test_workbench_schema.py
git commit -m "feat: define Workbench search contracts"
```

---

### Task 2: Prove generated validation and ConnectRPC behavior

**Files:**
- Modify: `tests/python/pyproject.toml`
- Create: `tests/python/test_workbench_search_contract.py`

**Interfaces:**
- Consumes: generated `workbench.v1.search_pb2`, `workbench.v1.search_connect`, `workbench.v1.workbench_pb2`, and `kaizen.audience.v1` modules.
- Produces: executable validation and generated JSON/ASGI compatibility evidence for both RPCs.

- [ ] **Step 1: Add the pinned validation runtime and RED imports**

Add `"protovalidate==1.0.0"` to `tests/python/pyproject.toml`.

Create `tests/python/test_workbench_search_contract.py` importing:

```python
from protovalidate import ValidationError, Validator
from workbench.v1.search_connect import (
    WorkbenchSearchService,
    WorkbenchSearchServiceASGIApplication,
    WorkbenchSearchServiceClient,
)
from workbench.v1.search_pb2 import (
    EXACT_MATCH_CLASS_CANONICAL_EXACT,
    MATCHED_FIELD_CANONICAL_TITLE,
    RETRIEVAL_LANE_LEXICAL,
    RETRIEVAL_LANE_SEMANTIC,
    ROUTING_MODE_HEURISTIC,
    SEARCH_SCOPE_TITLE,
    SEARCH_STATUS_OK,
    SOURCE_MODE_PRIMARY,
    AudienceFilterProvenance,
    EpisodeResource,
    LaneManifest,
    ListTitleEpisodesRequest,
    ListTitleEpisodesResponse,
    RetrievalContribution,
    RoutingManifest,
    SearchResult,
    SearchSourceManifest,
    SearchTitlesRequest,
    SearchTitlesResponse,
    SourceManifest,
    TitleSearchDetail,
)
```

Add a `StaticWorkbenchSearchService` implementing both generated methods and returning deterministic valid messages. Reuse the existing `invoke_asgi` style from `test_workbench_contract.py`, parameterized by path.

- [ ] **Step 2: Run generation/tests and verify RED**

Run:

```bash
just generate
PYTHON_TEST_BIN=/opt/homebrew/bin/python3.11 just python-contracts /tmp/rosetta-workbench-search-python-venv
```

Expected: FAIL until the new generated imports and test service fixtures agree with the schema; if Task 1 is already generated, the first newly added validation assertion must fail before its corresponding fixture/rule correction.

- [ ] **Step 3: Add executable request/result/routing validation cases**

Use one module-level `Validator()` and a helper:

```python
def assert_invalid(message) -> None:
    with pytest.raises(ValidationError):
        VALIDATOR.validate(message)
```

Prove:

- a complete title request is valid;
- blank/whitespace-only query and a 513-byte query fail;
- limit `0` and `51` fail;
- `TITLE` plus `parent_title_id` fails;
- missing audience context fails;
- blank/257-byte parent title ID and page sizes `0`/`101` fail;
- a `SearchResult` without its detail oneof fails;
- duplicate lexical contributions fail;
- contribution rank `0` fails;
- nonfinite/negative fused scores fail;
- routing weights outside `[0,1]` or not summing to one fail;
- model-active routing without model ID/version fails;
- heuristic routing with model ID/version fails;
- duplicate/noncontiguous final ranks fail;
- valid empty search results and valid empty episode pages pass.

- [ ] **Step 4: Add ProtoJSON, binary, and generated ASGI round trips**

Build one valid `SearchTitlesResponse` containing one canonical title exact result with lexical and semantic contributions, routing/source/lane manifests, audience provenance, and correlation ID. Build one valid episode response with deterministic season/episode/release fields.

For both request/response families:

- round-trip via `MessageToJson`/`Parse`;
- round-trip via `SerializeToString`/`FromString`;
- invoke generated ASGI paths:
  - `/workbench.v1.WorkbenchSearchService/SearchTitles`
  - `/workbench.v1.WorkbenchSearchService/ListTitleEpisodes`
- assert HTTP 200 and exact JSON fields;
- instantiate/close `WorkbenchSearchServiceClient` on the same event loop.

- [ ] **Step 5: Run the generated Python gate**

Run:

```bash
just generate
PYTHON_TEST_BIN=/opt/homebrew/bin/python3.11 just python-contracts /tmp/rosetta-workbench-search-python-venv
```

Expected: all generated Python contract and validation tests pass.

- [ ] **Step 6: Commit Task 2 and remove generated output**

```bash
git add tests/python/pyproject.toml tests/python/test_workbench_search_contract.py
git commit -m "test: verify Workbench search contracts"
rm -rf gen /tmp/rosetta-workbench-search-python-venv
```

---

### Task 3: Certify generated consumers and document ownership

**Files:**
- Modify: `tools/compile/audience_compile_test.go.template`
- Modify: `tools/compile/audience-smoke.ts.template`
- Modify: `README.md`
- Create: `docs/workbench_search_v1.md`

**Interfaces:**
- Consumes: generated Go/TypeScript/Python search symbols.
- Produces: explicit compile-time consumer evidence and the Rosetta-owned contract reference for Workbench #7.

- [ ] **Step 1: Write RED compile assertions**

Extend the Go compile template to import generated Workbench packages and type-check:

```go
var _ = &workbenchv1.SearchTitlesRequest{
    Query: "fullmetal",
    Scope: workbenchv1.SearchScope_SEARCH_SCOPE_TITLE,
    Limit: 20,
}
var _ workbenchv1connect.WorkbenchSearchServiceClient
```

Extend the TypeScript smoke template to import `SearchTitlesRequestSchema`, `SearchTitlesResponseSchema`, and `WorkbenchSearchService` from generated Workbench modules, create a request with `create(SearchTitlesRequestSchema, ...)`, and access both service method descriptors.

Run `just generate` followed by the compile gates after editing the templates. These are compile-coverage assertions over the schema completed in Tasks 1–2, so an immediate PASS is acceptable; no new production behavior is introduced in this step.

- [ ] **Step 2: Make the Go/TypeScript compile fixtures pass**

Use the generated import/module paths exactly as emitted by `just generate`. Keep the existing audience assertions intact. If the Python generator’s module names differ from the plan, use the generated names rather than creating compatibility aliases.

Run:

```bash
just generate
just generated-contracts
```

Expected: clean Go and TypeScript compilation.

- [ ] **Step 3: Document the governed contract**

Add `docs/workbench_search_v1.md` documenting:

- Rosetta owns only wire types and generated SDKs;
- Workbench owns retrieval, authorization, ranking, pagination-token signing, and UI behavior;
- `TITLE` is enabled in Slice A, `EPISODE` is reserved, and `ListTitleEpisodes` is the current explicit episode path;
- one-row-per-title indexing and future separate episode index;
- exact public size bounds;
- closed provenance/status/warning vocabularies and excluded provider details;
- current Go/TypeScript/Python compatibility matrix and separately tracked Rust certification;
- non-default BSR publication label `workbench-search-v1`;
- Workbench must pin the immutable BSR module commit rather than a mutable label.

Update `README.md`’s directory layout and generated-target sections to link this document and name the two Workbench services.

- [ ] **Step 4: Run complete Rosetta verification**

Run:

```bash
just check
just generate
just generated-contracts
PYTHON_TEST_BIN=/opt/homebrew/bin/python3.11 just python-contracts /tmp/rosetta-workbench-search-python-venv
BUF_BREAKING_AGAINST=buf.build/kaizen/rosetta just breaking
BUF_BREAKING_AGAINST=buf.build/kaizen/rosetta:045c39860c9c40178a3a1ed3088c218f just breaking
just descriptor
git diff --check
```

Expected: every command exits zero. `git status --short` contains only intentional source/documentation changes before the commit and ignored `gen/`/`dist/` output.

- [ ] **Step 5: Commit Task 3 and clean generated artifacts**

```bash
git add README.md docs/workbench_search_v1.md \
  tools/compile/audience_compile_test.go.template \
  tools/compile/audience-smoke.ts.template
git commit -m "docs: certify Workbench search consumers"
rm -rf gen dist /tmp/rosetta-workbench-search-python-venv
git status --short --branch
```

Expected: a clean feature branch ahead of `origin/main`.

---

## Release handoff

After all task reviews and the final whole-branch review pass:

1. Push the clean candidate to the BSR development label:

   ```bash
   buf push \
     --label workbench-search-v1 \
     --source-control-url "https://github.com/wunderkennd/kaizen-rosetta/commit/$(git rev-parse HEAD)"
   ```

2. Record the exact immutable `buf.build/kaizen/rosetta:<commit>` returned by `buf push`.
3. Verify the BSR descriptor matches the local candidate and resolve exact generated SDK metadata.
4. Build the release manifest with commit-bound verification evidence; do not promote the BSR default label.
5. Supply the immutable BSR module commit and Rosetta Git commit to the Workbench #7 lock-advance plan.
