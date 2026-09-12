---
name: vhtestgen
description: Generate a VUnit-first self-checking VHDL-2008 test project, with standalone GHDL fallback
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.
> **Layout note:** `ddoc/`, `rtl/`, `doc/`, `lib/` are the conventional tsfpga layout. When the project uses a different layout (e.g. `modules/<name>/{src,test,doc}`), follow the project's layout and keep the same file-naming conventions (`<ip>_arch.md`, `<module>_req.md`, `<module>.md`, `<module>.vhd`).

# VHDL Test Generator

Read `shared/ModernVHDL.md`, `shared/CodingStyle.md`, and `shared/HouseStyle.md`; they are authoritative for language revision, modern RTL practice, and concrete naming/style conventions.


Read `shared/Vunit.md` (VUnit-5 API: runner, phases, gate locks, checks, seeds, verification components) and `shared/McpToolPolicy.md`.

## Test-first (TDD) — default execution order

**Run this skill before `vhfill` for a given module, not after.** Per
`shared/Vunit.md` §15 ("Test-driven development (TDD) for RTL modules"),
the default project-wide policy is: generate the module's VUnit testbench
from its `<module>_req.md` first, confirm it is red (fails to elaborate
against a stub, or fails for the expected "not implemented yet" reason),
then hand off to `vhfill` to implement until that same testbench goes
green. When `vunit-mcp` is available, confirm the "fails to elaborate"
case with `vunit_elaborate` (recently added) rather than a full
`vunit_run_tests` — it runs a real GHDL elaboration pass and is the cheaper
way to establish the red baseline when the expected failure is structural
(missing entity/port/generic against a stub), reserving `vunit_run_tests`
for the "fails for the expected not-implemented-yet reason" case. Only fall back to writing the testbench after implementation when
the user explicitly asks for that order, or when retrofitting tests onto
already-existing, previously-untested RTL (a distinct, explicitly-flagged
case — record it as such, do not silently treat it as the default flow).

## Preferred verification architecture

If the project uses VUnit (a VUnit `run.py` exists, or `vunit_status`/`vunit_list_tests` succeed), always generate VUnit testbenches — never standalone ones. Authoring rules for generated runners/testbenches come from `shared/Vunit.md` (see the `vhunit` skill).

Infer the project's test conventions from the existing project:
- `run.py` registration style (VUnit-5 builtins, library dependencies)
- existing testbench structure under `tb/`
- test case naming, check style, and shared helpers
- simulator and output settings

If the conventions cannot be inferred (no existing tests to copy from, ambiguous or mixed structure, missing or broken `run.py`), ask the user which conventions to follow. Do not guess and do not invent a new structure silently.

If `vunit-mcp` is available:
1. call `vunit_status`
2. inspect project with `vunit_export_json`, `vunit_list_tests`, and `vunit_list_files`
3. preserve the existing `run.py` conventions
4. add tests in the same project style
5. validate discovery with `vunit_list_tests`

If VUnit is not present in the project, a standalone GHDL testbench may be generated instead (see Fallback standalone tests).

## Inputs

Use:
- `ddoc/<ip>_arch.md`
- module/IP docs
- top entity
- requirements
- register/protocol docs
- relevant precedent from `corvidex-mcp` when available (`search_hdl`/`search_vhdl` for conceptual precedent; prefer `find_definition`/`find_references` over grep once an exact port/generic/type name from the DUT is already known, e.g. confirming every consumer of a shared record type the test must construct)

## Recommended VUnit structure

```text
run.py
tb/
├── tb_<ip>.vhd
├── tb_pkg.vhd
└── ...
```

Project-specific structures may differ; follow the existing VUnit project.

## VUnit testbench rules

Authoring is delegated to `shared/Vunit.md` (authoritative VUnit-5 API) and
the `vhunit` skill: VHDL-2008, `vunit_context` + `runner_cfg`, named
`run("test_*")` cases, self-checking via `check_pkg`, a watchdog with a real
budget, seeded RNG, `run.py` in the VUnit-5 style with
`add_vhdl_builtins()`, and checker processes that respect the test phases
(gate locks / `runner_phase` events per `shared/Vunit.md` §7).

