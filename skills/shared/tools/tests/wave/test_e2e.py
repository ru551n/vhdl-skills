"""End-to-end tests: the real CLI process (python -m vhdl_tools wave ...).

Walks every wave command the way an agent would call it from a shell.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXPECTED_COMMANDS = {
    "open",
    "search",
    "values",
    "value-at",
    "analyze",
    "latency",
    "find",
    "plot",
}


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "vhdl_tools", "wave", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _text(*args: str) -> str:
    proc = _cli(*args)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


class TestE2E:
    def test_full_roundtrip(self, all_types_path: Path, tmp_path: Path) -> None:
        file = str(all_types_path)
        help_text = _cli("--help").stdout
        for command in EXPECTED_COMMANDS:
            assert command in help_text

        out = _text("open", "--file", file)
        assert "duration:  995ns" in out
        assert "timescale: 1fs per tick" in out

        out = _text("search", "--file", file, "--pattern", "clk")
        assert "tb_wave.clk" in out

        out = _text(
            "values",
            "--file",
            file,
            "--signal",
            "clk",
            "--start",
            "0ns",
            "--end",
            "20ns",
            "--max-changes",
            "10",
        )
        assert "5ns   1" in out

        out = _text(
            "value-at", "--file", file, "--time", "12ns", "--signals", "clk", "state"
        )
        assert "= 0" in out  # clk is low at 12ns (high 5ns -> 10ns)
        assert '= "run"' in out

        out = _text("analyze", "--file", file, "--signal", "clk")
        assert "period:   10ns" in out
        assert "frequency: 100MHz" in out

        out = _text("find", "--file", file, "--signal", "state", "--value", "run")
        assert "matches:  33" in out

        out = _text(
            "latency",
            "--json-input",
            '{"file": "%s", "a": "clk", "b": "state", "edge": "any"}' % file,
            "--end",
            "100ns",
        )
        assert "pairs:    20" in out

        png = tmp_path / "p.png"
        out = _text(
            "plot", "--file", file, "--signals", "clk", "state", "--out", str(png)
        )
        assert f"image:    {png}" in out
        assert png.read_bytes().startswith(b"\x89PNG")

    def test_error_exits_nonzero(self) -> None:
        proc = _cli("open", "--file", "/nonexistent/x.fst")
        assert proc.returncode == 1
        assert "not found" in proc.stdout
