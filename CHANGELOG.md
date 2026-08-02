# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Entries are generated from
Conventional Commits.

## [0.2.0](https://github.com/JulianoVinceCampos/postmortem-miner/compare/v0.1.0...v0.2.0) (2026-08-02)


### Features

* **web:** dashboard, container e deploy, ainda sem dependência de runtime ([#5](https://github.com/JulianoVinceCampos/postmortem-miner/issues/5)) ([125c0ec](https://github.com/JulianoVinceCampos/postmortem-miner/commit/125c0ecaa8169806f844f3e0f5f45a836534c096))


### Bug Fixes

* **web:** corrige o login invisivel, troca a credencial e aplica a nova paleta ([#8](https://github.com/JulianoVinceCampos/postmortem-miner/issues/8)) ([810445b](https://github.com/JulianoVinceCampos/postmortem-miner/commit/810445b68740a60da39bbbb987acedfb2a0654b9))
* **web:** HTTP/1.1 e drenagem de corpo, para não dessincronizar a conexão ([#7](https://github.com/JulianoVinceCampos/postmortem-miner/issues/7)) ([df8f61c](https://github.com/JulianoVinceCampos/postmortem-miner/commit/df8f61c0cc7e2ff29fea8c90bae1dbba6edc6e0f))
* **web:** implementa HEAD e pede revalidacao nos estaticos ([#9](https://github.com/JulianoVinceCampos/postmortem-miner/issues/9)) ([49a16f7](https://github.com/JulianoVinceCampos/postmortem-miner/commit/49a16f73da508a4578f98f3ab46495e3f023ea1e))


### Documentation

* **readme:** link the live demo instance ([#6](https://github.com/JulianoVinceCampos/postmortem-miner/issues/6)) ([23af0c5](https://github.com/JulianoVinceCampos/postmortem-miner/commit/23af0c555c374814e0d95d9ea5a0859d62ad671c))
* traduz README para PT-BR preservando termos tecnicos ([#3](https://github.com/JulianoVinceCampos/postmortem-miner/issues/3)) ([d959ead](https://github.com/JulianoVinceCampos/postmortem-miner/commit/d959ead8f9287f5db91db50796f48a2e6fc64450))

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