The testbench skeleton, `check_pkg` reference, randomization/queue/VC
references, and VUnit 4 vs 5 deltas live in `shared/Vunit.md` — do not
duplicate them here.

## Verification components (VCs)

Per `shared/Vunit.md` §12 ("Verification components (VCs)"):

- **Always use a premade VC/BFM; never hand-roll one unless it truly does
  not exist.** Built-in VUnit VCs (`axi_stream_master`/`axi_stream_slave`/
  `axi_stream_monitor`/`axi_stream_protocol_checker`, `axi_read_slave`/
  `axi_write_slave` + `memory_t`, `axi_lite_master`,
  `avalon_master`/`avalon_slave`/`avalon_source`/`avalon_sink`,
  `wishbone_master`/`wishbone_slave`, `uart_master`/`uart_slave`,
  `ram_master`, `bus_master_pkg`) and, where the project has hdl-modules,
  its `bfm.*` wrappers (`bfm.axi_read_slave`, `bfm.axi_write_slave`,
  `bfm.axi_slave`, `bfm.axi_lite_master`, `bfm.axi_stream_master`/
  `bfm.axi_stream_slave`, ...) cover every AXI4/AXI4-Lite/AXI4-Stream side
  a DUT can present. A hand-written slave/master/memory/response process
  is a defect to be fixed, not a shortcut: it re-implements handshake
  rules, backpressure randomization, data capture and response ordering
  that the BFM already gets right and keeps right. Real cost on this
  project: two AXI DMA testbenches shipped with hand-rolled AXI
  read/write slaves (own randomizer, own capture arrays, own BRESP
  queue) and had to be rewritten on `bfm.axi_read_slave`/
  `bfm.axi_write_slave` with `set_expected_word`/
  `check_expected_was_written`. When a BFM lacks one behavior (e.g. a
  non-OKAY `RRESP`/`BRESP` on one chosen beat -- VUnit's slave VC always
  answers OKAY), keep the BFM and add a *passive wire-level override of
  that one field* between BFM and DUT for that beat; the BFM still owns
  every handshake and data byte. Write a whole custom VC only when no
  built-in or hdl-modules one models the protocol at all.
- **Before reusing any higher-level BFM/VC wrapper** (e.g. an hdl-modules
  `bfm.*` wrapper around a raw VUnit VC), check its generic-range
  assertions against the actual interface width being tested — a wrapper
  built for the common case can silently be the wrong tool for a
  project-specific field. Concrete verified example: `bfm.axi_stream_master`/
  `bfm.axi_stream_slave` require `user_width mod 8 = 0` and will fail
  elaboration on a narrow non-byte-aligned `tuser` (e.g. a 1-2 bit
  SOF/border sideband) — use VUnit's raw `axi_stream_master`/
  `axi_stream_slave`/`axi_stream_pkg` directly in that case instead.
- **Prefer non-blocking VC calls for generating stimulus and verification
  data**: `push_axi_stream` (always non-blocking), `check_axi_stream(...,
  blocking => false)`, and non-blocking `pop_axi_stream(..., reference)` +
  a later `await_pop_axi_stream_reply`. Reserve the blocking forms for a
  directed test that must inspect a value before deciding what to drive
  next. Full verified blocking/non-blocking table in `shared/Vunit.md` §12.
- **If a custom VC genuinely is needed**, follow the handle-record +
  message-passing (`com`/`net`) pattern (not raw signal-poking from the test
  process) and implement any applicable VCI adapter (`as_stream`/`as_sync`,
  ...) so generic testbench code can still drive it. Full skeleton and the
  `vc_pkg.create_std_cfg` (id/logger/checker/unexpected-msg-policy) pattern
  in `shared/Vunit.md` §12 ("Writing a custom VC"). Expect this to be rare
  on this project — AXI4-Stream links are already covered by the raw
  built-in VC per the wrapper caveat above.
