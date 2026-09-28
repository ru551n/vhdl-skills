"""A minimal LSP client for vhdl_ls over stdio.

Each nav command starts vhdl_ls, asks its questions and stops it: a cold start
including analysis takes ~0.1 s even on ~900-file projects, so there is no
daemon and no cache.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from vhdl_tools.nav import NavError

DEFAULT_TIMEOUT = 30.0

#: Where vhdl_ls looks for its standard libraries by itself (vhdl_lang's
#: config.rs); relative entries are relative to the binary's directory.
INSTALLED_LIBRARY_DIRS = (
    "../vhdl_libraries",
    "../../vhdl_libraries",
    "/usr/lib/rust_hdl/vhdl_libraries",
    "/usr/local/lib/rust_hdl/vhdl_libraries",
    "../share/vhdl_libraries",
)

STD_LIBRARIES_HELP = (
    "No VHDL standard libraries (std, ieee) for vhdl_ls found. Searched "
    "$VHDL_LS_LIBRARIES, vhdl_ls's own install locations and "
    "~/.cache/speja/vhdl_libraries-*. Get them with:\n"
    "  git clone --depth 1 https://github.com/VHDL-LS/rust_hdl ~/.local/share/rust_hdl\n"
    "  export VHDL_LS_LIBRARIES=~/.local/share/rust_hdl/vhdl_libraries"
)


def find_vhdl_ls() -> Path:
    """``$VHDL_LS``, else ``vhdl_ls`` on PATH, else ``~/.cargo/bin/vhdl_ls``."""
    env = os.environ.get("VHDL_LS")
    if env:
        path = Path(env).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise NavError(f"$VHDL_LS={env} is not an executable file")
    for candidate in (shutil.which("vhdl_ls"), Path.home() / ".cargo" / "bin" / "vhdl_ls"):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return Path(candidate)
    raise NavError(
        "vhdl_ls not found (checked $VHDL_LS, PATH, ~/.cargo/bin). Install: cargo install vhdl_ls"
    )


def _version_key(path: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", path.name))


def find_std_libraries(vhdl_ls: Path) -> Path | None:
    """The directory to pass as ``-l`` (it holds the libraries' vhdl_ls.toml;
    vhdl_ls appends the file name itself), or None when vhdl_ls finds its own."""
    env = os.environ.get("VHDL_LS_LIBRARIES")
    if env:
        directory = Path(env).expanduser()
        if (directory / "vhdl_ls.toml").is_file():
            return directory
        raise NavError(f"$VHDL_LS_LIBRARIES={env} holds no vhdl_ls.toml")
    exe_dir = vhdl_ls.resolve().parent
    for location in INSTALLED_LIBRARY_DIRS:
        if (exe_dir / location / "vhdl_ls.toml").is_file():
            return None
    cache = Path.home() / ".cache" / "speja"
    for directory in sorted(cache.glob("vhdl_libraries-*"), key=_version_key, reverse=True):
        if (directory / "vhdl_ls.toml").is_file():
            return directory
    raise NavError(STD_LIBRARIES_HELP)


def vhdl_ls_command(vhdl_ls: Path, libraries: Path | None) -> list[str]:
    command = [str(vhdl_ls), "--silent", "--no-lint"]
    if libraries is not None:
        command += ["-l", str(libraries)]
    return command


class LspSession:
    """One language-server process for one command; ``timeout`` covers all of
    its requests together."""

    def __init__(self, root: Path, command: list[str], timeout: float = DEFAULT_TIMEOUT) -> None:
        self.root = root
        self._timeout = timeout
        self._deadline = time.monotonic() + timeout
        self._stderr = tempfile.TemporaryFile()
        try:
            self._proc = subprocess.Popen(
                command,
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
            )
        except OSError as exc:
            self._stderr.close()
            raise NavError(f"cannot start {command[0]}: {exc}") from exc
        self._inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()
        threading.Thread(target=self._read_loop, daemon=True).start()
        self._next_id = 0
        self._opened: set[Path] = set()
        try:
            self.request(
                "initialize",
                {
                    "processId": os.getpid(),
                    "rootUri": root.as_uri(),
                    "capabilities": {
                        "textDocument": {"documentSymbol": {"hierarchicalDocumentSymbolSupport": True}}
                    },
                },
            )
            self.notify("initialized", {})
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> LspSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _read_loop(self) -> None:
        stream = self._proc.stdout
        assert stream is not None
        while True:
            length = None
            while True:
                line = stream.readline()
                if not line:
                    self._inbox.put(None)
                    return
                if line in (b"\r\n", b"\n"):
                    break
                name, _, value = line.decode("ascii", "replace").partition(":")
                if name.strip().lower() == "content-length":
                    length = int(value)
            if length is not None:
                self._inbox.put(json.loads(stream.read(length)))

    def _send(self, message: dict[str, Any]) -> None:
        body = json.dumps(message).encode()
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            self._proc.stdin.flush()
        except OSError as exc:  # BrokenPipeError: the server is gone
            raise self._crashed(message.get("method", "a reply")) from exc

    def notify(self, method: str, params: Any) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: Any) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise NavError(f"vhdl_ls did not answer {method} within {self._timeout:g} s")
            try:
                message = self._inbox.get(timeout=remaining)
            except queue.Empty:
                continue
            if message is None:
                self._inbox.put(None)  # later calls see the exit too
                raise self._crashed(method)
            if "method" in message:  # a server request or notification
                if "id" in message:
                    self._send({"jsonrpc": "2.0", "id": message["id"], "result": None})
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise NavError(f"vhdl_ls {method} failed: {error.get('message', error)}")
            return message.get("result")

    def open(self, path: Path) -> None:
        """Tell the server about a file (once) before file-scoped requests."""
        if path in self._opened:
            return
        self._opened.add(path)
        self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": path.as_uri(),
                    "languageId": "vhdl",
                    "version": 1,
                    "text": path.read_text(encoding="utf-8", errors="replace"),
                }
            },
        )

    def _crashed(self, method: str) -> NavError:
        try:
            code: int | None = self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            code = None
        self._stderr.seek(0)
        tail = self._stderr.read().decode("utf-8", "replace").splitlines()[-20:]
        status = f"exited with code {code}" if code is not None else "closed its output"
        text = "\n".join(f"  {line}" for line in tail) or "  (nothing on stderr)"
        return NavError(f"vhdl_ls {status} during {method}. Last stderr lines:\n{text}")

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                self.notify("exit", None)
            except NavError:
                pass
            try:
                self._proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        self._stderr.close()
