"use strict";

/* Dashboard do postmortem-miner.
 *
 * Sem framework e sem CDN, por dois motivos: o demo publico nao carrega script de
 * terceiro, e o servidor e stdlib puro (ADR-0003) - seria estranho o backend nao ter
 * dependencia e o frontend ter cinco.
 *
 * O estado e um objeto simples. Cada view renderiza a partir dele; nada de binding
 * implicito, porque com oito telas isso e mais facil de depurar do que de abstrair.
 */

const state = {
  user: null,
  summary: null,
  patterns: null,
  matrix: null,
  tree: null,
  incidents: null,
  signals: null,
  report: null,
  selected: new Set(),
  view: "overview",
};

const $ = (id) => document.getElementById(id);

/* ---------------------------------------------------------------- rede --- */

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 401) {
    const error = new Error("unauthenticated");
    error.unauthenticated = true;
    throw error;
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.error || `HTTP ${response.status} em ${path}`);
  }
  return response.json();
}

/* --------------------------------------------------------------- utils --- */

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));

const pct = (value) => `${Math.round(value * 100)}%`;
const code = (value) => `<code>${esc(value)}</code>`;
const dash = (value) => (value ? esc(value) : "-");

function tokenList(tokens) {
  if (!tokens || tokens.length === 0) return "-";
  return tokens.map(code).join(" ");
}

/* ------------------------------------------------------------ graficos --- */

/* Barras horizontais em SVG. Escala pelo maior valor; rotulo a esquerda, numero no fim
   da barra. Suficiente para as duas distribuicoes que importam, e sem dependencia. */
function barChart(rows, { color = "bar" } = {}) {
  if (rows.length === 0) return '<p class="empty">Nada para mostrar.</p>';
  const rowH = 26;
  const labelW = 138;
  const width = 460;
  const barMax = width - labelW - 46;
  const max = Math.max(...rows.map((r) => r.value)) || 1;
  const height = rows.length * rowH + 8;

  const bars = rows
    .map((row, index) => {
      const y = index * rowH + 4;
      const w = Math.max(2, (row.value / max) * barMax);
      return `
        <text class="chart-label" x="0" y="${y + 14}">${esc(row.label)}</text>
        <rect class="${color}" x="${labelW}" y="${y + 4}" width="${w}" height="14" rx="3" />
        <text class="chart-value" x="${labelW + w + 6}" y="${y + 15}">${esc(row.value)}</text>`;
    })
    .join("");

  return `<svg viewBox="0 0 ${width} ${height}" role="img"
    aria-label="Grafico de barras com ${rows.length} series">${bars}</svg>`;
}

/* ---------------------------------------------------------------- views --- */

function renderOverview() {
  const s = state.summary;
  $("summary-cards").innerHTML = [
    { value: s.incidents, label: "incidentes no acervo" },
    { value: s.patterns, label: "padrões encontrados" },
    { value: pct(s.coverage), label: "do acervo explicado" },
    { value: s.triage_depth, label: "profundidade da triagem" },
    { value: s.unexplained, label: "fora de padrão" },
    { value: `${s.elapsed_ms} ms`, label: "tempo de análise" },
  ]
    .map(
      (card) =>
        `<div class="card"><div class="card-value">${esc(card.value)}</div>
         <div class="card-label">${esc(card.label)}</div></div>`
    )
    .join("");

  $("chart-patterns").innerHTML = barChart(
    state.patterns.map((p) => ({ label: p.id, value: p.size }))
  );

  $("chart-kinds").innerHTML = barChart(
    state.signals.map((group) => ({ label: group.kind, value: group.tokens.length })),
    { color: "bar-alt" }
  );

  const orphans = state.incidents.filter((i) => !i.pattern);
  $("unexplained").innerHTML = orphans.length
    ? `<table><thead><tr><th>id</th><th>título</th><th>serviço</th></tr></thead><tbody>${orphans
        .map(
          (i) =>
            `<tr><td>${code(i.id)}</td><td>${esc(i.title)}</td><td>${dash(i.service)}</td></tr>`
        )
        .join("")}</tbody></table>`
    : '<p class="empty">Todo incidente caiu em algum padrão.</p>';
}

