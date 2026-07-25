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

String limits are measured as UTF-8 bytes. “Non-whitespace” below means the
field also has a `\S` pattern and must contain at least one non-whitespace
character. “Whitespace permitted” means there is no such pattern: a
whitespace-only value is wire-valid if it satisfies the byte bound.

### Search request and result

| Message field | Exact validation |
| --- | --- |
| `SearchTitlesRequest.query` | 1–512 bytes; non-whitespace |
| `SearchTitlesRequest.limit` | 1–50 |
| `SearchTitlesRequest.request_id` | 0–128 bytes; whitespace permitted |
| `SearchTitlesRequest.parent_title_id`, when present | 1–256 bytes; non-whitespace |
| `EpisodeSearchDetail.parent_title_id` | 1–256 bytes; non-whitespace |
| `EpisodeSearchDetail.season_display` | 0–128 bytes; whitespace permitted |
| `EpisodeSearchDetail.episode_display` | 0–128 bytes; whitespace permitted |
| `RetrievalContribution.rank` | 1–1,000 |
| `AudienceFilterProvenance.policy_id` | 1–128 bytes; whitespace-only values are permitted |
| `AudienceFilterProvenance.policy_version` | 1–64 bytes; whitespace-only values are permitted |
| `AudienceFilterProvenance.registry_version` | 1–64 bytes; whitespace-only values are permitted |
| `SearchResult.resource_id` | 1–256 bytes; non-whitespace |
| `SearchResult.display_title` | 1–512 bytes; non-whitespace |
| `SearchResult.description` | 0–2,048 bytes; whitespace permitted |
| `SearchResult.image_url` | 0–2,048 bytes; whitespace permitted |
| `SearchResult.final_rank` | 1–50; ranks in a response are also unique and contiguous from one |
| `SearchResult.fused_score` | Finite and greater than or equal to zero; no finite upper bound |
| `SearchResult.contributions` | 0–2 items; lane values must be unique |
| `SearchResult.matched_fields` | 0–3 items; values must be unique |

### Routing, source, and warning metadata

| Message field | Exact validation |
| --- | --- |
| `RoutingManifest.policy_id` | 1–128 bytes; non-whitespace |
| `RoutingManifest.policy_version` | 1–64 bytes; non-whitespace |
| `RoutingManifest.model_id`, when present | 1–128 bytes; non-whitespace |
| `RoutingManifest.model_version`, when present | 1–64 bytes; non-whitespace |
| `RoutingManifest.lexical_weight` | Finite and in `[0, 1]` |
| `RoutingManifest.semantic_weight` | Finite and in `[0, 1]` |
| `RoutingManifest.reason_codes` | 0–10 items; values must be unique |
| `SourceManifest.logical_source_id` | 1–128 bytes; non-whitespace |
| `SourceManifest.logical_source_version` | 1–64 bytes; non-whitespace |
| `SourceManifest.document_manifest_version` | 1–128 bytes; non-whitespace |
| `SourceManifest.manifest_build_id` | 1–128 bytes; non-whitespace |
| `LaneManifest.candidate_count` | 0–1,000 |
| `SearchSourceManifest.lanes` | Exactly 2 items; lane values must be unique |
| `SearchWarning.message` | 1–256 bytes; non-whitespace |

The two routing weights must sum to `1.0` within `1e-9`. Model ID and version
must both be present for model-shadow or model-active routing and must both be
absent for every other routing mode.

### Responses and episode expansion

