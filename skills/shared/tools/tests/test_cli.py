"""CLI generation, input handling, exit codes and run locking."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from vhdl_tools import cli
from vhdl_tools.registry import Tool, ToolError, ToolRegistry, file_lock
from vhdl_tools.vunit import server as vunit_server
from vhdl_tools.vunit.config import Config


def test_every_tool_gets_a_command(capsys):
    for group, (module, prefix, _help) in cli.GROUPS.items():
        registry = __import__(module, fromlist=["tools"]).tools
        with pytest.raises(SystemExit):
            cli.main([group, "--help"])
        help_text = capsys.readouterr().out
        for name in registry.tools:
            assert name.removeprefix(prefix).replace("_", "-") in help_text


def test_options_from_model(capsys):
    with pytest.raises(SystemExit):
        cli.main(["vunit", "run-tests", "--help"])
    text = capsys.readouterr().out
    for flag in ("--test-patterns", "--num-threads", "--clean", "--no-clean",
                 "--waveform-format", "--json-input"):
        assert flag in text


def test_json_input_and_flags_override(monkeypatch, capsys):
    seen = {}
    registry = ToolRegistry("t", error_prefixes=("Error: ",))

    @registry.tool()
    def t_echo(a: str, b: int = 1, c: list[str] | None = None) -> str:
        seen.update(a=a, b=b, c=c)
        return "Error: nope" if a == "bad" else "fine"

    tool = registry.tools["t_echo"]
    assert cli.run_tool(registry, tool, {"a": "x", "b": "7", "c": ["p", "q"]}) == 0
    assert seen == {"a": "x", "b": 7, "c": ["p", "q"]}
    assert cli.run_tool(registry, tool, {"a": "bad"}) == 1
    assert cli.run_tool(registry, tool, {}) == 2  # missing required
    assert "fine" in capsys.readouterr().out


def test_tool_error_is_error():
    assert ToolRegistry("t").is_error(ToolError("anything"))
    assert not ToolRegistry("t").is_error("anything")


def test_lock_waits_and_says_so(tmp_path, capsys):
    tool = Tool(fn=lambda: None, lock=lambda: tmp_path / "sub" / "x.lock")
    order = []

    def holder():
        with file_lock(tool):
            order.append("first")
            time.sleep(0.5)

    # flock locks are per open file description, so a thread contends too.
    t = threading.Thread(target=holder)
    t.start()
    time.sleep(0.1)
    with file_lock(tool):
        order.append("second")
    t.join()
    assert order == ["first", "second"]
    assert "waiting" in capsys.readouterr().err


def test_elaborate_passes_flag(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "run.py").write_text(
        "import sys\n"
        "open('argv.txt', 'w').write(' '.join(sys.argv[1:]))\n"
        "x = sys.argv[sys.argv.index('-x') + 1]\n"
        "open(x, 'w').write('<testsuite tests=\"1\"><testcase classname=\"tb.t\" "
        "name=\"tb.t.a\" time=\"0.1\"/></testsuite>')\n"
    )
    monkeypatch.setattr(vunit_server, "_last_output_dir", None)
    monkeypatch.setattr(
        vunit_server,
        "_config",
        Config(
            project_dir=project,
            run_script=project / "run.py",
            python=sys.executable,
            simulator=None,
            output_dir=project / "vunit_out",
            timeout=30.0,
        ),
    )
    registry = vunit_server.tools
    code = cli.run_tool(registry, registry.tools["vunit_elaborate"], {})
    assert code == 0
    assert "--elaborate" in (project / "argv.txt").read_text()
    assert (project / ".vunit-mcp-cache" / "run.lock").exists()
    # The completed run's output dir survives into the next process.
    pointer = project / ".vunit-mcp-cache" / "last_output_dir"
    assert Path(pointer.read_text()) == project / "vunit_out"
