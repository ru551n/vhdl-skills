"""The Claude Code Read hook: deny big full VHDL reads with the index, allow the rest."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vhdl_tools.nav import hook
from vhdl_tools.registry import ToolError

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
    monkeypatch.setattr(hook, "nav_index", lambda file: "INDEX")


def test_decide_denies_big_full_read(tmp_path, fake_index):
    big = _vhdl(tmp_path, 200)
    output = hook.decide(_event(big))["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert reason.startswith(f"{big} has 200 lines")
    assert "offset=1, limit=200" in reason
    assert reason.endswith("\n\nINDEX")


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
    monkeypatch.setattr(hook, "nav_index", lambda file: ToolError("Error: vhdl_ls not found"))
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


def test_hook_with_real_index(nav, fixture_dir, monkeypatch):
    """``nav`` only supplies the skip when vhdl_ls is missing."""
    monkeypatch.setenv(hook.MIN_LINES_ENV, "10")
    leaf = fixture_dir / "lib_a" / "leaf.vhd"
    reason = hook.decide(_event(leaf))["hookSpecificOutput"]["permissionDecisionReason"]
    assert "entity leaf [6-15]" in reason
    assert "  process [20-26]" in reason


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
def test_launcher_denies_big_vhdl(nav, fixture_dir, monkeypatch):
    monkeypatch.setenv(hook.MIN_LINES_ENV, "10")
    result = subprocess.run(
        [str(LAUNCHER)],
        input=json.dumps(_event(fixture_dir / "lib_a" / "leaf.vhd")),
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
