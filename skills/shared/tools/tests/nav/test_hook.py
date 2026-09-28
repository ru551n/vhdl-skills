"""The Claude Code hooks: a Read of a large VHDL file gets the index instead,
and a prompt that names a large VHDL file gets its index attached."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from vhdl_tools.nav import NavError, hook
from vhdl_tools.nav.index import FileIndex, Region

INDEX = "big.vhd  500 lines\nentity e [1-500]"
LAUNCHER = Path(__file__).parents[3] / "bin" / "vhdl-read-hook"
HOOKS_JSON = Path(__file__).parents[5] / "hooks" / "hooks.json"
LINES = [f"-- line {n + 1}" for n in range(500)]
STATUS = Region("process status", "status", 220, 334)


def _event(path: Path, tool: str = "Read", transcript: Path | None = None, **extra: object) -> dict:
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": str(path), **extra},
    }
    if transcript is not None:
        event["transcript_path"] = str(transcript)
    return event


def _prompt(prompt: str, cwd: Path) -> dict:
    return {"hook_event_name": "UserPromptSubmit", "prompt": prompt, "cwd": str(cwd)}


def _vhdl(tmp_path: Path, lines: int, name: str = "big.vhd") -> Path:
    path = tmp_path / name
    path.write_text("-- line\n" * lines)
    return path


def _stub(monkeypatch, text: str = INDEX, found: list[Region] | None = None) -> dict:
    """Replace the real index; returns what the hook passed to it."""
    seen: dict = {}

    def fake(path, timeout):
        seen.update(path=path, timeout=timeout)
        return FileIndex(text, found or [], LINES)

    monkeypatch.setattr(hook, "file_index", fake)
    return seen


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.delenv(hook.MIN_LINES_ENV, raising=False)
    monkeypatch.delenv(hook.TIMEOUT_ENV, raising=False)


def _reason(decision: dict | None) -> str:
    assert decision is not None
    output = decision["hookSpecificOutput"]
    assert (output["hookEventName"], output["permissionDecision"]) == ("PreToolUse", "deny")
    return output["permissionDecisionReason"]


# --- Read hook -------------------------------------------------------------


def test_decide_denies_big_full_read(tmp_path, monkeypatch):
    _stub(monkeypatch)
    big = _vhdl(tmp_path, 500)
    reason = _reason(hook.decide(_event(big)))
    assert reason.startswith(f"{big} has 500 lines")
    assert "offset=1, limit=500" in reason
    assert reason.endswith("\n\n" + INDEX)


def test_decide_threshold_is_inclusive(tmp_path, monkeypatch):
    _stub(monkeypatch)
    assert hook.DEFAULT_MIN_LINES == 400
    assert hook.decide(_event(_vhdl(tmp_path, 399, "a.vhd"))) is None
    assert hook.decide(_event(_vhdl(tmp_path, 400, "b.vhdl"))) is not None


def test_decide_allows_ranged_reads(tmp_path, monkeypatch):
    _stub(monkeypatch)
    big = _vhdl(tmp_path, 500)
    assert hook.decide(_event(big, offset=1)) is None
    assert hook.decide(_event(big, limit=50)) is None
    assert hook.decide(_event(big, offset=1, limit=500)) is None  # the deliberate whole-file read
    assert hook.decide(_event(big, offset=100, limit=450)) is None


def test_decide_treats_a_near_whole_limit_as_a_full_read(tmp_path, monkeypatch):
    _stub(monkeypatch)
    big = _vhdl(tmp_path, 500)
    assert hook.decide(_event(big, limit=2000)) is not None
    assert hook.decide(_event(big, limit=400)) is not None  # 80%
    assert hook.decide(_event(big, limit=399)) is None


def test_decide_allows_other_files_and_tools(tmp_path, monkeypatch):
    _stub(monkeypatch)
    text = tmp_path / "notes.txt"
    text.write_text("x\n" * 900)
    assert hook.decide(_event(text)) is None
    assert hook.decide(_event(_vhdl(tmp_path, 500), tool="Edit")) is None
    assert hook.decide(_event(tmp_path / "missing.vhd")) is None
    assert hook.decide({}) is None


def test_env_threshold(tmp_path, monkeypatch):
    _stub(monkeypatch)
    monkeypatch.setenv(hook.MIN_LINES_ENV, "10")
    assert hook.decide(_event(_vhdl(tmp_path, 20))) is not None
    monkeypatch.setenv(hook.MIN_LINES_ENV, "0")
    assert hook.decide(_event(_vhdl(tmp_path, 900, "huge.vhd"))) is None
    monkeypatch.setenv(hook.MIN_LINES_ENV, "junk")
    assert hook.min_lines() == hook.DEFAULT_MIN_LINES


def test_decide_allows_when_index_fails(tmp_path, monkeypatch):
    def fail(path, timeout):
        raise NavError("vhdl_ls not found")

    monkeypatch.setattr(hook, "file_index", fail)
    assert hook.decide(_event(_vhdl(tmp_path, 500))) is None


@pytest.mark.parametrize(
    "text",
    [
        "big.vhd  500 lines",
        "big.vhd  500 lines\ncontext [1-2]: ieee.std_logic_1164.all",
        "big.vhd  500 lines\nNote: no vhdl_ls.toml; this directory was read as one library, ...",
    ],
)
def test_decide_allows_when_nothing_parsed(tmp_path, monkeypatch, text):
    """vhdl_ls lists no units for a file it cannot parse: no reason to refuse."""
    _stub(monkeypatch, text)
    assert hook.decide(_event(_vhdl(tmp_path, 500))) is None


def test_decide_allows_when_index_is_not_much_smaller(tmp_path, monkeypatch):
    big = _vhdl(tmp_path, 500)  # 4000 bytes
    _stub(monkeypatch, INDEX + "\n" + "x" * 2100)
    assert hook.decide(_event(big)) is None


def test_decide_gives_the_index_the_hook_budget(tmp_path, monkeypatch):
    seen = _stub(monkeypatch)
    monkeypatch.setenv(hook.TIMEOUT_ENV, "3")
    hook.decide(_event(_vhdl(tmp_path, 500)))
    assert seen["timeout"] == 3.0
    monkeypatch.delenv(hook.TIMEOUT_ENV)
    assert hook.hook_timeout() == hook.DEFAULT_TIMEOUT < 60


def _transcript(tmp_path: Path, *entries: dict) -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    return path


def _user(content: object) -> dict:
    return {"type": "user", "message": {"role": "user", "content": content}}


def test_last_user_prompt_skips_tool_results(tmp_path):
    transcript = _transcript(
        tmp_path,
        _user("first question"),
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
        _user("What does the status process assign?"),
        _user([{"type": "tool_result", "tool_use_id": "x", "content": "..."}]),
    )
    assert hook.last_user_prompt(str(transcript)) == "What does the status process assign?"
    listed = _transcript(tmp_path, _user([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]))
    assert hook.last_user_prompt(str(listed)) == "a\nb"
    assert hook.last_user_prompt(str(tmp_path / "missing.jsonl")) == ""
    assert hook.last_user_prompt(None) == ""


def test_decide_adds_the_regions_the_request_names(tmp_path, monkeypatch):
    _stub(monkeypatch, found=[STATUS])
    transcript = _transcript(tmp_path, _user("Which signals does the process status assign?"))
    reason = _reason(hook.decide(_event(_vhdl(tmp_path, 500), transcript=transcript)))
    assert f"\n\n{INDEX}\n\nSource of the regions your request names" in reason
    assert "--- process status [221-335]" in reason
    assert "221  -- line 221" in reason


# --- Prompt hook -----------------------------------------------------------


def _context(result: dict | None) -> str:
    assert result is not None
    output = result["hookSpecificOutput"]
    assert output["hookEventName"] == "UserPromptSubmit"
    return output["additionalContext"]


def test_prompt_attaches_the_index_of_named_files(tmp_path, monkeypatch):
    seen = _stub(monkeypatch, found=[STATUS])
    big = _vhdl(tmp_path, 500)
    context = _context(hook.prompt_context(_prompt("In `big.vhd`, what does status do?", tmp_path)))
    assert seen["path"] == big.resolve()
    assert context.startswith(f"vhdl-tools nav index of {big.resolve()} (500 lines)")
    assert INDEX in context
    assert "--- process status [221-335]" in context


def test_prompt_absolute_path_and_punctuation(tmp_path, monkeypatch):
    _stub(monkeypatch)
    big = _vhdl(tmp_path, 500)
    assert hook.prompt_context(_prompt(f"Look at {big}.", tmp_path / "elsewhere")) is not None


def test_prompt_ignores_small_missing_and_absent_files(tmp_path, monkeypatch):
    _stub(monkeypatch)
    _vhdl(tmp_path, 100, "small.vhd")
    assert hook.prompt_context(_prompt("see small.vhd", tmp_path)) is None
    assert hook.prompt_context(_prompt("see gone.vhd", tmp_path)) is None
    assert hook.prompt_context(_prompt("no files here", tmp_path)) is None
    monkeypatch.setenv(hook.MIN_LINES_ENV, "0")
    _vhdl(tmp_path, 500)
    assert hook.prompt_context(_prompt("see big.vhd", tmp_path)) is None


def test_prompt_takes_at_most_three_files_within_the_cap(tmp_path, monkeypatch):
    _stub(monkeypatch)
    for name in "abcd":
        _vhdl(tmp_path, 500, f"{name}.vhd")
    context = _context(hook.prompt_context(_prompt("a.vhd b.vhd c.vhd d.vhd", tmp_path)))
    assert context.count("vhdl-tools nav index of") == 3
    for name in "ab":  # big enough that a ~20 KB index is still under half the file
        (tmp_path / f"{name}.vhd").write_text(("-- " + "x" * 100 + "\n") * 500)
    _stub(monkeypatch, INDEX + "\n" + "y" * (hook.PROMPT_CONTEXT_CAP - 1000))
    context = _context(hook.prompt_context(_prompt("a.vhd b.vhd", tmp_path)))
    assert context.count("vhdl-tools nav index of") == 1


def test_prompt_allows_when_index_fails(tmp_path, monkeypatch):
    def fail(path, timeout):
        raise NavError("no vhdl_ls")

    monkeypatch.setattr(hook, "file_index", fail)
    _vhdl(tmp_path, 500)
    assert hook.prompt_context(_prompt("see big.vhd", tmp_path)) is None


# --- main and the launcher -------------------------------------------------


def test_main_dispatches_both_events(tmp_path, monkeypatch, capsys):
    _stub(monkeypatch)
    big = _vhdl(tmp_path, 500)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_event(big))))
    hook.main()
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_prompt("see big.vhd", tmp_path))))
    hook.main()
    assert "additionalContext" in json.loads(capsys.readouterr().out)["hookSpecificOutput"]


def test_main_allows_on_bad_input(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    hook.main()
    assert capsys.readouterr().out == ""


def test_main_allows_when_the_hook_raises(tmp_path, monkeypatch, capsys):
    def boom(event: dict) -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr(hook, "decide", boom)
    monkeypatch.setattr(hook, "prompt_context", boom)
    for event in (_event(_vhdl(tmp_path, 500)), _prompt("see big.vhd", tmp_path)):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        hook.main()
        assert capsys.readouterr().out == ""


def _big_leaf(fixture_dir: Path, tmp_path: Path) -> Path:
    """The fixture's leaf.vhd plus 450 comment lines: a file worth indexing."""
    big = tmp_path / "leaf.vhd"
    big.write_text((fixture_dir / "lib_a" / "leaf.vhd").read_text() + "-- filler comment line\n" * 450)
    return big


