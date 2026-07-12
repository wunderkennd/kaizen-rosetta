# ADR 0002: Define audience targeting as a neutral shared contract

- Status: Accepted
- Date: 2026-07-12

## Context

Audience rules are needed by experimentation, feature flags, merchandising,
recommendations, and authoring tools. The existing
`experimentation.common.v1.TargetingRule` is owned by Experimentation, stores
only string values, and represents a fixed AND-of-ORs shape. Expanding it would
make a domain-specific legacy contract the shared abstraction and force other
domains to inherit its naming, value model, and topology.

Audience evaluation also needs explicit provenance and privacy boundaries.
Authoring and preview workflows must distinguish observed values from synthetic,
defaulted, and overlaid values without turning the evaluation context into a
general-purpose user profile.

## Decision

Define `kaizen.audience.v1` as a neutral package owned by Rosetta. Audience
attributes carry one of four scalar types, provenance, and the version of the
registry that defines their canonical keys, normalization, allowed operators,
and sensitivity.

Use recursive expressions for audience rules rather than extending the fixed
shape of `experimentation.common.v1.TargetingRule`. Recursive predicate, ALL,
ANY, and NOT nodes can express current targeting and future domain-neutral rule
composition without adding another special-case container for each topology.
The expression schema will impose bounded depth and node counts so recursion is
safe for authoring and online use.

Keep the Experimentation targeting contract unchanged during migration. An
adapter may translate its AND-of-ORs form into audience expressions, but the
legacy type does not become the shared model and is not modified by this
decision.

`AudienceContext` contains registered decision attributes only. It excludes raw
user identifiers, email addresses, dates of birth, and watch-history events.
Those values are not necessary to evaluate registered audience predicates and
would create avoidable linkage, retention, authorization, and diagnostic-leak
risks. Producers must derive approved attributes, such as `account_age_days` or
`maturity_context`, before constructing a context.

## Alternatives considered

### Expand `experimentation.common.v1.TargetingRule`

Rejected because it would couple non-Experimentation consumers to a legacy
domain package, retain string-only comparison semantics, and make recursive
composition an awkward series of additive exceptions.

### Use a flat list or fixed AND-of-ORs structure

Rejected because it cannot represent nested negation or arbitrary combinations
without lossy transformations or parallel rule types. Bounded recursion is a
smaller and more durable shared contract.

### Carry a complete user profile in `AudienceContext`

Rejected because raw identity and behavioral history exceed the evaluator's
data needs and enlarge the privacy and security boundary. The registry provides
an explicit allowlist and sensitivity metadata instead.

## Consequences

- Multiple domains can share typed audience contracts without importing an
  Experimentation-owned targeting model.
- Registry versions and provenance make evaluation inputs auditable.
- Evaluators must validate recursive structures and registry compatibility;
  Rosetta defines only the schema and does not implement evaluation.
- Producers remain responsible for deriving, normalizing, and authorizing
  registered attributes before placing them in an `AudienceContext`.
- Raw identity and watch history cannot be transported through this contract.
