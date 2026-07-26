# Contributing

## Setup

```bash
make install     # editable install with dev extras, plus pre-commit hooks
make check       # sanitize + lint + tests, in the same order CI runs them
```

Python 3.11 or newer. The package itself has no runtime dependencies and that is a
design constraint, not an accident (see `docs/adr/ADR-0001`). A PR that adds one needs to
argue the case in the description.

## Adding a signal rule

This is the most common and most welcome contribution. One row in `_RULES` inside
`src/postmortem_miner/signals.py`:

```python
_RULES = (
    ("store.lock.contention", SignalKind.DATA_STORE, r"\block(?:s|ing)?\b|deadlock"),
    ("saturation.threads", SignalKind.SATURATION, r"threads?[^.\n]{0,20}?\d{3,}"),
)
```

What a good rule looks like:

1. **Canonical token** in `layer.thing.state` form. Reuse an existing prefix when one fits;
   a taxonomy with two names for the same thing stops clustering from working.
2. **Bilingual pattern.** Real corpora are written in more than one language, and a rule
   that only speaks English silently drops half the input. This has already happened
   here: `certificat` matches *certificate* but not *certificado*.
3. **A fixture in `tests/test_signals.py`**, in both languages when the phrasing differs.
4. **A bounded pattern.** Use `[^.\n]{0,30}` rather than `.*` so a long line cannot turn
   into pathological backtracking.

## What will get a PR sent back

- Corporate or customer context of any kind: hostnames, account ids, addresses, tax ids,
  or prose copied from a real postmortem. The `sanitize` gate blocks the obvious shapes,
  but reviewer judgement covers the rest.
- A new runtime dependency without a rationale.
- A signal rule with no test.
- Coverage below the current floor in `.coverage-floor`. The floor only goes up.

## Commits

Conventional Commits, enforced by a hook: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`,
`chore:`. The changelog and the version number are generated from them, so the message is
the release note.
