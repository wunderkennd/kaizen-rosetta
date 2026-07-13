# Audience v1 contract

This document defines the language-neutral semantics of
`kaizen.audience.v1`. The protobuf package carries contracts; it does not
provide an evaluator. Implementations must share these rules and the audience
conformance corpus.

## Validation boundary (Normative)

Protovalidate annotations enforce constraints that are local to a field or
message: a selected expression node, non-empty `ALL` and `ANY` groups, a child
for `NOT`, bounded field sizes, finite double values, required nonzero
attribute provenance, and required rule identity, revision, expression,
fingerprint, and registry version fields.

The following constraints require semantic validation by every producer and
consumer and must be represented in the shared conformance corpus:

- operator-specific operand arity and operand types;
- attribute registration and the registry's allowed-operator policy;
- consistency between the context value type, registry type, and operand type;
- maximum expression depth and total node count;
- normalized fingerprint computation; and
- RE2 compatibility and regex-pattern length.

A rule that fails structural or semantic validation is invalid and must not be
evaluated as a match or no-match result.

## Operators and types (Normative)

| Operator | Operand arity | Permitted registered attribute and operand types |
|---|---:|---|
| `EQUALS`, `NOT_EQUALS` | 1 | string, bool, int64, or double |
| `IN`, `NOT_IN` | 1..100 | string, bool, int64, or double; all operands have the same type |
| `GREATER_THAN`, `GREATER_THAN_OR_EQUALS`, `LESS_THAN`, `LESS_THAN_OR_EQUALS` | 1 | int64 or double |
| `CONTAINS` | 1 | string |
| `REGEX` | 1 | string containing an RE2-compatible pattern |
| `EXISTS`, `NOT_EXISTS` | 0 | any registered attribute type |

An operator must be defined and non-unspecified. The attribute key must resolve
exactly in the rule's registry version, and that registry entry must allow the
operator. Attribute values and operands must have the exact type declared by
the registry. Implementations must not coerce strings to numbers, numbers to
strings, booleans to strings, or int64 values to doubles. `IN` and `NOT_IN`
must not mix operand types. Regex evaluation must use a bounded,
RE2-compatible engine; backtracking-only constructs are invalid.

Every populated `AudienceAttribute` must declare exactly one of `OBSERVED`,
`SYNTHETIC`, `DEFAULT`, or `OVERLAY`. `UNSPECIFIED` and unknown numeric enum
values are invalid context and produce
`AUDIENCE_EVALUATION_REASON_CODE_INVALID_CONTEXT`. Every `double_value` must
be finite; NaN and positive or negative infinity are invalid at schema
validation and must never enter normalization or evaluation.

## Missing attributes and expression evaluation (Normative)

When a registered attribute is absent from the context, `NOT_EXISTS` evaluates
to true. Every other operator, including `EXISTS` and `NOT_EQUALS`, evaluates
to false. A missing attribute may produce
`AUDIENCE_EVALUATION_REASON_CODE_MISSING_ATTRIBUTE`; it is not itself an
invalid evaluation. An unregistered key is invalid rather than missing.

`ALL` evaluates to true only when every child matches. `ANY` evaluates to true
when at least one child matches. `NOT` reverses its child's match/no-match
decision. An invalid child decision reached during evaluation invalidates the
containing expression.

## Traversal and trace paths (Normative)

Evaluation traverses `ALL` and `ANY` children in protobuf repeated-field source
order. `ALL` short-circuits at the first child that evaluates to false; `ANY`
short-circuits at the first child that evaluates to true. Trace entries are
emitted in visitation order, so children skipped by short-circuit evaluation
do not produce entries.

An expression path identifies an `AudienceExpression` node. The root path is
`$`. An `ALL` child appends `.all[n]`, an `ANY` child appends `.any[n]`, and a
`NOT` child appends `.not`, where `n` is the child's zero-based source-order
index. For example: `$`, `$.all[0]`, `$.all[1].any[2]`, and `$.not`.
Logical-node and predicate trace entries both use the path of their containing
`AudienceExpression`.

## Expression limits (Normative)

Limits are measured on the complete expression before evaluation:

| Limit | Maximum |
|---|---:|
| Expression depth | 8 |
| Expression nodes | 128 |
| Values in one predicate | 100 |
| Attribute key | 64 UTF-8 bytes |
| Individual string value | 512 UTF-8 bytes |
| Regex pattern | 256 UTF-8 bytes |

The root node has depth 1. Every predicate, `ALL`, `ANY`, and `NOT` counts as
one node. A violation makes the rule invalid and produces
`AUDIENCE_EVALUATION_REASON_CODE_LIMIT_EXCEEDED` where diagnostics are
requested.

## Rule revisions and fingerprints (Normative)

