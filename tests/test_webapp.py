"""Tests for the stdlib dashboard.

Two layers, on purpose:

- Pure functions get called directly. Every auth branch and every payload shape is
  exercised without binding a socket, which is what keeps this fast.
- One real round trip over `http.client` covers the `Handler` shell, the cookie
  handshake and the static file path, because a handler that only ever runs in a unit
  test has never proven it can answer a socket.
"""

from __future__ import annotations

import json
import socket
import threading
from http import HTTPStatus
from http.client import HTTPConnection

import pytest

from postmortem_miner import webapp
from postmortem_miner.decision_tree import Node

SECRET = b"unit-test-secret"
CRLF = chr(13) + chr(10)  # sem escape literal, para o gate de sanitize


@pytest.fixture
def state(corpus_dir):
    return webapp.build_state(
        corpus_dir,
        credentials=webapp.Credentials(user="demo", password="demo"),
        secret=SECRET,
    )


# --- state ----------------------------------------------------------------------


def test_build_state_rejects_a_corpus_without_signals(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no postmortem"):
        webapp.build_state(empty)


def test_build_state_generates_a_secret_when_none_is_given(corpus_dir):
    built = webapp.build_state(corpus_dir)
    assert len(built.secret) == 32
    assert built.corpus == str(corpus_dir)


def test_credentials_default_when_env_is_empty():
    creds = webapp.Credentials.from_env({})
    assert creds == webapp.Credentials(webapp.DEFAULT_USER, webapp.DEFAULT_PASSWORD)


def test_credentials_read_the_environment():
    creds = webapp.Credentials.from_env({"PM_USER": "sre", "PM_PASSWORD": "pw"})
    assert (creds.user, creds.password) == ("sre", "pw")


def test_credentials_from_real_environment(monkeypatch):
    monkeypatch.setenv("PM_USER", "fromenv")
    monkeypatch.delenv("PM_PASSWORD", raising=False)
    creds = webapp.Credentials.from_env()
    assert creds.user == "fromenv"
    assert creds.password == webapp.DEFAULT_PASSWORD


def test_documented_default_credentials():
    """O README e a tela de login publicam esta credencial.

    Travar aqui e de proposito: mudar o default sem mudar a documentacao deixa o demo
    publico inacessivel para quem chega pelo README, e isso nao aparece em nenhum outro
    teste porque o resto da suite injeta a credencial explicitamente.
    """
    assert webapp.DEFAULT_USER == "julianovincedecampos"
    assert webapp.DEFAULT_PASSWORD == "postmortem-miner"


def test_stylesheet_lets_the_hidden_attribute_win():
    """Regressao de producao, e a que mais custou a achar.

    `.gate` e `.app` definem `display: grid`, e uma regra de autor com display vence o
    `[hidden] { display: none }` da folha de estilo do navegador. Sem a regra explicita,
    `element.hidden = true` nao esconde nada: o login autenticava, gravava o cookie, e a
    tela de login continuava por cima do dashboard - indistinguivel de "nao logou".
    """
    css = (webapp.WEB_ROOT / "styles.css").read_text(encoding="utf-8")
    assert "[hidden]" in css
    assert "display: none !important" in css


def test_the_login_screen_shows_the_default_credentials():
    """A tela publica a credencial; se divergir do default, ninguem entra."""
    html = (webapp.WEB_ROOT / "index.html").read_text(encoding="utf-8")
    assert webapp.DEFAULT_USER in html
    assert webapp.DEFAULT_PASSWORD in html


# --- auth -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user", "password", "expected"),
    [
        ("demo", "demo", True),
        ("demo", "wrong", False),
        ("wrong", "demo", False),
        ("", "", False),
    ],
)
def test_credentials_ok(state, user, password, expected):
    assert webapp.credentials_ok(state.credentials, user, password) is expected


def test_session_round_trip():
    token = webapp.make_session(SECRET, "demo", now=1000.0)
    assert webapp.read_session(SECRET, token, now=1000.0) == "demo"


def test_session_expires():
    token = webapp.make_session(SECRET, "demo", now=1000.0)
    later = 1000.0 + webapp.SESSION_TTL_SECONDS + 1
    assert webapp.read_session(SECRET, token, now=later) is None


def test_session_rejects_a_foreign_signature():
    token = webapp.make_session(SECRET, "demo", now=1000.0)
    assert webapp.read_session(b"another-secret", token, now=1000.0) is None


def test_session_rejects_a_tampered_user():
    token = webapp.make_session(SECRET, "demo", now=1000.0)
    _, expiry, signature = token.split(".")
    assert webapp.read_session(SECRET, f"root.{expiry}.{signature}", now=1000.0) is None


@pytest.mark.parametrize("token", [None, "", "onlyonepart", "a.b", "a.b.c.d"])
def test_session_rejects_malformed_tokens(token):
    assert webapp.read_session(SECRET, token) is None


def test_session_rejects_a_non_numeric_expiry():
    payload = "demo.notanumber"
    forged = f"{payload}.{webapp._sign(SECRET, payload)}"
    assert webapp.read_session(SECRET, forged) is None


def test_session_uses_the_wall_clock_by_default():
    assert webapp.read_session(SECRET, webapp.make_session(SECRET, "demo")) == "demo"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("", None),
        ("pm_session=abc", "abc"),
        ("other=1; pm_session=abc; x=2", "abc"),
        ("pm_session=", None),
        ("nothing=here", None),
    ],
)
def test_cookie_value(header, expected):
    assert webapp.cookie_value(header, webapp.SESSION_COOKIE) == expected


# --- payloads -------------------------------------------------------------------


def test_summary_payload_shape(state):
    summary = webapp.summary_payload(state)
    assert summary["incidents"] == len(state.analysis.incidents)
    assert 0.0 <= summary["coverage"] <= 1.0
    assert summary["signals_known"] > 0
    assert summary["version"]


def test_patterns_payload_reports_open_root_cause(state):
    payload = webapp.patterns_payload(state)
    assert payload, "the two-family corpus must produce at least one pattern"
    assert any(entry["open_root_cause"] for entry in payload)
    assert all(entry["size"] == len(entry["incident_ids"]) for entry in payload)


def test_patterns_payload_without_distinctive_signals(state):
    """A pattern with no distinctive token carries no sample evidence."""
    stripped = tuple(
        type(pattern)(
            id=pattern.id,
            name=pattern.name,
            incident_ids=pattern.incident_ids,
            distinctive=(),
            shared=pattern.shared,
        )
        for pattern in state.analysis.patterns
    )
    state.analysis = type(state.analysis)(
        incidents=state.analysis.incidents,
        patterns=stripped,
        tree=state.analysis.tree,
        coverage=state.analysis.coverage,
        elapsed_ms=state.analysis.elapsed_ms,
    )
    assert all(entry["sample_evidence"] is None for entry in webapp.patterns_payload(state))


def test_matrix_payload_shape(state):
    matrix = webapp.matrix_payload(state)
    assert set(matrix["support"]) == {pattern["id"] for pattern in matrix["patterns"]}


def test_incidents_payload_and_detail(state):
    listing = webapp.incidents_payload(state)
    assert listing
    detail = webapp.incident_detail(state, listing[0]["id"])
    assert detail is not None
    assert detail["signals"]
    assert {"token", "kind", "evidence"} <= set(detail["signals"][0])


def test_incident_detail_returns_none_for_an_unknown_id(state):
    assert webapp.incident_detail(state, "does-not-exist") is None


def test_signals_payload_groups_by_layer():
    grouped = webapp.signals_payload()
    assert grouped
    assert all(entry["tokens"] == sorted(entry["tokens"]) for entry in grouped)


def test_signals_payload_labels_an_unknown_token_as_other(monkeypatch):
    monkeypatch.setattr(webapp.signals, "known_tokens", lambda: ("not.a.real.token",))
    monkeypatch.setattr(webapp.signals, "kind_of", lambda _token: None)
    assert webapp.signals_payload() == [{"kind": "other", "tokens": ["not.a.real.token"]}]


def test_classify_payload_separates_unknown_tokens(state):
    known = webapp.signals.known_tokens()[0]
    result = webapp.classify_payload(state, [known, "bogus.token", "  "])
    assert result["unknown"] == ["bogus.token"]
    assert result["label"]
    assert all({"token", "answer"} == set(step) for step in result["path"])


def test_tree_payload_renders_questions_and_leaves():
    tree = Node(token="a", support=2, yes=Node(label="left", support=1, tie=("x",)), no=None)
    payload = webapp.tree_payload(tree)
    assert payload["kind"] == "question"
    assert payload["no"] is None
    assert payload["yes"] == {"kind": "leaf", "label": "left", "support": 1, "tie": ["x"]}


def test_tree_payload_defaults_an_unlabelled_leaf():
    assert webapp.tree_payload(Node())["label"] == "unknown"


def test_report_markdown_is_the_cli_report(state):
    assert webapp.report_markdown(state).startswith("# Incident pattern analysis")


# --- routing ---------------------------------------------------------------------


def test_health_needs_no_session(state):
    status, payload = webapp.handle_get(state, "/api/health", None)
    assert status is HTTPStatus.OK
    assert payload["status"] == "ok"


def test_session_endpoint_reports_anonymous(state):
    status, payload = webapp.handle_get(state, "/api/session", None)
    assert status is HTTPStatus.OK
    assert payload == {"authenticated": False, "user": None}


@pytest.mark.parametrize(
    "path",
    [
        "/api/summary",
        "/api/patterns",
        "/api/matrix",
        "/api/tree",
        "/api/incidents",
        "/api/signals",
        "/api/report",
        "/api/incidents/whatever",
        "/api/nope",
    ],
)
def test_every_private_get_refuses_an_anonymous_caller(state, path):
    status, payload = webapp.handle_get(state, path, None)
    assert status is HTTPStatus.UNAUTHORIZED
    assert payload == {"error": "authentication required"}


@pytest.mark.parametrize(
    "path",
    [
        "/api/summary",
        "/api/patterns",
        "/api/matrix",
        "/api/tree",
        "/api/incidents",
        "/api/signals",
        "/api/report",
    ],
)
def test_authenticated_gets_succeed(state, path):
    status, payload = webapp.handle_get(state, path, "demo")
    assert status is HTTPStatus.OK
    assert payload is not None


def test_incident_detail_route(state):
    incident_id = webapp.incidents_payload(state)[0]["id"]
    status, payload = webapp.handle_get(state, f"/api/incidents/{incident_id}", "demo")
    assert status is HTTPStatus.OK
    assert payload["id"] == incident_id


def test_incident_detail_route_404(state):
    status, payload = webapp.handle_get(state, "/api/incidents/ghost", "demo")
    assert status is HTTPStatus.NOT_FOUND
    assert payload == {"error": "unknown incident"}


def test_unknown_get_endpoint(state):
    status, payload = webapp.handle_get(state, "/api/whatever", "demo")
    assert status is HTTPStatus.NOT_FOUND
    assert payload == {"error": "unknown endpoint"}


def test_login_sets_a_session(state):
    status, payload, session = webapp.handle_post(
        state, "/api/login", {"user": "demo", "password": "demo"}, None
    )
    assert status is HTTPStatus.OK
    assert payload == {"authenticated": True, "user": "demo"}
    assert webapp.read_session(state.secret, session) == "demo"


def test_login_rejects_a_bad_password(state):
    status, payload, session = webapp.handle_post(
        state, "/api/login", {"user": "demo", "password": "nope"}, None
    )
    assert status is HTTPStatus.UNAUTHORIZED
    assert payload == {"error": "invalid credentials"}
    assert session is None


def test_login_with_an_empty_body(state):
    status, _, session = webapp.handle_post(state, "/api/login", {}, None)
    assert status is HTTPStatus.UNAUTHORIZED
    assert session is None


def test_logout_clears_the_cookie(state):
    status, payload, session = webapp.handle_post(state, "/api/logout", {}, "demo")
    assert status is HTTPStatus.OK
    assert payload == {"authenticated": False}
    assert session == ""


def test_classify_requires_a_session(state):
    status, payload, session = webapp.handle_post(state, "/api/classify", {"signals": []}, None)
    assert status is HTTPStatus.UNAUTHORIZED
    assert session is None
    assert payload == {"error": "authentication required"}


def test_classify_accepts_a_list(state):
    token = webapp.signals.known_tokens()[0]
    status, payload, _ = webapp.handle_post(state, "/api/classify", {"signals": [token]}, "demo")
    assert status is HTTPStatus.OK
    assert payload["observed"] == [token]


