---
name: vivado-gotchas
description: Vivado-specific synthesis, timing-estimation, place-and-route, and constraint gotchas (largely via tsfpga's Vivado backend) that are easy to silently get wrong
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.

# Vivado Gotchas

Reference knowledge, not a workflow. Load this whenever doing Vivado-specific
synthesis, timing-estimation, constraint, or place-and-route work — from
`vhsynth`, from `vhflow`, or standalone. These are project-independent Vivado
(and, where noted, tsfpga-wrapping-Vivado) behaviors that are easy to get
silently wrong because they fail quietly instead of erroring.

Read `shared/McpToolPolicy.md`.

## MCP preference

For an actual tsfpga project's own Vivado build (not the portable Yosys
flow), prefer `tsfpga-mcp`'s project-mode tools over manually invoking
Vivado/`build_fpga.py` via `bash` and over manually opening or grepping the
generated report files:

- `tsfpga_project_status` / `tsfpga_project_list_builds` instead of
  manually locating build directories or guessing which builds exist.
- `tsfpga_project_build` (with `project_filters` to scope it) instead of
  invoking `build_fpga.py`/Vivado directly from the shell.
- `tsfpga_project_get_timing_report`, `tsfpga_project_get_utilization_report`,
  and `tsfpga_project_get_drc_report` instead of manually reading
  `timing.rpt`, a utilization report, or a DRC report off disk.

This does not remove the need for the Vivado-behavior knowledge below —
the gotchas about post-synthesis hook reliability, XDC parsing, and report
content are exactly what these report-retrieval tools are surfacing, and
still apply when reasoning about *why* a retrieved report looks the way it
does. Fall back to manually invoking Vivado/`build_fpga.py` and reading its
generated report files directly only when `tsfpga-mcp` (or its project-mode
tools specifically) is unavailable.

**When falling back to a manually-launched background build, block on the
actual process, not a name-pattern match that can match yourself.** A
common way to wait for a long `build_fpga.py`/Vivado run launched with
`nohup ... &` is a loop like `until ! pgrep -f "<pattern>"; do sleep N;
done` — but `pgrep -f` also matches the shell/awk/sleep invocation
running the loop itself if the pattern is generic enough, so the loop
never observes "no match" and spins forever even after the real build
exits. Capture the actual PID at launch time (`$!` from the backgrounding
command) and poll with `ps -p "$PID" >/dev/null 2>&1` instead — a specific
PID cannot self-match.

## Post-synthesis TCL hooks cannot reliably query the constraint/clock state

A `STEPS.SYNTH_DESIGN.TCL.POST` build-step hook runs after `synth_design`
completes, and it looks like the design (including any `create_clock`
constraints just parsed during that same `synth_design` run) should be live
and queryable. It is not reliable: `get_clocks` from inside such a hook can
come back empty even though the constraint file was parsed with zero
errors/warnings during `Processing XDC Constraints`, and even though the
design has real registers.

This is not a one-off fluke — it is a known, named limitation. From an
authoritative tsfpga source comment on exactly this: *"It would have been
more efficient to use post-synthesis hooks (since the design would already be
open), IF that mechanism had worked. It seems to be very bugged."* Their own
workaround is to never rely on a post-synth hook for anything that needs to
read back the design's timing/clock state; instead they put `open_run`,
`report_timing`, `report_clock_interaction`, etc. **directly in the main
build TCL script**, right after the run finishes, not in a hook attached to
that run.

Practical rule: if a check needs to *read back* clock/timing/constraint
state that was just established during synthesis, do not reach for a
post-synthesis hook. Either:
- put the query directly in the build script after the run (like tsfpga
  does), or
- open the run explicitly (`open_run <synth_run>`) in whatever script
  performs the query, rather than trusting an automatically-attached hook's
  implicit context.

Hooks remain fine for things that only *write* a report from data that does
not depend on this fragile live-constraint-state (e.g. `report_utilization`,
`report_design_analysis -logic_level_distribution` right after synthesis —
these work fine as hooks and are exactly what tsfpga itself uses hooks for).

## XDC constraint files only execute a restricted command subset

A `.xdc`/constraint file loaded as part of a run's constraint set is parsed
by a dedicated SDC/XDC-subset parser, not full Tcl. Arbitrary Tcl commands
placed in a `.xdc` file (e.g. a `puts` for debugging) can be silently
dropped — no error, no warning, nothing printed, even though the file's
actual constraint commands (`create_clock`, `set_property`, etc.) do apply
normally. Do not use a `.xdc` file as a place to inject debug prints or
general scripting; use a `BuildStepTclHook`-style hook (a real `.tcl` file
attached to a build step) for that instead — but see the caveat above about
what such a hook can and cannot reliably observe.

