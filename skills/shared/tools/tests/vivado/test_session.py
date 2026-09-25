"""Sessions, against a stand-in Vivado: tclsh running the real server script."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading

import pytest

from vhdl_tools.registry import ToolError
from vhdl_tools.vivado import server
from vhdl_tools.vivado.server import HierarchyInput, StopInput, TclInput

pytestmark = pytest.mark.skipif(shutil.which("tclsh") is None, reason="needs tclsh")

# Takes Vivado's command line, stubs the design commands the tests use, and
# sources the server script with the -tclargs as argv.
FAKE_VIVADO = """#!/usr/bin/env tclsh
set src [lindex $argv [expr {[lsearch $argv -source] + 1}]]
set argv [lrange $argv [expr {[lsearch $argv -tclargs] + 1}] end]
proc open_checkpoint {f} { set ::design [file rootname [file tail $f]] }
proc current_design {} { return $::design }
proc report_utilization {args} { return "header\\n+--+\\n| $::design |\\n+--+" }
proc get_cells {args} { return [expr {[lindex $args end] eq "u_ok" ? "u_ok" : ""}] }
source $src
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = tmp_path / "vivado"
    fake.write_text(FAKE_VIVADO)
    fake.chmod(0o755)
    monkeypatch.setenv("TSFPGA_MCP_VIVADO", str(fake))
    monkeypatch.setattr(server, "STATE_DIR", tmp_path / "state")
    started = []
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        started.append(args[0][-1])  # the checkpoint
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(server.subprocess, "Popen", popen)
    a, b = tmp_path / "top_a.dcp", tmp_path / "top_b.dcp"
    a.touch()
    b.touch()
    yield a, b, started
    server.vivado_stop(StopInput())


def test_agents_share_a_session_per_checkpoint(env):
    a, b, started = env
    results = {}

    def ask(key, dcp):
        results[key] = server.vivado_tcl(TclInput(dcp=str(dcp), script="current_design"))

    threads = [threading.Thread(target=ask, args=(i, a)) for i in range(3)]
    threads.append(threading.Thread(target=ask, args=("b", b)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert [results[i] for i in range(3)] == ["top_a"] * 3
    assert results["b"] == "top_b"
    assert sorted(started) == [str(a), str(b)]  # one Vivado per checkpoint, not per caller


def test_output_errors_and_truncation(env):
    a, _, _ = env
    tcl = lambda s: server.vivado_tcl(TclInput(dcp=str(a), script=s))  # noqa: E731
    assert tcl("puts a; puts -nonewline b; puts c") == "a\nbc"  # each line once
    err = tcl("error boom")
    assert isinstance(err, ToolError) and "boom" in err
    many = tcl("for {set i 0} {$i < 500} {incr i} {puts $i}")
    assert many.splitlines()[-1] == "... 300 more lines cut; narrow the query."


def test_hierarchy_drops_header_and_checks_node(env):
    a, _, _ = env
    assert server.vivado_hierarchy(HierarchyInput(dcp=str(a))).startswith("+--+\n| top_a |")
    assert server.vivado_hierarchy(HierarchyInput(dcp=str(a), node="u_ok")).startswith("+--+")
    missing = server.vivado_hierarchy(HierarchyInput(dcp=str(a), node="u_nope"))
    assert isinstance(missing, ToolError) and "no instance named u_nope" in missing


def test_rebuild_restarts_and_stop_is_per_checkpoint(env):
    a, b, started = env
    for dcp in (a, b):
        server.vivado_tcl(TclInput(dcp=str(dcp), script="current_design"))
    os.utime(a, (1, 1))  # a new build of a
    assert server.vivado_tcl(TclInput(dcp=str(a), script="current_design")) == "top_a"
    assert started.count(str(a)) == 2

    assert server.vivado_stop(StopInput(dcp=str(a))) == "stopped 1 session(s)"
    assert server.vivado_tcl(TclInput(dcp=str(b), script="current_design")) == "top_b"
    assert started.count(str(b)) == 1  # b was not touched


def test_missing_checkpoint(env, tmp_path):
    result = server.vivado_tcl(TclInput(dcp=str(tmp_path / "nope.dcp"), script="x"))
    assert isinstance(result, ToolError) and "no such checkpoint" in result