| Message field | Exact validation |
| --- | --- |
| `SearchTitlesResponse.contract_version` | 1–64 bytes; non-whitespace |
| `SearchTitlesResponse.results` | 0–50 items |
| `SearchTitlesResponse.warnings` | 0–20 items |
| `SearchTitlesResponse.correlation_id` | 1–128 bytes; non-whitespace |
| `EpisodeResource.resource_id` | 1–256 bytes; non-whitespace |
| `EpisodeResource.parent_title_id` | 1–256 bytes; non-whitespace |
| `EpisodeResource.display_title` | 1–512 bytes; non-whitespace |
| `EpisodeResource.season_display` | 0–128 bytes; whitespace permitted |
| `EpisodeResource.episode_display` | 0–128 bytes; whitespace permitted |
| `EpisodeResource.image_url` | 0–2,048 bytes; whitespace permitted |
| `ListTitleEpisodesRequest.parent_title_id` | 1–256 bytes; non-whitespace |
| `ListTitleEpisodesRequest.page_size` | 1–100 |
| `ListTitleEpisodesRequest.page_token` | 0–2,048 bytes; whitespace permitted |
| `ListTitleEpisodesRequest.request_id` | 0–128 bytes; whitespace permitted |
| `ListTitleEpisodesResponse.contract_version` | 1–64 bytes; whitespace-only values are permitted |
| `ListTitleEpisodesResponse.episodes` | 0–100 items |
| `ListTitleEpisodesResponse.next_page_token` | 0–2,048 bytes; whitespace permitted |
| `ListTitleEpisodesResponse.warnings` | 0–20 items |
| `ListTitleEpisodesResponse.correlation_id` | 1–128 bytes; whitespace-only values are permitted |

Three episode ordering scalars have no additional Protovalidate rule:
`EpisodeResource.season_order` and `EpisodeResource.episode_order` retain the
native `uint32` range `0–4,294,967,295`, while
`EpisodeResource.release_order` retains the native `uint64` range
`0–18,446,744,073,709,551,615`. The
`TitleSearchDetail.episode_details_available` and `RoutingManifest.fallback`
fields are booleans.

Required message/relationship rules are also part of validation:

- both request families require `audience_context`;
- title scope forbids a present `SearchTitlesRequest.parent_title_id`;
- every `SearchResult` requires exactly one title/episode detail whose type
  agrees with `resource_kind`, plus audience provenance;
- `SearchSourceManifest.source`, `SearchTitlesResponse.routing`, and
  `SearchTitlesResponse.source` are required; and
- enum fields marked `defined_only` reject unknown numeric values, and the
  validated enum fields reject their zero `UNSPECIFIED` member.

These wire rules bound accepted messages. Workbench can impose stricter
operational limits without changing the contract.

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

The complete closed enum vocabularies are:

- `SearchScope`: `SEARCH_SCOPE_UNSPECIFIED`, `SEARCH_SCOPE_TITLE`,
  `SEARCH_SCOPE_EPISODE`.
- `RetrievalLane`: `RETRIEVAL_LANE_UNSPECIFIED`,
  `RETRIEVAL_LANE_LEXICAL`, `RETRIEVAL_LANE_SEMANTIC`.
- `ExactMatchClass`: `EXACT_MATCH_CLASS_UNSPECIFIED`,
  `EXACT_MATCH_CLASS_NONE`, `EXACT_MATCH_CLASS_CANONICAL_EXACT`,
  `EXACT_MATCH_CLASS_ALIAS_EXACT`, `EXACT_MATCH_CLASS_PREFIX`.
- `MatchedField`: `MATCHED_FIELD_UNSPECIFIED`,
  `MATCHED_FIELD_CANONICAL_TITLE`, `MATCHED_FIELD_ALIAS`,
  `MATCHED_FIELD_DESCRIPTION`.
- `SearchStatus`: `SEARCH_STATUS_UNSPECIFIED`, `SEARCH_STATUS_OK`,
  `SEARCH_STATUS_EMPTY`, `SEARCH_STATUS_TIMEOUT`,
  `SEARCH_STATUS_UNAVAILABLE`, `SEARCH_STATUS_INVALID_RESPONSE`,
  `SEARCH_STATUS_CAPACITY_EXHAUSTED`, `SEARCH_STATUS_PERMISSION_DENIED`,
  `SEARCH_STATUS_CONFIGURATION_ERROR`, `SEARCH_STATUS_DEGRADED`.
- `SourceMode`: `SOURCE_MODE_UNSPECIFIED`, `SOURCE_MODE_PRIMARY`,
  `SOURCE_MODE_SHADOW`.