## A user `create_clock` on a plain port can silently produce zero clocks

Symptom: a `.xdc` constraint containing `create_clock -period <T> -name clk
[get_ports clk]` is parsed with `Processing XDC Constraints` reporting no
errors, `get_ports clk` resolves the port correctly, and yet a later
`get_clocks` / `report_timing_summary`'s Clock Summary shows **zero** defined
clocks, and `check_timing`'s `no_clock` section lists every register in the
design as unclocked. Before assuming the RTL, the XDC syntax, or the port
name is wrong, check two things:

1. Whether the observation itself is trustworthy — see "Post-synthesis TCL
   hooks cannot reliably query constraint state" above; a hook-based
   `get_clocks` returning empty does not prove the clock was never created,
   it may only prove the hook can't see it.
2. Whether some other automatic mechanism (see the tsfpga auto-clock note
   below) is fighting your constraint, e.g. a placeholder/auto-generated
   constraint file loaded at a different processing order that also touches
   the same port.

Do not "fix" this by adding more constraint files blindly; verify by opening
the run directly (`open_run <synth_run>`) in a plain script and querying
`get_clocks` there, which is the reliable way tsfpga itself does it.

## tsfpga's netlist-build timing-estimate flag: what it actually measures, and its ordering bug

tsfpga's `VivadoNetlistProject(analyze_synthesis_timing=True, ...)` is the
idiomatic way to get a fast, synthesis-only (no place-and-route) maximum
achievable clock frequency **estimate** for a netlist build, without a
hand-rolled XDC+hook combo (which is unreliable per the sections above).
What it actually does:

- Regex-detects clock port names in the top-level VHDL file (any port
  containing `clk` or `clock`, with an optional `_`-delimited prefix/suffix)
  and auto-generates `create_clock -name "<port>" -period 2.0 [get_ports
  "<port>"]` for each — a fixed, tool-internal period (2 ns / 500 MHz as of
  the version this was verified against), not something the caller supplies
  directly per instance.
- Opens the synthesized run (`open_run`) and runs `report_timing -setup`
  into a `timing.rpt` file, then parses its `slack` line.
- Converts that slack into `build_result.maximum_synthesis_frequency_hz =
  1e9 / (clock_period_ns - slack_ns)`. This formula is **independent of the
  2 ns constraint value actually used** — it always converges to
  `1 / (worst path delay)`, so it is a legitimate general max-frequency
  estimate regardless of what period the tool happened to constrain against.
- This is a **synthesis-only estimate**: no placement, no routing, so it is
  optimistic/inaccurate versus a real post-place-and-route number. Never
  report it as "meets timing" or as a signed-off Fmax.

**Ordering bug** (verified against a real tsfpga 2026-era install): inside
`VivadoNetlistProject.build()`, `self._check_size(build_result=result)` — the
call that runs every user-supplied `build_result_checkers` entry — executes
**before** the few lines further down in the same method that parse
`timing.rpt` and set `result.maximum_synthesis_frequency_hz`. Consequence: a
custom `BuildResultChecker` that reads `build_result.maximum_synthesis_frequency_hz`
will **always see `None`** at check time, regardless of whether a real,
easily-passing number exists in `timing.rpt` on disk moments later. This is
not a design-side mistake to "fix" by making the checker tolerate `None` —
that would silently stop checking anything. Until the ordering is fixed
upstream (or overridden via a subclass that reorders it), treat the
frequency number the same way genuinely un-checkable vendor numbers are
treated elsewhere: read it from the printed build summary, or — preferably —
`tsfpga_project_get_timing_report` rather than manually opening `timing.rpt`
on disk; record it as a hand-verified, dated comment next to the relevant
build entry, and re-measure after any change that could move it — do not
expect an automated `build_result_checkers` gate to enforce it.

## A leaf entity's out-of-context Fmax is blind to cones that start at an input port

The single most dangerous way to misread the synthesis-only estimate above:
it reports **register-to-register** paths. On an out-of-context netlist
build, a purely combinational cone whose *start point is a top-level input
port* is not a register-to-register path, so it is never timed and never
appears as the worst path. A leaf entity whose real work is one deep
combinational cone hanging off its input ports will therefore report a
spectacular Fmax — the tool is timing whatever small internal
register-to-register path happens to remain, not the logic you care about.

