"""Claude Code ``PreToolUse`` hook for ``Read``.

A full read (no offset, no limit) of a VHDL file with at least
``VHDL_NAV_INDEX_MIN_LINES`` lines (default 150; 0 turns the hook off) is
denied, and the reason Claude sees is the file's ``vhdl-tools nav index``, so
it reads only the ranges it needs. Anything unexpected allows the read: this
hook must never be the reason a file cannot be read.

Run as ``python -m vhdl_tools.nav.hook`` (see ``skills/shared/bin/vhdl-read-hook``).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from vhdl_tools.nav.server import nav_index
from vhdl_tools.registry import ToolError

MIN_LINES_ENV = "VHDL_NAV_INDEX_MIN_LINES"
DEFAULT_MIN_LINES = 150
#: Seconds the index may take; past that the Read is allowed. Well under
#: Claude Code's 60 s hook timeout, so the hook always decides for itself.
TIMEOUT_ENV = "VHDL_NAV_HOOK_TIMEOUT"
DEFAULT_TIMEOUT = 10.0
VHDL_SUFFIXES = frozenset({".vhd", ".vhdl"})


def min_lines() -> int:
    try:
        return int(os.environ.get(MIN_LINES_ENV, DEFAULT_MIN_LINES))
    except ValueError:
        return DEFAULT_MIN_LINES


def hook_timeout() -> float:
    try:
        return float(os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """The hook output that denies this Read, or None to allow it."""
    if event.get("tool_name") != "Read":
        return None
    tool_input = event.get("tool_input") or {}
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        return None
    path = Path(str(tool_input.get("file_path") or ""))
    if path.suffix.lower() not in VHDL_SUFFIXES or not path.is_file():
        return None
    threshold = min_lines()
    if threshold <= 0:
        return None
    with path.open(encoding="utf-8", errors="replace") as handle:
        lines = sum(1 for _ in handle)
    if lines < threshold:
        return None
    index = nav_index(str(path), timeout=hook_timeout())
    if isinstance(index, ToolError) or index.startswith("Error:"):
        return None
    # No design units means vhdl_ls could not parse the file (e.g. mid-edit),
    # and an index not much smaller than the file saves nothing: allow both.
    if not any(not line.startswith("context ") for line in index.splitlines()[1:]):
        return None
    if len(index) * 2 > path.stat().st_size:
        return None
    reason = (
        f"{path} has {lines} lines, so the vhdl-tools nav hook shows its index "
        "instead of the full text. Read the ranges you need with offset and limit "
        "(a range [a-b] is offset=a, limit=b-a+1). To read the whole file anyway, "
        f"use offset=1, limit={lines}.\n\n{index}"
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main() -> None:
    try:
        decision = decide(json.load(sys.stdin))
    except Exception:  # a broken hook must never block a read
        decision = None
    if decision is not None:
        json.dump(decision, sys.stdout)


if __name__ == "__main__":
    main()
