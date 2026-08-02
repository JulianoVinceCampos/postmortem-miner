# ADR-0003: Dashboard web sobre a biblioteca padrão

- **Status:** aceito
- **Data:** 2026-08-01
- **Revisita:** [ADR-0001](ADR-0001-zero-runtime-dependencies.md)

## Contexto

ADR-0001 fixou zero dependência de runtime e fechou com uma condição explícita:
*"revisit if the report needs to be anything other than markdown"*. Um dashboard web é
exatamente esse gatilho, então a decisão vem revisitada, não contornada.

O motivo de existir um dashboard é que markdown responde bem à pergunta "o que este
acervo diz" e responde mal a "e este incidente aqui, agora?". Marcar sinais numa lista e
ver a árvore responder é uma interação; ler uma árvore renderizada em Mermaid dentro de um
arquivo não é. Some-se a isso que um projeto sem tela acessível obriga quem avalia a
clonar o repositório para formar opinião.

O caminho óbvio seria FastAPI mais uvicorn. Duas dependências, sete transitivas, e o
argumento central do ADR-0001 vai embora: `pip install postmortem-miner` deixa de
funcionar num bastion sem índice acessível no minuto três de um incidente.

## Decisão

A camada web usa apenas a biblioteca padrão. Concretamente:

- HTTP é `http.server.ThreadingHTTPServer`. Roteamento é comparação de string sobre
  `urlparse(path).path`, em tabela de dispatch.
- Sessão é cookie assinado com `hmac` e `hashlib.sha256`, segredo de `secrets`. Não há
  store de sessão, então não há store para operar.
- Serialização é `json`. O frontend é HTML, CSS e JavaScript sem framework e sem CDN,
  com os gráficos gerados como SVG inline.

`dependencies = []` continua verdadeiro no `pyproject.toml`. A instalação não mudou.

A verificação de credencial acontece **no servidor**. As credenciais são um portão de
demonstração sobre dado sintético e somente leitura, não um controle de segurança, mas
um portão validado em JavaScript não é um portão, e num projeto sobre análise de
incidente isso seria uma contradição visível.

## Consequências

**Bom.** O argumento do ADR-0001 permanece intacto: nada a auditar no runtime, nada a
resolver na instalação, imagem de container sem etapa de resolução de dependência. O
demo público não carrega script de terceiro, o que também simplifica a postura de CSP.
A análise roda uma vez na subida e fica em memória, então a navegação não paga o pipeline
a cada requisição.

**Ruim.** `http.server` não é um servidor de produção: sem limite de requisição por
cliente, sem TLS, sem *graceful shutdown* além do que o `ThreadingHTTPServer` oferece.
Isso é aceitável porque a superfície é leitura sobre dado sintético e o TLS fica no
proxy da plataforma de deploy. O roteamento manual também não ganha validação de schema
de graça, então cada payload de entrada é normalizado à mão, visível em
`handle_post`, que trata corpo ausente, corpo grande demais e JSON inválido como
corpo vazio.

Não há autorização por papel: quem entra vê tudo. Modelar papéis sobre dado sintético
seria cerimônia.

**Revisitar se** a ferramenta passar a escrever algo (aí aparecem CSRF e concorrência de
escrita, e o `http.server` deixa de ser suficiente), ou se o dashboard precisar servir
mais de um acervo por processo.
