"""Tiny stand-in for the MCP server object the tool modules used to register on.

Each ``@tools.tool()`` function becomes a CLI subcommand (see ``cli.py``).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # ponytail: no fcntl on Windows -> runs are not serialized there
    fcntl = None  # type: ignore[assignment]


class ToolError(str):
    """A tool result that reports failure: same text, non-zero exit code."""


@dataclass
class Tool:
    fn: Callable[..., Any]
    lock: Callable[[], Path] | None = None


@dataclass
class ToolRegistry:
    name: str
    instructions: str = ""
    #: Result prefixes that mean "this call failed" (each server's own convention).
    error_prefixes: tuple[str, ...] = ()
    tools: dict[str, Tool] = field(default_factory=dict)

    def tool(
        self, *, lock: Callable[[], Path] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a tool. ``lock`` returns the lock file that serializes
        runs of this tool (compile/simulate/build) across processes."""

        def register(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[fn.__name__] = Tool(fn, lock)
            return fn

        return register

    def is_error(self, result: str) -> bool:
        return isinstance(result, ToolError) or result.startswith(self.error_prefixes)


@contextmanager
def file_lock(tool: Tool) -> Iterator[None]:
    """Hold the tool's lock file (if any) for the duration of the call.

    A lock path that cannot be resolved (e.g. a configuration error) means
    no lock: the tool itself then reports the problem.
    """
    path: Path | None = None
    if tool.lock is not None and fcntl is not None:
        try:
            path = tool.lock()
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            path = None
    if path is None:
        yield
        return
    with open(path, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                f"vhdl-tools: another run holds {path}; waiting for it to finish",
                file=sys.stderr,
                flush=True,
            )
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield
