"""HTTP dashboard for the miner, on the standard library only.

Why `http.server` and not FastAPI: ADR-0001 says the installed package depends on the
standard library, because the tool has to run on whatever box can reach the postmortem
archive during an incident. A dashboard is a reason to revisit that decision, not a reason
to drop it - see ADR-0003. The whole web layer here is `http.server`, `json`, `hmac` and
`secrets`, so `pip install postmortem-miner` still pulls nothing.

Shape of the module, deliberately:

- Pure functions build every payload and every auth decision. They take data and return
  data, so each branch is testable without binding a socket.
- `Handler` is a thin shell that maps a request to one of those functions. It holds no
  logic worth testing twice.
- The corpus is analysed once, at startup, and cached in `AppState`. The corpus does not
  change while the process runs, and re-analysing per request would turn a 30 ms page into
  a 30 ms page plus the whole pipeline.

Auth is a signed cookie checked on the server. The credentials are a demo gate, not a
security control - the data is synthetic and read-only - but the check still happens
server-side, because a gate enforced in JavaScript is not a gate.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from postmortem_miner import __version__, decision_tree, report, signals
from postmortem_miner.models import Incident
from postmortem_miner.parser import parse_corpus
from postmortem_miner.patterns import DEFAULT_THRESHOLD
from postmortem_miner.patterns import matrix as pattern_matrix

WEB_ROOT = Path(__file__).resolve().parent / "web"

SESSION_COOKIE = "pm_session"
SESSION_TTL_SECONDS = 28_800  # eight hours: one working day, then re-auth
_SESSION_PARTS = 3  # user.expiry.signature
DEFAULT_USER = "demo"
DEFAULT_PASSWORD = "demo"
MAX_BODY_BYTES = 64 * 1024

# Endpoints reachable without a session. Health has to answer for the container
# probe before anyone logs in; login would be a deadlock otherwise.
PUBLIC_API = frozenset({"/api/health", "/api/login", "/api/session"})


# --------------------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Credentials:
    user: str
    password: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Credentials:
        source = env if env is not None else dict(os.environ)
        return cls(
            user=source.get("PM_USER") or DEFAULT_USER,
            password=source.get("PM_PASSWORD") or DEFAULT_PASSWORD,
        )


@dataclass(slots=True)
class AppState:
    """Everything a request needs, computed once."""

    analysis: report.Analysis
    credentials: Credentials
    secret: bytes
    corpus: str

    @property
    def by_id(self) -> dict[str, Incident]:
        return {incident.id: incident for incident in self.analysis.incidents}


def build_state(
    corpus: Path,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    credentials: Credentials | None = None,
    secret: bytes | None = None,
) -> AppState:
    """Parse and analyse the corpus once, then freeze it into the app state."""
    started = time.perf_counter()
    incidents = parse_corpus(corpus)
    if not incidents:
        raise ValueError(f"no postmortem with recognisable signals found in {corpus}")
    elapsed_ms = (time.perf_counter() - started) * 1000
    analysis = report.analyse(incidents, threshold=threshold, elapsed_ms=elapsed_ms)
    return AppState(
        analysis=analysis,
        credentials=credentials or Credentials.from_env(),
        # A per-process secret means sessions do not survive a restart. That is the
        # right trade for a stateless demo: no shared secret to leak, no store to run.
        secret=secret or secrets.token_bytes(32),
        corpus=str(corpus),
    )


# --------------------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------------------


def credentials_ok(credentials: Credentials, user: str, password: str) -> bool:
    """Constant-time comparison on both fields, so timing says nothing useful."""
    user_ok = hmac.compare_digest(credentials.user.encode(), user.encode())
    password_ok = hmac.compare_digest(credentials.password.encode(), password.encode())
    return user_ok and password_ok


def _sign(secret: bytes, payload: str) -> str:
    digest = hmac.new(secret, payload.encode("utf-8"), sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_session(secret: bytes, user: str, *, now: float | None = None) -> str:
    """`user.expiry.signature`, urlsafe. No secret material in the cookie itself."""
    expiry = int((now if now is not None else time.time()) + SESSION_TTL_SECONDS)
    payload = f"{user}.{expiry}"
    return f"{payload}.{_sign(secret, payload)}"


def read_session(secret: bytes, token: str | None, *, now: float | None = None) -> str | None:
    """Return the user carried by a valid token, or None. Fails closed on anything odd."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != _SESSION_PARTS:
        return None
    user, raw_expiry, signature = parts
    if not hmac.compare_digest(_sign(secret, f"{user}.{raw_expiry}"), signature):
        return None
    try:
        expiry = int(raw_expiry)
    except ValueError:
        return None
    if expiry < (now if now is not None else time.time()):
        return None
    return user


