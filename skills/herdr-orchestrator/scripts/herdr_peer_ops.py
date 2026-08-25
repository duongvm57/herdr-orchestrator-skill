#!/usr/bin/env python3
"""Stable Peer-facing interface for durable result handoff and escalation."""

from __future__ import annotations

import sys
from pathlib import Path

import herdr_orchestrator


OPERATIONS = {
    "handoff": "peer-handoff",
    "reopen": "peer-reopen",
    "dependency": "peer-dependency",
    "blocked": "peer-blocked",
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in OPERATIONS:
        available = ", ".join(OPERATIONS)
        print(f"usage: herdr_peer_ops.py <{available}> [options]", file=sys.stderr)
        return 2
    run_dir = Path(__file__).resolve().parent.parent
    return herdr_orchestrator.main(
        [OPERATIONS[sys.argv[1]], "--run-dir", str(run_dir), *sys.argv[2:]]
    )


if __name__ == "__main__":
    raise SystemExit(main())