def test_classify_ignores_a_non_list_payload(state):
    status, payload, _ = webapp.handle_post(
        state, "/api/classify", {"signals": "not-a-list"}, "demo"
    )
    assert status is HTTPStatus.OK
    assert payload["observed"] == []


def test_unknown_post_endpoint(state):
    status, payload, _ = webapp.handle_post(state, "/api/nope", {}, "demo")
    assert status is HTTPStatus.NOT_FOUND
    assert payload == {"error": "unknown endpoint"}


# --- static files ----------------------------------------------------------------


@pytest.mark.parametrize("path", ["", "/", "/index.html", "/app.js", "/styles.css"])
def test_static_file_serves_the_bundle(path):
    resolved = webapp.static_file(path)
    assert resolved is not None
    target, content_type = resolved
    assert target.is_file()
    assert content_type.startswith("text/")


@pytest.mark.parametrize(
    "path",
    ["/../pyproject.toml", "/nope.html", "/web", "/index.html/", "//app.js", "/APP.JS"],
)
def test_static_file_refuses_anything_outside_the_allowlist(path):
    assert webapp.static_file(path) is None


def test_static_file_returns_none_when_the_bundle_is_missing(monkeypatch, tmp_path):
    """Allowlisted name, arquivo ausente: nada a servir, e ninguem explode."""
    monkeypatch.setattr(webapp, "WEB_ROOT", tmp_path)
    assert webapp.static_file("/app.js") is None


def test_login_signs_the_configured_user_not_the_submitted_string(state):
    _, payload, session = webapp.handle_post(
        state, "/api/login", {"user": "demo", "password": "demo"}, None
    )
    assert payload["user"] == state.credentials.user
    assert webapp.read_session(state.secret, session) == state.credentials.user


# --- one real round trip ---------------------------------------------------------