- **Give every VC instance driving/checking a real `tready`/`tvalid` link
  a non-zero randomized `stall_config` by default** (both the driving
  master and the checking slave), seeded from the test's own RNG. Always
  simulate with backpressure where the protocol supports it — this is
  what actually exercises the DUT's elastic/backpressure implementation,
  not just its steady-state datapath. Include one directed zero-stall
  (`null_stall_config`) sanity case too. Full API and rationale in
  `shared/Vunit.md` §12 ("Randomized backpressure via `stall_config`").

## Test plan

Cover:
- reset/default state
- nominal flow
- legal min/max values
- handshake/backpressure (via randomized `stall_config` on both VC sides, per "Verification components" above — not just a directed single-stall case)
- boundary/wrap/saturation
- specified error cases
- latency/pipeline behavior
- register access where present
- concurrent interface behavior where relevant

Maintain `tb/<ip>/tc_list.md` if the project uses that artifact, mapping test names to requirements.

## Waveform readiness

For tests likely to need signal-level debug, design them so `vunit_run_tests` can be invoked with waveform recording. Waveform files are consumed by `peeper-mcp`.

## Fallback standalone tests

Only when the project does not use VUnit, or the user explicitly requests standalone tests:
- generate standalone VHDL-2008 TB
- use assertions
- emit exactly one `[FINISH] PASS` or `[FINISH] FAIL`
- terminate via `std.env.finish`


## Modern verification rules

- Prefer independent named VUnit testcases.
- Use deterministic tests by default.
- For randomized tests, record/report the seed and make failure reproducible.
- Prefer scoreboards/reference models over checking implementation-internal signals.
- When the DUT implements a specifiable numeric/algorithmic transform
  (DSP, image/pixel processing, codec, protocol datapath), prefer a
  **Python reference model** (`<module>_model.py` next to `run.py`) as the
  single source of expected-behavior truth, hooked into the VUnit test
  via `pre_config` (generate stimulus + expected output into
  `output_path`) and `post_check` (compare the testbench's dumped output
  against the model's expected output). See `shared/Vunit.md`, "Python
  reference models (golden models)", for the exact `pre_config`/
  `post_check` signatures (both must explicitly `return True`) and the
  stimulus/expected file-exchange pattern. Do not hand-compute expected
  values inline in the testbench when a reference model is warranted.
  **Never check generated vectors into the repository.** Generate them on
  the fly, per test config, in `pre_config` into that test's
  `output_path`, and have the testbench read them back through the
  `output_path : string` generic VUnit fills automatically (no
  hand-built absolute `vectors_root` generic). Checked-in vectors are
  pure overhead: they churn the repo on every model edit, need one
  duplicate tree per generic configuration, silently drift from the
  model until someone remembers the regeneration step, and hide which
  Python parameters produced them. Real case: a `test/vectors/` tree
  that was checked in needed a second, near-duplicate
  `test/vectors_pe_rows_16/` tree the moment one generic got a second
  legal value -- the `pre_config` form needs one extra `add_config`
  line instead. Keep the generator importable and deterministic
  (fixed per-case seeds) so a failing test is reproducible without
  any stored artifact. A
  VHDL-side reimplementation of the same golden model is not a substitute
  for this exchange — see `shared/Vunit.md`'s "Two independent golden
  models are not a cross-check" for a real case where that gap (a
  transposed weight-packing index) survived 68/68 VHDL and 205/205 Python
  tests, all green, because neither suite ever consumed an artifact from
  the other.
- Test protocol invariants: stability under stall, ordering, no loss/duplication.
- Test reset during relevant traffic/state when allowed by the requirement.
- Test min/max/boundary generic configurations when practical.
- Add functional coverage only when it has a clear requirement mapping.
- Preserve existing OSVVM/UVVM infrastructure rather than replacing it.
- Generate waveforms for diagnosis, not as the primary pass/fail mechanism.

## CDC verification tests

When CDC logic is present:
- vary source/destination clock periods and relative phases
- exercise reset sequencing in both domains
- stress back-to-back events/transactions
- test FIFO overflow/underflow protections where relevant
- use assertions/checkers for handshake/data-stability assumptions

Simulation complements but does not replace static CDC/timing analysis.

## Generic configuration coverage

Exercise representative generic configurations: minimum valid, default/common,
boundary values, and enabled/disabled feature variants where applicable.
