"""The Claude Code Read hook: deny big full VHDL reads with the index, allow the rest."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from vhdl_tools.nav import hook
from vhdl_tools.registry import ToolError

INDEX = "big.vhd  200 lines\nentity e [1-200]"
LAUNCHER = Path(__file__).parents[3] / "bin" / "vhdl-read-hook"
HOOKS_JSON = Path(__file__).parents[5] / "hooks" / "hooks.json"


def _event(path: Path, tool: str = "Read", **extra: object) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": str(path), **extra},
    }


def _vhdl(tmp_path: Path, lines: int, name: str = "big.vhd") -> Path:
    path = tmp_path / name
    path.write_text("-- line\n" * lines)
    return path


@pytest.fixture
def fake_index(monkeypatch):
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    monkeypatch.setattr(hook, "nav_index", lambda file, **_: INDEX)


def test_decide_denies_big_full_read(tmp_path, fake_index):
    big = _vhdl(tmp_path, 200)
    output = hook.decide(_event(big))["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert reason.startswith(f"{big} has 200 lines")
    assert "offset=1, limit=200" in reason
    assert reason.endswith("\n\n" + INDEX)


def test_decide_threshold_is_inclusive(tmp_path, fake_index):
    assert hook.decide(_event(_vhdl(tmp_path, 149, "a.vhd"))) is None
    assert hook.decide(_event(_vhdl(tmp_path, 150, "b.vhdl"))) is not None


def test_decide_allows_ranged_reads(tmp_path, fake_index):
    big = _vhdl(tmp_path, 200)
    assert hook.decide(_event(big, offset=1)) is None
    assert hook.decide(_event(big, limit=50)) is None


def test_decide_allows_other_files_and_tools(tmp_path, fake_index):
    text = tmp_path / "notes.txt"
    text.write_text("x\n" * 500)
    assert hook.decide(_event(text)) is None
    assert hook.decide(_event(_vhdl(tmp_path, 200), tool="Edit")) is None
    assert hook.decide(_event(tmp_path / "missing.vhd")) is None
    assert hook.decide({}) is None


def test_env_threshold(tmp_path, fake_index, monkeypatch):
    small = _vhdl(tmp_path, 20)
    monkeypatch.setenv(hook.MIN_LINES_ENV, "10")
    assert hook.decide(_event(small)) is not None
    monkeypatch.setenv(hook.MIN_LINES_ENV, "0")
    assert hook.decide(_event(_vhdl(tmp_path, 500, "huge.vhd"))) is None
    monkeypatch.setenv(hook.MIN_LINES_ENV, "junk")
    assert hook.min_lines() == hook.DEFAULT_MIN_LINES


def test_decide_allows_when_index_fails(tmp_path, monkeypatch):
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    monkeypatch.setattr(hook, "nav_index", lambda file, **_: ToolError("Error: vhdl_ls not found"))
    assert hook.decide(_event(_vhdl(tmp_path, 200))) is None


def test_main_prints_the_decision(tmp_path, fake_index, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_event(_vhdl(tmp_path, 200)))))
    hook.main()
    output = json.loads(capsys.readouterr().out)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_allows_on_bad_input(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    hook.main()
    assert capsys.readouterr().out == ""


def test_main_allows_when_decide_raises(tmp_path, monkeypatch, capsys):
    def boom(event: dict) -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr(hook, "decide", boom)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_event(_vhdl(tmp_path, 200)))))
    hook.main()
    assert capsys.readouterr().out == ""


def _big_leaf(fixture_dir: Path, tmp_path: Path) -> Path:
    """The fixture's leaf.vhd plus 200 comment lines: a file worth indexing."""
    big = tmp_path / "leaf.vhd"
    big.write_text((fixture_dir / "lib_a" / "leaf.vhd").read_text() + "-- filler comment line\n" * 200)
    return big