def cookie_value(header: str | None, name: str) -> str | None:
    """Minimal cookie reader: the stdlib parser is lenient in ways we do not need."""
    if not header:
        return None
    for chunk in header.split(";"):
        key, _, value = chunk.strip().partition("=")
        if key == name:
            return value or None
    return None


# --------------------------------------------------------------------------------------
# payloads
# --------------------------------------------------------------------------------------


def tree_payload(node: decision_tree.Node) -> dict[str, Any]:
    """The triage tree as nested JSON, so the browser can draw it without Mermaid."""
    if node.is_leaf:
        return {
            "kind": "leaf",
            "label": node.label or "unknown",
            "support": node.support,
            "tie": list(node.tie),
        }
    return {
        "kind": "question",
        "token": node.token,
        "support": node.support,
        "yes": tree_payload(node.yes) if node.yes else None,
        "no": tree_payload(node.no) if node.no else None,
    }


def summary_payload(state: AppState) -> dict[str, Any]:
    analysis = state.analysis
    return {
        "incidents": len(analysis.incidents),
        "patterns": len(analysis.patterns),
        "coverage": round(analysis.coverage, 4),
        "triage_depth": decision_tree.depth(analysis.tree),
        "elapsed_ms": round(analysis.elapsed_ms, 2),
        "unexplained": len(analysis.unexplained),
        "signals_known": len(signals.known_tokens()),
        "corpus": state.corpus,
        "version": __version__,
    }


def patterns_payload(state: AppState) -> list[dict[str, Any]]:
    by_id = state.by_id
    out: list[dict[str, Any]] = []
    for pattern in state.analysis.patterns:
        open_root_cause = [
            incident_id
            for incident_id in pattern.incident_ids
            if incident_id in by_id and not by_id[incident_id].root_cause_addressed
        ]
        sample_evidence = None
        if pattern.incident_ids and pattern.distinctive:
            first = by_id.get(pattern.incident_ids[0])
            if first is not None:
                sample_evidence = first.evidence_for(pattern.distinctive[0])
        out.append(
            {
                "id": pattern.id,
                "name": pattern.name,
                "size": pattern.size,
                "incident_ids": list(pattern.incident_ids),
                "distinctive": list(pattern.distinctive),
                "shared": sorted(pattern.shared),
                "open_root_cause": open_root_cause,
                "sample_evidence": sample_evidence,
            }
        )
    return out


def matrix_payload(state: AppState) -> dict[str, Any]:
    columns, table = pattern_matrix(state.analysis.patterns, state.analysis.incidents)
    return {
        "signals": list(columns),
        "patterns": [
            {"id": pattern.id, "name": pattern.name} for pattern in state.analysis.patterns
        ],
        "support": {
            pattern_id: {token: round(value, 4) for token, value in row.items()}
            for pattern_id, row in table.items()
        },
    }


def _incident_brief(incident: Incident, pattern_of: dict[str, str]) -> dict[str, Any]:
    return {
        "id": incident.id,
        "title": incident.title,
        "service": incident.service,
        "severity": incident.severity,
        "occurred_on": incident.occurred_on,
        "root_cause_addressed": incident.root_cause_addressed,
        "signal_count": len(incident.signals),
        "pattern": pattern_of.get(incident.id),
    }


