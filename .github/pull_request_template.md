## What changes

<!-- One paragraph. What is different after this PR. -->

## Why

<!-- The problem being solved. Link an issue if there is one. -->

## How to verify

<!-- Exact commands a reviewer can run. `make check` is usually enough. -->

```bash
make check
```

## Risks and rollback

<!-- What could break, and how to undo it. "None" is a valid answer if it is true. -->

## Checklist

- [ ] `make check` passes locally
- [ ] New behaviour is covered by a test that fails without the change
- [ ] No corporate context added (hostnames, account ids, addresses, tax ids, real prose)
- [ ] New signal rules include a fixture in both languages, when applicable
- [ ] Docs or ADR updated when a design decision changed