Confirmed on a real design: a requantize leaf reported **520 MHz** standalone
while being the **46.77 MHz critical path of the composition entity that
instantiated it**. Its whole ~21 ns cone (bias-add, multiply, rounded shift,
saturate) started at its `s_*_m2s.data` / `*_rd_data` input ports, so the
standalone build timed a 1-LUT `valid_q -> data_q/CE` path and reported
520 MHz. Inside the parent, with that cone fed by another submodule's
registers, it became the bottleneck.

**Rule: treat a leaf's out-of-context Fmax as an upper bound and nothing
more. Only a composition entity — one where the cone's source registers are
inside the same netlist — produces a number worth acting on. Never optimise a
leaf against its own standalone figure, and never conclude "this leaf is
fine, look elsewhere" from one.**

Corollaries worth budgeting for:

- **Fixing the reported critical path may buy nothing at the top level.**
  Each fix only reveals the next comparable path. On the design above the
  progression across four reworks was 46.77 -> 46.77 -> 47.66 -> 159.72 ->
  159.95 MHz: two of the four reworks moved the top-level number by ~0 and
  ~1 MHz, and were still necessary — they were what exposed the path whose
  fix delivered the 3.4x jump. Do not judge a timing rework by its immediate
  top-level delta; judge it by whether the path it targeted is gone.
- **Expect a plateau, and stop at it.** Once several paths sit within a few
  hundred ps of each other, further single-path fixes yield fractions of a
  MHz (above: +0.23 MHz) because a different module simply takes over as
  worst path. That is the signal that the estimate is exhausted and the
  remaining margin question belongs to real place-and-route, not to more
  out-of-context iterations.