def test_hook_with_real_index(nav, fixture_dir, tmp_path):
    """``nav`` only supplies the skip when vhdl_ls is missing."""
    leaf = _big_leaf(fixture_dir, tmp_path)
    reason = _reason(hook.decide(_event(leaf)))
    assert "entity leaf [6-15]" in reason
    assert "  process (clk) [20-26]" in reason


def test_hook_allows_a_file_that_does_not_parse(nav, tmp_path):
    broken = tmp_path / "broken.vhd"
    broken.write_text(
        "entity broken is\n  port (\n    clk : in bit;\n    q : out bit\n;\nend entity;\n"
        + "-- filler\n" * 450
    )
    assert hook.decide(_event(broken)) is None


def _launch(event: dict, env: dict | None = None, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(LAUNCHER)], input=json.dumps(event), capture_output=True, text=True, timeout=timeout, env=env
    )


needs_uv = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")


@needs_uv
def test_launcher_skips_non_vhdl_quickly(tmp_path):
    result = _launch(_event(tmp_path / "x.py"), timeout=5)
    assert (result.returncode, result.stdout) == (0, "")
    result = _launch(_prompt("a question about x.vhdx and nothing else", tmp_path), timeout=5)
    assert (result.returncode, result.stdout) == (0, "")


@needs_uv
def test_launcher_denies_big_vhdl(nav, fixture_dir, tmp_path):
    result = _launch(_event(_big_leaf(fixture_dir, tmp_path)))
    assert result.returncode == 0
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


