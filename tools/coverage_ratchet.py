#!/usr/bin/env python3
"""Coverage ratchet: the floor only ever goes up.

Reads the current line coverage from coverage.xml, compares it with `.coverage-floor`,
and either raises the floor or fails the build. A fixed threshold rots - people learn
to live just above it. A ratchet turns coverage into a one-way door.

    python3 tools/coverage_ratchet.py                 # check only
    python3 tools/coverage_ratchet.py --update        # raise the floor when it improved

Exit 0 ok, 1 regression, 2 usage error.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR_FILE = ROOT / ".coverage-floor"
REPORT = ROOT / "coverage.xml"
# Coverage measurement wobbles by fractions between runs and Python versions.
TOLERANCE = 0.5


def read_floor() -> float:
    if not FLOOR_FILE.exists():
        return 0.0
    raw = FLOOR_FILE.read_text(encoding="utf-8").strip()
    return float(raw) if raw else 0.0


def read_coverage(report: Path) -> float:
    # Parsing our own CI artefact, not untrusted input.
    root = ET.parse(report).getroot()
    rate = root.get("line-rate")
    if rate is None:
        raise ValueError("coverage.xml has no line-rate attribute")
    return float(rate) * 100


def main() -> int:
    parser = argparse.ArgumentParser(description="Coverage ratchet.")
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--update", action="store_true", help="raise the floor if it improved")
    args = parser.parse_args()

    if not args.report.exists():
        print(f"error: coverage report not found: {args.report}")
        return 2

    floor = read_floor()
    current = read_coverage(args.report)
    print(f"coverage: {current:.2f}%  floor: {floor:.2f}%")

    if current + TOLERANCE < floor:
        print(f"REGRESSION: coverage dropped {floor - current:.2f} points below the floor")
        return 1

    if current > floor + TOLERANCE:
        if args.update:
            FLOOR_FILE.write_text(f"{current:.2f}\n", encoding="utf-8")
            print(f"floor raised to {current:.2f}%")
        else:
            print(f"floor can be raised to {current:.2f}% (run with --update)")
    else:
        print("floor held")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
