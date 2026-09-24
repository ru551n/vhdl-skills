"""Tests for the peeper_* tools (called directly)."""

from __future__ import annotations

from pathlib import Path

from vhdl_tools.wave.server import peeper_open, peeper_search, tools


class TestPeeperOpen:
    def test_output(self, all_types_path: Path) -> None:
        out = peeper_open(str(all_types_path))
        assert f"file:      {all_types_path}" in out
        assert "format:    FST" in out
        assert "nvc" in out
        assert "timescale: 1fs per tick" in out
        assert "duration:  995ns" in out
        assert "signals:   7" in out

    def test_bench_duration(self, bench_path: Path) -> None:
        out = peeper_open(str(bench_path))
        assert "duration:  2ms" in out

    def test_missing_file(self) -> None:
        assert "not found" in peeper_open("/nonexistent/x.fst")

    def test_unsupported_or_corrupt_file(self, tmp_path: Path) -> None:
        # Any tool opening a non-VCD/FST/GHW (or corrupt) file must return
        # a clean error string instead of an unhandled RuntimeError.
        bad = tmp_path / "not_a_waveform.fst"
        bad.write_text("this is definitely not a waveform file")
        out = peeper_open(str(bad))
        assert "could not be opened" in out


class TestPeeperSearch:
    def test_lists_all(self, all_types_path: Path) -> None:
        out = peeper_search(str(all_types_path))
        assert "signals: 7" in out
        assert "tb_wave.clk" in out
        real_line = next(line for line in out.splitlines() if "real_sig" in line)
        assert "real" in real_line

    def test_pattern_case_insensitive(self, all_types_path: Path) -> None:
        out = peeper_search(str(all_types_path), pattern="STATE")
        assert "signals: 1" in out
        assert "tb_wave.state" in out

    def test_pattern_no_match(self, all_types_path: Path) -> None:
        out = peeper_search(str(all_types_path), pattern="zzz")
        assert "signals: 0" in out
        assert "no signal name contains 'zzz'" in out

    def test_limit(self, all_types_path: Path) -> None:
        out = peeper_search(str(all_types_path), limit=2)
        assert "signals: 7" in out
        assert "showing 2" in out
        assert sum(line.startswith("  tb_") for line in out.splitlines()) == 2

    def test_missing_file(self) -> None:
        assert "not found" in peeper_search("/nonexistent/x.fst")

    def test_unsupported_or_corrupt_file(self, tmp_path: Path) -> None:
        # Every tool opens the file via the same _open() helper, so this
        # clean error isn't specific to peeper_open.
        bad = tmp_path / "not_a_waveform.vcd"
        bad.write_text("garbage")
        assert "could not be opened" in peeper_search(str(bad))


class TestServer:
    def test_tools_registered(self) -> None:
        assert {"peeper_open", "peeper_search"} <= set(tools.tools)

    def test_instructions_mention_open_first(self) -> None:
        assert "vhdl-tools wave open" in tools.instructions


class TestScopeSummary:
    """`wave open` shows the design, not every package a testbench pulls in."""

    GHDL = [
        "standard", "textio", "std_logic_1164", "numeric_std", "check_pkg",
        "run_pkg", "logger_pkg", "tb_strobe_gen.dut", "tb_strobe_gen",
    ]
    NVC = ["tb_strobe_gen.dut", "tb_strobe_gen", "vunit_lib.run_pkg", "vunit_lib.check_pkg"]

    def test_ghdl_packages_are_counted_not_listed(self) -> None:
        from vhdl_tools.wave.server import scope_summary

        out = scope_summary(self.GHDL)
        assert out.startswith("9: tb_strobe_gen, tb_strobe_gen.dut")
        assert "7 package and library scopes not listed" in out
        assert "logger_pkg" not in out

    def test_nvc_library_scopes_are_counted_not_listed(self) -> None:
        from vhdl_tools.wave.server import scope_summary

        out = scope_summary(self.NVC)
        assert out.startswith("4: tb_strobe_gen, tb_strobe_gen.dut")
        assert "vunit_lib" not in out.split(" (")[0]
        assert "2 package and library scopes not listed" in out

    def test_without_a_design_tree_the_names_are_listed_up_to_a_limit(self) -> None:
        from vhdl_tools.wave.server import scope_summary

        names = [f"s{i}" for i in range(25)]
        out = scope_summary(names)
        assert out.startswith("25: s0, s1")
        assert "s19" in out and "s20" not in out
        assert "5 more not listed" in out

    def test_a_small_flat_file_lists_everything(self) -> None:
        from vhdl_tools.wave.server import scope_summary

        assert scope_summary(["tb_wave"]) == "1: tb_wave"