def test_hook_with_real_index(nav, fixture_dir, tmp_path, monkeypatch):
    """``nav`` only supplies the skip when vhdl_ls is missing."""
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    leaf = _big_leaf(fixture_dir, tmp_path)
    reason = hook.decide(_event(leaf))["hookSpecificOutput"]["permissionDecisionReason"]
    assert "entity leaf [6-15]" in reason
    assert "  process (clk) [20-26]" in reason


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_launcher_skips_non_vhdl_quickly(tmp_path):
    result = subprocess.run(
        [str(LAUNCHER)],
        input=json.dumps(_event(tmp_path / "x.py")),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert (result.returncode, result.stdout) == (0, "")


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_launcher_denies_big_vhdl(nav, fixture_dir, tmp_path, monkeypatch):
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    result = subprocess.run(
        [str(LAUNCHER)],
        input=json.dumps(_event(_big_leaf(fixture_dir, tmp_path))),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"


def test_hooks_json_points_at_the_launcher():
    config = json.loads(HOOKS_JSON.read_text())
    (entry,) = config["hooks"]["PreToolUse"]
    assert entry["matcher"] == "Read"
    (command,) = entry["hooks"]
    assert command["type"] == "command"
    assert command["command"] == '"${CLAUDE_PLUGIN_ROOT}/skills/shared/bin/vhdl-read-hook"'
    assert LAUNCHER.is_file()


def test_decide_allows_when_nothing_parsed(tmp_path, monkeypatch):
    """vhdl_ls lists no units for a file it cannot parse; an index of just
    the title line is no reason to refuse the Read."""
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    monkeypatch.setattr(hook, "nav_index", lambda file, **_: "big.vhd  200 lines")
    assert hook.decide(_event(_vhdl(tmp_path, 200))) is None
    monkeypatch.setattr(hook, "nav_index", lambda file, **_: "big.vhd  200 lines\ncontext [1-2]: ieee.std_logic_1164.all")
    assert hook.decide(_event(_vhdl(tmp_path, 200))) is None
    note_only = "big.vhd  200 lines\nNote: no vhdl_ls.toml; this directory was read as one library, ..."
    monkeypatch.setattr(hook, "nav_index", lambda file, **_: note_only)
    assert hook.decide(_event(_vhdl(tmp_path, 200))) is None


def test_decide_allows_when_index_is_not_much_smaller(tmp_path, monkeypatch):
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    big = _vhdl(tmp_path, 200)  # 1600 bytes
    monkeypatch.setattr(hook, "nav_index", lambda file, **_: INDEX + "\n" + "x" * 900)
    assert hook.decide(_event(big)) is None


def test_hook_allows_a_file_that_does_not_parse(nav, tmp_path, monkeypatch):
    """``nav`` only supplies the skip when vhdl_ls is missing."""
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    broken = tmp_path / "broken.vhd"
    broken.write_text(
        "entity broken is\n  port (\n    clk : in bit;\n    q : out bit\n;\nend entity;\n"
        + "-- filler\n" * 200
    )
    assert hook.decide(_event(broken)) is None


def test_decide_gives_the_index_the_hook_budget(tmp_path, monkeypatch):
    seen = {}

    def fake(file, timeout):
        seen["timeout"] = timeout
        return INDEX

    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    monkeypatch.setenv(hook.TIMEOUT_ENV, "3")
    monkeypatch.setattr(hook, "nav_index", fake)
    assert hook.decide(_event(_vhdl(tmp_path, 200))) is not None
    assert seen["timeout"] == 3.0
    monkeypatch.delenv(hook.TIMEOUT_ENV)
    assert hook.hook_timeout() == hook.DEFAULT_TIMEOUT < 60


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_launcher_allows_when_vhdl_ls_never_answers(tmp_path):
    stuck = tmp_path / "vhdl_ls"
    stuck.write_text("#!/bin/sh\nexec sleep 60\n")
    stuck.chmod(0o755)
    libraries = tmp_path / "libs"
    libraries.mkdir()
    (libraries / "vhdl_ls.toml").write_text("[libraries]\n")
    env = {**os.environ, "VHDL_LS": str(stuck), "VHDL_LS_LIBRARIES": str(libraries),
           hook.TIMEOUT_ENV: "1"}
    env.pop(hook.MIN_LINES_ENV, None)
    start = time.monotonic()
    result = subprocess.run(
        [str(LAUNCHER)],
        input=json.dumps(_event(_vhdl(tmp_path, 200))),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert (result.returncode, result.stdout) == (0, "")
    assert time.monotonic() - start < 10