- `RoutingMode`: `ROUTING_MODE_UNSPECIFIED`, `ROUTING_MODE_DISABLED`,
  `ROUTING_MODE_HEURISTIC`, `ROUTING_MODE_MODEL_SHADOW`,
  `ROUTING_MODE_MODEL_ACTIVE`.
- `LanguageHint`: `LANGUAGE_HINT_UNSPECIFIED`, `LANGUAGE_HINT_UNKNOWN`,
  `LANGUAGE_HINT_ENGLISH`, `LANGUAGE_HINT_JAPANESE`,
  `LANGUAGE_HINT_OTHER`.
- `ScriptHint`: `SCRIPT_HINT_UNSPECIFIED`, `SCRIPT_HINT_UNKNOWN`,
  `SCRIPT_HINT_LATIN`, `SCRIPT_HINT_JAPANESE`, `SCRIPT_HINT_MIXED`,
  `SCRIPT_HINT_OTHER`.
- `RomajiHint`: `ROMAJI_HINT_UNSPECIFIED`, `ROMAJI_HINT_UNKNOWN`,
  `ROMAJI_HINT_UNLIKELY`, `ROMAJI_HINT_POSSIBLE`, `ROMAJI_HINT_LIKELY`.
- `ConfidenceBand`: `CONFIDENCE_BAND_UNSPECIFIED`,
  `CONFIDENCE_BAND_UNKNOWN`, `CONFIDENCE_BAND_LOW`,
  `CONFIDENCE_BAND_MEDIUM`, `CONFIDENCE_BAND_HIGH`.
- `RoutingReasonCode`: `ROUTING_REASON_CODE_UNSPECIFIED`,
  `ROUTING_REASON_CODE_BALANCED_DEFAULT`,
  `ROUTING_REASON_CODE_ANALYZER_FAILURE`,
  `ROUTING_REASON_CODE_CANONICAL_EXACT`,
  `ROUTING_REASON_CODE_ALIAS_EXACT`,
  `ROUTING_REASON_CODE_DESCRIPTIVE_QUERY`,
  `ROUTING_REASON_CODE_ROMAJI_OR_MIXED_SCRIPT`,
  `ROUTING_REASON_CODE_SINGLE_HEALTHY_LANE`,
  `ROUTING_REASON_CODE_LOW_CONFIDENCE`,
  `ROUTING_REASON_CODE_MODEL_SHADOW_ONLY`,
  `ROUTING_REASON_CODE_MODEL_ACTIVE`.
- `SearchWarningCode`: `SEARCH_WARNING_CODE_UNSPECIFIED`,
  `SEARCH_WARNING_CODE_LEXICAL_TIMEOUT`,
  `SEARCH_WARNING_CODE_LEXICAL_UNAVAILABLE`,
  `SEARCH_WARNING_CODE_LEXICAL_INVALID_RESPONSE`,
  `SEARCH_WARNING_CODE_LEXICAL_CAPACITY`,
  `SEARCH_WARNING_CODE_SEMANTIC_TIMEOUT`,
  `SEARCH_WARNING_CODE_SEMANTIC_UNAVAILABLE`,
  `SEARCH_WARNING_CODE_SEMANTIC_INVALID_RESPONSE`,
  `SEARCH_WARNING_CODE_SEMANTIC_CAPACITY`,
  `SEARCH_WARNING_CODE_ROUTING_FALLBACK`,
  `SEARCH_WARNING_CODE_MALFORMED_CANDIDATE_DROPPED`,
  `SEARCH_WARNING_CODE_PARTIAL_EPISODE_RESULTS`.

Search results also reuse the closed `ResourceKind` vocabulary from the
Workbench v1 contract: `RESOURCE_KIND_UNSPECIFIED`, `RESOURCE_KIND_SERIES`,
`RESOURCE_KIND_MOVIE`, and `RESOURCE_KIND_EPISODE`. Warning text is bounded
explanatory text, not a channel for provider-native diagnostics.

Generated consumers must handle unknown future enum values defensively;
Rosetta's current `defined_only` validation rejects them on governed messages.
Providers and their internal scores remain an implementation detail even when
Workbench changes from Databricks Vector Search to OpenSearch.

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
