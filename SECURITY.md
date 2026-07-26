# Security policy

## Reporting a vulnerability

Open a [private security advisory](https://github.com/JulianoVinceCampos/postmortem-miner/security/advisories/new).
Please do not open a public issue for anything exploitable.

Expect an acknowledgement within 7 days. If the report is valid I will agree a
disclosure timeline with you before publishing anything.

## Threat model

This tool reads local markdown files and writes a report. It makes no network calls, has
no runtime dependencies, and needs no credentials. The realistic risks are therefore:

| Risk | Mitigation |
|---|---|
| Malicious input file causing a crash or hang | Property-based tests fuzz the parser and the extractor; every regex is bounded, with no unbounded backtracking construct |
| Path traversal via a corpus argument | Only files under the given directory are read, and only for reading |
| Sensitive content leaking into a report | The report only quotes text that is already in the input files |
| Sensitive content leaking into **this repository** | `tools/sanitize_scan.py` plus `.semgrep/no-corp-leak.yml` and gitleaks over the full history, running as the first CI stage |

## Supported versions

The latest released minor version receives fixes. This project is pre-1.0: the CLI
contract may change between minor versions, and the CHANGELOG says so when it does.