@needs_uv
def test_launcher_attaches_index_to_a_prompt(nav, fixture_dir, tmp_path):
    _big_leaf(fixture_dir, tmp_path)
    result = _launch(_prompt("What does leaf.vhd do?", tmp_path))
    assert result.returncode == 0
    assert "entity leaf [6-15]" in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


@needs_uv
def test_launcher_allows_when_vhdl_ls_never_answers(tmp_path):
    stuck = tmp_path / "vhdl_ls"
    stuck.write_text("#!/bin/sh\nexec sleep 60\n")
    stuck.chmod(0o755)
    libraries = tmp_path / "libs"
    libraries.mkdir()
    (libraries / "vhdl_ls.toml").write_text("[libraries]\n")
    env = {**os.environ, "VHDL_LS": str(stuck), "VHDL_LS_LIBRARIES": str(libraries), hook.TIMEOUT_ENV: "1"}
    env.pop(hook.MIN_LINES_ENV, None)
    start = time.monotonic()
    result = _launch(_event(_vhdl(tmp_path, 500)), env=env, timeout=30)
    assert (result.returncode, result.stdout) == (0, "")
    assert time.monotonic() - start < 10


def test_hooks_json_registers_both_hooks():
    config = json.loads(HOOKS_JSON.read_text())["hooks"]
    command = '"${CLAUDE_PLUGIN_ROOT}/skills/shared/bin/vhdl-read-hook"'
    (read,) = config["PreToolUse"]
    assert read["matcher"] == "Read"
    assert [h["command"] for h in read["hooks"]] == [command]
    (prompt,) = config["UserPromptSubmit"]
    assert "matcher" not in prompt
    assert [h["command"] for h in prompt["hooks"]] == [command]
    assert LAUNCHER.is_file()