@pytest.fixture
def live(state):
    """A real server on an ephemeral port, torn down with the test."""
    httpd = webapp.make_server(state, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def _request(port, method, path, body=None, cookie=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    return response, raw


def test_live_serves_the_dashboard_html(live):
    response, raw = _request(live, "GET", "/")
    assert response.status == HTTPStatus.OK
    assert response.getheader("X-Frame-Options") == "DENY"
    assert b"postmortem-miner" in raw


def test_live_health_is_public(live):
    response, raw = _request(live, "GET", "/api/health")
    assert response.status == HTTPStatus.OK
    assert json.loads(raw)["status"] == "ok"


def test_live_login_then_read_then_logout(live):
    response, _ = _request(live, "POST", "/api/login", {"user": "demo", "password": "demo"})
    assert response.status == HTTPStatus.OK
    cookie = response.getheader("Set-Cookie")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    session = cookie.split(";")[0]

    response, raw = _request(live, "GET", "/api/summary", cookie=session)
    assert response.status == HTTPStatus.OK
    assert json.loads(raw)["patterns"] >= 1

    response, _ = _request(live, "POST", "/api/logout", {}, cookie=session)
    assert "Max-Age=0" in response.getheader("Set-Cookie")


def test_live_refuses_an_anonymous_read(live):
    response, _ = _request(live, "GET", "/api/summary")
    assert response.status == HTTPStatus.UNAUTHORIZED


def test_live_unknown_static_path_is_json_404(live):
    response, raw = _request(live, "GET", "/not-a-file")
    assert response.status == HTTPStatus.NOT_FOUND
    assert json.loads(raw) == {"error": "not found"}


def test_live_post_outside_the_api_is_404(live):
    response, _ = _request(live, "POST", "/somewhere", {})
    assert response.status == HTTPStatus.NOT_FOUND


def test_live_invalid_json_body_is_treated_as_empty(live):
    conn = HTTPConnection("127.0.0.1", live, timeout=5)
    conn.request("POST", "/api/login", body=b"{not json", headers={"Content-Length": "9"})
    response = conn.getresponse()
    response.read()
    conn.close()
    assert response.status == HTTPStatus.UNAUTHORIZED


def test_live_oversized_body_is_treated_as_empty(live):
    conn = HTTPConnection("127.0.0.1", live, timeout=5)
    conn.putrequest("POST", "/api/login")
    conn.putheader("Content-Length", str(webapp.MAX_BODY_BYTES + 1))
    conn.endheaders()
    conn.send(b"x" * (webapp.MAX_BODY_BYTES + 1))
    response = conn.getresponse()
    response.read()
    conn.close()
    assert response.status == HTTPStatus.UNAUTHORIZED


def _read_one_response(stream):
    """Le uma resposta HTTP inteira: status, headers e corpo por Content-Length.

    Escrito a mao porque o objetivo do teste e nao usar um cliente que reconecta ou
    normaliza a conexao por baixo.
    """
    status = stream.readline().decode("latin-1").strip()
    length = 0
    while True:
        line = stream.readline().decode("latin-1").strip()
        if not line:
            break
        name, _, value = line.partition(":")
        if name.strip().lower() == "content-length":
            length = int(value.strip())
    return status, (stream.read(length) if length else b"")


def test_live_answers_two_requests_on_one_socket(live):
    """Duas requisicoes sequenciais na mesma conexao TCP, como faz um proxy.

    Regressao de producao. O default de BaseHTTPRequestHandler e HTTP/1.0, que fecha a
    conexao depois de cada resposta. Atras do proxy do Render, que reusa a conexao
    upstream, isso dessincronizava o par requisicao/resposta: um GET anonimo em
    /api/summary voltou 404 com corpo "Not Found" no lugar de 401, e /api/nope voltou 401.

    Duas tentativas anteriores nao serviram, e vale registrar por que: http.client
    reconecta sozinho quando o servidor fecha a conexao, escondendo o sintoma; e enviar
    as duas requisicoes num unico sendall (pipelining) e racy. Ler uma resposta inteira
    antes de enviar a proxima e deterministico.
    """
    health = ("GET /api/health HTTP/1.1" + CRLF + "Host: localhost" + CRLF + CRLF).encode()
    summary = ("GET /api/summary HTTP/1.1" + CRLF + "Host: localhost" + CRLF + CRLF).encode()

    with socket.create_connection(("127.0.0.1", live), timeout=5) as sock:
        stream = sock.makefile("rwb")

        stream.write(health)
        stream.flush()
        status, body = _read_one_response(stream)
        assert status.startswith("HTTP/1.1 200"), f"esperado HTTP/1.1, veio {status!r}"
        assert json.loads(body)["status"] == "ok"

        stream.write(summary)
        stream.flush()
        status, body = _read_one_response(stream)
        assert status.startswith(
            "HTTP/1.1 401"
        ), f"segunda requisicao na mesma conexao falhou: {status!r}"
        assert json.loads(body) == {"error": "authentication required"}

        stream.close()


def test_live_body_is_drained_so_the_connection_survives(live):
    """Um POST fora da API tem o corpo drenado e a conexao segue utilizavel.

    Sem drenar, o keep-alive parseava os bytes sobrando como a proxima linha de request
    e o servidor logava Bad request syntax. E o mesmo modo de falha do HTTP/1.0, entrando
    pelo outro lado.
    """
    payload = b'{"a": 1}'
    head = (
        "POST /somewhere HTTP/1.1"
        + CRLF
        + "Host: localhost"
        + CRLF
        + "Content-Type: application/json"
        + CRLF
        + f"Content-Length: {len(payload)}"
        + CRLF
        + CRLF
    ).encode()
    health = ("GET /api/health HTTP/1.1" + CRLF + "Host: localhost" + CRLF + CRLF).encode()

    with socket.create_connection(("127.0.0.1", live), timeout=5) as sock:
        stream = sock.makefile("rwb")

        stream.write(head + payload)
        stream.flush()
        status, _ = _read_one_response(stream)
        assert status.startswith("HTTP/1.1 404"), status

        stream.write(health)
        stream.flush()
        status, body = _read_one_response(stream)
        assert status.startswith(
            "HTTP/1.1 200"
        ), f"a conexao nao sobreviveu ao POST com corpo: {status!r}"
        assert json.loads(body)["status"] == "ok"

        stream.close()


def test_log_message_tolerates_a_single_argument(state, capsys):
    handler = webapp.Handler.__new__(webapp.Handler)
    handler.command = "GET"
    handler.path = "/api/health"
    handler.log_message("%s", "only-one")
    assert "GET /api/health" in capsys.readouterr().out
