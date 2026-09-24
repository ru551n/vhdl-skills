"""The peeper_* waveform (VCD/FST) measurement tools.

The server is stateless from the caller's point of view: every tool takes
the waveform file path, and results never depend on a "current file".
The only server state is a small LRU of open files (see
:mod:`vhdl_tools.wave.store`) so repeated calls on the same file stay fast.
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from vhdl_tools.registry import ToolError, ToolRegistry

from vhdl_tools.wave.analyze import analyze, is_xz, rising_edges, value_runs
from vhdl_tools.wave.env import env_int
from vhdl_tools.wave.formatting import format_value, truncation_note
from vhdl_tools.wave.store import (
    AmbiguousSignal,
    FileStore,
    Resolution,
    SignalInfo,
    SignalNotFound,
    WaveformFile,
    WaveformOpenError,
)
from vhdl_tools.wave.timeutil import (
    TimeValueError,
    display_unit,
    format_ticks,
    parse_time,
)

#: Default cap on the signal list vhdl-tools wave search returns without a pattern.
MAX_SEARCH_RESULTS = env_int("MAX_SEARCH_RESULTS", "100")

#: Default cap on changes vhdl-tools wave values returns.
MAX_ROWS = env_int("MAX_ROWS", "1000")

#: Max plotted points per trace; denser change lists are decimated.
_MAX_PTS = 10_000

#: Max value labels drawn on a text lane (longest runs first).
_MAX_TEXT_LABELS = 24

#: Max run boundaries drawn on a text lane before striding.
_MAX_TEXT_RUNS_DRAWN = 2000
# Steps a numeric lane writes its value on; beyond this the lane is too dense to
# label and `values` is the way to read it.
_MAX_STEP_LABELS = 40
# Share of the window one character of a step label needs to be readable.
_LABEL_CHAR_SHARE = 0.008
_UNKNOWN_RE = re.compile(r"[01xzuwlh_-]+", re.IGNORECASE)


def _is_unknown(value: object) -> bool:
    """A bit pattern with X, U, Z, W or don't-care in it: a value the simulator
    does not know."""
    return (
        isinstance(value, str)
        and _UNKNOWN_RE.fullmatch(value) is not None
        and any(c not in "01_" for c in value)
    )


def _numbers_and_unknowns(values: np.ndarray, entering: object) -> bool:
    """Every value a number or an unknown bit pattern: a numeric lane with gaps,
    not a text lane. An enum or a string signal is not."""
    number = (int, float, np.integer, np.floating)
    return all(
        isinstance(v, number) or _is_unknown(v)
        for v in (entering, *values.tolist())
    )

#: Per-lane geometry for vhdl-tools wave plot.
_LANE_HEIGHT = 1.0
_LANE_GAP = 0.4

_STORE = FileStore()

tools = ToolRegistry(
    "vhdl_tools.wave",
    instructions=(
        "Measure VCD/FST waveform files: signal values, period/duty, latency, "
        "event search, and PNG plots. Every tool takes the waveform file "
        "path and opens it itself, so calling vhdl-tools wave open first is optional "
        "— it is just a quick way to learn a file's timescale and duration "
        "upfront, which frame every window you pass elsewhere. Signal "
        "names accept case-insensitive full names or unique suffixes "
        "('clk' matches tb.dut.clk). Times are human-readable '10ns' / "
        "'1.5us' or integer file ticks."
    ),
)


def _open(file: str) -> str | None:
    """Return a self-describing error, or None if *file* opened."""
    try:
        _STORE.open(file)
    except (FileNotFoundError, WaveformOpenError) as exc:
        return ToolError(str(exc))
    return None


_SCOPE_LIMIT = 20


def scope_summary(names: list[str], limit: int = _SCOPE_LIMIT) -> str:
    """The scope count and the scopes worth reading first.

    A VUnit testbench pulls in dozens of package scopes (check_pkg, logger_pkg,
    numeric_std, ...): GHDL writes each as a flat top-level scope, NVC under its
    library (vunit_lib.run_pkg). The design is the instance tree instead: a
    listed top-level scope with listed scopes below it (tb, tb.dut). That tree is
    shown and the rest counted. Without one, the names are listed up to `limit`.
    """
    listed = set(names)
    roots = sorted(
        n
        for n in names
        if "." not in n and any(m.startswith(n + ".") for m in listed)
    )
    design = sorted(n for n in names if n.split(".", 1)[0] in roots)
    shown = design if design else names
    head = shown[:limit]
    out = f"{len(names)}: {', '.join(head)}"
    notes = []
    if len(shown) > limit:
        notes.append(f"{len(shown) - limit} more not listed")
    if design and len(names) > len(design):
        hidden = len(names) - len(design)
        notes.append(f"{hidden} package and library scopes not listed")
    return out + (f" ({'; '.join(notes)})" if notes else "")


@tools.tool()
def peeper_open(file: str) -> str:
    """What is in this waveform file?

    Answers "what's in this waveform file? how long did the simulation run? what's
    the timescale?". Optional — every other peeper_* tool opens the file
    itself, so you never have to call this first — but it is a cheap way
    to learn a new file's timescale and duration upfront, which frame
    every window you pass elsewhere. Use vhdl-tools wave search to list the
    individual signals.
    """
    error = _open(file)
    if error is not None:
        return ToolError(error)
    f = _STORE.open(file)
    tps = f.ticks_per_second
    lines = [
        f"file:      {f.path}",
        f"format:    {f.wf.file_format}",
        f"writer:    {f.wf.version} ({f.wf.date})",
        f"timescale: {format_ticks(1, tps)} per tick",
        f"duration:  {format_ticks(f.duration(), tps)} (last change across "
        "sampled signals)",
        f"scopes:    {scope_summary(f.scope_names)}",
        f"signals:   {len(f.signals)} (vhdl-tools wave search lists them)",
    ]
    return "\n".join(lines)


@tools.tool()
def peeper_search(file: str, pattern: str = "", limit: int = MAX_SEARCH_RESULTS) -> str:
    """Which signals are in this waveform file?

    Answers "what signals does this waveform file contain? is there a signal named
    X?". Pass a case-insensitive substring of `pattern` to narrow the list
    on large designs. The names shown are what you pass to vhdl-tools wave values,
    vhdl-tools wave analyze, vhdl-tools wave latency, vhdl-tools wave find and vhdl-tools wave plot — full names
    or unique suffixes. Header-only: nothing is decoded, so this is fast
    even on big files.
    """
    error = _open(file)
    if error is not None:
        return ToolError(error)
    f = _STORE.open(file)
    pat = pattern.lower()
    matches = [s for s in f.signals if not pat or pat in s.full_name.lower()]
    total = len(matches)
    shown = matches[: max(limit, 1)]
    header = f"signals: {total}"
    if total > len(shown):
        header += f" (showing {len(shown)}; refine with pattern or raise limit)"
    lines = [f"file: {f.path}", header]
    for s in shown:
        tags = []
        if s.is_real:
            tags.append("real")
        if s.is_string:
            tags.append("string")
        if s.bitwidth is not None and s.bitwidth > 1:
            tags.append(f"{s.bitwidth}b")
        tag = f"  [{', '.join(tags)}]" if tags else ""
        lines.append(f"  {s.full_name}  {s.var_type}{tag}")
    if total == 0:
        lines.append(f"no signal name contains {pattern!r}")
    return "\n".join(lines)


@tools.tool()
def peeper_values(
    file: str,
    signal: str,
    start: str | int = "0",
    end: str | int | None = None,
    max_changes: int = MAX_ROWS,
) -> str:
    """What values did this signal have in this time window?

    Answers "what did <signal> do between A and B?". Times are
    human-readable ('10ns', '1.5us') or integer file ticks; the window
    is [start, end) — omit end to run to the signal's last change.
    Wide (>= 32 bit) values are shown in hex; X/Z samples and enum/
    string values are kept as-is. For statistics instead of a change
    list, use vhdl-tools wave analyze; for one time point, vhdl-tools wave value-at.
    """
    error = _open(file)
    if error is not None:
        return ToolError(error)
    f = _STORE.open(file)
    try:
        res = f.resolve(signal)
        start_t = _ticks(f, start)
        end_t = None if end is None else _ticks(f, end)
        if end_t is not None and end_t <= start_t:
            return ToolError(
                f"window is empty: end ({_tm(f, end_t)}) "
                f"must be after start ({_tm(f, start_t)})"
            )
        info = res.signal
        times, values = f.window(info.full_name, start_t, end_t)
    except (AmbiguousSignal, SignalNotFound, TimeValueError) as exc:
        return ToolError(str(exc))

    if end_t is not None:
        window_text = f"[{_tm(f, start_t)}, {_tm(f, end_t)})"
    else:
        window_text = f"[{_tm(f, start_t)}, end of file)"
    entering_value = _fmt_value(info, f.value_at(info.full_name, start_t))
    header = [
        f"file:     {f.path}",
        f"signal:   {info.full_name}" + (f"  (matched {signal!r})" if res.note else ""),
        f"window:   {window_text}",
        f"entering: {entering_value} (value at window start)",
    ]
    if len(times) == 0:
        held = f.value_at(info.full_name, start_t)
        header.append(
            f"no changes in this window — {info.full_name} held "
            f"{_fmt_value(info, held)} throughout"
        )
        return "\n".join(header)

    shown = min(len(times), max(max_changes, 1))
    header.append(
        f"changes:  {shown}"
        + (f" of {len(times)} (truncated)" if shown < len(times) else "")
    )
    col = max(len(_tm(f, int(t))) for t in times[:shown])
    lines = header + [
        f"  {_tm(f, int(t)).ljust(col)}  {_fmt_value(info, v)}"
        for t, v in zip(times[:shown], values[:shown], strict=True)
    ]
    if shown < len(times):
        lines.append(
            f"truncated after {shown} changes — narrow the window "
            "(start='...' / end='...') or raise max_changes; "
            "for statistics use vhdl-tools wave analyze"
        )
    return "\n".join(lines)


@tools.tool()
def peeper_value_at(file: str, time: str | int, signals: list[str]) -> str:
    """What were these signals at this exact time?

    Answers "what was <signal> at 10ns?" (batch: pass several signals in
    one call). Returns the value held at that instant (the last change
    at or before the time). Time is human-readable ('10ns') or integer
    file ticks. If the time is past the end of the file, the last
    recorded value is returned and flagged. For a whole window of
    changes, use vhdl-tools wave values.
    """
    error = _open(file)
    if error is not None:
        return ToolError(error)
    f = _STORE.open(file)
    if not signals:
        return ToolError("no signals given — pass at least one signal name")
    try:
        t = _ticks(f, time)
        duration = f.duration()
        rows = []
        for name in signals:
            res = f.resolve(name)
            val = f.value_at(res.signal.full_name, t)
            suffix = (
                f"  (beyond file end at {_tm(f, duration)} — last recorded value)"
                if t > duration
                else ""
            )
            note = f"  (matched {name!r})" if res.note else ""
            value_text = _fmt_value(res.signal, val)
            rows.append(f"  {res.signal.full_name}{note} = {value_text}{suffix}")
    except (AmbiguousSignal, SignalNotFound, TimeValueError) as exc:
        return ToolError(str(exc))
    return "\n".join([f"file: {f.path}", f"time: {_tm(f, t)}", *rows])


@tools.tool()
def peeper_sample(
    file: str,
    clock: str,
    signals: list[str],
    start: str | int = "0",
    end: str | int | None = None,
    max_rows: int = 100,
) -> str:
    """What did these signals hold at each rising edge of this clock?

    Answers "walk me through the cycles around the failure": one row per
    rising edge of `clock` in [start, end), one column per signal, each the
    value it had just before the edge, which is what a register clocked there
    samples. A signal that changes on the edge itself therefore shows its old
    value, as the hardware sees it. At most max_rows rows; narrow the window
    for more.
    """
    error = _open(file)
    if error is not None:
        return ToolError(error)
    f = _STORE.open(file)
    if not signals:
        return ToolError("no signals given — pass at least one signal name")
    try:
        start_t = _ticks(f, start)
        end_t = None if end is None else _ticks(f, end)
        win_end = end_t if end_t is not None else f.duration() + 1
        if win_end <= start_t:
            return ToolError(
                f"window is empty: end ({_tm(f, win_end)}) "
                f"must be after start ({_tm(f, start_t)})"
            )
        ci = f.resolve(clock).signal
        ct, cv = f.window(ci.full_name, start_t, win_end)
        if f.packed(ci.full_name).kind != "int" or np.any((cv < 0) | (cv > 1)):
            return ToolError(f"clock {ci.full_name} is not a binary signal")
        edges = rising_edges(ct, cv, int(f.value_at(ci.full_name, start_t)), start_t)
        infos = []
        for name in signals:
            info = f.resolve(name).signal
            if info not in infos:
                infos.append(info)
    except (AmbiguousSignal, SignalNotFound, TimeValueError) as exc:
        return ToolError(str(exc))
    lines = [
        f"file:     {f.path}",
        f"clock:    {ci.full_name}, {len(edges)} rising edges in"
        f" [{_tm(f, start_t)}, {_tm(f, win_end)})",
        "values:   each signal just before the edge, as a register samples it",
        "columns:  " + ", ".join(f"{i.leaf} = {i.full_name}" for i in infos),
        "",
    ]
    shown = edges[:max_rows]
    table = [["edge", *(i.leaf for i in infos)]]
    for e in shown:
        row = [_tm(f, int(e))]
        for info in infos:
            value = f.value_at(info.full_name, int(e) - 1) if e > 0 else None
            row.append("-" if value is None else _fmt_value(info, value))
        table.append(row)
    widths = [max(len(r[c]) for r in table) for c in range(len(table[0]))]
    for r in table:
        lines.append("  ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)))
    lines = [ln.rstrip() for ln in lines]
    if len(edges) > len(shown):
        lines.append(
            f"({truncation_note(len(shown), len(edges), 'edges; narrow the window')})"
        )
    return "\n".join(lines)


@tools.tool()
def peeper_analyze(
    file: str, signal: str, start: str | int = "0", end: str | int | None = None
) -> str:
    """How fast, how long, how much is this signal?

    Answers "what's the period / frequency / duty cycle of <signal>?",
    "how much time is <signal> in X/Z?", "what's the min/max/mean of this
    real?", "which values does <signal> take and how often?". This is the
    statistics tool: it summarizes a window instead of listing changes.
    Times are human-readable ('10ns') or integer ticks; the window is
    [start, end) — omit end to run to the signal's last change. For a raw
    change list use vhdl-tools wave values; for edge-to-edge timing between two
    signals use vhdl-tools wave latency.
    """
    error = _open(file)
    if error is not None:
        return ToolError(error)
    f = _STORE.open(file)
    try:
        res = f.resolve(signal)
        info = res.signal
        start_t = _ticks(f, start)
        end_t = None if end is None else _ticks(f, end)
        if end_t is not None and end_t <= start_t:
            return ToolError(
                f"window is empty: end ({_tm(f, end_t)}) "
                f"must be after start ({_tm(f, start_t)})"
            )
        packed = f.packed(info.full_name)
        times, values = f.window(info.full_name, start_t, end_t)
        # Effective end: explicit end, or the signal's last change.
        win_end = (
            end_t if end_t is not None else int(times[-1]) if len(times) else start_t
        )
        # Degenerate: with an open end and nothing (or only the value at
        # start_t) to measure, say so plainly.
        if end_t is None and win_end <= start_t:
            held = f.value_at(info.full_name, start_t)
            return (
                f"file:     {f.path}\n"
                f"signal:   {info.full_name}\n"
                f"window:   [{_tm(f, start_t)}, end of file)\n"
                f"no changes after {_tm(f, start_t)} — {info.full_name}"
                f" held {_fmt_value(info, held)} for the rest of the file"
            )
        entering = f.value_at(info.full_name, start_t)
        body = analyze(
            times,
            values,
            packed.kind,
            entering,
            start_t,
            win_end,
            info.bitwidth,
            info.is_1bit,
            info.is_bit_vector,
            info.is_real,
            f.ticks_per_second,
            lambda t: _tm(f, t),
        )
    except (AmbiguousSignal, SignalNotFound, TimeValueError) as exc:
        return ToolError(str(exc))
    header = [
        f"file:     {f.path}",
        f"signal:   {info.full_name}" + (f"  (matched {signal!r})" if res.note else ""),
        f"window:   [{_tm(f, start_t)}, {_tm(f, win_end)})",
    ]
    return "\n".join([*header, body])


@tools.tool()
def peeper_latency(
    file: str,
    a: str,
    b: str,
    edge: Literal["rise", "any"] = "rise",
    start: str | int = "0",
    end: str | int | None = None,
) -> str:
    """How long from A's edge to B's edge?

    Answers "what's the propagation delay from <a> to <b>?", "how long
    after <a>'s rising edge does <b> rise?". For every edge of A in
    [start, end) it finds the first edge of B at or after that moment and
    reports min/max/mean/p50/stddev over all such pairs, plus the first
    and last pairs. edge='rise' needs both signals to be binary (0/1);
    use edge='any' for any change. Times are human-readable or ticks.
    With A and B the same signal, each edge pairs with the next one: the
    interval between its edges. vhdl-tools wave analyze gives a clock's
    period and duty directly.
    """
    error = _open(file)
    if error is not None:
        return ToolError(error)
    f = _STORE.open(file)
    try:
        ra, rb = f.resolve(a), f.resolve(b)
        ia, ib = ra.signal, rb.signal
        start_t = _ticks(f, start)
        end_t = None if end is None else _ticks(f, end)
        if end_t is not None and end_t <= start_t:
            return ToolError(
                f"window is empty: end ({_tm(f, end_t)}) "
                f"must be after start ({_tm(f, start_t)})"
            )
        end_label = _tm(f, end_t) if end_t is not None else "end of file"
        pa, pb = f.packed(ia.full_name), f.packed(ib.full_name)
        ta, va = f.window(ia.full_name, start_t, end_t)
        tb, vb = f.window(ib.full_name, start_t, end_t)
        ea_name = "rising edges"
        if edge == "rise":
            for name, kind, values, times, full, info in (
                (a, pa.kind, va, ta, ia.full_name, ia),
                (b, pb.kind, vb, tb, ib.full_name, ib),
            ):
                if kind == "int":
                    bad_mask = (values < 0) | (values > 1)
                    is_binary = len(values) == 0 or not bool(np.any(bad_mask))
                    bad_idx = int(np.argmax(bad_mask)) if not is_binary else None
                else:
                    is_binary = False
                    bad_idx = 0 if len(values) > 0 else None
                if not is_binary:
                    detail = ""
                    if bad_idx is not None:
                        bad_value = _fmt_value(info, values[bad_idx])
                        bad_time = _tm(f, int(times[bad_idx]))
                        detail = f" (saw value {bad_value} at time {bad_time})"
                    return ToolError(
                        f"edge='rise' needs binary (0/1) signals; {full}"
                        f" (from {name!r}) is not binary{detail}"
                        " — use edge='any'"
                    )
            ea = rising_edges(ta, va, int(f.value_at(ia.full_name, start_t)), start_t)
            eb = rising_edges(tb, vb, int(f.value_at(ib.full_name, start_t)), start_t)
        else:
            ea, eb, ea_name = ta, tb, "edges"
        if len(ea) == 0:
            return (
                f"file:     {f.path}\n"
                f"window:   [{_tm(f, start_t)}, {end_label})\n"
                f"no {ea_name} on {ia.full_name} in this window"
            )
        if len(eb) == 0:
            return (
                f"file:     {f.path}\n"
                f"window:   [{_tm(f, start_t)}, {end_label})\n"
                f"no {ea_name} on {ib.full_name} in this window"
            )
        # One signal against itself: each edge pairs with the next one, the
        # interval between edges. "At or after" would pair every edge with itself.
        same = ia.full_name == ib.full_name
        idx = np.searchsorted(eb, ea, side="right" if same else "left")
        matched = idx < len(eb)
        if not matched.any():
            return (
                f"file:     {f.path}\n"
                f"window:   [{_tm(f, start_t)}, {end_label})\n"
                f"no matched pairs — {ib.full_name} has no {ea_name}"
                f" at or after {ia.full_name}'s edges in this window"
            )
        ae, be = ea[matched], eb[idx[matched]]
        deltas = be - ae
        unmatched = int((~matched).sum())

        def fmt(t: np.number | float) -> str:
            return _tm(f, _round_sig3(round(float(t))))

        lines = [
            f"file:     {f.path}",
            f"a:        {ia.full_name} ({len(ea)} {ea_name})",
            f"b:        {ib.full_name} ({len(eb)} {ea_name})",
            f"window:   [{_tm(f, start_t)}, {end_label})",
            f"pairs:    {len(deltas)} "
            + (
                "(each edge -> the next edge)"
                if same
                else "(each a edge -> first b edge at/after it)"
            )
            + (
                f"; {unmatched} a edges unmatched (b quiet)"
                if unmatched and not same
                else ""
            ),
            f"min:      {fmt(deltas.min())}",
            f"max:      {fmt(deltas.max())}",
            f"mean:     {fmt(deltas.mean())}",
            f"p50:      {fmt(np.percentile(deltas, 50))}",
            f"stddev:   {fmt(deltas.std())}",
        ]
        if len(deltas) > 5:
            lines.append("first:")
            lines += [
                f"  a@{_tm(f, int(x))} -> b@{_tm(f, int(y))} ({fmt(d)})"
                for x, y, d in zip(ae[:3], be[:3], deltas[:3], strict=True)
            ]
            lines.append("last:")
            lines += [
                f"  a@{_tm(f, int(x))} -> b@{_tm(f, int(y))} ({fmt(d)})"
                for x, y, d in zip(ae[-2:], be[-2:], deltas[-2:], strict=True)
            ]
        else:
            lines.append("pairs:")
            lines += [
                f"  a@{_tm(f, int(x))} -> b@{_tm(f, int(y))} ({fmt(d)})"
                for x, y, d in zip(ae, be, deltas, strict=True)
            ]
    except (AmbiguousSignal, SignalNotFound, TimeValueError) as exc:
        return ToolError(str(exc))
    return "\n".join(lines)


@tools.tool()
def peeper_find(
    file: str, signal: str, value: str | int, start: str | int = "0", limit: int = 100
) -> str:
    """When was the signal equal to this value?

    Answers "when did <signal> become <value>?", "when is the bus in X?",
    "when does the FSM enter <state>?". Int signals take decimal or hex
    ('0x1f'); string/enum signals match case-insensitively; on logic
    vectors 'x' or 'z' matches an all-X/all-Z bus. Returns each interval
    the value is held, with its duration, from `start` onwards. For a
    single time point use vhdl-tools wave value-at; for statistics use
    vhdl-tools wave analyze.
    """
    error = _open(file)
    if error is not None:
        return ToolError(error)
    f = _STORE.open(file)
    try:
        res = f.resolve(signal)
        info = res.signal
        start_t = _ticks(f, start)
        target = _parse_target(value, info)
        target_text = _fmt_value(info, target)
        duration = f.duration()
        if start_t >= duration:
            return (
                f"file:     {f.path}\n"
                f"signal:   {info.full_name}\n"
                f"value:    {target_text}\n"
                f"matches:  0 — start ({_tm(f, start_t)}) is beyond the"
                f" end of the file (at {_tm(f, duration)})"
            )
        packed = f.packed(info.full_name)
        i = int(np.searchsorted(packed.times, start_t, side="left"))
        times_win = packed.times[i:]
        entering = f.value_at(info.full_name, start_t)
        if len(times_win) == 0:
            held_text = _fmt_value(info, entering)
            if _value_eq(entering, target):
                return (
                    f"file:     {f.path}\n"
                    f"signal:   {info.full_name}\n"
                    f"value:    {target_text}\n"
                    f"matches:  1 — held from {_tm(f, start_t)} to end of"
                    f" file (held for {_tm(f, duration - start_t)})"
                )
            return (
                f"file:     {f.path}\n"
                f"signal:   {info.full_name}\n"
                f"value:    {target_text}\n"
                f"matches:  0 — the signal held {held_text} throughout"
                f" (no changes after {_tm(f, start_t)})"
            )
        run_times, run_values, run_len = value_runs(
            times_win, packed.values[i:], entering, start_t, duration
        )
        matches = [
            (rt, rl)
            for rt, rv, rl in zip(run_times, run_values, run_len, strict=True)
            if rl > 0 and _value_eq(rv, target)
        ]
    except (AmbiguousSignal, SignalNotFound, TimeValueError) as exc:
        return ToolError(str(exc))
    header = [
        f"file:     {f.path}",
        f"signal:   {info.full_name}" + (f"  (matched {signal!r})" if res.note else ""),
        f"value:    {target_text}",
    ]
    if not matches:
        distinct: dict[object, int] = {}
        for rv in run_values:
            distinct[rv] = distinct.get(rv, 0) + 1
        top = sorted(distinct.items(), key=lambda kv: -kv[1])[:5]
        hint = ", ".join(f"{_fmt_value(info, v)} ({n}x)" for v, n in top)
        return "\n".join(
            [
                *header,
                "matches:  0",
                f"the signal took these values after {_tm(f, start_t)}: {hint}",
            ]
        )
    shown = min(len(matches), max(limit, 1))
    lines = [
        *header,
        f"matches:  {len(matches)}"
        + (f" (showing {shown})" if shown < len(matches) else ""),
    ]
    lines += [f"  {_tm(f, rt)}  held for {_tm(f, rl)}" for rt, rl in matches[:shown]]
    if shown < len(matches):
        lines.append(
            f"truncated after {shown} — narrow with start='...' or raise limit"
        )
    return "\n".join(lines)


def _decimate_idx(n: int) -> np.ndarray:
    """Indices into an n-point series, keeping ~_MAX_PTS points.

    Always includes the last point so the trace reaches the window end.
    """
    if n <= _MAX_PTS:
        return np.arange(n)
    stride = int(np.ceil(n / _MAX_PTS))
    idx = np.arange(0, n, stride)
    if idx[-1] != n - 1:
        idx = np.append(idx, n - 1)
    return idx


def _draw_plot_lane(
    ax: Axes,
    f: WaveformFile,
    info: SignalInfo,
    lane_base: float,
    start_t: int,
    win_end: int,
    scale: float,
    color: tuple[float, ...],
    edges: np.ndarray | None = None,
) -> str:
    """Draw one signal's window in its lane; return a one-line summary.

    With `edges`, a dot at each one on the value the signal had just before it:
    the value a register clocked there samples.
    """
    packed = f.packed(info.full_name)
    times, values = f.window(info.full_name, start_t, win_end)
    entering = f.value_at(info.full_name, start_t)
    n_changes = len(times)
    kind = packed.kind
    wide = (info.bitwidth or 0) > 32
    wide_int = kind == "int" and wide
    as_text = kind == "str" and (wide or not _numbers_and_unknowns(values, entering))
    if as_text or wide_int:
        # Text lane: held values as labels, X/Z spans shaded. String/enum
        # signals (kind "str", possibly mixing ints with X/Z strings) and
        # wide int buses (> 32 bit, which don't plot meaningfully as
        # numbers) both render here.
        run_times, run_values, run_len = value_runs(
            times, values, entering, start_t, win_end
        )
        runs = [
            (rt, rv, rl)
            for rt, rv, rl in zip(run_times, run_values, run_len, strict=True)
            if rl > 0
        ]
        stride = max(1, (len(runs) - 1) // _MAX_TEXT_RUNS_DRAWN)
        if len(runs) > 1:
            x_lines = (
                np.asarray([rt for rt, _rv, _rl in runs[1::stride]], dtype=np.float64)
                * scale
            )
            ax.vlines(
                x_lines,
                lane_base,
                lane_base + _LANE_HEIGHT,
                color="0.8",
                lw=0.5,
            )
        xz_runs = [(rt, rv, rl) for rt, rv, rl in runs if is_xz(rv)]
        for rt, _rv, rl in xz_runs:
            ax.add_patch(
                Rectangle(
                    (rt * scale, lane_base),
                    rl * scale,
                    _LANE_HEIGHT,
                    facecolor="0.9",
                    edgecolor="none",
                    alpha=0.9,
                    lw=0,
                )
            )
        labels = [(rt, rv, rl) for rt, rv, rl in runs if not is_xz(rv)]
        shown = (
            labels
            if len(labels) <= _MAX_TEXT_LABELS
            else sorted(labels, key=lambda r: -r[2])[:_MAX_TEXT_LABELS]
        )
        for rt, rv, rl in shown:
            ax.annotate(
                _fmt_value(info, rv),
                xy=((rt + rl / 2) * scale, lane_base + 0.5),
                ha="center",
                va="center",
                fontsize=7,
                color="0.1",
            )
        note = ""
        if len(shown) < len(labels):
            note = f", showing {len(shown)} of {len(labels)} labels"
        plural = "" if len(xz_runs) == 1 else "s"
        return f"text ({len(runs)} runs, {len(xz_runs)} x/z interval{plural}{note})"
    # A signal holds each value until its next change, so every lane is a
    # staircase, and its last value is held to the end of the window. Straight
    # lines between changes drew a counter as ramps that never happened.
    binary = kind != "float" and (info.is_1bit or (info.bitwidth or 0) <= 1)
    x = np.concatenate((np.array([start_t], dtype=np.int64), times))
    raw: list[object] = [entering, *values.tolist()]
    if kind == "str":
        unknown = np.array([_is_unknown(v) for v in raw], dtype=bool)
        num = np.array(
            [np.nan if u else float(v) for v, u in zip(raw, unknown, strict=True)]
        )
    else:
        unknown = np.zeros(len(raw), dtype=bool)
        num = np.asarray(raw, dtype=np.float64)
    known = num[~unknown]
    if binary:
        vmin, vmax = 0.0, 1.0
    elif len(known):
        vmin, vmax = float(known.min()), float(known.max())
    else:
        vmin = vmax = 0.0
    span = vmax - vmin
    rel = np.full(len(num), 0.5) if span == 0 else (num - vmin) / span
    rel[unknown] = np.nan
    idx = _decimate_idx(len(x))
    y = lane_base + rel[idx]
    ax.step(
        np.append(x[idx], win_end) * scale,
        np.append(y, y[-1]),
        where="post",
        color=color,
        lw=1.0 if binary else 0.8,
    )
    ends = np.append(x[1:], win_end)
    notes: list[str] = []

    # Unknown spans in red on the lane itself, as a simulator's viewer draws X.
    spans: list[tuple[int, int]] = []
    for i in np.flatnonzero(unknown):
        t0, t1 = int(x[i]), int(ends[i])
        if spans and spans[-1][1] == t0:
            spans[-1] = (spans[-1][0], t1)
        elif t1 > t0:
            spans.append((t0, t1))
    for t0, t1 in spans:
        ax.add_patch(
            Rectangle(
                (t0 * scale, lane_base),
                (t1 - t0) * scale,
                _LANE_HEIGHT,
                facecolor=(1.0, 0.88, 0.88),
                edgecolor="none",
                lw=0,
            )
        )
        ax.hlines(lane_base + 0.5, t0 * scale, t1 * scale, color="red", lw=1.5)
    if spans:
        plural = "" if len(spans) == 1 else "s"
        notes.append(f"{len(spans)} unknown interval{plural} in red")

    # A lane that never changes has no edge to show its level: say it.
    if binary and not unknown.any() and len(np.unique(num)) == 1:
        level = _fmt_value(info, _plain(raw[0], kind))
        ax.annotate(
            f"constant {level}",
            xy=(0.01, lane_base + 0.5),
            xycoords=("axes fraction", "data"),
            va="center",
            fontsize=7,
            color="0.1",
        )
        notes.append(f"constant {level}")

    if edges is not None and len(edges):
        before = np.searchsorted(x, edges, side="left") - 1
        ok = before >= 0
        sampled = rel[before[ok]]
        known_dot = ~np.isnan(sampled)
        ax.plot(
            edges[ok][known_dot] * scale,
            lane_base + sampled[known_dot],
            "o",
            ms=2.5,
            color=color,
        )
        if (~known_dot).any():
            ax.plot(
                edges[ok][~known_dot] * scale,
                np.full(int((~known_dot).sum()), lane_base + 0.5),
                "o",
                ms=2.5,
                color="red",
            )

    # Values on the steps and the lane's range, so exact numbers are in the
    # picture and not guessed from a height.
    if not binary:
        window = max(win_end - start_t, 1)
        steps = [
            (int(x[i]), int(ends[i]), raw[i])
            for i in range(len(x))
            if not unknown[i] and ends[i] > x[i]
        ]
        if len(idx) < len(x) or len(steps) > _MAX_STEP_LABELS:
            notes.append("no labels: too dense, exact values: vhdl-tools wave values")
        else:
            labelled = 0
            for t0, t1, v in steps:
                text = _fmt_value(info, _plain(v, kind))
                if (t1 - t0) / window < _LABEL_CHAR_SHARE * len(text):
                    continue
                r = 0.5 if span == 0 else (float(v) - vmin) / span
                below = r > 0.6
                y_label = lane_base + r + (-0.06 if below else 0.06)
                ax.annotate(
                    text,
                    xy=((t0 + t1) / 2 * scale, y_label),
                    ha="center",
                    va="top" if below else "bottom",
                    fontsize=7,
                    color="0.1",
                )
                labelled += 1
            notes.append(f"labels on {labelled} of {len(steps)} steps")
        if len(known):
            lo = _fmt_value(info, _plain(vmin, kind))
            hi = _fmt_value(info, _plain(vmax, kind))
            if span:
                marks = ((0.0, f"min {lo}"), (1.0, f"max {hi}"))
            else:
                marks = ((0.5, f"= {lo}"),)
            for level, label in marks:
                ax.annotate(
                    label,
                    xy=(1.004, lane_base + level),
                    xycoords=("axes fraction", "data"),
                    va="center",
                    fontsize=6,
                    color="0.4",
                )
            notes.append(f"min {lo}, max {hi}")

    dec = f", decimated to {len(idx)} points" if len(idx) < n_changes else ""
    lane = "binary" if binary else "numeric"
    extra = "".join(f"; {note}" for note in notes)
    return f"{lane} ({n_changes} changes{dec}{extra})"


def _plain(value: object, kind: str) -> object:
    """A value as the int or float format_value expects. A real signal stays a
    float; an integer one that went through a float array is an int again."""
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if kind == "float" else int(value)
    return value


@tools.tool()
def peeper_plot(
    file: str,
    signals: list[str],
    start: str | int = "0",
    end: str | int | None = None,
    out: str | None = None,
    mark: list[str] | None = None,
    clock: str | None = None,
) -> str:
    """Show me the waveforms: a PNG plot of these signals in this window.

    Answers "show me <signal(s)> around time A" / "what does the bus look
    like here?". One lane per signal: binary signals step between 0 and 1,
    small numeric signals step between their values, and wide buses plus string/enum
    signals show their held values as text labels with X/Z spans shaded.
    Times are human-readable ('10ns', '1.5us') or integer file ticks; the
    window is [start, end) — omit end to run to the end of the file.
    Dense signals are decimated to ~10000 points so large files stay fast.
    Writes the PNG to `out` (default: a new temp file) and returns a text
    summary whose 'image:' line is the PNG path. For statistics
    use vhdl-tools wave analyze; for exact values use vhdl-tools wave values.
    Numeric steps carry their values when they fit, and X/U/Z spans are red on
    their own lane. mark draws a labelled vertical line at each given time,
    such as the failing check's time from vhdl-tools vunit get-test-waveform.
    clock puts a dot at each of its rising edges on the value each signal had
    just before it, the value a register samples, and a faint line at the edge.
    Past the last recorded time the window is shaded: there is no data there.
    """
    error = _open(file)
    if error is not None:
        return ToolError(error)
    f = _STORE.open(file)
    if not signals:
        return ToolError("no signals given — pass at least one signal name")
    fig: Figure | None = None
    try:
        start_t = _ticks(f, start)
        end_t = None if end is None else _ticks(f, end)
        duration = f.duration()
        if end_t is not None and end_t <= start_t:
            return ToolError(
                f"window is empty: end ({_tm(f, end_t)}) "
                f"must be after start ({_tm(f, start_t)})"
            )
        if end_t is None and start_t >= duration:
            return ToolError(
                f"window is empty: start ({_tm(f, start_t)}) is beyond the"
                f" end of the file (at {_tm(f, duration)})"
            )
        win_end = end_t if end_t is not None else duration
        resolved: list[Resolution] = []
        seen: set[str] = set()
        for name in signals:
            res = f.resolve(name)
            if res.signal.full_name not in seen:
                seen.add(res.signal.full_name)
                resolved.append(res)
        unit, per_unit = display_unit(duration, f.ticks_per_second)
        scale = float(f.ticks_per_second / per_unit)
        edges = None
        clock_line = None
        if clock is not None:
            ci = f.resolve(clock).signal
            ct, cv = f.window(ci.full_name, start_t, win_end)
            if f.packed(ci.full_name).kind != "int" or np.any((cv < 0) | (cv > 1)):
                return ToolError(f"clock {ci.full_name} is not a binary signal")
            edges = rising_edges(
                ct, cv, int(f.value_at(ci.full_name, start_t)), start_t
            )
            clock_line = (
                f"clock:    {ci.full_name}, {len(edges)} rising edges (dots: the"
                " value each signal had just before the edge, as a register"
                " samples it)"
            )
        n = len(resolved)
        fig, ax = plt.subplots(figsize=(10, 0.9 * n + 1.4))
        ax.set_xlim(start_t * scale, win_end * scale)
        summaries: list[str] = []
        for i, res in enumerate(resolved):
            color = plt.cm.tab10(i % 10)
            summaries.append(
                _draw_plot_lane(
                    ax,
                    f,
                    res.signal,
                    i * (_LANE_HEIGHT + _LANE_GAP),
                    start_t,
                    win_end,
                    scale,
                    color,
                    edges,
                )
            )
        if edges is not None:
            ax.vlines(
                edges * scale,
                -0.2,
                (n - 1) * (_LANE_HEIGHT + _LANE_GAP) + _LANE_HEIGHT + 0.2,
                color="0.85",
                lw=0.5,
                zorder=0,
            )
        # No data past the file's last recorded time: shade it, so a missing
        # edge there does not read as a signal that stopped.
        data_end = max(
            [duration]
            + [
                int(f.packed(r.signal.full_name).times[-1])
                for r in resolved
                if len(f.packed(r.signal.full_name).times)
            ]
        )
        end_line = None
        if win_end > data_end:
            ax.axvspan(
                data_end * scale, win_end * scale, color="0.93", zorder=0, lw=0
            )
            ax.annotate(
                "no data",
                xy=((data_end + win_end) / 2 * scale, 0.02),
                xycoords=("data", "axes fraction"),
                ha="center",
                fontsize=7,
                color="0.4",
            )
            end_line = f"data:     no data after {_tm(f, data_end)} (end of file)"
        ax.set_yticks([i * (_LANE_HEIGHT + _LANE_GAP) + 0.5 for i in range(n)])
        ax.set_yticklabels([res.signal.leaf for res in resolved])
        ax.set_ylim(-0.2, (n - 1) * (_LANE_HEIGHT + _LANE_GAP) + _LANE_HEIGHT + 0.2)
        ax.set_xlabel(f"time ({unit})")
        ax.set_title(
            f"{os.path.basename(f.path)}   [{_tm(f, start_t)}, {_tm(f, win_end)})"
        )
        ax.grid(axis="x", linewidth=0.3, alpha=0.4)
        marked: list[str] = []
        outside: list[str] = []
        for m in mark or []:
            t = _ticks(f, m)
            if not start_t <= t <= win_end:
                outside.append(_tm(f, t))
                continue
            ax.axvline(t * scale, color="red", linestyle="--", lw=1)
            ax.annotate(
                _tm(f, t),
                xy=(t * scale, 1.0),
                xycoords=("data", "axes fraction"),
                ha="center",
                va="bottom",
                fontsize=7,
                color="red",
            )
            marked.append(_tm(f, t))
        if out:
            png_path = os.path.abspath(out)
        else:
            fd, png_path = tempfile.mkstemp(prefix="peeper-plot-", suffix=".png")
            os.close(fd)
        fig.savefig(png_path, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig)
        fig = None
        lines = [
            f"file:     {f.path}",
            f"window:   [{_tm(f, start_t)}, {_tm(f, win_end)})",
            f"image:    {png_path}",
            f"traces:   {n}",
        ]
        for extra in (clock_line, end_line):
            if extra:
                lines.insert(3, extra)
        if marked or outside:
            note = f" ({', '.join(outside)} outside the window)" if outside else ""
            lines.insert(3, f"marks:    {', '.join(marked) or 'none'}{note}")
        for res, summary in zip(resolved, summaries, strict=True):
            note = f"  (matched {res.signal.leaf!r})" if res.note else ""
            lines.append(f"  {res.signal.full_name}{note}  {summary}")
        lines.append(
            "stats: vhdl-tools wave analyze; exact values: vhdl-tools wave values; narrow the"
            " window to read dense labels"
        )
        return "\n".join(lines)
    except (AmbiguousSignal, SignalNotFound, TimeValueError) as exc:
        if fig is not None:
            plt.close(fig)
        return ToolError(str(exc))


def _fmt_value(info: SignalInfo, value: object) -> str:
    return format_value(value, info.bitwidth)


_INT_RE = re.compile(r"-?\d+")


def _parse_target(value: str | int, info: SignalInfo) -> int | str:
    """Parse a vhdl-tools wave find target: int stays int, hex/decimal strings
    become ints, everything else stays a string. 'x'/'z' on a logic
    vector expands to the full-width all-X/all-Z pattern."""
    if isinstance(value, int):
        return value
    s = value.strip()
    if s.lower().startswith("0x"):
        try:
            return int(s, 16)
        except ValueError:
            return s
    if _INT_RE.fullmatch(s):
        return int(s)
    if s.lower() in ("x", "z") and info.is_bit_vector and info.bitwidth:
        return s * info.bitwidth
    return s


def _value_eq(actual: object, target: object) -> bool:
    if isinstance(target, int):
        return isinstance(actual, int) and actual == target
    return isinstance(actual, str) and actual.lower() == str(target).lower()


def _ticks(f: WaveformFile, value: str | int) -> int:
    return parse_time(value, f.ticks_per_second)


def _tm(f: WaveformFile, ticks: int) -> str:
    return format_ticks(ticks, f.ticks_per_second)


def _round_sig3(ticks: int) -> int:
    """Round ticks to 3 significant figures for statistics display.

    A min/mean/stddev of deltas can carry as many digits as the file's
    timescale; rounding keeps statistics readable. Exact tick values
    (timestamps, individual intervals) are left untouched.
    """
    if ticks <= 0:
        return 0
    magnitude: int = 10 ** max(len(str(ticks)) - 3, 0)  # mypy 2 types ** as Any
    # Integer round-half-up to the nearest multiple of `magnitude`.
    return ((ticks + magnitude // 2) // magnitude) * magnitude

