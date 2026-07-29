# postmortem-miner

[![pr-ci](https://github.com/JulianoVinceCampos/postmortem-miner/actions/workflows/pr-ci.yml/badge.svg)](https://github.com/JulianoVinceCampos/postmortem-miner/actions/workflows/pr-ci.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=JulianoVinceCampos_postmortem-miner&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=JulianoVinceCampos_postmortem-miner)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=JulianoVinceCampos_postmortem-miner&metric=coverage)](https://sonarcloud.io/summary/new_code?id=JulianoVinceCampos_postmortem-miner)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/JulianoVinceCampos/postmortem-miner/badge)](https://scorecard.dev/viewer/?uri=github.com/JulianoVinceCampos/postmortem-miner)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Seus postmortems já sabem o que vive quebrando. Esta ferramenta os lê de volta pra você
como uma árvore de decisão de triagem.**

No corpus sintético que acompanha o projeto:

> **8 padrões explicam 90% de 20 incidentes, em 17 ms, com uma profundidade de triagem de 4.**

Quatro perguntas para classificar um incidente ao vivo contra tudo o que o arquivo já viu.
Os 10% restantes são dois incidentes pontuais (one-off) que genuinamente não pertencem a
nenhum padrão — e a ferramenta diz isso, em vez de inventar um.

## Por quê

Times escrevem bons postmortems e depois nunca os leem como um conjunto. Cada um é a
história de uma noite. Lidos juntos, vinte deles viram um mapa: os mesmos quatro ou cinco
failure modes, cada um com uma assinatura distinta, a maioria com uma root cause que ninguém
teve tempo de corrigir.

Esse mapa é exatamente o que você quer no minuto três de um incidente, e construí-lo à mão
leva uma tarde que ninguém tem. Então: automatize a leitura, mantenha o raciocínio explicável
(explainable) e deixe a ferramenta te dizer quando ela não sabe.

## Início rápido

```bash
git clone https://github.com/JulianoVinceCampos/postmortem-miner
cd postmortem-miner
make report        # gera o corpus e reproduz o número acima
```

Nada a instalar para isso: o pacote usa apenas a biblioteca padrão (standard library)
([ADR-0001](docs/adr/ADR-0001-zero-runtime-dependencies.md)). Python 3.11+.

Sem `make`:

```bash
python3 tools/gen_corpus.py --out corpus --count 18 --seed 7
PYTHONPATH=src python3 -m postmortem_miner.cli mine corpus --out out/report.md
```

Contra o seu próprio arquivo:

```bash
python -m postmortem_miner.cli mine path/to/postmortems --out report.md --json analysis.json
```

No meio de um incidente, com os sinais que você está olhando agora:

```bash
python -m postmortem_miner.cli classify path/to/postmortems \
  --signals saturation.pool.exhausted,store.lock.contention
# -> P2 pool exhausted + pool wait
```

`postmortem-miner signals` lista todos os tokens que ele consegue reconhecer.

## Como a árvore se parece

Gerada a partir do corpus sintético, renderizada direto no relatório:

```mermaid
flowchart TD
    n0{"lifecycle.schedule.window?"}
    n1{"app.cast_error?"}
    n2["P5 cast error + npe<br/>n=2"]
    n1 -->|yes| n2
    n3{"app.retry_storm?"}
    n4["P6 retry storm + batch window<br/>n=2"]
    n3 -->|yes| n4
    n5["P8 deploy recent + query slow<br/>n=2"]
    n3 -->|no| n5
    n1 -->|no| n3
    n0 -->|yes| n1
    n6{"network.healthcheck.fail?"}
    n7{"lifecycle.cert.expired?"}
    n8["P4 cert expired + timeout external<br/>n=2"]
    n7 -->|yes| n8
    n9["P3 acl block + healthcheck fail<br/>n=2"]
    n7 -->|no| n9
    n6 -->|yes| n7
    n10{"resource.cpu.saturated?"}
    n11["P2 pool exhausted + pool wait<br/>n=3"]
    n10 -->|yes| n11
    n12{"resource.gc.pressure?"}
    n13["P1 gc pressure + memory exhausted<br/>n=3"]
    n12 -->|yes| n13
    n14["P7 rollback long + transaction monolithic<br/>n=4"]
    n12 -->|no| n14
    n10 -->|no| n12
    n6 -->|no| n10
    n0 -->|no| n6
```

O relatório também traz uma matriz de suporte sinal-por-padrão (signal-by-pattern support
matrix), o trecho de evidência (evidence snippet) por trás de cada classificação, e uma
contagem de quantas ocorrências de cada padrão ainda têm uma root cause não tratada. Essa
última coluna costuma ser a desconfortável.

## Como funciona

```
markdown ──▶ Incident ──▶ signal tokens ──▶ patterns ──▶ decision tree ──▶ report
             parser        signals           patterns     decision_tree     report
```

**Parsing** é deliberadamente tolerante. O frontmatter é opcional, nomes de campos são
aceitos em inglês e português, e a data é recuperada do frontmatter, do nome do arquivo ou do
corpo. Um parser que descarta um postmortem por causa de um nome de campo é um parser que
ninguém roda.

**Extração de sinais** mapeia o texto corrido para tokens canônicos como
`saturation.pool.exhausted` através de uma tabela de regex curada e bilíngue: 31 tokens
distribuídos em 8 camadas, cada um carregando o trecho (snippet) de texto que o produziu. Não
são embeddings, e o [ADR-0002](docs/adr/ADR-0002-regex-rules-not-embeddings.md) argumenta
longamente o porquê. A versão curta: às 3 da manhã você precisa de uma conclusão com a qual
possa discutir, não de um similarity score no qual você tem que confiar.

**Clustering** é single-linkage sobre a similaridade de Jaccard dos conjuntos de sinais. O K
é desconhecido de antemão, e uma cadeia de incidentes relacionados deve poder se juntar sem
forçar um centroide que não significa nada operacionalmente.

**Sinais distintivos** são a saída interessante, não os clusters. Um sinal presente em todos
os incidentes do corpus é ruído de fundo (background noise); um que é frequente dentro de um
padrão e raro fora dele é uma pergunta de triagem. O requisito de margem (margin) é o que faz
a diferença.

**A árvore** é information gain guloso (greedy), com profundidade limitada a 4. Árvores mais
profundas pontuam melhor e não ajudam ninguém: ninguém percorre nove perguntas com a produção
fora do ar.

Tudo é determinístico. Mesmo corpus, os mesmos bytes na saída — é isso que permite ao CI
defender o número deste README, em vez de confiar que alguém o atualizou.

## Taxonomia de sinais

| Camada | Tokens de exemplo |
|---|---|
| `resource` | `cpu.saturated`, `memory.exhausted`, `gc.pressure`, `disk.pressure` |
| `saturation` | `pool.exhausted`, `pool.wait`, `threads`, `queue.backlog` |
| `store` | `lock.contention`, `rollback.long`, `query.slow`, `transaction.monolithic` |
| `network` | `acl.block`, `lb.imbalance`, `healthcheck.fail`, `timeout.external` |
| `application` | `npe`, `cast_error`, `batch_error`, `retry_storm`, `error_swallowed`, `callback_missing` |
| `lifecycle` | `deploy.recent`, `cert.expired`, `schedule.window`, `restart.reactive` |
| `workload` | `traffic.spike`, `payload.large`, `batch.window` |
| `topology` | `single_node`, `all_nodes` |

Adicionar uma regra é uma linha mais uma fixture. Veja [CONTRIBUTING](CONTRIBUTING.md) — é a
contribuição mais útil que você pode fazer.

## O corpus é sintético, de propósito

O corpus que acompanha o projeto é gerado por `tools/gen_corpus.py`: 8 famílias de incidentes
mais dois incidentes pontuais (one-off) que deliberadamente se recusam a formar cluster,
metade em inglês e metade em português, determinístico para um dado seed.

Os failure modes são realistas porque são comuns a qualquer stack JVM-mais-banco-relacional
atrás de um load balancer. Nada aqui vem de um sistema, cliente ou colega real. Isso é imposto
(enforced), não prometido: `tools/sanitize_scan.py` bloqueia instance ids, account ids, tax
ids, endereços privados e hostnames internos, e é o **primeiro** job no CI — antes do linting
— porque um vazamento no histórico público do git é o único erro aqui que não dá para desfazer.
A suíte de testes garante que o gate passa neste repositório sem nenhum waiver.

## O que ainda não faz

- **Derivar SLIs candidatas a partir do histórico de incidentes.** O próximo passo
  interessante: o arquivo já implica quais indicadores teriam previsto cada padrão. Planejado
  para a 0.2.
- **Feedback loop.** Classificar um incidente ao vivo deveria permitir anexá-lo ao corpus.
- **Qualquer coisa em escala de escrita.** O clustering é O(n²); ok até alguns milhares de
  postmortems.

## Desenvolvimento

```bash
make install   # extras de dev mais hooks de pre-commit
make check     # sanitize + lint + testes, na ordem do CI
make cov       # coverage mais o ratchet
```

O pipeline roda dez camadas: pre-commit, sanitize, lint, build e testes em três versões do
Python, coverage com um ratchet que só sobe, Semgrep, CodeQL como blocking check, dependency
review com OSV, o quality gate do SonarCloud, e atestação de SBOM mais build provenance.

## Licença

MIT. Veja [LICENSE](LICENSE).
