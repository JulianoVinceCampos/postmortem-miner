# Componentes e como se conectam

Um diagrama só, de componentes, e o texto que explica cada aresta. Não há C4 nem diagrama
de sequência aqui de propósito: com um pipeline linear e um único processo, aquelas
camadas repetiriam a mesma informação em três níveis de zoom.

## O diagrama

```mermaid
flowchart LR
    subgraph entrada["Entrada"]
        corpus[("corpus/<br/>markdown")]
    end

    subgraph nucleo["Núcleo: stdlib, determinístico"]
        parser["parser<br/><small>markdown → Incident</small>"]
        signals["signals<br/><small>prosa → tokens + evidência</small>"]
        patterns["patterns<br/><small>Jaccard + union-find</small>"]
        tree["decision_tree<br/><small>ganho de informação</small>"]
        report["report<br/><small>Analysis → markdown / json</small>"]
    end

    subgraph saidas["Saídas"]
        cli["cli<br/><small>mine · classify · signals · serve</small>"]
        webapp["webapp<br/><small>http.server + sessão HMAC</small>"]
    end

    subgraph browser["Navegador"]
        ui["dashboard<br/><small>HTML · CSS · JS, sem framework</small>"]
    end

    corpus --> parser
    parser --> signals
    signals --> patterns
    patterns --> tree
    patterns --> report
    tree --> report

    report --> cli
    report --> webapp
    tree --> webapp
    signals --> webapp

    webapp <-->|JSON sobre HTTP| ui

    classDef core fill:#e8f1fa,stroke:#1668b3,color:#0d4e88
    classDef edge fill:#f2f8f4,stroke:#0f8b8d,color:#1c6b45
    classDef data fill:#fff,stroke:#5b6b7c,color:#16222f
    class parser,signals,patterns,tree,report core
    class cli,webapp,ui edge
    class corpus data
```

## As arestas, uma por uma

**`corpus → parser`.** O acervo é um diretório de markdown. `parse_corpus` lê cada
arquivo, extrai frontmatter com um parser de subconjunto de YAML próprio (ADR-0001) e
devolve `Incident`. Arquivo sem metadado reconhecível degrada para "sem metadado" em vez
de erro, porque um acervo real tem arquivo torto.

**`parser → signals`.** Cada incidente tem sua prosa varrida por regras de regex que
emitem `Signal(token, kind, evidence)`. O `evidence` é o que mantém tudo auditável: todo
token guarda o trecho original que o produziu. Sem embeddings: ADR-0002 explica por quê.

**`signals → patterns`.** Incidentes viram conjuntos de tokens. Similaridade é Jaccard,
agrupamento é single-linkage por union-find. De cada grupo saem os sinais *distintivos*
(alto suporte dentro, baixo fora) que dão nome ao padrão.

**`patterns → decision_tree`.** Os padrões rotulam os incidentes e a árvore cresce por
ganho de informação sobre presença binária de sinal. Profundidade limitada em quatro:
uma árvore de nove níveis é melhor no papel e inútil com produção parada.

**`patterns → report` e `tree → report`.** `report.analyse` empacota incidentes, padrões,
árvore e cobertura num `Analysis` congelado. É a única estrutura que as saídas consomem.

**`report → cli`.** `mine` escreve markdown e JSON, `classify` percorre a árvore com os
sinais de um incidente ao vivo, `signals` lista a taxonomia.

**`report → webapp`, `tree → webapp`, `signals → webapp`.** O `serve` monta o
`AppState` **uma vez** na subida: parse, análise e taxonomia ficam em memória. O corpus
não muda enquanto o processo vive, e reanalisar por requisição transformaria uma página de
30 ms na página mais o pipeline inteiro.

**`webapp ↔ dashboard`.** JSON sobre HTTP. O navegador chama `/api/summary`,
`/api/patterns`, `/api/matrix`, `/api/tree`, `/api/incidents`, `/api/signals` e
`/api/report` em paralelo depois do login, e `POST /api/classify` quando o usuário marca
sinais. `/api/health` responde sem sessão, porque a sonda do container precisa dela antes
de qualquer login existir.

## O que a direção das setas garante

O núcleo não conhece as saídas. `parser`, `signals`, `patterns`, `decision_tree` e
`report` não importam nada de `cli` nem de `webapp`, e é o que permite o dashboard existir
sem que o caminho da CLI ganhe uma dependência ou um ramo condicional.

Consequência prática: o dashboard não é uma segunda fonte de verdade. A tela de relatório
mostra literalmente a saída de `report.to_markdown`, a mesma que `mine --out` escreve. Se
os dois divergirem, é bug, não decisão de produto.

## Fronteira de confiança

Uma só, e fica no `webapp`: tudo antes dele lê arquivo local e é determinístico; tudo
depois é entrada de rede. Por isso a normalização de payload e a checagem de sessão vivem
ali, e apenas ali. O `Handler` é casca fina justamente para que essa fronteira caiba em
funções puras testáveis sem abrir socket.