The pair (`rule_id`, `revision`) identifies an immutable rule revision.
Revisions start at 1 and increase monotonically for a stable `rule_id`.
`content_fingerprint` is the lowercase hexadecimal SHA-256 digest of the
normalized semantic expression and excludes rule identity, revision, name,
description, registry version, and all other presentation metadata.

Normalization is recursive:

1. Retain each predicate's canonical attribute key, operator, and typed
   operands. Scalar types are part of the normalized value; no coercion is
   permitted.
2. For `IN` and `NOT_IN`, sort operands by their typed canonical value and
   remove exact typed duplicates. Preserve operand order for every other
   operator.
3. Normalize each logical child. For commutative `ALL` and `ANY` nodes, sort
   children by the raw bytes of each child's SHA-256 digest. Preserve the
   structure and child of `NOT`.
4. Serialize the normalized data with the complete RFC 8785 JSON
   Canonicalization Scheme, hash its UTF-8 bytes with SHA-256, and encode the
   digest as 64 lowercase hexadecimal characters. RFC 8785 finite-double
   semantics apply: value-equivalent exponent spellings serialize identically,
   negative zero serializes as `0`, subnormal and maximum finite IEEE 754
   values use ECMAScript-compatible rendering, and Unicode property names are
   sorted by UTF-16 code units. NaN and infinities are rejected.

The shared conformance corpus defines the normalized JSON representation,
typed ordering examples, and portable wire vectors. Every one of the 48 cases
contains `expectedWire.rule` and `expectedWire.context`; each record has a
lowercase `binaryHex` Protobuf payload and `canonicalProtoJson`, which is the
RFC 8785 serialization of the standard ProtoJSON object. These are
language-neutral `AudienceRule` and `AudienceContext` vectors, including cases
that are schema-valid Protobuf messages but invalid under audience policy.

A downstream evaluator must perform both directions for each message:

1. Hex-decode `binaryHex`, parse the named audience message, emit standard
   ProtoJSON, apply RFC 8785, and compare with `canonicalProtoJson`.
2. Parse `canonicalProtoJson` as ProtoJSON and compare the resulting message
   semantically with the message decoded from `binaryHex`.

The stored bytes use deterministic serialization solely to make the corpus
reviewable. Protobuf field order and map-entry order are not canonical across
all runtimes, so consumers compare decoded messages, not reserialized byte
identity. Implementations must also agree with the corpus fingerprints;
protobuf wire serialization, map iteration order, and source expression order
must not affect the digest. Semantically equivalent permutations of `ALL`,
`ANY`, `IN`, and `NOT_IN` therefore have the same fingerprint.

Canonical sorting exists only in the normalized fingerprint representation.
It must never reorder or mutate the stored expression tree and does not change
source-order evaluation traversal or trace paths.

## Diagnostics and privacy (Normative)

An evaluation decision is `MATCH`, `NO_MATCH`, or `INVALID`. Diagnostics may
identify the rule revision, fingerprint, expression path, canonical attribute
key, operator, decision, and reason code. They must never contain raw actual or
expected audience values. This prohibition applies to trace entries, error
messages, logs, metrics labels, and diagnostic fields in preview responses
regardless of registry sensitivity classification.

Detailed traces are optional and may be disabled in production. Attribute
provenance remains on the input context so preview interfaces can distinguish
observed, synthetic, defaulted, and overlaid attributes without copying values
into diagnostics. Provenance is mandatory; `UNSPECIFIED` is never a valid
placeholder for a populated attribute. Audience contexts must not contain raw
user identifiers, email addresses, dates of birth, raw watch history, or
unrestricted profile or campaign payloads; producers must derive and authorize
registered attributes before constructing a context.

## Legacy Experimentation CNF mapping (Normative)

The legacy `experimentation.common.v1.TargetingRule` is an AND-of-ORs form. A
lossless adapter maps every legacy `TargetingPredicate` to an
`AudiencePredicate`, each `TargetingGroup.predicates` list to
`ANY(predicates...)`, and the top-level `TargetingRule.groups` list to
`ALL(groups...)`. Legacy string operands remain strings and must never be
parsed or coerced. Stable rule identity and revision metadata are supplied by
the migration system, not inferred from presentation fields.

Legacy operators with direct audience equivalents map to those equivalents.
Unknown or unsupported operators, empty groups, an empty top-level group list,
non-canonical or unregistered attribute keys, disallowed operators, and any
result that fails audience type or arity rules make conversion invalid. An
adapter must report
`AUDIENCE_EVALUATION_REASON_CODE_LEGACY_CONVERSION_FAILURE`; it must not drop,
rewrite, or silently broaden a predicate. The legacy protobuf remains
unchanged during migration.
