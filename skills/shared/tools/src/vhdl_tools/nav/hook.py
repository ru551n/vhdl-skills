"""Claude Code hooks that put the VHDL index in front of large files.

``PreToolUse`` on ``Read``: a full read (no offset and no limit, or a limit
covering most of what a Read returns) of a VHDL file with at least
``VHDL_NAV_INDEX_MIN_LINES`` lines (default 2000, the most a Read returns:
below that, reading once and answering from context measured cheaper; 0
turns the hooks off) is
denied, and the reason Claude sees is the file's ``vhdl-tools nav index`` plus
the source of any regions the user's last message names.

``UserPromptSubmit``: when a message names such a file, its index (and the
regions the message names) is attached before Claude starts, so its first
read can already be a range.

Anything unexpected allows the read or attaches nothing: these hooks must
never be the reason a file cannot be read. Run as ``python -m
vhdl_tools.nav.hook`` (see ``skills/shared/bin/vhdl-read-hook``).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from vhdl_tools.nav import NavError
from vhdl_tools.nav.index import FileIndex, excerpt
from vhdl_tools.nav.server import file_index

#: Lines a Claude Code Read returns at most without a limit.
READ_LINE_CAP = 2000
MIN_LINES_ENV = "VHDL_NAV_INDEX_MIN_LINES"
#: Measured: below this, reading the file once and answering from context is
#: cheaper than any index, so the hooks only act where a Read truncates anyway.
DEFAULT_MIN_LINES = READ_LINE_CAP
#: Seconds the index may take; past that the Read is allowed. Well under
#: Claude Code's 60 s hook timeout, so the hook always decides for itself.
TIMEOUT_ENV = "VHDL_NAV_HOOK_TIMEOUT"
DEFAULT_TIMEOUT = 10.0
VHDL_SUFFIXES = frozenset({".vhd", ".vhdl"})
#: A limit covering this share of what a Read can return, without an offset,
#: is a full read.
NEAR_WHOLE = 0.8
MAX_PROMPT_FILES = 3
#: Characters attached to one prompt at most.
PROMPT_CONTEXT_CAP = 20_000
#: Bytes of the transcript read from its end to find the last user message.
TRANSCRIPT_TAIL = 1_000_000

_VHDL_PATH = re.compile(
    r"""(?:^|(?<=[\s'"`(<\[]))([^\s'"`()<>\[\]]+\.vhdl?)(?=$|[\s'"`)>\],.;:!?])""", re.IGNORECASE
)


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


def _line_count(path: Path) -> int:
    with path.open(encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def _useful_index(path: Path) -> FileIndex | None:
    """The index, or None when it cannot be built or would not help: no design
    units (vhdl_ls could not parse the file, e.g. mid-edit), or not much
    smaller than the file."""
    try:
        index = file_index(path, timeout=hook_timeout())
    except NavError:
        return None
    if not any(not line.startswith(("context ", "Note:")) for line in index.text.splitlines()[1:]):
        return None
    if len(index.text) * 2 > path.stat().st_size:
        return None
    return index


def _with_excerpt(index: FileIndex, request: str) -> str:
    quoted = excerpt(request, index.regions, index.lines)
    return f"{index.text}\n\n{quoted}" if quoted else index.text


def last_user_prompt(transcript: str | None) -> str:
    """The text of the last message the user typed (not a tool result)."""
    if not transcript:
        return ""
    try:
        with open(transcript, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - TRANSCRIPT_TAIL))
            data = handle.read().decode("utf-8", "replace")
    except OSError:
        return ""
    for line in reversed(data.splitlines()):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "user":
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
            if texts:
                return "\n".join(texts)
    return ""


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """The PreToolUse output that denies this Read, or None to allow it."""
    if event.get("tool_name") != "Read":
        return None
    tool_input = event.get("tool_input") or {}
    path = Path(str(tool_input.get("file_path") or ""))
    if path.suffix.lower() not in VHDL_SUFFIXES or not path.is_file():
        return None
    threshold = min_lines()
    if threshold <= 0:
        return None
    lines = _line_count(path)
    if lines < threshold:
        return None
    offset, limit = tool_input.get("offset"), tool_input.get("limit")
    if offset is not None or (limit is not None and limit < NEAR_WHOLE * min(lines, READ_LINE_CAP)):
        return None  # a range; offset=1 with a full limit is the deliberate whole read
    index = _useful_index(path)
    if index is None:
        return None
    reason = (
        f"{path} has {lines} lines, so the vhdl-tools nav hook shows its index "
        "instead of the full text. Read the ranges you need with offset and limit "
        "(a range [a-b] is offset=a, limit=b-a+1). To read the whole file anyway, "
        f"use offset=1, limit={lines}.\n\n"
        + _with_excerpt(index, last_user_prompt(event.get("transcript_path")))
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def prompt_context(event: dict[str, Any]) -> dict[str, Any] | None:
    """The UserPromptSubmit output attaching the index of large VHDL files the
    message names, or None."""
    threshold = min_lines()
    if threshold <= 0:
        return None
    prompt = str(event.get("prompt") or "")
    cwd = Path(str(event.get("cwd") or "."))
    paths: list[Path] = []
    for match in _VHDL_PATH.finditer(prompt):
        path = Path(match.group(1)).expanduser()
        path = (path if path.is_absolute() else cwd / path).resolve()
        if path.is_file() and path not in paths:
            paths.append(path)
    blocks: list[str] = []
    used = 0
    for path in paths[:MAX_PROMPT_FILES]:
        lines = _line_count(path)
        if lines < threshold:
            continue
        index = _useful_index(path)
        if index is None:
            continue
        block = (
            f"vhdl-tools nav index of {path} ({lines} lines), attached because the "
            "message names it. Read only the ranges you need with offset and limit.\n\n"
            + _with_excerpt(index, prompt)
        )
        if used + len(block) > PROMPT_CONTEXT_CAP:
            break
        blocks.append(block)
        used += len(block)
    if not blocks:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n\n".join(blocks),
        }
    }


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if event.get("hook_event_name") == "UserPromptSubmit":
            output = prompt_context(event)
        else:
            output = decide(event)
    except Exception:  # a broken hook must never block a read or a prompt
        output = None
    if output is not None:
        json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
