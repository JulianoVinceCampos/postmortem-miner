"""Command line interface.

    postmortem-miner mine corpus/ --out out/report.md --json out/analysis.json
    postmortem-miner classify corpus/ --signals saturation.pool.exhausted,store.lock.contention
    postmortem-miner signals

Exit codes: 0 success, 1 usage/runtime error. Nothing else, so it composes in CI.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from postmortem_miner import __version__, decision_tree, report, signals, webapp
from postmortem_miner.parser import parse_corpus
from postmortem_miner.patterns import DEFAULT_THRESHOLD


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="postmortem-miner",
        description="Turn a pile of postmortems into a triage decision tree.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    mine = sub.add_parser("mine", help="analyse a corpus of postmortems")
    mine.add_argument("corpus", type=Path, help="directory with postmortem markdown files")
    mine.add_argument("--out", type=Path, help="write the markdown report here")
    mine.add_argument("--json", type=Path, dest="json_out", help="write machine-readable output")
    mine.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Jaccard similarity to join two incidents (default {DEFAULT_THRESHOLD})",
    )
    mine.add_argument("--quiet", action="store_true", help="suppress the summary on stdout")

    classify = sub.add_parser("classify", help="classify a live incident against a corpus")
    classify.add_argument("corpus", type=Path)
    classify.add_argument(
        "--signals", required=True, help="comma-separated signal tokens observed right now"
    )
    classify.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)

    sub.add_parser("signals", help="list every signal token the extractor knows")

    serve = sub.add_parser("serve", help="serve the read-only dashboard over HTTP")
    serve.add_argument("corpus", type=Path)
    # Loopback by default: a tool that binds every interface the moment you try it is
    # a bad neighbour. The container overrides it explicitly.
    serve.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    serve.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="bind port (default $PORT or 8000)",
    )
    serve.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    return parser


def _analyse(corpus: Path, threshold: float) -> report.Analysis:
    started = time.perf_counter()
    incidents = parse_corpus(corpus)
    if not incidents:
        raise ValueError(f"no postmortem with recognisable signals found in {corpus}")
    elapsed_ms = (time.perf_counter() - started) * 1000
    return report.analyse(incidents, threshold=threshold, elapsed_ms=elapsed_ms)


def _cmd_mine(args: argparse.Namespace) -> int:
    analysis = _analyse(args.corpus, args.threshold)
    markdown = report.to_markdown(analysis)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(report.to_json(analysis), encoding="utf-8")

    if not args.quiet:
        if args.out or args.json_out:
            print(
                f"{len(analysis.patterns)} patterns explain "
                f"{analysis.coverage * 100:.0f}% of {len(analysis.incidents)} incidents "
                f"in {analysis.elapsed_ms:.0f} ms "
                f"(triage depth {decision_tree.depth(analysis.tree)})"
            )
            for target in (args.out, args.json_out):
                if target:
                    print(f"  wrote {target}")
        else:
            print(markdown)
    return 0


def _cmd_classify(args: argparse.Namespace) -> int:
    analysis = _analyse(args.corpus, args.threshold)
    observed = frozenset(token.strip() for token in args.signals.split(",") if token.strip())
    unknown = observed - set(signals.known_tokens())
    if unknown:
        print(f"warning: unknown tokens ignored: {', '.join(sorted(unknown))}", file=sys.stderr)
    print(decision_tree.classify(analysis.tree, observed))
    return 0


def _cmd_signals(_: argparse.Namespace) -> int:
    for token in signals.known_tokens():
        print(token)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    return webapp.serve(args.corpus, host=args.host, port=args.port, threshold=args.threshold)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {
        "mine": _cmd_mine,
        "classify": _cmd_classify,
        "signals": _cmd_signals,
        "serve": _cmd_serve,
    }
    try:
        return handlers[args.command](args)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
