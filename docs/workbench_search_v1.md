# Workbench Search v1 Contract

`workbench/v1/search.proto` defines the provider-neutral transport shared by
the Workbench API and renderer. It is additive to
`workbench/v1/workbench.proto`: page preview remains on
`workbench.v1.PageWorkbenchService`, while search and episode expansion use
`workbench.v1.WorkbenchSearchService`.

## Ownership boundary

Rosetta owns:

- the Protobuf wire types, validation annotations, enum vocabularies, and RPC
  method definitions;
- the generated Go, TypeScript, and Python SDK surfaces; and
- compatibility evidence for those generated consumers.

Workbench owns:

- caller authorization and enforcement of Unity Catalog permissions;
- query analysis, retrieval-provider selection, lexical and semantic
  retrieval, routing, fusion, ranking, and degraded-result policy;
- construction and verification of audience filters;
- pagination behavior and signing, verification, and expiry of opaque page
  tokens; and
- API composition, renderer state, watch-history behavior, and all UI
  presentation.

Rosetta does not choose a search provider or prescribe a retrieval query. The
contract cannot carry arbitrary SQL, filter expressions, table names, index
names, endpoint names, credentials, embeddings, model logits, query plans,
provider-native payloads, or provider-native scores.

## Slice A scope

`SearchTitles` is title-first. `SEARCH_SCOPE_TITLE` is enabled in Workbench
Slice A. `SEARCH_SCOPE_EPISODE` is reserved for a later slice and Slice A must
reject it at runtime; publishing the enum value does not enable episode search.
For current episode detail, a client selects a title and then calls
`ListTitleEpisodes` with its `parent_title_id`.

The initial retrieval document model is one row per title. Episode expansion is
a separate repository operation, which leaves the transport compatible with a
future deployment that uses separate title and episode indices. Adding such an
index does not change the current ownership boundary or make
`SEARCH_SCOPE_EPISODE` active automatically.

## Public bounds

Bounds are measured as UTF-8 bytes for strings.

| Surface | Bound |
| --- | --- |
| Search query | 1–512 bytes and at least one non-whitespace character |
| Search result limit | 1–50 |
| Episode page size | 1–100 |
| Resource and parent-title IDs | 1–256 bytes and at least one non-whitespace character |
| Request IDs | At most 128 bytes |
| Correlation IDs | 1–128 bytes and at least one non-whitespace character for search; 1–128 bytes for episode expansion |
| Opaque page tokens | At most 2,048 bytes |
| Search results per response | At most 50 |
| Episode resources per response | At most 100 |
| Warnings per response | At most 20 |
| Retrieval contributions per result | At most 2, with unique lanes and one-based ranks |
| Matched-field categories per result | At most 3 and unique |
| Source lane manifests | Exactly 2 with unique lanes |
| Routing reason codes | At most 10 and unique |
| Display titles | 1–512 bytes and at least one non-whitespace character |
| Descriptions | At most 2,048 bytes |
| Image URLs | At most 2,048 bytes |
| Season and episode display strings | At most 128 bytes |
| Policy and logical source IDs | 1–128 bytes |
| Policy and logical source versions | 1–64 bytes |
| Document manifest and manifest build IDs | 1–128 bytes |

Fused scores and routing weights must be finite and nonnegative. Each routing
weight is in `[0, 1]`, and lexical plus semantic weight must equal `1.0` within
`1e-9`. Final result ranks are one-based, unique, and contiguous. These wire
rules bound accepted messages; Workbench can impose stricter operational limits
without changing the contract.

## Closed provenance and outcome vocabulary

Search exposes typed, provider-neutral provenance:

- `AudienceFilterProvenance` identifies the applied policy, policy version, and
  audience-registry version.
- `RoutingManifest` identifies the routing mode, policy, optional model
  identity, language/script/romaji/confidence hints, normalized lane weights,
  fallback state, and closed reason codes.
- `SearchSourceManifest` identifies a logical source, source version, document
  manifest version, manifest build, primary/shadow mode, and exactly one
  lexical plus one semantic lane status.
- `RetrievalContribution` records only the closed lexical or semantic lane and
  its one-based rank.

`SearchStatus` is closed to `OK`, `EMPTY`, `TIMEOUT`, `UNAVAILABLE`,
`INVALID_RESPONSE`, `CAPACITY_EXHAUSTED`, `PERMISSION_DENIED`,
`CONFIGURATION_ERROR`, and `DEGRADED`, plus the required `UNSPECIFIED` value.

`SearchWarningCode` is closed to lexical and semantic `TIMEOUT`,
`UNAVAILABLE`, `INVALID_RESPONSE`, and `CAPACITY` conditions, plus
`ROUTING_FALLBACK`, `MALFORMED_CANDIDATE_DROPPED`, and
`PARTIAL_EPISODE_RESULTS`, with the required `UNSPECIFIED` value. Warning text
is bounded explanatory text, not a channel for provider-native diagnostics.

Unknown future enum values must be handled as unknown by consumers. Providers
and their internal scores remain an implementation detail even when Workbench
changes from Databricks Vector Search to OpenSearch.

## Generated compatibility

| Consumer | Rosetta generation | Certification |
| --- | --- | --- |
| Go | Protobuf messages and Connect-Go client/server | Generated package compile and typed `WorkbenchSearchServiceClient` assertion |
| TypeScript | Protobuf-ES v2 messages and Connect service descriptors | Strict TypeScript compile, request/response creation, and both RPC descriptor assertions |
| Python | Google Protobuf messages/stubs and ConnectRPC Python services | Executable Protovalidate, serialization, ASGI route, and async-client tests |
| Rust | Not generated in the current Rosetta matrix | Separately tracked certification; not a blocker for this v1 contract |

The generated matrix certifies transport compatibility only. It does not move
retrieval, policy, or UI ownership into Rosetta.

## Publication and downstream pinning

Development publication uses the non-default BSR label
`workbench-search-v1`. The label is mutable and must not be used as a
downstream dependency lock. After review, publication returns an immutable BSR
module commit; Workbench must pin that exact
`buf.build/kaizen/rosetta:<module-commit>` coordinate and the corresponding
Rosetta Git commit. Rosetta must not promote the BSR default label as part of
this development slice.

The release manifest binds the local descriptor digest, Git commit, immutable
BSR module commit, generator pins, and exact generated-SDK verification.
Publication alone is not compatibility evidence, and Workbench must not advance
its lock from a mutable label.
