# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Entries are generated from
Conventional Commits.

## 0.1.0 (2026-07-26)


### Features

* domain model, forgiving parser and bilingual signal extraction ([1f0685a](https://github.com/JulianoVinceCampos/postmortem-miner/commit/1f0685a55bc860d2937678f4e6b4b9e967f32f91))
* pattern discovery, triage decision tree, reports and CLI ([adbdd6c](https://github.com/JulianoVinceCampos/postmortem-miner/commit/adbdd6cdff42fbf4257a5e3369225bdcd3652607))
* sanitize gate, coverage ratchet and deterministic corpus generator ([5d2f8b7](https://github.com/JulianoVinceCampos/postmortem-miner/commit/5d2f8b79ea75b605de2f1e526b8acf2a7eb14f4b))


### Documentation

* readme with measured results, ADRs, contributing and security policy ([5138e65](https://github.com/JulianoVinceCampos/postmortem-miner/commit/5138e65db1c3928f2a1a73eb16331eaceeacfda2))

## [0.1.0] - unreleased

### Added

- Signal extraction with a bilingual (pt-BR / en) rule table covering 31 canonical tokens
  across 8 layers.
- Forgiving postmortem parser: optional frontmatter with a stdlib-only YAML subset,
  section aliases in both languages, date recovery from frontmatter, filename or body.
- Pattern discovery via single-linkage clustering over Jaccard similarity of signal sets,
  with distinctive-signal scoring that requires a margin over the rest of the corpus.
- Triage decision tree built by greedy information gain, depth-capped, rendered as
  Mermaid, plus `classify` to route a live incident's signals to a known pattern.
- Markdown and JSON reports, both deterministic for a given corpus.
- Deterministic synthetic corpus generator: 8 incident families plus one-off incidents
  that deliberately do not cluster.
- `sanitize` gate (stdlib, zero dependencies) and coverage ratchet, both tested.
