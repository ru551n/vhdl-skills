"""The vivado_* tools: query a built design (.dcp) through a persistent Vivado.

Every call names its checkpoint; there is no "current design". The first call
for a checkpoint starts a background Vivado with it open, serving Tcl on a
localhost socket, and later calls from any process or agent reuse it. Each
checkpoint gets its own Vivado, so agents on different designs never see each
other's. A rebuilt checkpoint (new mtime) gets a fresh session. A session exits
after IDLE_S seconds without queries, or on ``vhdl-tools vivado stop``.

State per checkpoint lives in ``~/.cache/vhdl-tools/vivado/<hash>/``:
``state.json`` (port, token, process group), ``lock`` (held while a session is
checked or started, so concurrent first calls wait for one startup instead of
racing) and ``vivado.log``.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from pydantic import BaseModel, Field

from vhdl_tools.registry import ToolError, ToolRegistry

STATE_DIR = Path.home() / ".cache" / "vhdl-tools" / "vivado"
IDLE_S = 30 * 60
START_TIMEOUT_S = 30 * 60  # includes open_checkpoint, which is slow on big designs
MAX_LINES = 200

tools = ToolRegistry(
    "vivado",
    instructions=(
        "Every command names a checkpoint (.dcp). The first command for a checkpoint "
        "opens it in a background Vivado (seconds to minutes); later commands reuse it "
        "and answer in well under a second. Sessions exit after 30 idle minutes."
    ),
    error_prefixes=("Error: ",),
)

# Runs inside Vivado: opens the checkpoint, then serves requests "<token>\n<tcl script>".
# The reply is "OK"/"ERROR" on the first line, then whatever the script puts'ed, then its
# result. Requests are handled one at a time (Vivado's Tcl is single-threaded).
SERVER_TCL = r"""
lassign $argv ::port ::token ::idle_s ::dcp
open_checkpoint $::dcp
set ::last [clock seconds]

proc capture_puts {args} {
    set a $args
    set nl 1
    if {[lindex $a 0] eq "-nonewline"} { set nl 0; set a [lrange $a 1 end] }
    if {[llength $a] == 2 && [lindex $a 0] ni {stdout stderr}} { return [_real_puts {*}$args] }
    append ::out [lindex $a end]
    if {$nl} { append ::out "\n" }
    return
}