def _pattern_of(state: AppState) -> dict[str, str]:
    return {
        incident_id: f"{pattern.id} {pattern.name}"
        for pattern in state.analysis.patterns
        for incident_id in pattern.incident_ids
    }


def incidents_payload(state: AppState) -> list[dict[str, Any]]:
    pattern_of = _pattern_of(state)
    return [_incident_brief(incident, pattern_of) for incident in state.analysis.incidents]


def incident_detail(state: AppState, incident_id: str) -> dict[str, Any] | None:
    incident = state.by_id.get(incident_id)
    if incident is None:
        return None
    detail = _incident_brief(incident, _pattern_of(state))
    detail.update(
        {
            "source": incident.source,
            "trigger": incident.trigger,
            "mitigation": incident.mitigation,
            "signals": [
                {"token": signal.token, "kind": str(signal.kind), "evidence": signal.evidence}
                for signal in incident.signals
            ],
        }
    )
    return detail


def signals_payload() -> list[dict[str, Any]]:
    """Known tokens grouped by layer, which is how the taxonomy is meant to be read."""
    grouped: dict[str, list[str]] = {}
    for token in signals.known_tokens():
        kind = signals.kind_of(token)
        grouped.setdefault(str(kind) if kind else "other", []).append(token)
    return [{"kind": kind, "tokens": sorted(tokens)} for kind, tokens in sorted(grouped.items())]


def classify_payload(state: AppState, observed: list[str]) -> dict[str, Any]:
    known = set(signals.known_tokens())
    tokens = frozenset(token.strip() for token in observed if token.strip())
    unknown = sorted(tokens - known)
    label, path = decision_tree.classify_path(state.analysis.tree, tokens & known)
    return {
        "label": label,
        "observed": sorted(tokens),
        "unknown": unknown,
        "path": [{"token": token, "answer": answer} for token, answer in path],
    }


def report_markdown(state: AppState) -> str:
    return report.to_markdown(state.analysis)


# --------------------------------------------------------------------------------------
# routing
# --------------------------------------------------------------------------------------


def _json_error(status: HTTPStatus, message: str) -> tuple[HTTPStatus, dict[str, Any]]:
    return status, {"error": message}


"""Read-only GET endpoints, as a table. A dict beats a ladder of `if path ==`:
adding a view is one line, and the router stays flat enough to read."""
_GET_ROUTES: dict[str, Callable[[AppState], Any]] = {
    "/api/summary": summary_payload,
    "/api/patterns": patterns_payload,
    "/api/matrix": matrix_payload,
    "/api/incidents": incidents_payload,
    "/api/tree": lambda state: tree_payload(state.analysis.tree),
    "/api/signals": lambda _state: signals_payload(),
    "/api/report": lambda state: {"markdown": report_markdown(state)},
}

_INCIDENT_PREFIX = "/api/incidents/"


def handle_get(state: AppState, path: str, user: str | None) -> tuple[HTTPStatus, Any]:
    """Route a GET under /api. Returns (status, payload) - never touches the socket."""
    if path == "/api/health":
        return HTTPStatus.OK, {"status": "ok", "version": __version__}
    if path == "/api/session":
        return HTTPStatus.OK, {"authenticated": user is not None, "user": user}

    if user is None:
        return _json_error(HTTPStatus.UNAUTHORIZED, "authentication required")

    builder = _GET_ROUTES.get(path)
    if builder is not None:
        return HTTPStatus.OK, builder(state)

    if path.startswith(_INCIDENT_PREFIX):
        detail = incident_detail(state, path.removeprefix(_INCIDENT_PREFIX))
        return (
            (HTTPStatus.OK, detail)
            if detail is not None
            else _json_error(HTTPStatus.NOT_FOUND, "unknown incident")
        )

    return _json_error(HTTPStatus.NOT_FOUND, "unknown endpoint")


