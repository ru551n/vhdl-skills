---
name: vhsynth
description: Synthesize a VHDL module or full IP using tsfpga-mcp when available, with local Yosys+GHDL fallback
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.

# VHDL Synthesizer

Read `shared/ModernVHDL.md`, `shared/CodingStyle.md`, and `shared/HouseStyle.md`; they are authoritative for language revision, modern RTL practice, and concrete naming/style conventions.


Read `shared/McpToolPolicy.md`.

Load the `vivado-gotchas` skill before any Vivado-backed synthesis, timing
estimate, constraint, or place-and-route work (whether via `tsfpga-mcp`, a
project's own `build_fpga.py`, or a raw `VivadoProject`/`VivadoNetlistProject`)
— it collects Vivado/tsfpga-specific behaviors (post-synthesis hook
reliability, XDC parsing restrictions, the `analyze_synthesis_timing`
ordering bug, DSP inference template sensitivity, etc.) that are easy to get
silently wrong. Load the `vivado-design` skill alongside it for the
design-time decisions behind a Vivado build (inference templates,
attributes, reset/clocking/CDC methodology, timing-closure report reading,
per-family CLB/BRAM/URAM/DSP facts) — it is the positive methodology the
gotchas skill assumes.

## Backend priority

1. **`tsfpga-mcp`** for portable VHDL synthesis/resource summaries.
2. **local Yosys + GHDL plugin** when MCP is unavailable.

Do not describe `tsfpga-mcp` resource synthesis as vendor timing closure.

When the question is about design structure — instance hierarchy,
generate-block expansion, resolved generics — rather than resource counts,
prefer `tsfpga_hierarchy` (recently added) over a full `tsfpga_synthesize`
run or manually reading source/`ghdl`-elaborating by hand: it runs GHDL
elaboration (generics resolved) without paying for full technology-mapping
synthesis, so it is far cheaper for a pure hierarchy/structure question.

`tsfpga-mcp` only reports aggregated resource counts (LUTs, FFs, DSPs, block RAMs, or raw cell
counts for `chip=generic`) — never a per-port netlist dump.

## Per-module smoke check (run after every module goes green)

Do not defer all synthesis to the final IP-level phase. As soon as a
module's testbench goes green (`vhfill`/`vhtestgen` loop passes), run a
quick `tsfpga_synthesize`/local-fallback pass on that module alone (its own
entity as `top`, `chip=generic` is enough — no need for a specific
vendor/family at this stage) before moving to the next module. Purpose:
catch synthesis-only failures (constructs that simulate fine but don't
synthesize) and resource-count blow-ups (e.g. an accidental full-width
multiply/unrolled loop/latch inference) while the change causing them is
still fresh, rather than at IP-level integration when it's harder to
localize. This smoke check does not replace the final documented
`synth/<module>/synth_report.md` — it's a fast sanity gate, so recording
just the resource-count summary and a pass/fail note in `flow_status.md`
is enough; no separate report file is required for it. Treat any GHDL/Yosys
error, or a resource count that is unexpectedly large/non-zero compared to
similarly-sized sibling modules, as a blocker to resolve before continuing
the flow.

## Keep synthesis runs scoped

Yosys runtime does not scale with source size — it scales with how big the
netlist ends up. A failed block-RAM inference in one module has produced a
2m45s synthesis where sibling entities in the same project each took
0.2-8.5s: the design fell back to distributed RAM (4608 RAM32M/RAM64M-class
cells, ~23700 LUTs), and Yosys' runtime degrades badly at that cell count.
Source size did not predict this; only the utilization report would have.
For a real Vivado project build, retrieve it with
`tsfpga_project_get_utilization_report` rather than manually opening/
grepping the generated report file. See `shared/ModernVHDL.md`'s "Memory:
infer the intended RAM type, and prove it" for the failure mode that causes
this class of blowup.

Because the blowup is not predictable from the RTL, do not default to
synthesizing everything on every iteration:

- While iterating on one module, synthesize only that module (the
  per-module smoke check above, `top` set to the entity in question) — not
  the whole project, and not the top level.
- Run the full set of builds only at integration points: before a commit
  that touches a shared package or more than one module, and in CI.
- Filter instead of building all: `tsfpga_project_list_builds` and
  `tsfpga_project_build` take `project_filters` (wildcards, e.g.
  `["*window_gen*"]`) — use it to target the module(s) at hand rather than
  running every netlist build in the project.
- Leave `use_existing_project` at its default (`true`) while iterating; it
  reuses the project directory instead of forcing a clean re-create. Pass
  `false` only when the project definition itself changed (module set,
  generics, constraints), not on every rebuild.
- Treat a sudden jump in synthesis time as a design signal, not an
  annoyance: it usually means a netlist blowup (failed RAM/DSP inference,
  unintended replication, a combinational explosion). Stop and read the
  utilization report rather than waiting out the build.

## Estimate from leaves; defer the expensive integration build

A composition entity's synthesis can cost 30-300x its leaves (measured:
`conv_core` 858s versus 3.2s/5.1s/21s/23s for its four submodules). Do not
pay that cost to answer a question the leaves already answer.

