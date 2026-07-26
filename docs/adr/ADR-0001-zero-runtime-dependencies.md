# ADR-0001: Zero runtime dependencies

- **Status:** accepted
- **Date:** 2026-07-25

## Context

The obvious implementation reaches for `pyyaml` for frontmatter, `scikit-learn` for
clustering, `click` for the CLI and `jinja2` for the report. All four are good libraries.

But consider when this tool is actually used. It is minute three of an incident, on
whatever machine has access to the postmortem archive: a bastion, a locked-down laptop, a
container built from a base image nobody wants to change right now. In that moment
`pip install` is a dependency on network access, on an index being reachable, and on a
package resolving for whatever Python happens to be installed.

## Decision

The installed package depends on the standard library only. Concretely:

- Frontmatter uses a small YAML subset parser instead of `pyyaml`. The corpus only ever
  needs scalars and lists.
- Clustering is single-linkage over Jaccard similarity via union-find, about 30 lines,
  instead of `scikit-learn`.
- The CLI is `argparse`.
- The report is f-strings, because the output is markdown, not HTML.

Dev and CI dependencies (pytest, coverage, hypothesis, ruff) are unconstrained. They never
ship.

## Consequences

**Good.** `git clone && python -m postmortem_miner.cli mine corpus/` works on any box with
Python 3.11. No supply chain to audit for the runtime, which also means the SCA surface is
purely the dev tooling. Startup is milliseconds, so it is usable interactively.

**Bad.** The YAML subset will reject exotic frontmatter that `pyyaml` would accept; the
parser is deliberately forgiving so odd input degrades to "no metadata" rather than an
error. Clustering is O(n²) in the number of incidents. For an archive of a few thousand
postmortems that is still under a second, and any corpus large enough to hurt has a
different problem: nobody is reading it.

**Revisit if** a corpus in the tens of thousands appears, or if the report needs to be
anything other than markdown.