- **Re-measure every leaf after every rework, not just the one you changed.**
  Improving a leaf's input-port cone can change how the parent's other leaves
  get mapped (see "A timing fix in one leaf can change another leaf's RAM/DSP
  inference" below), which moves both their resource counts and their
  contribution to the critical path.

## A timing fix in one leaf can change another leaf's RAM/DSP inference

Registering a leaf's input-port cone does not only change that leaf. When the
signal driving it comes from a *different* submodule's memory, giving it a
clean capture register can flip that other module's inference decision.
Confirmed on a real design: pipelining a requantize leaf so its `bias_rd_data`
input landed on a plain stage-1 register instead of feeding a 21 ns
combinational cone moved the parent's count from **10 to 14 RAMB36** — Vivado
had been partially dissolving the *weight buffer's* bias memory into fabric to
shorten that cone, and stopped once the cone was gone. The higher number was
the correct one; the old 10 was the anomaly.

Practical consequences:

- A parent's resource counts are not a stable baseline across timing reworks
  of its children, even when the child's own counts are unchanged in the
  direction you expected. Re-measure the parent after every child rework.
- Verify parent counts **leaf-additively** as an integrity check rather than
  just re-pinning whatever the build printed: sum the leaves' measured
  DSP/BRAM primitives and confirm the parent matches (e.g. `32 DSP = 32
  (requant, 2/lane x 16) + 0 (window gen, was 4)`; `14 RAMB36 = 11 (weight
  buffer) + 3 (window gen)`). When the sum does *not* match, that is the
  cheapest available detector of a silent inference change — much cheaper
  than reading utilization hierarchies.
- Keep DSP checkers strict (they encode structural invariants like
  "two DSPs per lane") and give FF checkers explicit headroom; FF counts move
  by hundreds under pipelining and retiming, DSP counts should not move at
  all without a design reason.

## Enabling timing analysis changes synthesis itself, not just what gets reported afterward

Turning on `analyze_synthesis_timing=True` is **not** a pure post-hoc
analysis switch, and the resource-count drift it causes is not just a
reporting-method artifact — verify the actual mechanism before assuming
that. In `VivadoNetlistProject.create()`, this flag also controls whether an
unconditionally-appended, `"early"`-processing-order auto-clock constraint
file gets populated with a real `create_clock -period <T> [get_ports
<clk>]` on the auto-detected clock port. That constraint file is loaded via
`read_xdc` and left `USED_IN_SYNTHESIS` (the default) — so it is live
**during `synth_design` itself**, not merely during the later
`open_run`/`report_timing` step. A previously-unconstrained netlist build
(no clock at all, pure area-oriented out-of-context synthesis) and the same
RTL/generics built with a real clock constraint present are two genuinely
different synthesis runs, and Vivado is free to make different
area/timing tradeoffs (register retiming, BRAM-cascade choices, LUTRAM vs.
block RAM, etc.) between them.

In practice this can move **LUT and FF totals, not just the RAMB18/RAMB36
split** — confirmed on a real design where enabling this flag across six
existing netlist builds shifted FF counts by several hundred and BRAM
primitive counts by several units each, failing 3 of 6 previously-passing
`build_result_checkers`. Do not assume a resource checker baselined under
"no clock constraint" synthesis carries over unchanged once this flag is
turned on (or vice versa); re-measure and re-baseline every counter, not
just BRAM split, whenever this flag's setting changes for a given build.

## Vivado's DSP48E1 MACC inference is template-sensitive

Vivado's default synthesis maps a plain, unconditional multiply-accumulate
(`acc := acc + a * b`, no extra gating between the multiply and the add)
into DSP48E1 blocks, packing two independent small (e.g. 8x8) multiplies per
DSP48E1 when widths allow. Gating the accumulate with an intermediate
condition between the multiply and the add (e.g. `if some_valid_flag then
acc := acc + a * b`) is enough to make Vivado fall back to LUT fabric for
the *entire* multiply-accumulate array instead — not a partial degradation,
a full miss of the DSP inference template. This is Vivado-specific: a
different backend (e.g. Yosys) may map every multiply to its own DSP
primitive unconditionally, regardless of the surrounding control structure,
so the two backends can legitimately report wildly different DSP counts
(zero vs. one-per-lane) for the exact same RTL — neither number is "wrong",
they are answering different questions about the same design under
different mapping templates. If DSP inference is required for a given
signal, keep the multiply-then-accumulate expression as close to the plain,
unconditional template as possible, or verify counts empirically rather than
assuming the "obvious" DSP count from the RTL's arithmetic shape.

## Netlist (out-of-context) synthesis specifics

- `VivadoNetlistProject`-style builds invoke `synth_design -top <entity>
  -part <part> -assert -no_iobuf` — a plain top-level synthesis with IO
  buffering suppressed, not `-mode out_of_context`. Top-level ports keep
  their RTL names (no `_IBUF`/`_OBUF` suffix noise), which matters when
  writing constraints that reference ports by name.
- A `Constraint`'s `processing_order` (`early`/`normal`/`late`) controls
  which constraint file's directives win when more than one touches the
  same object (e.g. a tool's own auto-generated placeholder constraint
  loaded "early" so a user's "normal"-order file can override it). Check
  processing order before assuming two constraint files conflict or that
  one silently overrides the other.
- Re-running a build against an existing project directory fails fast with
  "Project ... already exists" rather than silently reusing/updating it;
  delete the stale generated project directory before a from-scratch rerun
  when the project's construction (module set, generics, constraints)
  changed.

## Always delegate timing analysis and timing fixes to a strong model

Reading a critical-path report and deciding what to change (re-pipeline a
MAC chain, break a combinational adder tree, move a register across a
module boundary) requires holding the full path — every gate/register/net
the report lists, why each one is on the path, and what a correctness-
preserving restructuring looks like — in context at once, and getting it
subtly wrong (an off-by-one-cycle pipeline stage, a dropped valid/enable
that used to gate a now-relocated register) produces a design that still
"passes" functional tests written against the old timing but is wrong, or a
design that still fails timing for a different, unnoticed reason. This is a
qualitatively harder reasoning task than the mechanical
measure-and-record-a-number work above it. Never do timing analysis or
timing fixes with a fast/cheap model pass, and do not have the orchestrating
agent eyeball a `timing.rpt` critical path itself as a shortcut — always
delegate both analyzing *why* a path is slow and implementing the fix to a
strong-tier model (e.g. `task` with `model_tier: "strong"`), even under
time/cost pressure. If timing work must be split across independent
entities, running several strong-model subagents in parallel (one per
entity) is fine and often faster than serializing them — the "strong model
only" rule is about capability per unit of work, not about avoiding
parallelism.

## Composition-entity synthesis time does not scale with source size

A composition entity's Vivado (or Yosys) synthesis time is driven by the
size of the netlist it produces, not by its source line count or how many
submodules it has. A failed RAM/DSP inference in one leaf can turn what
should be a sub-minute build into an 18-minute one for a design that looks
similarly sized to its siblings. Treat a sudden jump in synthesis time as a
signal to check the utilization report (`tsfpga_project_get_utilization_report`
when the build went through `tsfpga-mcp` project mode) for a fallback mapping
(distributed RAM instead of block RAM, LUT fabric instead of DSP), not as an
annoyance to wait out. See `shared/DesignPatterns.md` / `vhsynth`'s own notes on
backend/runtime choices for the general (non-Vivado-specific) version of
this rule.
