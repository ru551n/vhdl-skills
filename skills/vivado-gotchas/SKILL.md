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
treated elsewhere: read it from the printed build summary / `timing.rpt`,
record it as a hand-verified, dated comment next to the relevant build
entry, and re-measure by hand after any change that could move it — do not
expect an automated `build_result_checkers` gate to enforce it.

## Enabling timing analysis can shift reported resource counts, not just add timing data

Turning on `analyze_synthesis_timing=True` (or, more generally, moving from a
"hook right after synth_design, design never opened" utilization report to
an "open the run, then report_utilization" one) can change the *reported*
RAMB18/RAMB36 split for the exact same RTL and generics — even though the
combined "how much block RAM does this really need" answer is close. Do not
assume a resource checker baselined under one reporting mode carries over
unchanged when the build is switched to the other mode; re-measure and
re-baseline the specific counters that could be report-method-sensitive
(BRAM primitive-type split is the one seen in practice; LUT/FF/DSP totals
were stable across the switch in the same test).

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

## Composition-entity synthesis time does not scale with source size

A composition entity's Vivado (or Yosys) synthesis time is driven by the
size of the netlist it produces, not by its source line count or how many
submodules it has. A failed RAM/DSP inference in one leaf can turn what
should be a sub-minute build into an 18-minute one for a design that looks
similarly sized to its siblings. Treat a sudden jump in synthesis time as a
signal to check the utilization report for a fallback mapping (distributed
RAM instead of block RAM, LUT fabric instead of DSP), not as an annoyance to
wait out. See `shared/DesignPatterns.md` / `vhsynth`'s own notes on
backend/runtime choices for the general (non-Vivado-specific) version of
this rule.