/* Um no da arvore: a caixa, e quando for pergunta, os dois ramos abaixo. */
function treeNode(node) {
  if (!node) {
    return '<span class="node node-leaf unknown">ramo ausente</span>';
  }
  if (node.kind === "leaf") {
    const label = node.label || "unknown";
    const tie =
      node.tie && node.tie.length ? ` · empate com ${node.tie.map(esc).join(", ")}` : "";
    const unknown = label === "unknown" ? " unknown" : "";
    return `<span class="node node-leaf${unknown}">${esc(label)}
      <span class="node-count">· n=${node.support}${tie}</span></span>`;
  }
  return `<span class="node node-q">${esc(node.token)} ?</span>
    <ul class="branch">
      <li><span class="edge edge-yes">sim</span>${treeNode(node.yes)}</li>
      <li><span class="edge edge-no">não</span>${treeNode(node.no)}</li>
    </ul>`;
}

function renderTree() {
  $("tree").innerHTML = `<ul><li>${treeNode(state.tree)}</li></ul>`;
}

function renderPatterns() {
  $("patterns").innerHTML = state.patterns
    .map((p) => {
      const open = p.open_root_cause.length;
      const badge = open
        ? `<span class="pill pill-open">causa raiz aberta em ${open}/${p.size}</span>`
        : '<span class="pill pill-ok">causa raiz endereçada</span>';
      const evidence = p.sample_evidence
        ? `<p class="panel-sub"><strong>Amostra de evidência</strong>
           (${code(p.incident_ids[0])}): ${esc(p.sample_evidence)}</p>`
        : "";
      return `<article class="panel">
        <h3>${code(p.id)} ${esc(p.name)} ${badge}</h3>
        <p class="panel-sub">${p.size} incidentes: ${p.incident_ids.map(code).join(" ")}</p>
        <table>
          <tbody>
            <tr><th>sinais distintivos</th><td>${tokenList(p.distinctive)}</td></tr>
            <tr><th>sempre presentes</th><td>${tokenList(p.shared)}</td></tr>
          </tbody>
        </table>
        ${evidence}
        ${open ? '<p class="panel-sub">Recorrência é esperada até a causa raiz mudar.</p>' : ""}
      </article>`;
    })
    .join("");
}

function renderMatrix() {
  const m = state.matrix;
  if (!m.signals.length) {
    $("matrix").innerHTML = '<p class="empty">Nenhum sinal distintivo para cruzar.</p>';
    return;
  }
  const head = m.patterns.map((p) => `<th>${esc(p.id)}</th>`).join("");
  const rows = m.signals
    .map((token) => {
      const cells = m.patterns
        .map((p) => {
          const value = (m.support[p.id] || {})[token] || 0;
          const text = value >= 0.99 ? "<strong>100%</strong>" : value ? pct(value) : "-";
          return `<td class="num">${text}</td>`;
        })
        .join("");
      return `<tr><td>${code(token)}</td>${cells}</tr>`;
    })
    .join("");
  const legend = m.patterns.map((p) => `${code(p.id)} ${esc(p.name)}`).join(" &middot; ");
  $("matrix").innerHTML = `<table><thead><tr><th>sinal</th>${head}</tr></thead>
    <tbody>${rows}</tbody></table><p class="panel-sub">Legenda: ${legend}</p>`;
}

function renderIncidents() {
  const term = $("incident-filter").value.trim().toLowerCase();
  const rows = state.incidents.filter((i) =>
    !term
      ? true
      : [i.id, i.title, i.service, i.pattern, i.severity]
          .map((v) => String(v ?? "").toLowerCase())
          .some((v) => v.includes(term))
  );

  if (rows.length === 0) {
    $("incidents").innerHTML = '<p class="empty">Nenhum incidente casa com o filtro.</p>';
    return;
  }

  $("incidents").innerHTML = `<table>
    <thead><tr>
      <th>id</th><th>título</th><th>serviço</th><th>severidade</th>
      <th>padrão</th><th>sinais</th><th>causa raiz</th>
    </tr></thead>
    <tbody>${rows
      .map(
        (i) => `<tr class="clickable" data-id="${esc(i.id)}">
        <td>${code(i.id)}</td><td>${esc(i.title)}</td><td>${dash(i.service)}</td>
        <td>${dash(i.severity)}</td>
        <td>${i.pattern ? esc(i.pattern) : '<span class="pill pill-muted">fora de padrão</span>'}</td>
        <td class="num">${i.signal_count}</td>
        <td>${
          i.root_cause_addressed
            ? '<span class="pill pill-ok">endereçada</span>'
            : '<span class="pill pill-open">aberta</span>'
        }</td>
      </tr>`
      )
      .join("")}</tbody></table>`;

  $("incidents")
    .querySelectorAll("tr.clickable")
    .forEach((row) => row.addEventListener("click", () => openIncident(row.dataset.id)));
}

