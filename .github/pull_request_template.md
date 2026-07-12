## Contract review checklist

- [ ] `just check` and generated Python, Go, and TypeScript compilation pass.
- [ ] Breaking compatibility is checked against the released default BSR label.
- [ ] A release manifest records the immutable BSR commit and all six active generated SDK publication/verification records.
- [ ] Any BSR publication targets a non-default development label only.

## Default-label promotion gate

- [ ] The repository has been transferred from the personal `wunderkennd` account to a GitHub organization.
- [ ] Real domain-owner and schema-governance teams exist and replace the temporary `@wunderkennd` CODEOWNERS entries.
- [ ] Branch protection requires approval from both teams for owned schema and release paths.
- [ ] The development-label descriptor, generated SDK consumers, and release manifest have passed before `main` promotion.

Until every promotion item is satisfied, do not update or promote the default
BSR `main` label.
