# ADR-0002: A curated regex rule table, not embeddings

- **Status:** accepted
- **Date:** 2026-07-25

## Context

Grouping similar incidents is the textbook use case for sentence embeddings: encode each
postmortem, cluster the vectors, done. It would take fewer lines than the rule table in
`signals.py` and would generalise to phrasings nobody anticipated.

The alternative is a curated table of regexes mapping prose to canonical signal tokens,
which is more code, needs maintenance, and misses phrasings it was never taught.

## Decision

Explicit regex rules, evaluated in a fixed order, each emitting a canonical token plus the
snippet of evidence that produced it.

Three reasons, in the order that matters:

1. **A triage tool has to explain itself.** "Matched `pool 80/80` at this line" is
   something an on-call engineer can argue with at 3am. "Cosine similarity 0.82 to a
   cluster centroid" is something they have to trust. Under pressure, trust is not
   available and arguing is the whole job.
2. **Correction is cheap.** When a rule is wrong you edit one line and the fix is
   reviewable in a diff. Fixing an embedding model means rebuilding a training set, and
   the failure mode is invisible until someone notices the clusters drifted.
3. **It runs anywhere, in milliseconds.** No model download, no GPU, no API key, no
   network. Which matters precisely when it matters (see ADR-0001).

## Consequences

**Good.** Every conclusion traces to a line of input. Adding a signal is a one-line
contribution, which is the documented contribution path. Output is byte-for-byte
deterministic, so the numbers in the README are defended by CI rather than asserted.

**Bad.** Recall depends on the rule table. A phrasing nobody wrote a rule for is invisible,
and the table needs to be bilingual by hand. A real bug found in review: `certificat`
matched *certificate* but not *certificado*, so the whole Portuguese half of a family was
silently dropped. That class of mistake is the cost of this decision, and the mitigation is
that every rule ships with a fixture in both languages.

**Revisit if** the corpus grows past a few thousand postmortems from many independent
authors, where hand-curating recall stops scaling. Even then the likely shape is a hybrid:
rules for the signals that drive decisions, embeddings for discovery of candidates a human
then promotes to a rule.
