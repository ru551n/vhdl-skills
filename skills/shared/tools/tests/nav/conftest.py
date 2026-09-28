"""Run ``vhdl-tools nav`` commands against the fixture project."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from vhdl_tools import cli
from vhdl_tools.nav import NavError
from vhdl_tools.nav.lsp import find_std_libraries, find_vhdl_ls

FIXTURE = Path(__file__).parent / "fixture"

NavRunner = Callable[..., tuple[int, str]]


def _vhdl_ls_ready() -> bool:
    try:
        find_std_libraries(find_vhdl_ls())
    except NavError:
        return False
    return True


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE


@pytest.fixture
def fixture_copy(tmp_path) -> Path:
    target = tmp_path / "fixture"
    shutil.copytree(FIXTURE, target)
    return target


@pytest.fixture
def nav_cli(capsys) -> NavRunner:
    """``run("find", "--name", "x", config=...)`` -> (exit code, stdout).
    ``config=None`` leaves ``--config`` out."""

    def run(*args: str, config: Path | None = FIXTURE) -> tuple[int, str]:
        argv = ["nav", *args]
        if config is not None:
            argv += ["--config", str(config)]
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        return exc.value.code, capsys.readouterr().out

    return run


@pytest.fixture
def nav(nav_cli) -> NavRunner:
    """``nav_cli``, skipped when vhdl_ls or its standard libraries are missing."""
    if not _vhdl_ls_ready():
        pytest.skip("vhdl_ls or its standard libraries are not installed")
    return nav_cli