function markSelectedRow(id) {
  $("incidents")
    .querySelectorAll("tr.clickable")
    .forEach((row) => row.setAttribute("aria-selected", String(row.dataset.id === id)));
}

async function openIncident(id) {
  const detail = await api(`/api/incidents/${encodeURIComponent(id)}`);
  $("incident-detail-title").innerHTML = `${code(detail.id)} ${esc(detail.title)}`;
  $("incident-detail").innerHTML = `
    <table><tbody>
      <tr><th>arquivo</th><td>${code(detail.source)}</td></tr>
      <tr><th>ocorrido em</th><td>${dash(detail.occurred_on)}</td></tr>
      <tr><th>gatilho</th><td>${dash(detail.trigger)}</td></tr>
      <tr><th>mitigação</th><td>${dash(detail.mitigation)}</td></tr>
      <tr><th>padrão</th><td>${detail.pattern ? esc(detail.pattern) : "fora de padrão"}</td></tr>
      <tr><th>causa raiz</th><td>${
        detail.root_cause_addressed
          ? '<span class="pill pill-ok">endereçada</span>'
          : '<span class="pill pill-open">aberta</span>'
      }</td></tr>
    </tbody></table>
    <h3 style="margin-top:18px">Sinais extraídos</h3>
    <p class="panel-sub">Cada linha guarda o trecho original que gerou o token.</p>
    <table><thead><tr><th>token</th><th>camada</th><th>evidência</th></tr></thead>
      <tbody>${detail.signals
        .map(
          (s) =>
            `<tr><td>${code(s.token)}</td>
             <td><span class="pill pill-kind">${esc(s.kind)}</span></td>
             <td>${esc(s.evidence)}</td></tr>`
        )
        .join("")}</tbody></table>`;
  $("incident-detail-panel").hidden = false;
  markSelectedRow(id);
  $("incident-detail-panel").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function closeIncidentDetail() {
  $("incident-detail-panel").hidden = true;
  markSelectedRow(null);
}

function renderSignals() {
  $("signals").innerHTML = state.signals
    .map(
      (group) => `<article class="panel">
        <h3><span class="pill pill-kind">${esc(group.kind)}</span>
          ${group.tokens.length} sinais</h3>
        <p class="panel-sub">${group.tokens.map(code).join(" ")}</p>
      </article>`
    )
    .join("");
}

function updateSelectedCount() {
  const total = state.selected.size;
  $("selected-count").textContent =
    total === 0
      ? "Nenhum sinal marcado."
      : `${total} ${total === 1 ? "sinal marcado" : "sinais marcados"}.`;
}

function renderPicker() {
  $("classify-picker").innerHTML = state.signals
    .map(
      (group) => `<div class="picker-group">
        <h4>${esc(group.kind)}</h4>
        ${group.tokens
          .map(
            (token) =>
              `<label><input type="checkbox" value="${esc(token)}"${
                state.selected.has(token) ? " checked" : ""
              } />${esc(token)}</label>`
          )
          .join("")}
      </div>`
    )
    .join("");

  $("classify-picker")
    .querySelectorAll("input[type=checkbox]")
    .forEach((box) =>
      box.addEventListener("change", () => {
        if (box.checked) state.selected.add(box.value);
        else state.selected.delete(box.value);
        updateSelectedCount();
      })
    );

  updateSelectedCount();
}

async function runClassify() {
  const result = $("classify-result");
  if (state.selected.size === 0) {
    result.innerHTML = '<p class="empty">Selecione ao menos um sinal para classificar.</p>';
    return;
  }
  try {
    const answer = await api("/api/classify", {
      method: "POST",
      body: JSON.stringify({ signals: [...state.selected] }),
    });
    const steps = answer.path.length
      ? answer.path
          .map(
            (step) => `<div class="path-step">
              <span class="edge ${step.answer ? "edge-yes" : "edge-no"}">${
                step.answer ? "sim" : "não"
              }</span>${code(step.token)}
            </div>`
          )
          .join("")
      : '<p class="empty">A árvore respondeu na raiz, sem perguntas.</p>';
    const unknown = answer.unknown.length
      ? `<p class="panel-sub">Ignorados por não existirem na taxonomia:
         ${answer.unknown.map(code).join(" ")}</p>`
      : "";
    result.innerHTML = `
      <div class="verdict">${esc(answer.label)}</div>
      <p class="panel-sub">${answer.observed.length} sinais observados</p>
      <h3 style="margin-top:14px;font-size:13px">Caminho percorrido</h3>
      ${steps}${unknown}`;
  } catch (failure) {
    if (failure.unauthenticated) {
      showGate();
      return;
    }
    result.innerHTML = `<p class="gate-error">${esc(failure.message)}</p>`;
  }
}

/* --------------------------------------------------------------- router --- */

const RENDER = {
  overview: renderOverview,
  tree: renderTree,
  classify: renderPicker,
  patterns: renderPatterns,
  matrix: renderMatrix,
  incidents: renderIncidents,
  signals: renderSignals,
  report: () => {
    $("report").textContent = state.report.markdown;
  },
};

function show(view) {
  if (!RENDER[view]) view = "overview";
  state.view = view;

  document.querySelectorAll(".view").forEach((section) => {
    section.hidden = section.id !== `view-${view}`;
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.setAttribute("aria-current", String(button.dataset.view === view));
  });

  // O detalhe de um incidente nao faz sentido fora da sua view.
  if (view !== "incidents") closeIncidentDetail();

  RENDER[view]();
  window.scrollTo({ top: 0, behavior: "instant" });
  if (location.hash !== `#${view}`) {
    history.replaceState(null, "", `#${view}`);
  }
}

/* ----------------------------------------------------------------- boot --- */

function showGate() {
  $("app").hidden = true;
  $("gate").hidden = false;
}

async function loadAll() {
  const [summary, patterns, matrix, tree, incidents, signalList, report] = await Promise.all([
    api("/api/summary"),
    api("/api/patterns"),
    api("/api/matrix"),
    api("/api/tree"),
    api("/api/incidents"),
    api("/api/signals"),
    api("/api/report"),
  ]);
  Object.assign(state, {
    summary, patterns, matrix, tree, incidents, signals: signalList, report,
  });
}

async function enterApp(user) {
  await loadAll();
  state.user = user;
  $("gate").hidden = true;
  $("app").hidden = false;
  $("who").textContent = user;
  $("brand-version").textContent = `v${state.summary.version}`;
  show(location.hash.replace("#", "") || "overview");
}

function wire() {
  document
    .querySelectorAll(".nav-item")
    .forEach((button) => button.addEventListener("click", () => show(button.dataset.view)));

  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("login-button");
    const error = $("login-error");
    error.hidden = true;
    button.disabled = true;

    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user: $("user").value, password: $("password").value }),
      });

      if (response.status === 401) {
        error.textContent = "Credencial inválida.";
        error.hidden = false;
        return;
      }
      if (!response.ok) {
        error.textContent = `O servidor respondeu ${response.status}.`;
        error.hidden = false;
        return;
      }

      const body = await response.json();
      // Separa os dois modos de falha de proposito. Autenticar e carregar os dados sao
      // etapas distintas, e tratar as duas como "login falhou" foi o que tornou um bug de
      // renderizacao indistinguivel de credencial errada.
      try {
        await enterApp(body.user);
      } catch (loadFailure) {
        error.textContent = `Autenticado, mas os dados não carregaram: ${loadFailure.message}`;
        error.hidden = false;
      }
    } catch {
      error.textContent = "Não foi possível falar com o servidor.";
      error.hidden = false;
    } finally {
      button.disabled = false;
    }
  });

  $("logout").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    state.selected.clear();
    showGate();
  });

  $("incident-filter").addEventListener("input", () => {
    closeIncidentDetail();
    renderIncidents();
  });
  $("incident-detail-close").addEventListener("click", closeIncidentDetail);

  $("classify-run").addEventListener("click", runClassify);
  $("classify-clear").addEventListener("click", () => {
    state.selected.clear();
    renderPicker();
    $("classify-result").innerHTML = '<p class="empty">Nenhum sinal selecionado ainda.</p>';
  });

  window.addEventListener("hashchange", () => {
    const view = location.hash.replace("#", "");
    if (RENDER[view] && view !== state.view) show(view);
  });
}

(async function main() {
  wire();
  try {
    const session = await api("/api/session");
    if (session.authenticated) {
      await enterApp(session.user);
      return;
    }
  } catch {
    /* sessao ausente ou dados indisponiveis: cai no portao */
  }
  showGate();
})();