- **Synthesize the leaves, then add them up.** FFs, block RAMs and DSP
  blocks are *structural* — they are additive across a composition and
  stable between tool versions. Verified on a real design: the composite's
  FF/BRAM/DSP each matched the sum of its four submodules exactly
  (2033/75/106), while LUTs came out ~1.5% below the sum from
  cross-boundary optimization. So: leaf sums give an exact FF/BRAM/DSP
  prediction and a slightly conservative LUT upper bound.
- **State it as an estimate.** Report "estimated from measured submodules,
  integration build deferred" — never as a measured composite result. The
  "never claim success without a real tool result" rule applies to the
  claim, not to the arithmetic: measured leaves *are* real tool results.
- **Run the integration build only when it decides something**: before a
  commit that changes a shared package or crosses module boundaries, when
  re-baselining CI checkers, when leaf sums approach a device limit, or
  when the composition itself (not its leaves) is what changed.
- **This deferral is for area only. It never applies to timing.** A leaf's
  out-of-context Fmax does not time any cone that starts at the leaf's own
  input ports, so leaves fed with configuration or data from a sibling can
  each report well above target while the composed design is an order of
  magnitude short. Register a top-level (or pinnable-wrapper) build as soon
  as the design has a top and run it before any timing claim; see
  `shared/TimingAndResources.md` §1.
- The same logic applies to answering resource questions during design
  exploration: a 5-second spike on a representative memory/datapath shape
  beats a 15-minute build of the real thing, and usually answers the
  question better because you can sweep configurations.

## Backend choice: Yosys for leaves, vendor tools for integration

- **Yosys + GHDL plugin**: fast per-module smoke checks and spikes. Its
  numbers are not vendor-accurate and shift between Yosys versions (a local
  dev build has measured ~2.7x fewer LUTs than the release build CI used for
  the same RTL) — treat Yosys LUT counts as trend data, not baselines.
- **Vendor synthesis (Vivado etc.) via `tsfpga-mcp` project mode / a
  `VivadoNetlistProject`**: use for integration-level and top-level builds,
  and for any number that will become a committed CI checker limit.
- Yosys and vendor numbers are **not comparable**. When a checker limit
  moves from one backend to the other, re-baseline it and record which tool
  produced it in the comment next to the limit.
- **Cap every Yosys netlist build at a 10-minute timeout.** If it has not
  finished by then, kill it and run that build with the vendor tool
  (Vivado etc.) instead — do not wait it out and do not retry it on Yosys.
  A Yosys run that exceeds 10 minutes is telling you the netlist blew up
  (failed RAM/DSP inference, unrolled write-enable loops, wide-array
  replication); the vendor tool both finishes and gives the number that
  actually counts for a CI baseline. Record in the report which backend
  produced each number.
- **Never pass `-flatten` to `synth_xilinx` in an ad-hoc spike.** On
  memory-heavy designs (wide arrays, per-lane write-enable loops) it is the
  single biggest RAM multiplier and has OOM-killed sessions. Plain
  `synth_xilinx -family <fam>; stat` reports everything needed. Redirect the
  log to a file and parse a summary line out of it rather than reading it —
  Yosys logs are large enough to be a problem on their own.
- Keep long or known-slow builds out of the tight edit-test loop. The
  simulation regression (`vhunit`/`vhtestgen`) is the fast gate; synthesis
  is the slower structural gate and belongs at module-done and integration
  boundaries, not on every edit.

## Inputs

Must know:
- complete source set
- top entity
- target chip/flow (`generic`, `xilinx`, `intel`, `microchip`)
- target family where required
- generic overrides, if any
- for a non-VHDL top: which VHDL entities it instantiates, if any

Never infer a required target, family or generic value.

If the top entity has more than one architecture, ask which one to synthesize — `tsfpga-mcp` has
no architecture-selection parameter, so the only way to pick one is to include only that
architecture's source file in the synthesis source set.

## Preferred workflow — tsfpga-mcp

### 1. Status

Call `tsfpga_status`.

If the GHDL plugin, Yosys flow, or required environment is unavailable, either fix/report configuration or use a fallback backend.

### 2. Inspect sources

Use `tsfpga_inspect` when:
- the top entity is uncertain
- generics need discovery
- multiple architectures are present
- source ambiguity is possible (e.g. a unit declared in both VHDL and Verilog)

Resolve every `Notes:` ambiguity by asking the user before synthesizing.

If the goal is understanding/verifying the design's instance hierarchy
(generate-block-expanded instance names, resolved generics) rather than
producing resource counts, call `tsfpga_hierarchy` (recently added) instead
of proceeding to a full synthesis run — it is a much cheaper way to answer
that specific question.

