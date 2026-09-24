"""Tests for peeper_plot."""

from __future__ import annotations

from pathlib import Path

from vhdl_tools.registry import ToolError
from vhdl_tools.wave.server import peeper_plot

PNG_MAGIC = b"\x89PNG"


def _text(res: object) -> str:
    assert isinstance(res, str) and not isinstance(res, ToolError)
    return res


def _image(res: object) -> bytes:
    line = next(ln for ln in _text(res).splitlines() if ln.startswith("image:"))
    return Path(line.split("image:")[1].strip()).read_bytes()


class TestPeeperPlot:
    def test_returns_text_and_image(self, all_types_path: Path) -> None:
        res = peeper_plot(str(all_types_path), ["clk", "state", "real_sig"])
        assert _image(res).startswith(PNG_MAGIC)
        lines = _text(res).splitlines()
        assert lines[0] == f"file:     {all_types_path}"
        assert "window:   [0ns, 995ns)" in lines
        assert "traces:   3" in lines
        for name in ("tb_wave.clk", "tb_wave.state", "tb_wave.real_sig"):
            assert any(line.startswith(f"  {name}") for line in lines)

    def test_png_file_written(self, all_types_path: Path) -> None:
        res = peeper_plot(str(all_types_path), ["clk"])
        line = next(
            line for line in _text(res).splitlines() if line.startswith("image:")
        )
        path = Path(line.split("image:")[1].strip())
        assert path.exists()
        assert path.stat().st_size > 2000
        assert path.read_bytes().startswith(PNG_MAGIC)

    def test_lane_kinds(self, all_types_path: Path) -> None:
        text = _text(peeper_plot(str(all_types_path), ["clk", "state", "real_sig"]))
        clk_line = next(line for line in text.splitlines() if "tb_wave.clk" in line)
        assert "binary (199 changes)" in clk_line
        state_line = next(line for line in text.splitlines() if "tb_wave.state" in line)
        assert "text (" in state_line
        assert "x/z interval" in text
        real_line = next(line for line in text.splitlines() if "real_sig" in line)
        assert "numeric (99 changes" in real_line

    def test_decimated(self, bench_path: Path) -> None:
        text = _text(peeper_plot(str(bench_path), ["clk"]))
        assert "window:   [0ns, 2ms)" in text
        dec = next(line for line in text.splitlines() if "decimated" in line)
        pts = int(dec.split("to ")[1].split(" points")[0])
        assert pts <= 10_001

    def test_window(self, all_types_path: Path) -> None:
        text = _text(peeper_plot(str(all_types_path), ["clk"], start="10ns"))
        assert "window:   [10ns, 995ns)" in text

    def test_xz_shaded(self, all_types_path: Path) -> None:
        text = _text(peeper_plot(str(all_types_path), ["data"]))
        data_line = next(line for line in text.splitlines() if "tb_wave.data" in line)
        # data has 14 changes -> 14 held runs; it opens with an all-X span.
        assert "text (14 runs, 1 x/z interval)" in data_line

    def test_duplicate_signals_deduped(self, all_types_path: Path) -> None:
        text = _text(peeper_plot(str(all_types_path), ["clk", "tb_wave.clk"]))
        assert "traces:   1" in text
        assert text.count("tb_wave.clk") == 1

    def test_missing_file(self) -> None:
        assert "not found" in peeper_plot("/nonexistent/x.fst", ["clk"])

    def test_unknown_signal(self, all_types_path: Path) -> None:
        assert "no signal named 'nope'" in peeper_plot(str(all_types_path), ["nope"])

    def test_no_signals(self, all_types_path: Path) -> None:
        assert "no signals given" in peeper_plot(str(all_types_path), [])

    def test_empty_window(self, all_types_path: Path) -> None:
        out = peeper_plot(str(all_types_path), ["clk"], start="50ns", end="10ns")
        assert "window is empty" in out

    def test_start_beyond_file_end(self, all_types_path: Path) -> None:
        out = peeper_plot(str(all_types_path), ["clk"], start="2us")
        assert "beyond the end of the file" in out

    def test_out_path(self, all_types_path: Path, tmp_path: Path) -> None:
        out = tmp_path / "plot.png"
        text = _text(peeper_plot(str(all_types_path), ["clk"], out=str(out)))
        assert f"image:    {out}" in text
        assert out.read_bytes().startswith(PNG_MAGIC)