def handle_post(
    state: AppState, path: str, body: dict[str, Any], user: str | None
) -> tuple[HTTPStatus, Any, str | None]:
    """Route a POST. Third element is a session token to set, or None."""
    if path == "/api/login":
        given_user = str(body.get("user", ""))
        given_password = str(body.get("password", ""))
        if not credentials_ok(state.credentials, given_user, given_password):
            return HTTPStatus.UNAUTHORIZED, {"error": "invalid credentials"}, None
        # A sessao e assinada sobre a credencial configurada, nao sobre a string que
        # chegou na requisicao. Depois de credentials_ok as duas sao iguais, mas assim
        # nada vindo da rede alcanca um header Set-Cookie, nem por construcao.
        return (
            HTTPStatus.OK,
            {"authenticated": True, "user": state.credentials.user},
            make_session(state.secret, state.credentials.user),
        )

    if path == "/api/logout":
        return HTTPStatus.OK, {"authenticated": False}, ""

    if user is None:
        return HTTPStatus.UNAUTHORIZED, {"error": "authentication required"}, None

    if path == "/api/classify":
        raw = body.get("signals", [])
        observed = raw if isinstance(raw, list) else []
        return HTTPStatus.OK, classify_payload(state, [str(token) for token in observed]), None

    return HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"}, None


_HTML = "text/html; charset=utf-8"

# O bundle e um conjunto fixo de tres arquivos, nao um diretorio para servir. Mapear
# URL -> (nome, content-type) explicitamente elimina a construcao de caminho a partir
# de entrada de rede: nao ha travessia a barrar porque nao ha caminho a montar. Vale
# tambem para o content-type, que deixa de vir de inferencia sobre nome de arquivo.
_STATIC: dict[str, tuple[str, str]] = {
    "": ("index.html", _HTML),
    "/": ("index.html", _HTML),
    "/index.html": ("index.html", _HTML),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


def static_file(path: str) -> tuple[Path, str] | None:
    """Resolve uma URL para um arquivo do bundle e seu content-type, ou None."""
    entry = _STATIC.get(path)
    if entry is None:
        return None
    name, content_type = entry
    candidate = WEB_ROOT / name
    if not candidate.is_file():
        return None
    return candidate, content_type


# --------------------------------------------------------------------------------------
# server
# --------------------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    """Thin shell. Every decision it makes lives in a function above."""

    server_version = f"postmortem-miner/{__version__}"
    state: AppState

    def log_message(self, _format: str, *args: Any) -> None:
        # One line per request, without the default timestamp noise. The stdlib passes
        # (format, method-line, status, size); the status is the only part worth a line.
        print(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else '?'}")

    # -- helpers ----------------------------------------------------------------

    def _current_user(self) -> str | None:
        token = cookie_value(self.headers.get("Cookie"), SESSION_COOKIE)
        return read_session(self.state.secret, token)

    def _send_json(self, status: HTTPStatus, payload: Any, session: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if session is not None:
            self._send_session_cookie(session)
        self._send_hardening_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_session_cookie(self, session: str) -> None:
        if session:
            cookie = (
                f"{SESSION_COOKIE}={session}; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age={SESSION_TTL_SECONDS}"
            )
        else:
            cookie = f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
        self.send_header("Set-Cookie", cookie)

    def _send_hardening_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            return {}
        try:
            parsed = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    # -- verbs ------------------------------------------------------------------

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            status, payload = handle_get(self.state, path, self._current_user())
            self._send_json(status, payload)
            return

        resolved = static_file(path)
        if resolved is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        target, content_type = resolved
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._send_hardening_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        status, payload, session = handle_post(
            self.state, path, self._read_body(), self._current_user()
        )
        self._send_json(status, payload, session)


def make_server(state: AppState, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"state": state})
    return ThreadingHTTPServer((host, port), handler)


def serve(
    corpus: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    threshold: float = DEFAULT_THRESHOLD,
) -> int:  # pragma: no cover - blocking loop, exercised by the container health check
    state = build_state(corpus, threshold=threshold)
    summary = summary_payload(state)
    httpd = make_server(state, host, port)
    print(
        f"postmortem-miner {__version__} on http://{host}:{port}  "
        f"({summary['incidents']} incidents, {summary['patterns']} patterns, "
        f"user {state.credentials.user})"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        httpd.server_close()
    return 0
