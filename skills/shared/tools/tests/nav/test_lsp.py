"""LspSession against a stand-in server, and finding vhdl_ls and its libraries."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from vhdl_tools.nav import NavError
from vhdl_tools.nav.lsp import (
    STD_LIBRARIES_HELP,
    LspSession,
    find_std_libraries,
    find_vhdl_ls,
    vhdl_ls_command,
)

FAKE = Path(__file__).parent / "fake_lsp.py"


def _session(tmp_path: Path, mode: str, timeout: float = 10.0) -> LspSession:
    return LspSession(tmp_path, [sys.executable, str(FAKE), mode], timeout=timeout)


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def _libraries(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "vhdl_ls.toml").write_text("[libraries]\n")
    return directory


def test_request_round_trip(tmp_path):
    with _session(tmp_path, "echo") as session:
        result = session.request("workspace/symbol", {"query": "fifo"})
    assert result["method"] == "workspace/symbol"
    assert result["params"] == {"query": "fifo"}
    assert result["notifications"] == ["initialized"]


def test_open_sends_did_open_once(tmp_path):
    source = tmp_path / "a.vhd"
    source.write_text("entity a is end entity;\n")
    with _session(tmp_path, "echo") as session:
        session.open(source)
        session.open(source)
        result = session.request("x", {})
    assert result["notifications"].count("textDocument/didOpen") == 1


def test_server_requests_are_answered(tmp_path):
    with _session(tmp_path, "server_request") as session:
        result = session.request("workspace/symbol", {"query": ""})
    assert result["method"] == "workspace/symbol"


def test_error_reply(tmp_path):
    with _session(tmp_path, "error") as session, pytest.raises(NavError, match="no such method"):
        session.request("bogus", {})


def test_crash_reports_stderr_tail(tmp_path):
    with _session(tmp_path, "crash") as session, pytest.raises(NavError) as exc:
        session.request("workspace/symbol", {"query": ""})
    message = str(exc.value)
    assert "exited with code 101" in message
    assert "boom" in message


def test_timeout(tmp_path):
    start = time.monotonic()
    with _session(tmp_path, "hang", timeout=1.0) as session, pytest.raises(NavError, match="within 1 s"):
        session.request("workspace/symbol", {"query": ""})
    assert time.monotonic() - start < 10


def test_start_failure(tmp_path):
    with pytest.raises(NavError, match="cannot start"):
        LspSession(tmp_path, [str(tmp_path / "missing")])


def test_command():
    assert vhdl_ls_command(Path("/x/vhdl_ls"), None) == ["/x/vhdl_ls", "--silent", "--no-lint"]
    assert vhdl_ls_command(Path("/x/vhdl_ls"), Path("/libs")) == [
        "/x/vhdl_ls",
        "--silent",
        "--no-lint",
        "-l",
        "/libs",
    ]


def test_find_vhdl_ls_from_env(tmp_path, monkeypatch):
    exe = _executable(tmp_path / "bin" / "vhdl_ls")
    monkeypatch.setenv("VHDL_LS", str(exe))
    assert find_vhdl_ls() == exe


def test_find_vhdl_ls_bad_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VHDL_LS", str(tmp_path / "nope"))
    with pytest.raises(NavError, match="not an executable"):
        find_vhdl_ls()


def test_find_vhdl_ls_cargo_bin(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    exe = _executable(tmp_path / ".cargo" / "bin" / "vhdl_ls")
    assert find_vhdl_ls() == exe


def test_find_vhdl_ls_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(NavError, match="cargo install vhdl_ls"):
        find_vhdl_ls()


def test_std_libraries_env_first(tmp_path, monkeypatch):
    libs = _libraries(tmp_path / "libs")
    monkeypatch.setenv("VHDL_LS_LIBRARIES", str(libs))
    assert find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls")) == libs


def test_std_libraries_env_without_toml(tmp_path, monkeypatch):
    (tmp_path / "libs").mkdir()
    monkeypatch.setenv("VHDL_LS_LIBRARIES", str(tmp_path / "libs"))
    with pytest.raises(NavError, match="holds no vhdl_ls.toml"):
        find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls"))


def test_std_libraries_next_to_binary_need_no_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS_LIBRARIES", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _libraries(tmp_path / "vhdl_libraries")
    assert find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls")) is None


def test_std_libraries_speja_cache_highest_version(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS_LIBRARIES", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    cache = tmp_path / "home" / ".cache" / "speja"
    _libraries(cache / "vhdl_libraries-0.9.0")
    newest = _libraries(cache / "vhdl_libraries-0.14.6")
    assert find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls")) == newest


@pytest.mark.skipif(
    any(Path(p, "vhdl_ls.toml").is_file() for p in ("/usr/lib/rust_hdl/vhdl_libraries", "/usr/local/lib/rust_hdl/vhdl_libraries")),
    reason="this machine has system-wide vhdl_ls libraries",
)
def test_std_libraries_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS_LIBRARIES", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    with pytest.raises(NavError) as exc:
        find_std_libraries(_executable(tmp_path / "bin" / "vhdl_ls"))
    assert str(exc.value) == STD_LIBRARIES_HELP
    assert "VHDL_LS_LIBRARIES" in STD_LIBRARIES_HELP and "rust_hdl" in STD_LIBRARIES_HELP


def test_close_is_quick_when_exit_is_ignored(tmp_path):
    """vhdl_ls stops only after shutdown + exit; closing must not wait out a timeout."""
    session = _session(tmp_path, "lsp_server")
    session.request("x", {})
    start = time.monotonic()
    session.close()
    assert time.monotonic() - start < 0.5