class TestLaneDrawing:
    """How a lane is drawn, not only what the summary says about it."""

    def _lane(self, path: Path, name: str, end: int):
        import matplotlib.pyplot as plt

        from vhdl_tools.wave.server import _STORE, _draw_plot_lane

        f = _STORE.open(str(path))
        info = f.resolve(name).signal
        fig, ax = plt.subplots()
        try:
            _draw_plot_lane(ax, f, info, 0.0, 0, end, 1.0, (0.0, 0.0, 1.0))
            return ax.get_lines()[-1]
        finally:
            plt.close(fig)

    def test_a_counter_is_a_staircase(self, all_types_path: Path) -> None:
        # A counter holds each value until its next change. Joining the change
        # points with straight lines drew ramps and slopes that never happened.
        line = self._lane(all_types_path, "cnt", 50_000_000)
        assert line.get_drawstyle() == "steps-post"

    def test_every_lane_holds_its_last_value_to_the_window_end(
        self, all_types_path: Path
    ) -> None:
        for name in ("cnt", "clk"):
            line = self._lane(all_types_path, name, 50_000_000)
            assert line.get_xdata()[-1] == 50_000_000, name


MIXED_VCD = """$timescale 1ns $end
$scope module tb $end
$var wire 1 ! valid $end
$var wire 4 " cnt [3:0] $end
$upscope $end
$enddefinitions $end
#0
x!
b0000 "
#10
0!
b0001 "
#20
1!
b0010 "
#30
0!
bxxxx "
#40
b0011 "
"""


class TestPlotForAnLlm:
    """What an agent needs from a picture: shape, exact values, unknowns, the
    failing time."""

    def _plot(self, tmp_path: Path, **kwargs: object) -> str:
        path = tmp_path / "mixed.vcd"
        path.write_text(MIXED_VCD)
        return _text(
            peeper_plot(
                str(path),
                ["valid", "cnt"],
                end="50ns",
                out=str(tmp_path / "p.png"),
                **kwargs,
            )
        )

    def test_unknowns_stay_on_the_signal_lane_in_red(self, tmp_path: Path) -> None:
        # A std_logic that is X for a while is still a binary lane, and a
        # counter that goes X is still a numeric lane: the unknown span is
        # drawn red on it rather than turning the lane into text.
        out = self._plot(tmp_path)
        valid = next(ln for ln in out.splitlines() if "tb.valid" in ln)
        cnt = next(ln for ln in out.splitlines() if "tb.cnt" in ln)
        assert "binary" in valid and "1 unknown interval in red" in valid
        assert "numeric" in cnt and "1 unknown interval in red" in cnt

    def test_numeric_steps_carry_their_values(self, tmp_path: Path) -> None:
        out = self._plot(tmp_path)
        cnt = next(ln for ln in out.splitlines() if "tb.cnt" in ln)
        assert "labels on 4 of 4 steps" in cnt
        assert "min 0, max 3" in cnt

    def test_a_mark_is_drawn_and_reported(self, tmp_path: Path) -> None:
        out = self._plot(tmp_path, mark=["35ns", "80ns"])
        assert "marks:    35ns" in out
        assert "80ns outside the window" in out

    def test_dense_numeric_lanes_drop_their_labels(self, bench_path: Path) -> None:
        # 200 changes in the window: far too many values to write on the steps.
        out = _text(peeper_plot(str(bench_path), ["tb_bench.cnt"], end="2us"))
        cnt = next(ln for ln in out.splitlines() if "tb_bench.cnt" in ln)
        assert "no labels: too dense" in cnt