### 3. Choose target

If the user did not already provide a valid target, call `tsfpga_targets`.

If several materially different targets fit and the choice affects the answer, require an explicit target rather than guessing. `family` is only accepted for `chip=xilinx`/`intel`/`microchip`, never for `chip=generic`.

### 4. Resolve complete source set

Preferred:
- `vunit_list_files` when `vunit-mcp` is available and sources are registered
- otherwise `shared/HierarchyFilelist.md`

All dependencies must be passed because synthesis does not rely on persistent work-library state.

### 5. Synthesize

Use `tsfpga_synthesize` with:
- `sources`, `top`, `chip`
- `family` if required by the chosen chip
- `generics` if supplied (VHDL top only; the type from `tsfpga_inspect` decides interpretation)
- `vhdl_entities` when `top` is a Verilog/SystemVerilog module (or the design has no VHDL top): the VHDL entity names it instantiates
- `discard_ffinit` only for `chip=microchip`, when flip-flop initial values fail legalization

Record the returned:
- backend/flow
- resource counts
- synthesis diagnostics

## Scope

`tsfpga-mcp` and local Yosys+GHDL produce portable synthesis/resource feedback.
Post-route timing, vendor Fmax, site utilization, power estimation, and
place-and-route are out of scope; state that in the report instead of
fabricating results.

### Fast post-synthesis timing estimate vs full place-and-route closure

These are two different questions; do not let one stand in for the other in
a report:

- **Post-synthesis (synth-only) slack estimate**: adding a clock-period
  constraint (XDC/SDC) plus a vendor-tool post-synthesis TCL hook that
  reports worst setup/hold slack right after `synth_design`, before any
  place-and-route. This is fast (order of a build's normal synthesis time,
  no extra P&R runtime) and useful as an early, repeatable regression
  signal on the leaves of a design (see "Estimate from leaves" above) —
  but synthesis-stage slack is measured on an unplaced, unrouted netlist,
  so it is optimistic/inaccurate versus the final routed result and must
  never be reported as "meets timing" or as an Fmax number. Label it
  explicitly as an estimate in any report or checker.
- Do not assume a project's `tsfpga-mcp`-style "analyze synthesis timing"
  flag covers this: such flags commonly check only clock-domain-crossing
  and pulse-width constraint violations, not setup/hold slack — verify
  what a given flag actually reports before relying on it, and add a
  custom post-synthesis TCL hook when a slack number is actually needed.
  When a real per-project Vivado build was run through `tsfpga-mcp`'s
  project-mode tools, retrieve the resulting number with
  `tsfpga_project_get_timing_report` rather than manually parsing
  `timing.rpt`; see `vivado-gotchas` for the hook-reliability caveats
  behind where that report data actually comes from.
- **Full timing closure** requires place-and-route (and, for signoff,
  the vendor's static timing analysis on the routed design). Reserve this
  for when there is a complete top-level design to place and route — a
  synth-only estimate on leaf/submodule netlists cannot substitute for it,
  since inter-module routing and placement congestion are exactly what it
  cannot see. State which of the two a given result is whenever timing is
  reported.

## Outputs

Write `synth/<module>/synth_report.md` containing:
- date/backend
- source set/top
- target chip/family
- generics
- synthesis result
- resources
- diagnostics

Backend-specific raw artifacts may be stored beside the report.

Never fabricate synthesis, timing, Fmax, utilization or power.


## Modern synthesis checks

Review synthesis diagnostics for:
- unintended latches
- inferred clocks/gated clocks
- unexpected RAM/DSP inference
- width truncation/constant propagation surprises
- unconstrained or missing clock intent
- high-fanout reset/control issues
- hierarchy unexpectedly optimized away when it matters for debug/constraints

For FPGA sign-off, portable Yosys/GHDL synthesis is an early feedback step.
Vendor implementation remains authoritative for timing closure and device mapping.

## Initialization verification

When RTL relies on declaration initial values instead of reset:
- verify the exact target family/backend
- inspect synthesis output for retained INIT/power-up semantics
- report any initialization dropped, transformed, or unsupported
- fail the portability assumption if the backend cannot prove the required state

A successful RTL compile is not proof of hardware power-up initialization.

## CDC synthesis/implementation checks

For designs containing CDC:
- verify synchronizer attributes survived synthesis
- verify CDC/timing constraints were loaded
- inspect tool CDC/timing warnings
- confirm asynchronous clock relationships are represented correctly
- confirm predefined CDC IP/macros were preserved/implemented as intended

Do not suppress CDC/timing warnings with broad exceptions.

## Vendor inference verification

When vendor attributes/primitives/IP are used, verify intended inference,
inspect ignored/unsupported-attribute warnings, confirm exact family/tool
support, and report any fallback that changes architecture or performance.