proc serve {chan addr port} {
    fconfigure $chan -blocking 1 -translation lf -encoding utf-8
    if {[gets $chan] ne $::token} { close $chan; return }
    set script [read $chan]
    set ::last [clock seconds]
    set ::out ""
    rename puts _real_puts
    rename capture_puts puts
    set rc [catch {uplevel #0 $script} res]
    rename puts capture_puts
    rename _real_puts puts
    puts $chan [expr {$rc == 1 ? "ERROR" : "OK"}]
    puts -nonewline $chan $::out
    if {$res ne ""} { puts $chan $res }
    close $chan
}

proc check_idle {} {
    if {[clock seconds] - $::last > $::idle_s} { exit }
    after 60000 check_idle
}

socket -server serve -myaddr 127.0.0.1 $::port
check_idle
vwait forever
"""


class SessionError(RuntimeError):
    """A session could not be found or started."""


def _request(state: dict, script: str) -> str:
    with socket.create_connection(("127.0.0.1", state["port"])) as s:
        s.sendall(f"{state['token']}\n{script}".encode())
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while data := s.recv(65536):
            chunks.append(data)
    return b"".join(chunks).decode()


def _alive(state: dict) -> bool:
    try:
        _request(state, "")
        return True
    except OSError:
        return False


def _kill(state: dict) -> None:
    try:
        os.killpg(state["pgid"], signal.SIGTERM)
    except ProcessLookupError:
        pass


def _vivado() -> str:
    exe = os.environ.get("TSFPGA_MCP_VIVADO", "").strip() or shutil.which("vivado")
    if not exe:
        raise SessionError("no vivado executable: set TSFPGA_MCP_VIVADO or add 'vivado' to PATH")
    return exe


def _session(dcp: Path) -> dict:
    """A live session for this checkpoint, started if needed."""
    if not dcp.is_file():
        raise SessionError(f"no such checkpoint: {dcp}")
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_dir = STATE_DIR / hashlib.sha1(str(dcp).encode()).hexdigest()[:12]
    run_dir.mkdir(mode=0o700, exist_ok=True)
    state_file = run_dir / "state.json"
    mtime = dcp.stat().st_mtime
    with open(run_dir / "lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(state_file.read_text())
        except (OSError, ValueError):
            state = None
        if state and state["mtime"] == mtime and _alive(state):
            return state
        if state:
            _kill(state)  # dead, or the checkpoint was rebuilt
        return _start(dcp, mtime, run_dir, state_file)


def _start(dcp: Path, mtime: float, run_dir: Path, state_file: Path) -> dict:
    tcl = run_dir / "server.tcl"
    tcl.write_text(SERVER_TCL)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # The socket runs arbitrary Tcl (and so shell commands): only holders of the token get in.
    token = secrets.token_hex(16)
    with open(run_dir / "vivado.log", "w") as log:
        p = subprocess.Popen(
            [_vivado(), "-mode", "batch", "-nojournal", "-nolog", "-notrace", "-source", str(tcl),
             "-tclargs", str(port), token, str(IDLE_S), str(dcp)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, cwd=run_dir)
    state = {"dcp": str(dcp), "mtime": mtime, "port": port, "token": token, "pgid": p.pid}
    fd = os.open(state_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    print(f"vhdl-tools: opening {dcp.name} in Vivado", file=sys.stderr, flush=True)
    deadline = time.time() + START_TIMEOUT_S
    while time.time() < deadline:
        if p.poll() is not None:
            raise SessionError(f"Vivado exited while opening {dcp}, see {run_dir / 'vivado.log'}")
        if _alive(state):
            return state
        time.sleep(1)
    _kill(state)
    raise SessionError(f"Vivado did not open {dcp} within {START_TIMEOUT_S} s")


def _query(dcp: str, script: str) -> tuple[bool, str]:
    reply = _request(_session(Path(dcp).expanduser().resolve()), script)
    status, _, body = reply.partition("\n")
    return status == "OK", body


def _format(ok: bool, body: str) -> str:
    lines = body.rstrip().splitlines()
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + [f"... {len(lines) - MAX_LINES} more lines cut; narrow the query."]
    text = "\n".join(lines)
    return text if ok else ToolError(f"Error: Tcl failed:\n{text}")


class TclInput(BaseModel):
    dcp: str = Field(description="Vivado checkpoint (.dcp) to query")
    script: str = Field(description="Tcl to run against the design; '-' reads it from stdin")


@tools.tool()
def vivado_tcl(input: TclInput) -> str:
    """Run Tcl against a checkpoint and print what it puts, then its result.

    Use -return_string on report_* commands. Output is cut at 200 lines: count
    first (llength), then filter by hierarchy or type."""
    script = sys.stdin.read() if input.script == "-" else input.script
    try:
        return _format(*_query(input.dcp, script))
    except SessionError as exc:
        return ToolError(f"Error: {exc}")


class HierarchyInput(BaseModel):
    dcp: str = Field(description="Vivado checkpoint (.dcp) to query")
    node: str = Field("", description="Hierarchical instance to start from (default: the top)")
    depth: int = Field(2, description="Levels of hierarchy below the node")


@tools.tool()
def vivado_hierarchy(input: HierarchyInput) -> str:
    """Instance tree with LUT, FF, SRL, RAMB and DSP counts per instance."""
    script = ""
    cells = ""
    if input.node:
        script = (f"set c [get_cells -quiet {{{input.node}}}]\n"
                  f'if {{$c eq ""}} {{error "no instance named {input.node}"}}\n')
        cells = "-cells $c "
    script += f"report_utilization -hierarchical -hierarchical_depth {input.depth} {cells}-return_string"
    try:
        ok, body = _query(input.dcp, script)
    except SessionError as exc:
        return ToolError(f"Error: {exc}")
    if ok and "+--" in body:
        body = body[body.find("+--"):]  # drop the report header
    return _format(ok, body)


class StopInput(BaseModel):
    dcp: str | None = Field(None, description="Checkpoint whose session to stop (default: all)")


@tools.tool()
def vivado_stop(input: StopInput) -> str:
    """Shut down the Vivado session for a checkpoint, or all sessions."""
    target = str(Path(input.dcp).expanduser().resolve()) if input.dcp else None
    stopped = 0
    for state_file in STATE_DIR.glob("*/state.json"):
        state = json.loads(state_file.read_text())
        if target in (None, state["dcp"]):
            _kill(state)
            state_file.unlink()
            stopped += 1
    return f"stopped {stopped} session(s)"
