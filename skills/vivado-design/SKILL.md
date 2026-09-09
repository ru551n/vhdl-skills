---
name: vivado-design
description: Design methodology and device-architecture reference for VHDL targeting AMD/Xilinx Vivado parts — UltraFast principles, inference templates, synthesis attributes, reset/clocking/CDC, XDC, timing closure, plus 7-series, UltraScale/UltraScale+ and Versal specifics, verified against the AMD guides
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.

# Vivado Design

Reference knowledge, not a workflow. Load this for any design that targets
an AMD/Xilinx part built with Vivado — from `vharch` (architecture and
block partitioning), `vhdesign` (module proposal), `vhfill` (RTL) and
`vhsynth` (design-time decisions behind a build) — and standalone when
reasoning about how RTL maps onto an AMD device. It is the positive
design methodology: what to write so that Vivado infers the intended
primitives, closes timing, and produces a clean CDC/DRC/methodology
report, grounded in AMD's own guides (cited by number as pointers; the
guides remain the authority). It is deliberately distinct from two things
that already exist:

- `skills/vivado-gotchas/SKILL.md` — Vivado/tsfpga *tool quirks* that
  fail silently (hook ordering, XDC parsing, out-of-context estimate
  blindness, template-sensitive inference). When a rule below has a
  known silent-failure mode, it points at the gotcha by section title.
- `shared/TimingAndResources.md` and `shared/DesignPatterns.md` —
  *vendor-neutral* timing-closure and resource rules and patterns. This
  skill is the Vivado-specific layer on top: how those rules map onto
  AMD's methodology, attributes, primitives and families. They are
  pointed to, not restated.

Read `shared/VendorPolicy.md` before using anything below marked as an
attribute, primitive or macro: every step below `PORTABLE_VHDL` must be
classified and justified.

Where a number below is family-wide it is stated; where it depends on the
exact part (counts of DSPs, BRAMs, buffers, SLRs, transceivers) it is not,
and the product table / data sheet for the part is the place to look.
Numbers were verified against the AMD document versions listed under
"Sources" at the end; when a newer guide disagrees, follow the guide.

---

## Part A — General Vivado design methodology

Applies to every AMD family. Each rule states the mechanism; the
mechanism is what makes it general.

### A1. UltraFast principles as they reach the RTL (UG949)

UG949 (UltraFast Design Methodology Guide) is organised around one idea:
timing closure is a property of the RTL and constraints, and the
implementation tools only recover what the RTL allows. Consequences for
the writer of VHDL:

- **Design for timing from the first line.** Budget LUT levels per stage
  for the target clock and speed grade, and read the logic-level
  histogram, not the worst path (`shared/TimingAndResources.md`,
  "Fundamentals"). Vivado's synthesis-only report already gives that
  histogram (`report_design_analysis -logic_level_distribution`), and it
  is the number that RTL controls; placement and routing add delay on top
  and cannot remove levels.
- **Register every hierarchical boundary, both directions.** UG949's
  out-of-context (OOC) and incremental flows, `KEEP_HIERARCHY`, Pblocks
  and SLR assignment all work per hierarchy; a hierarchy whose inputs or
  outputs are combinational cannot be timed, floorplanned or reused in
  isolation. A registered boundary also makes a leaf's OOC build honest
  — see `vivado-gotchas`, "A leaf entity's out-of-context Fmax is blind
  to cones that start at an input port".
- **Hierarchy is a tool boundary, not a synthesis boundary.** The
  default `synth_design -flatten_hierarchy rebuilt` optimises across
  boundaries and rebuilds names afterwards, so hierarchy costs nothing
  in QoR. Do not flatten manually for performance, and do not add
  `KEEP_HIERARCHY` "for structure" — it blocks cross-boundary
  optimisation (see A3).
- **Baseline before optimising.** UG949's baselining procedure: constrain
  clocks; run `check_timing`, `report_clock_networks`,
  `report_clock_interaction`; record WNS/TNS/failing endpoints after
  synthesis; only then add I/O delays and exceptions, implement, and
  re-record after each of opt/place/phys_opt/route; finish with
  `report_exceptions -ignored`. A design that fails timing at the
  synthesis baseline has an RTL problem, and no implementation strategy
  will fix it.
- **Control sets are a resource.** Every unique (clock, clock-enable,
  set/reset) triple is a control set, and flip-flops with different
  control sets cannot share a slice. UG949: acceptable when control sets
  are below 7.5 % of the CLB register count divided by 8; reduce
  recommended at 7.5–15 %; required above 15 % (`report_control_sets
  -verbose`). RTL creates control sets by putting a reset or an enable
  on a small group of registers; close `if` conditionals with an `else`
  on small groups, reserve clock enables for wide buses.
- **Avoid unnecessary pipelining on Versal** — UG1387 has a section by
  that name. The rule is general: every register stage costs a control
  set and latency; add stages where the histogram says, not everywhere.

### A2. HDL inference — the templates Vivado recognises (UG901 ch. "HDL Coding Techniques")

UG901 ships the templates; Vivado's language templates (Tools → Language
Templates → VHDL → Synthesis Constructs) are the same code. Match them.
Vendor-neutral inference rules (one memory signal per generate instance,
one array access per port) are in `shared/TimingAndResources.md` §7.

**Block RAM.**
- Synchronous read infers block RAM; an asynchronous read (array indexed
  outside the clocked process) infers distributed RAM. Both need a
  `process(clk)` write with `rising_edge`.
- Read-during-write mode comes from statement order alone: read before
  write in the process = READ_FIRST; write, then read the written data =
  WRITE_FIRST (UG901 marks this the recommended template); read guarded by
  `if we = '0'` = NO_CHANGE. Do not write `we`-dependent read logic
  that is not one of these three; it becomes a bypass mux in fabric.
- Simple dual-port with one clock and byte-write true dual-port are
  written with a **shared variable** in UG901's VHDL templates
  ("Correct Modelization with a Shared Variable"); a signal written from
  two processes is illegal VHDL and a signal written from one process
  with two textually different accesses degrades inference (§7 above).
- Byte-write enables infer when the data is arranged in equal columns
  of 8, 9, 16 or 18 bits (any column count); other widths get separate
  RAMs. Asymmetric ports with byte-write are **not** inferable — use
  `xpm_memory_*` for that combination.
- Output register: write a second registered stage after the RAM read
  (UG901 "Pipelining the RAM"); Vivado packs it into the primitive's
  `DO*_REG`. Keep the output register free of logic between RAM and
  register, and free of asynchronous reset. UG901's resettable-output
  template uses a synchronous reset on the output register only; the
  house rule (`shared/TimingAndResources.md`) is no reset on data at all.
- Initialisation: a constant aggregate default on the signal, or an
  `impure function` reading the file with `std.textio` into an array of
  `bit_vector` — UG901's VHDL example reads binary rows only ("integer or
  hex format do not work" for that example). Generate the file; do not
  hand-edit.
- For simple-dual-port RAM with a registered read address the write mode
  is chosen by `rw_addr_collision` (A3): `auto` gives WRITE_FIRST for
  timing, `no` gives NO_CHANGE for power.
- Deep memories cascade automatically; `cascade_height` limits the chain
  (UltraScale/Versal BRAM and URAM). Longer chains save fabric muxing
  and power; shorter chains save the cascade delay.
- UltraRAM (UltraScale+, Versal) is inferred with `ram_style = "ultra"` on
  a memory that is single-clock, has no initial contents, and resets its
  output register only to zero (no `SRVAL`); NO_CHANGE is its native mode.
- VHDL-2008 three-dimensional arrays and record-typed memories infer.

**Distributed RAM and ROM.**
- Distributed RAM = asynchronous read template above; use it for small,
  wide or many-ported memories (UG901 "Choosing Between Distributed RAM
  and Dedicated Block RAM"). Only SLICEM LUTs can hold it, so a design
  that infers a lot of LUTRAM competes with SRLs for the same LUTs.
- A block ROM needs a clocked read of a constant array and `rom_style =
  "block"` (UG901 "ROM Inference on an Array"); an unregistered read of
  a constant becomes LUTs.

**Shift registers (SRL).**
- Recognised shape: clock, optional clock enable, serial in, serial out
  — `shreg <= shreg(DEPTH-2 downto 0) & si;` or the equivalent loop.
  Nothing else: the SRL primitive has no reset, so any reset on the
  chain forces flip-flops. Do not reset delay lines.
- A dynamic delay is an indexed read `q <= shreg(to_integer(addr))`.
- `srl_style` on the **last** register of the chain chooses the
  reg/SRL/reg wrapping (A3); `-shreg_min_size` (default 3) is the
  extraction threshold.
- An SRL exposes only the addressed tap and the last stage (Q31/MC31
  for cascading); a chain whose intermediate stages are read elsewhere
  cannot be one SRL — expect flip-flops for those stages.

**DSP blocks.**
- Vivado infers multiply, multiply-add, multiply-subtract and
  multiply-accumulate into DSP blocks by default; plain adders,
  subtracters and accumulators stay in fabric unless `use_dsp = "yes"`.
- Register absorption: a single multiplier absorbs up to two register
  levels on each operand and after the product; a MAC absorbs two on
  operands, one after the multiply, one after the adder and one on the
  add/sub select. Write those registers as plain registers (no reset,
  or synchronous only) and they become A1/A2, B1/B2, M and P. `keep`
  on a register stops its absorption.
- Pre-adder: `(a + d) * b` with **signed** arithmetic and one extra bit
  of width on the pre-adder result; the D-port width per family is in
  Part B.
- The accumulate must be unconditional between multiply and add. A
  condition in between falls back to fabric for the whole array — see
  `vivado-gotchas`, "Vivado's DSP48E1 MACC inference is
  template-sensitive". Gate with the DSP's own clock enable (a registered
  `ce`) or with a `first`-flag load (`shared/DesignPatterns.md`,
  "Position-boundary flag").
- Asynchronous reset on any of those registers keeps them out of the
  block: DSP and block RAM internal registers have synchronous reset only
  (UG949 "Synchronous Reset vs. Asynchronous Reset", with a worked
  multiplier example).
- UG901 publishes no numeric size threshold below which a multiplier goes
  to LUTs; it is a tool heuristic, lowered by `-directive
  AreaMultThresholdDSP` or forced by `use_dsp`. Verify the count in the
  utilisation report; do not assume it from the RTL shape.
- INT8 packing (two products per block on DSP48E1/E2, three native on
  DSP58) is per family — Part B and `shared/DesignPatterns.md`, "Packed
  multiply".

**Counters, FSMs, latches.**
- UG901 has no counter template; a counter is an adder with a register.
  Compare against a registered terminal-count flag, not the wide value
  (`shared/TimingAndResources.md`, "Fundamentals").
- FSM recognition requires a reset or power-up state ("Specify a reset
  or power-up state for Vivado synthesis to identify a Finite State
  Machine, or set FSM_ENCODING to none"). Default encoding is `auto`;
  one-hot is chosen for up to 32 states. Look for `[Synth 8-802]
  inferred FSM` and `[Synth 8-3354] encoded FSM` in the log to confirm
  extraction, and register the outputs (Moore) so decoding is not in the
  datapath.
- `[Synth 8-327] inferring latch` is always a coding error (incomplete
  `if`/`case`); fix it, never waive it.
- A process without a sensitivity list cannot describe asynchronous
  control in Vivado; `process(all)` and `rising_edge` templates are the
  supported forms.

**Language level.** Vivado synthesises a subset of VHDL-2008 (enable with
`FILE_TYPE {VHDL 2008}` / `read_vhdl -vhdl2008`): `process(all)`,
if/case generate, unary reductions, matching operators, reading output
ports, generics in packages, unconstrained element types, block comments
— the set `shared/ModernVHDL.md` relies on. VHDL-2019 support is a newer,
smaller subset. Anything outside is "tool-dependent" per
`shared/SynthesizableVHDL.md` and must be verified with the toolchain.

### A3. Synthesis attributes (UG901 ch. "Synthesis Attributes")

Attributes are a last resort after structure. The order is: write the
template (A2) → check the utilisation report → only then add the
attribute, isolated next to the object, with a comment saying why
(`shared/VendorPolicy.md`). Facts that govern all of them:

- Attributes are case-insensitive. Unknown attributes are passed through
  to the netlist. A conflicting XDC `set_property` wins over the RTL
  attribute — except `KEEP` and `DONT_TOUCH`, which XDC cannot set and
  which must be in the RTL.
- An attribute on a hierarchy affects its boundary only, except
  `DSP_FOLDING`, `RAM_STYLE`, `ROM_STYLE`, `SHREG_EXTRACT` and `USE_DSP`,
  which also propagate to signals inside it.
- VHDL syntax: `attribute ram_style : string; attribute ram_style of
  mem : signal is "block";`. `max_fanout`, `cascade_height`,
  `retiming_forward` and `retiming_backward` are `integer`; the rest are
  `string` (`async_reg` also accepts `boolean`).

| Attribute | Values | On | Use it when |
|---|---|---|---|
| `ram_style` | `block`, `distributed`, `registers`, `ultra`, `mixed`, `auto` | memory signal or hierarchy | the report shows the wrong memory type after the template is right; `ultra` for URAM; `mixed` lets the tool split depth across types |
| `rom_style` | `block`, `distributed`, `ultra` (Versal) | constant array | a lookup table lands in LUTs and should be block ROM (needs the clocked read) |
| `ram_decomp` | `power`, `area` | memory | a deep memory should be split so one primitive is enabled at a time (A11) |
| `rw_addr_collision` | `auto`, `yes`, `no` | SDP RAM with registered read address | choose WRITE_FIRST bypass (`yes`) vs NO_CHANGE power (`no`); RTL only |
| `cascade_height` | integer (0/1 = off) | memory | limit BRAM/URAM cascade depth for timing, or lengthen it for power |
| `use_dsp` | `yes`, `no`, `simd`, `logic` (module level only) | signal > architecture > entity | put an adder/accumulator in a DSP (`yes`), keep a multiplier out (`no`), pack four 12-bit / two 24-bit adds (`simd`), map wide XOR into the DSP (`logic`) |
| `dsp_folding` | `yes`, `no` | entity/architecture, RTL only | two MACs joined by an adder should time-share one DSP at a faster clock (`dsp_folding_fastclock` names it) |
| `max_fanout` | integer (`-1` = none) | register or signal | local replication of a medium-fanout control net; never globally, never on resets/clock enables that place_design should handle — UG949 prefers manual or hierarchical replication for the largest nets |
| `shreg_extract` | `yes`, `no` | signal or entity | stop a delay line from becoming an SRL (e.g. to retime it or for `mark_debug`); precedence over `srl_style` and `-shreg_min_size` |
| `srl_style` | `register`, `srl`, `srl_reg`, `reg_srl`, `reg_srl_reg`, `block` | last register of the chain | the SRL's clock-to-out is on a critical path (`srl_reg`) or the input needs a fabric register (`reg_srl`) |
| `fsm_encoding` | `one_hot`, `sequential`, `johnson`, `gray`, `user_encoding`, `none`, `auto` (default) | state register | the tool's choice measured badly; `none` to stop extraction; `user_encoding` to keep the RTL codes |
| `fsm_safe_state` | `auto_safe_state`, `reset_state`, `power_on_state`, `default_state` | state register | illegal states must recover (SEU); `default_state` needs an `others`/`default` branch |
| `keep` | `true`, `false` | signal, RTL only, not ports | keep a net for debug or to stop absorption into a DSP/RAM; **synthesis only** — place/route may still remove it |
| `dont_touch` | `true`, `false` | signal, entity, architecture | keep through synthesis **and** implementation (forward-annotated); overrides other attributes; blocks retiming/replication/`gated_clock` conversion |
| `keep_hierarchy` | `true`, `soft`, `false` | entity/architecture (instance via XDC) | preserve a boundary for OOC, incremental or scoped constraints; UG901: `soft` is preferred over `true` (only constant propagation crosses); not on modules with I/O buffers or tristates |
| `async_reg` | `true`, `false` | synchroniser registers | every hand-written synchroniser (A6); implies `dont_touch`, forces adjacent placement, feeds `report_cdc`/`report_synchronizer_mtbf` |
| `mark_debug` | `true`, `false` | signal (net) | ILA probing (A12); stops replication/retiming/removal of that net |
| `extract_enable` | `yes`, `no` | register | force/forbid the CE pin (control-set pressure vs. LUT logic) |
| `extract_reset` | `yes`, `no` | register | force/forbid the R pin; **synchronous resets only** |
| `direct_enable` / `direct_reset` | `yes` | port/signal (nets in XDC) | the named signal must reach the CE/R pin directly (no LUT in front) |
| `retiming_forward` / `retiming_backward` | integer (0 = off) | signal/register | move a register across logic by N levels without enabling global retiming; not timing-driven; blocked by `dont_touch`, `mark_debug`, exceptions, instantiated cells |
| `black_box` | `yes` | entity/architecture | a module to be filled later (OOC/DCP) |
| `io_buffer_type` | `none` | top port, RTL only | suppress the automatic IBUF/OBUF on a port (netlist builds do this globally with `-no_iobuf`) |
| `iob` | `true`, `false` | register, RTL only | pack an I/O register into the pad |
| `clock_buffer_type` | `bufg`, `bufh`, `bufio`, `bufmr`, `bufr`, `none` | top clock port | the automatic BUFG is wrong for this port |
| `gated_clock` | `yes` | clock signal | mark legacy gated clocks for `-gated_clock_conversion` (A5) |
| `critical_sig_opt` | `true` | register with critical feedback | Shannon-decompose a self-feeding critical path at area cost |
| `-- synthesis translate_off/on` | pragma | region | remove simulation-only code; note the simulation/synthesis mismatch it creates |

Not attributes but the same decision surface: `synth_design -directive`
(`AreaOptimized_high/medium`, `AlternateRoutability`,
`AreaMapLargeShiftRegToBRAM`, `AreaMultThresholdDSP`, `FewerCarryChains`,
`PerformanceOptimized`, `RuntimeOptimized`, `LogicCompaction`,
`PowerOptimized_*`), `-global_retiming auto|on|off` (auto = on for
Versal, off otherwise; port-driven registers are not retimed in OOC),
`-max_bram`/`-max_dsp`/`-max_uram` (`-1` = part maximum),
`-control_set_opt_threshold`, `-resource_sharing`, `-fsm_extraction`,
`-shreg_min_size`, `-no_srlextract`, `-cascade_dsp auto|tree|force`,
`-mode out_of_context`. There is **no** `retiming` on/off attribute in
current UG901; per-object retiming is the two integer attributes above,
global retiming is the switch. Block-level overrides
(`BLOCK_SYNTH.STRATEGY`, `.RETIMING`, `.SHREG_MIN_SIZE`, …) apply per
hierarchy via `set_property` on the cell.

### A4. Reset methodology (UG949 ch. "Resets"; UG901 "Coding Guidelines")

Mechanism first: every AMD flip-flop primitive has one synchronous or
asynchronous set/reset pin (FDRE/FDSE sync, FDCE/FDPE async); DSP and
block-RAM internal registers have **synchronous reset only**; SRLs and
LUTRAM have **no reset**; and every distinct reset net is a control set.
The rules follow:

1. **Do not reset by default.** UG949: "Do not code the reset by default
   without ascertaining its real need." The Global Set/Reset (GSR)
   initialises every sequential cell at the end of configuration to its
   `INIT` (declaration initial value; zero unless FDSE/FDPE), so a global
   power-up reset is unnecessary. The house convention is resetless by
   default with declaration initial values —
   `shared/TsfpgaCodingConventions.md`, "Reset policy", and the decision
   rule in `shared/FpgaInitialization.md` (for Vivado targets condition
   3 of that rule is satisfied by GSR; the others are design questions).
2. **Reset control, not data.** Resets "might be required on the control
   path logic … generally less necessary on the data path". Reset
   `valid`, FSM state, counters, handshake flags. Never reset RAM
   contents, SRL delay lines, pipeline payload, DSP operand registers, or
   memory output registers (except a synchronous reset-to-zero where the
   protocol requires it).
3. **Synchronous, active-high.** UG949 recommends synchronous resets:
   they map directly to the primitive pins and to DSP/BRAM internal
   registers, and a synchronous reset that does not fit a primitive can
   be remapped into the D-path logic (control-set remap); an
   asynchronous one cannot. UG901: describe clock-enable, set and reset
   as active-High; an active-low reset costs an inverter LUT on every
   control set. The house form is `reset : in std_ulogic := '0'`
   (`shared/TsfpgaCodingConventions.md`).
4. **Why asynchronous resets hurt, specifically:** registers with an
   asynchronous reset are not absorbed into DSP or block RAM (UG949's
   multiplier example: AREG/BREG/MREG all 0, product emulated with
   fabric registers plus LUT2s), cannot be remapped when control sets are
   merged, and their assertion can corrupt LUTRAM/SRL/BRAM contents
   through the surrounding logic. Retiming (`-global_retiming`,
   `retiming_forward/backward`) moves registers across logic; a register
   with a reset carries a constraint on its value that retiming must
   preserve, so a reset on a datapath register blocks the move
   (`shared/TimingAndResources.md`, "Structure registers so the tool can
   move them"). If a legacy interface forces an asynchronous reset,
   synchronise its **release** to the clock (`xpm_cdc_async_rst`) and keep
   it off the datapath.
5. **Reset synchroniser structure.** One per clock domain: register the
   incoming reset through an `xpm_cdc_sync_rst` (synchronous reset in,
   `DEST_SYNC_FF` stages, default 4) or `xpm_cdc_async_rst` (asynchronous
   assert, synchronised deassert), then fan out from a registered copy
   per block. A single reset flip-flop reaching the whole design is a
   timing path (`shared/TimingAndResources.md` §8); let the tool
   replicate a register you provide, or replicate hierarchically. Reset
   crossing between domains is a CDC (A6, `shared/CdcPolicy.md`, "Reset
   crossing").
6. **Global-reset-release / device start-up.** GSR and GWE are released
   at the end of configuration asynchronously to every user clock; UG949
   "Controlling and Synchronizing Device Startup": if the release is not
   synchronised to a domain, or the clock is faster than GWE can be
   released safely, "portions of the design can go into an unknown
   state". Remedies, in UG949's order: clock enables or a synchronised
   reset on the state-holding logic (FSMs, counters), gating the clock at
   an instantiated buffer's CE until the MMCM has locked, delaying reset
   release by several cycles through an `ASYNC_REG` synchroniser chain,
   and the Clocking Wizard's "Safe Clock Startup". Treat MMCM `LOCKED`
   as an asynchronous signal: synchronise it before using it as a reset
   term (A5).

### A5. Clocking (UG949 ch. "Clocking Guidelines"; UG472 / UG572 / AM003)

- **Generate clocks in an MMCM/PLL**, instantiated through the Clocking
  Wizard or the primitive; never leave inputs floating, never tie `RST`
  to ground, use `LOCKED` (synchronised) in the reset sequence. Clocks
  derived from MMCM/PLL outputs are auto-derived generated clocks in
  timing (A7); rename them with `create_generated_clock -name` rather
  than re-defining them.
- **Drive the global clock network from the right buffer.** 7-series:
  BUFG (global, 32 per device/SLR), BUFH (horizontal, per clock region),
  BUFR (regional, with divide), BUFIO (I/O clock tree within a bank),
  BUFMR (extend regional clocks over three regions). UltraScale/Versal:
  the general network is BUFGCE / BUFGCE_DIV / BUFGCTRL only (no
  BUFH/BUFR in the primitive list), sourced from a GCIO pin, an MMCM/PLL,
  a BUFG_GT, or — not recommended — fabric. Use `BUFGCE_DIV` rather than
  a second MMCM output when dividing a clock that must stay synchronous
  with its parent (no phase-error penalty on the CDC); parallel
  `BUFGCE_DIV`s must share CE and RST.
- **Clock enables, not gated clocks.** Fine-grained gating in HDL
  "disrupts functionality and prevents efficient use of the dedicated
  clocking resources"; a LUT in a clock path is `TIMING-14` in
  `report_methodology`. Write `if ce = '1' then` inside `rising_edge`
  (`shared/DesignPatterns.md`, "Clock enable"). For power, gate at the
  buffer: `BUFGCE`/`BUFGCTRL` CE (UltraScale also `BUFGCE_DIV`,
  `BUFG_GT`; 7-series `BUFHCE`/`BUFR`/`BUFMRCE`). Legacy gated clocks:
  `synth_design -gated_clock_conversion auto` plus the `gated_clock`
  attribute; `dont_touch`/`keep_hierarchy`/`mark_debug` on the path
  block the conversion.
- **Clock muxing** only with `BUFGCTRL`/`BUFGMUX`, and UG949 recommends it
  for asynchronous clocks only, because the two branches' insertion
  delays cannot be balanced.
- **Avoid local (non-global) clocks**: unpredictable skew, poor
  routability. Vivado inserts a buffer for fabric-driven clocks with more
  than ~30 loads; `report_clock_utilization` finds the rest.
- **Clock-domain planning.** Decide the domains in `vharch`: one domain per
  independent rate, everything else a synchronous divided/multiplied
  clock from the same MMCM. Every additional asynchronous domain is a
  CDC class, a clock group and a reset synchroniser. Up to 24 clocks
  route into one clock region on UltraScale/Versal (12 horizontal clock
  lines per region on 7-series); more distinct clocks than that in one
  area is a placement problem.
- **Clock roots and skew.** On large or SSI designs set
  `USER_CLOCK_ROOT` on the net driven by the buffer (verify with
  `report_clock_utilization -clock_roots_only`); use `CLOCK_DELAY_GROUP`
  only to match delay between clocks that cross synchronously; global
  clocks driving more than one SLR belong in the centre SLR.
- **Verify** with `report_clock_networks` (unconstrained clock source
  points), `check_timing` (`no_clock`, `unconstrained_internal_endpoint`),
  `report_methodology -checks [get_methodology_checks {TIMING-* XDC*}]`
  and `report_clock_utilization`.

### A6. Clock-domain crossing (UG949 ch. "Clock Domain Crossing"; UG906; UG974/UG953 XPM)

Policy and classification are in `shared/CdcPolicy.md`; the project's own
proven blocks come first there (hdl-modules' `resync_*` and
`asynchronous_fifo` ship `async_reg` and scoped constraints — A13). The
Vivado layer:

- **XPM_CDC first** when no project block fits. `library xpm; use
  xpm.vcomponents.all;` (non-project flows need `auto_detect_xpm`).
  Available in both UG953 (7-series) and UG974 (UltraScale): `xpm_cdc_single`
  (level), `xpm_cdc_array_single` (independent bits, not a coherent bus),
  `xpm_cdc_gray` (counter/pointer), `xpm_cdc_pulse`, `xpm_cdc_handshake`
  (coherent bus, `WIDTH` 1–1024, optional destination handshake),
  `xpm_cdc_sync_rst`, `xpm_cdc_async_rst`. There is no
  "low-latency handshake" XPM in the current library guides. Key
  parameters: `DEST_SYNC_FF` 2–10 (default 4), `SRC_INPUT_REG`,
  `INIT_SYNC_FF`, `SIM_ASSERT_CHK`. XPMs are recognised by
  `report_synchronizer_mtbf` and get special placement in `place_design`;
  the default `DEST_SYNC_FF` is conservative on 7-series — iterate with
  `report_synchronizer_mtbf` on UltraScale+ if latency matters.
- **`async_reg` on every hand-written synchroniser register** (both
  stages, and any further stage counted in the MTBF). It implies
  `dont_touch`, keeps the chain in one slice, and is what `report_cdc`
  uses to tell a synchroniser from an unsynchronised crossing (`CDC-2`
  is "missing ASYNC_REG").
- **Crossing classes → structure** (`shared/DesignPatterns.md`, "CDC"
  sections): level → 2+ FF; pulse → toggle or `xpm_cdc_pulse`; coherent
  bus → handshake with held data or `xpm_cdc_handshake`; stream → async
  FIFO (`xpm_fifo_async`, hdl-modules `asynchronous_fifo`, Gray-coded
  pointers); reset → `xpm_cdc_*_rst`. Never synchronise a bus bit-by-bit
  (`CDC-4`/`CDC-6`), never put logic (`CDC-10`) or fan-out (`CDC-11`) in
  front of the first stage, never drive a synchroniser from more than one
  clock (`CDC-12`).
- **Constraints are half the CDC.** Which one is correct:
  - `set_clock_groups -asynchronous` between clock domains that have
    **no** timed relationship anywhere. It disables analysis on every
    path between the groups, has the highest priority, and **overrides**
    `set_max_delay` — including the `set_max_delay -datapath_only` that
    XPM_CDC macros and hdl-modules blocks carry in their own scoped
    constraints. UG949: "XPM CDCs are not compatible with the
    set_clock_groups constraint". UG903: to constrain and report specific
    paths between asynchronous clocks, use timing exceptions only, not
    clock groups.
  - `set_max_delay -datapath_only -from … -to …` on a specific crossing:
    bounds the latency (skew between bits of a Gray pointer or handshake
    bus) while ignoring clock skew and hold; this is what the macros use.
  - `set_bus_skew` for a multi-bit bus crossing under a handshake, where
    the requirement is skew between bits rather than latency.
  - `set_false_path -from/-to` only where the crossing is otherwise
    proven safe and only in the stated direction; never a broad
    domain-to-domain false path to silence a report
    (`shared/CdcPolicy.md`, "Constraints are part of the CDC
    implementation").
  Priority (UG903): `set_clock_groups` > `set_false_path` >
  `set_max_delay`/`set_min_delay` > `set_multicycle_path`; more specific
  object types win (pins > cells > clocks) and `from/through/to` beats
  `from/to`. Run `report_exceptions -ignored` after adding any.
- **Gates.** `report_clock_interaction` must show every asynchronous pair
  as "Max Delay Datapath Only", "Partial False Path" or "User Ignored" —
  never "Timed (unsafe)" (red) or "Partial False Path (unsafe)".
  `report_cdc` must have no Critical: `CDC-1` (1-bit unsynchronised),
  `CDC-4` (multi-bit unsynchronised), `CDC-7` (async clear/preset
  unsynchronised), `CDC-10`–`CDC-14`; review every Warning (`CDC-2`,
  `-5`, `-6`, `-8`, `-15` CE-controlled, `-16` MUX-controlled, `-26`
  LUTRAM read/write collision). Waive (`create_waiver`) only with the
  structural reason in the waiver description; the hdl-modules blocks
  ship exactly such waivers. `report_methodology` `TIMING-9`/`-10`/`-11`
  flag unknown CDC, missing synchroniser property and an inappropriate
  `-datapath_only`.

### A7. Constraints — XDC (UG903; UG949 ch. "Design Constraints")

- **What belongs where.** Timing constraints and physical constraints in
  separate files; per-module constraints in their own file **scoped** to
  the entity (`read_xdc -ref <entity>` — what tsfpga's
  `scoped_constraints/` does — or `SCOPED_TO_REF`/`SCOPED_TO_CELLS`
  properties); project-level clocks, I/O, clock groups and floorplan in
  the project constraints. A scoped file is evaluated with
  `current_instance` set to each instance, so cell/pin names are relative
  to the entity and clocks defined elsewhere remain visible; `get_ports`
  inside it resolves to the top-level port or the boundary pin. A scoped
  file shipped with a reusable block must therefore reference only that
  block's own register names, and only names that survive synthesis (a
  reason to `keep`/name registers deliberately in CDC blocks).
- **Ordering.** Files are read in list order (project mode) or `read_xdc`
  order; with IP: user EARLY → IP EARLY → user NORMAL → IP LATE (the
  `_clocks.xdc`, clock-dependent) → user LATE; `PROCESSING_ORDER`
  (`EARLY`/`NORMAL`/`LATE`) on the file object. Recommended sequence
  inside a file: primary clocks, virtual clocks, generated clocks, clock
  groups, bus skew, I/O delays; then false paths, max/min delay,
  multicycle, case analysis, disable timing. A clock referenced before it
  is defined is an error; a generated clock defined before its master is
  an error. See `vivado-gotchas`, "Netlist (out-of-context) synthesis
  specifics" for how processing order decides which of two files
  touching the same object wins.
- **Clocks.** `create_clock` on input ports (and 7-series GT output
  pins); everything downstream of MMCM/PLL, `BUFGCE_DIV`, `BUFG_GT`, GT
  common/channel, `ISERDES` and bit-slice primitives is **auto-derived**;
  UG949 says rely on auto-derivation. A user `create_clock` on an object
  that has an auto-derived clock replaces it (no more auto clock there).
  Use `create_generated_clock` only for clocks the tool cannot derive
  (fabric dividers, which should not exist — A5) or to rename. See
  `vivado-gotchas`, "A user `create_clock` on a plain port can silently
  produce zero clocks".
- **I/O delays are mandatory** for every timed pin: `set_input_delay`
  (max = external Tco + board data delay + clock delay to the external
  device − clock delay to the FPGA; min analogous) and
  `set_output_delay`, against a virtual clock when the external
  waveform differs. `TIMING-18` flags missing I/O delay; `check_timing`
  lists unconstrained endpoints. For a pinnable timing harness constrain
  with zero delay, not false paths (`shared/TimingAndResources.md` §1).
- **Exceptions are last** (`shared/TimingAndResources.md`, "Prefer
  structure to constraints"). A multicycle path must be genuinely
  multicycle by construction (registered enable that provably holds the
  endpoint for N cycles), documented in the RTL, and constrained with
  the matching `-setup`/`-hold` pair from UG903's multicycle examples —
  a `-setup` alone moves the hold check too. `set_false_path` only on
  structurally impossible
  paths, static configuration registers that are proven quiescent, or
  the stated direction of a safe CDC. Every exception you add: run
  `report_exceptions -ignored` and `report_methodology`.
- **`set_property` on nets/cells** is how attributes are applied
  post-synthesis (`ASYNC_REG`, `MAX_FANOUT`, `USER_SLR_ASSIGNMENT`,
  `USER_CLOCK_ROOT`, `CLOCK_BUFFER_TYPE`, `IOSTANDARD`, `PACKAGE_PIN`);
  `KEEP`/`DONT_TOUCH` cannot be set from XDC. `USED_IN_SYNTHESIS` /
  `USED_IN_IMPLEMENTATION` gate a file to one stage (synthesis-only for
  attributes that shape the netlist, implementation-only for
  placement); a `DONT_TOUCH` in a synthesis XDC still propagates.
- XDC is an SDC-subset parser, not Tcl — see `vivado-gotchas`, "XDC
  constraint files only execute a restricted command subset".

### A8. Timing-closure methodology (UG949 ch. "Timing Closure"; UG906; UG1292 quick reference)

**Report sequence, every time, in this order:**

1. `report_timing_summary` — WNS/TNS/WHS/THS per clock, `check_timing`
   section, unconstrained endpoints. WNS is the primary metric.
2. `report_design_analysis -logic_level_distribution` (after synthesis)
   and `-timing -max_paths N` (after place/route) — logic levels per
   path, plus the per-path breakdown of clock skew, net delay vs. logic
   delay. Also `-complexity` (Rent exponent: 0–0.65 normal, 0.65–0.85
   high for blocks over ~15 k instances, > 0.85 very high; average
   fanout < 4 normal, 4–5 high, > 5 very high) and `-congestion`
   (levels 1–2 none, 3–4 mild, 5 moderate, 6 high, 7–8 likely
   unroutable; "5 or higher often impacts QoR").
3. `report_high_fanout_nets` — the largest control nets and their
   fanout.
4. `report_qor_assessment` (score 1: will not complete implementation;
   2: completes but not timing; 3: likely not; 4: likely meets; 5:
   meets; ±1) and `report_qor_suggestions` — the tool's own ranked
   fixes, including ML strategies (top-3 from
   `report_qor_suggestions` is UG1292's recommended strategy sweep).
5. `report_methodology` (TIMING-*, XDC*) and `report_control_sets`.

**Reading the failure signature:**

| Signature in the reports | Cause | Fix |
|---|---|---|
| Logic delay dominates; many LUT levels; slack barely moves from synthesis to route | logic depth | RTL: split the stage, tree the reduction, decode early (`shared/TimingAndResources.md`, Fundamentals, §2, §3) |
| Net delay dominates on a net with hundreds/thousands of loads | fan-out | replicate the driver (manual/hierarchical > `max_fanout` local > `opt_design -hier_fanout_limit`); a > 5000-load net is tolerable only at ≤ 125 MHz with < 13 levels (UG949) |
| Net delay dominates on low-fanout nets; congestion ≥ 5 in the region; long detours | congestion / routability | reduce utilisation in the region (LUT-combining, control-set merge), `AlternateRoutability` synthesis directive, spread with Pblocks, `-directive` on place_design; check `report_design_analysis -congestion` top cells |
| Path crosses SLRs; large skew term; Laguna in the path | SSI placement | register both sides of the crossing, `USER_SLR_ASSIGNMENT`, dedicated pipeline (A10) |
| Clock skew large, `TIMING-6/-7/-8` (no common clock/node/period) | clocking | same buffer type/root, `CLOCK_DELAY_GROUP`, `BUFGCE_DIV` for synchronous divide, fix the constraint if the relation is false (A5, A6) |
| Hold violations after route; `TIMING-15/-16` large hold/setup requirements | wrong exception or CDC constraint | `report_exceptions`, fix the `-hold` on multicycles, remove the false path |
| Passes synthesis estimate, fails only after route | fan-out or congestion, not depth | as above; a synthesis-only estimate is a proxy for depth only (`shared/TimingAndResources.md` §1) |

**Fixes, in order of preference** (UG949 iterates RTL+constraints →
synthesis options → implementation directives):

1. **Structure.** Pipeline, tree, decode early, register configuration
   boundaries, replace the wide compare, move the register in RTL. This
   is the only fix that lowers the logic-level histogram and the only one
   that survives a tool upgrade.
2. **Attributes** on the object (A3): `srl_style`, `use_dsp`,
   `ram_style`, `retiming_forward/backward`, local `max_fanout`,
   `extract_enable/reset`.
3. **Synthesis directives**: `-directive PerformanceOptimized` /
   `AlternateRoutability` / `FewerCarryChains`, `-global_retiming on`,
   `-control_set_opt_threshold`, `BLOCK_SYNTH.*` per hierarchy.
4. **Implementation directives and strategies**: `opt_design`,
   `place_design -directive` (UG1292: try up to ten placer directives
   plus `phys_opt_design` iterations — `Aggressive*`, `Alternate*`),
   `phys_opt_design` (also post-route), `route_design -directive`,
   overconstrain a critical clock by ≤ 0.5 ns with
   `set_clock_uncertainty` during place, `group_path -weight`, and the
   incremental flow (`read_checkpoint -incremental`, UG904) once the
   design is within reach so later minor changes do not reshuffle.
5. **Floorplan** (A10) — last, and only for the residual placement
   problem.

**The plateau.** Fixing the reported critical path reveals the next one;
several consecutive fixes may move WNS by nothing while being necessary.
Judge a rework by whether its target path is gone from the histogram,
not by the immediate WNS delta; once several paths are within a few
hundred picoseconds of each other, single-path fixes are exhausted and
the remaining question belongs to place-and-route strategies, not to
more RTL iteration. The full argument, with a worked progression, is in
`vivado-gotchas`, "A leaf entity's out-of-context Fmax is blind …",
corollaries. Delegate reading a critical path and choosing the
restructuring to a strong model (`vivado-gotchas`, "Always delegate
timing analysis and timing fixes to a strong model").

### A9. Resource usage (UG949 ch. "Reviewing Utilization"; UG901; UG474/UG574/AM005)

- **Utilisation thresholds** (UG949, verified wording): overall
  utilisation above 70–80 % → reduce; avoid LUT **and** DSP/RAMB/URAM both
  above 80 %; keep LUT below ~60 % when the hard-macro utilisation is
  high; on SSI parts one SLR above ~85 % of a resource hurts even when
  the device average is 70 %. There is no per-resource table in current
  UG949 — the thresholds live inside `report_failfast` /
  `report_qor_assessment` and are adjusted per device. Do not quote
  fixed percentages beyond these.
- **LUT/FF balance.** Slices pair LUTs and flip-flops 1:2 (7-series 4+8,
  UltraScale/Versal 8+16 per slice); a design that is FF-heavy relative
  to that ratio packs poorly only if control sets fragment it (A1). A
  design that is LUT-heavy is depth-bound; pipelining costs flip-flops
  that are otherwise free.
- **MUXF7/F8/F9 and carry chains** are the free wide structures: a 16:1
  mux is four LUT6 plus F7/F8 in one slice (7-series), up to 32:1 with
  F9 on UltraScale; Versal removed them and cascades LUT to LUT
  instead. Adders/comparators use the carry chain (CARRY4 / CARRY8 /
  LOOKAHEAD8), one LUT level plus a chain whose length is the width;
  `FewerCarryChains` trades chain use for LUTs when routing is the
  problem. UG1788/UG1387: a `LOOKAHEAD8` is reported as several logic
  levels but costs one to two LUT delays — read Versal histograms with
  that in mind.
- **Distributed vs. block RAM** (UG901 "Choosing Between …"): distributed
  for small (tens of words), wide, asynchronously-read or many-ported
  memories and for register files; block RAM above that, always with
  the output register; URAM (where present) for large single-clock
  buffers with 72-bit-wide access. Distributed RAM and SRLs both consume
  SLICEM LUTs, which are a fraction of all LUTs (about one third on
  7-series, one half on Versal CLBs) — check `LUTRAMs` and `SRLs` in the
  utilisation report separately from `Logic LUTs`.
- **DSP packing.** The block's port widths decide how many narrow
  products fit (Part B: two 8-bit products on DSP48E1/DSP48E2 by
  designer-side packing with a shared operand; three native 9×8 terms on
  DSP58). Choose the shift from the *real* port width of the family
  (`shared/DesignPatterns.md`, "Packed multiply"), unpack before
  summation, pin the DSP count in a build checker. `use_dsp = "simd"`
  packs four 12-bit or two 24-bit adds (two 24-bit on DSP58 also) when
  no multiplier is needed; `-cascade_dsp` and `dsp_folding` are the
  other DSP-count levers.
- **Sums are leaf-additive.** FF, BRAM, URAM and DSP counts add exactly
  across a composition; use that to detect a lost inference in the top
  report (`vivado-gotchas`, "A timing fix in one leaf can change another
  leaf's RAM/DSP inference"; `shared/TimingAndResources.md` §7).
- **Control sets** (A1) and **high-fanout nets** are utilisation
  problems before they are timing problems: `report_control_sets`,
  `report_high_fanout_nets`, `opt_design -control_set_merge`
  / `-merge_equivalent_drivers`, `CONTROL_SET_REMAP`.

### A10. Floorplanning and physical (UG949 ch. "Floorplanning", "SLR"; UG906)

- **Pblocks last and small.** UG949: limit floorplanning to the portions
  that need it; keep a Pblock within one clock region; do not overlap;
  minimise nets crossing Pblock boundaries; re-test without Pblocks after
  a tool upgrade. Legitimate uses: assign a block to an SLR, separate two
  congested blocks, keep a CDC or clocking structure local.
- **SSI devices (multi-SLR).** Every SLR crossing goes through Laguna
  TX/RX registers on a super-long line (SLL). Register both sides of a
  crossing with plain flip-flops (no reset, no CE — they must be
  packable into Laguna: `USER_SLL_REG` marks them; ignored if the pin
  does not cross or fans out to more than one SLR). Wide buses above
  ~250 MHz need three stages (source SLR, Laguna, destination SLR); AXI
  register slices with auto-pipelining do this for AXI. Soft placement:
  `USER_SLR_ASSIGNMENT` on cells (SLR name or an arbitrary group tag),
  `USER_CROSSING_SLR` on a register-to-register net with fanout 1; hard:
  an SLR Pblock (`resize_pblock -add SLR0`). `phys_opt_design
  -slr_crossing_opt` re-times crossings. Clocks that span SLRs are
  rooted in the centre SLR. Check `report_utilization -slr` — a full
  SLR is worse than a full device.
- **Clock-region awareness.** A clock region is the placement unit:
  a fixed column count of CLBs, BRAM, DSP (per-family sizes in Part B)
  and up to 24 (UltraScale/Versal) or 12 (7-series) clocks. A block that
  needs more BRAM/DSP than one region holds is spread across regions
  whatever the Pblock says; size Pblocks on `CLOCKREGION` ranges, not on
  Laguna sites.
- **I/O placement.** Pins are chosen per bank: one `IOSTANDARD` voltage
  family per bank (HR ≤ 3.3 V, HP ≤ 1.8 V on 7-series/UltraScale; XPIO/HDIO
  on Versal), clock-capable pins for clock inputs, DCI/ODELAY only in
  HP. `PACKAGE_PIN`/`IOSTANDARD` go in the physical XDC. Put I/O
  registers in the pad (`iob`) or the bit-slice logic, and keep the
  first fabric register close — an I/O bank on the far side of the die
  from its logic is a clock-region problem before it is a timing one.

### A11. Power (UG949 "Power"; UG907)

- Clock enables reduce dynamic power on wide registers; gate clocks at
  the buffer CE (`BUFGCE`, `BUFGCE_DIV`, `BUFG_GT`) when a whole domain
  idles — never in fabric.
- Block RAM: drive `EN` low when idle (the biggest single lever; the RAM
  burns power on every enabled cycle regardless of address);
  `cascade_height = 4` or `ram_decomp = "power"` so one primitive at a
  time is selected (UG949 quotes roughly halved dynamic power); URAM and
  UltraScale BRAM have a `SLEEP` pin for long idle periods — check UG573
  / AM007 for the wake-up latency before using it.
- `power_opt_design` (UG907) inserts BRAM enable and output-register CE
  gating automatically (array enable, write enable and output-register
  CE when nothing is written or read); pre-place saves the most and may
  cost timing, post-place preserves timing; exclude cells with
  `set_power_opt`; **not supported on Versal**. Cascaded BRAMs are
  address-disabled by `opt_design`.
- DSP: keep operand registers enabled only when valid (a registered CE
  on A/B); an idle multiplier with toggling inputs is dynamic power.
- Unused hard blocks (transceivers, unused SLRs, PS peripherals) are
  powered down by their own configuration; unused I/O banks should be
  left unpowered or configured per the family's pinout guide.
- `report_power` per hierarchy after routing is the measurement; anything
  before routing is an estimate of activity, not of power.

### A12. Debug and verification hooks (UG949 "Debugging", "DRC Closure", "Out-of-Context Synthesis"; UG906)

- `mark_debug` on the signal in RTL (or `set_property MARK_DEBUG true
  [get_nets …]`) keeps the net from being replicated, retimed or
  removed; then insert the ILA with the Set Up Debug wizard / netlist
  insertion (most flexible), or instantiate `ila`/`vio` in HDL. Debug
  nets are `dont_touch` for the rest of the flow — remove the attributes
  before the final timing run or budget for them.
- Gates on every build: `report_drc` (Critical Warnings become Errors at
  bitstream) and `report_methodology` (TIMING-*/XDC*/CDC-related checks;
  `set_property SEVERITY` on a DRC check only with a written reason).
  `report_cdc` and `report_clock_interaction` are gates (A6).
- **OOC synthesis** of leaves (`synth_design -mode out_of_context`, or
  tsfpga's `VivadoNetlistProject`) gives fast area numbers and a
  register-to-register timing **upper bound**; `-mode out_of_context`
  suppresses I/O buffer inference; `HD.CLK_SRC` tells the tool where the
  clock buffer will sit; port-driven registers are not retimed in OOC.
  Its blind spots are the subject of `vivado-gotchas`, "A leaf entity's
  out-of-context Fmax is blind to cones that start at an input port" and
  "Enabling timing analysis changes synthesis itself".
- **Incremental compile** (`read_checkpoint -incremental` before
  `place_design`, UG904) reuses placement/routing from a reference
  checkpoint; use it after the design is near closure and changes are
  local, not as a way to hide a structural problem.
- OOC/`keep_hierarchy soft`/`black_box` are the building blocks of a
  bottom-up flow; every module used that way needs a registered boundary
  (A1) and its own scoped constraints (A7).

### A13. tsfpga integration notes (tsfpga 13.x; hdl-modules 6.x)

Verified against the tsfpga source (`tsfpga/module.py`,
`tsfpga/constraint.py`, `tsfpga/vivado/project.py`,
`tsfpga/vivado/build_result_checker.py`, `tsfpga/vivado/tcl.py`).

- **Scoped constraints**: `<module>/scoped_constraints/<entity>.tcl` (also
  `entity_constraints/` and `hdl/constraints/`; `.tcl` or `.xdc`). The
  file stem must equal an entity in the module's synthesis files
  (`validate_scoped_entity` raises otherwise). Applied as `read_xdc -ref
  <entity> [-unmanaged] <file>` with `PROCESSING_ORDER LATE` — so they
  are evaluated per instance, after the project constraints, and may
  reference only that entity's own cells. This is where a reusable
  block's `set_max_delay -datapath_only`, `set_false_path`, `set_bus_skew`
  and `create_waiver` belong (A6, A7).
- **Project constraints**: `tsfpga.constraint.Constraint(file,
  used_in_synthesis=True, used_in_implementation=True,
  scoped_constraint=False, processing_order="normal")` in the
  `VivadoProject(constraints=[...])` list — clocks, I/O, clock groups,
  physical. `processing_order` is the `PROCESSING_ORDER` property (A7).
- **Projects**: `VivadoProject(name, modules, part, top=name+"_top",
  generics, constraints, tcl_sources, build_step_hooks, default_run_index,
  impl_explore, **other_arguments)` for the real top-level build (synthesis
  through bitstream, `synth_only`/`from_impl` in `build()`);
  `VivadoNetlistProject(..., analyze_synthesis_timing=False,
  build_result_checkers=[...])` for out-of-context leaf area (and an
  optional synthesis-only Fmax estimate — read `vivado-gotchas`,
  "tsfpga's netlist-build timing-estimate flag" before trusting it);
  `VivadoIpCoreProject` for IP generation only. `build_step_hooks` are
  `BuildStepTclHook(tcl_file, hook_step)` with steps such as
  `STEPS.SYNTH_DESIGN.TCL.POST`, `STEPS.ROUTE_DESIGN.TCL.PRE` — and see
  `vivado-gotchas`, "Post-synthesis TCL hooks cannot reliably query the
  constraint/clock state".
- **Checkers** (`tsfpga.vivado.build_result_checker`): `TotalLuts`,
  `LogicLuts`, `LutRams`, `Srls`, `Ffs`, `Ramb36`, `Ramb18`, `Ramb`
  (36 + 18/2), `Uram`, `DspBlocks`, `MaximumLogicLevel`, each with
  `LessThan`/`EqualTo`/`GreaterThan`. Names are Vivado's own
  `report_utilization -hierarchical` column headers. Pin structural
  invariants exactly (`DspBlocks(EqualTo(n))`, `Ramb36(EqualTo(n))`) and
  give FF/LUT headroom; a `MaximumLogicLevel` checker is the cheapest
  depth gate a leaf can carry.
- **Netlist builds** invoke `synth_design -top … -part … -assert
  -no_iobuf` (not `-mode out_of_context`); ports keep RTL names.
- **hdl-modules** (`resync`, `fifo` modules) is the project-library layer
  that `shared/CdcPolicy.md` puts first: `resync_level`,
  `resync_level_on_signal`, `resync_slv_level`, `resync_pulse`,
  `resync_counter`, `resync_twophase` (coherent bus; the former
  `resync_slv_level_coherent`), `resync_twophase_handshake`,
  `resync_cycles`, `resync_sticky_level`, `resync_rarely_valid`,
  `asynchronous_fifo` — with `async_reg` in the RTL and scoped
  `set_max_delay -datapath_only` / `set_false_path` / `set_bus_skew` /
  `create_waiver` constraints. There is no reset-synchroniser entity in
  hdl-modules; use `xpm_cdc_sync_rst`/`xpm_cdc_async_rst` or a project
  block for that.
- `build_fpga.py` conventions and the MCP wrappers around them are in
  `vivado-gotchas` ("MCP preference") and `vhsynth`.

---

## Part B — Device / architecture specifics

Same headings per family so they can be compared. Per-part quantities
(how many DSPs, BRAMs, buffers, SLRs, transceivers) are deliberately
absent — they are in the family data sheet / product selection guide
named under each family.

### B1. 7-series (Spartan-7, Artix-7, Kintex-7, Virtex-7, Zynq-7000)

Guides: UG474 (CLB), UG479 (DSP48E1), UG473 (memory), UG472 (clocking),
UG471 (SelectIO), DS180 (overview / product tables), UG585 (Zynq-7000
TRM), UG953 (libraries incl. XPM).

**CLB / slice.** Two slices per CLB; per slice four LUT6 (each usable as
one 6-input or two 5-input functions with shared inputs) and eight
storage elements, of which four can be latches instead of flip-flops
(then the other four are unusable). SLICEL vs SLICEM: only SLICEM LUTs
can be distributed RAM or SRL; roughly two thirds of slices are SLICEL.
Carry: `CARRY4`, four bits per slice, cascaded up a column (not across
SLRs). Muxes: F7AMUX/F7BMUX/F8MUX give four 4:1 (one LUT each), two
8:1 (two LUTs) or one 16:1 (four LUTs) per slice. SRL: one SLICEM LUT is
an `SRLC32E` (1–32 taps) or two SRL16s; the four LUTs cascade to 128
deep inside a slice; longer chains go through fabric. Distributed RAM
per SLICEM (LUTs used): 32×1S (1), 32×1D (2), 32×2Q / 32×6 SDP (4),
64×1S (1), 64×1D (2), 64×1Q / 64×3 SDP (4), 128×1S (2), 128×1D (4),
256×1S (4) — 256 bits per CLB.

**Block RAM.** `RAMB36E1` = 36 Kb, or two independent `RAMB18E1`.
Port width TDP: ×1…×36 per port (RAMB36), ×1…×18 (RAMB18). SDP: ×64/×72
(RAMB36), ×32/×36 (RAMB18). Write modes WRITE_FIRST (default),
READ_FIRST, NO_CHANGE per port — NO_CHANGE is not available in SDP mode.
Byte-write enables: 4 (RAMB36 TDP), 8 (RAMB36 SDP), 2/4 (RAMB18);
not with the dual-clock FIFO or ECC modes. Optional output register
(`DO*_REG`, +1 cycle). Cascade: two RAMB36 to one 64K×1 without fabric
(64K×1 mode only). ECC: one 64-bit SEC-DED block per RAMB36 (SDP ×64).
Hard FIFOs `FIFO18E1`/`FIFO36E1` (standard and first-word-fall-through).
**No UltraRAM.**

**DSP48E1.** 25×18 two's-complement multiplier (43-bit product,
sign-extended to 48); 25-bit pre-adder on the A path (`A ± D`, D
register) — so a pre-added operand is 25 bits; 48-bit three-input
adder/subtracter/accumulator and 48-bit logic unit (ALUMODE); SIMD
`ONE48` / `TWO24` / `FOUR12` (multiplier must be unused); pattern
detector with mask (convergent rounding, overflow/underflow,
auto-reset for terminal count); cascades ACIN/ACOUT (30), BCIN/BCOUT (18),
PCIN/PCOUT (48), CARRYCASCIN/OUT and MULTSIGNIN/OUT (96-bit accumulate
across two blocks). Registers: A1/A2, B1/B2, AD, C, D, M, P plus
OPMODE(7)/ALUMODE(4)/INMODE(5)/CARRYINSEL(3) control registers. **No
native INT8 mode.** INT8 packing rule: two 8-bit products per block by
placing two 8-bit signed weights in the 25-bit port as `w_hi·2^S + w_lo`
and the shared 8-bit activation on the 18-bit port; S must be at least
the low product's width (16 bits for signed 8×8) and `8 + S ≤ 25`, so
16 ≤ S ≤ 17; the low product is signed, so its sign borrows one from
the high field — correct on unpack, every cycle, before any
accumulation (`shared/DesignPatterns.md`, "Packed multiply"). Accumulate
in the 48-bit P path only after unpacking, or keep the packed
accumulator short enough that the fields cannot overlap.

**Clocking.** 32 global clock lines / BUFG per monolithic device (per
SLR on SSI parts); per clock region 12 BUFH (12 horizontal clock lines),
4 BUFR, 4 BUFIO, 2 BUFMR. CMT = one `MMCME2_ADV` + one `PLLE2_ADV`
(up to 24 CMTs per device, one per clock region). MMCM: seven O counters
(CLKOUT0–6, CLKOUT0–3 also inverted), fractional divide on CLKOUT0 and
CLKFBOUT, fine/dynamic phase shift, CLKOUT6 cascades into CLKOUT4. PLL:
six outputs (CLKOUT0–5), no fractional/inverted outputs.
BUFGCE/BUFGCE_1/BUFGMUX/BUFGMUX_CTRL are `BUFGCTRL` presets. Clock
region = 50 CLBs tall, one 50-pin I/O bank, ten RAMB36 and 20 DSP48E1
per column, one CMT, one GT quad.

**I/O / SERDES.** HR banks (1.2–3.3 V) and HP banks (1.2–1.8 V, DCI and
ODELAY); Spartan-7/Artix-7 HR only, Kintex-7/Virtex-7 HR + HP (Virtex-7
HT: HP only). `ISERDESE2`/`OSERDESE2`: up to 8:1 SDR, 10:1/14:1 DDR with
master/slave (input) or width expansion (output). Transceivers:
Spartan-7 none; Artix-7 GTP; Kintex-7 GTX; Virtex-7 GTX/GTH (and GTZ on
HT) — counts per part in DS180.

**Speed grades.** −1, −2, −3 at 1.0 V (−3 as extended-temperature −3E);
low-voltage variants are family-specific: −1LI (0.95 V, Spartan-7/
Artix-7/some Kintex-7), −2LI (0.95 V, larger Kintex-7), −2LE (1.0 V or
0.9 V for Artix-7/Kintex-7; 1.0 V only for Virtex-7); plus −1Q
(Spartan-7 expanded temperature) and −2GE (Virtex-7 faster
transceivers). Check DS180 Table "speed grade / voltage" for the part.

**Family-specific design advice.** The 25-bit A path is the packing
limit (S ≤ 17); the 18-bit shift of the UltraScale recipe does not fit.
Four LUTs per slice and CARRY4 mean a W-bit carry chain spans W/4
slices, twice the UltraScale span — budget adder width per stage
against the period (`shared/TimingAndResources.md`, "Carry chains
count"). 12 clocks per region is the tightest clocking budget of the
three families. No URAM: buffers beyond a few Mb are external memory.
Two-thirds SLICEL: a design heavy in LUTRAM/SRL runs out of SLICEM
before it runs out of LUTs. The largest Virtex-7 parts are SSI (DS180
lists the SLR count per part) — SLR rules (A10) apply there.

### B2. UltraScale and UltraScale+ (Kintex/Virtex UltraScale; Artix/Kintex/Virtex UltraScale+, Zynq UltraScale+ MPSoC, RFSoC)

Guides: UG574 (CLB), UG579 (DSP48E2), UG573 (memory), UG572 (clocking),
UG571 (SelectIO), UG570 (configuration; SSI table), UG1026 (migration
from 7-series), WP486 (INT8 packing), DS890 (overview / product tables),
DS892/DS893/DS922/DS923/DS925 (family data sheets), UG1085 (Zynq
UltraScale+ MPSoC TRM), UG974 (libraries incl. XPM).

**CLB / slice.** One slice per CLB; eight LUT6 (one 6-input or two
5-input functions each) and sixteen flip-flops (two per LUT, Q1/Q2).
Control sets within a slice: **two clocks and two set/resets** (one
each per half, A–D and E–H, eight flip-flops each) and **four
clock-enable groups** (per half × per Q1/Q2); synchronous vs.
asynchronous set/reset is chosen per group of eight, set vs. reset per
flip-flop; when one register in a CE group uses CE, the other three
must too. So the flip-flops of one slice can carry at most two
reset nets and four enable nets — this is the mechanism behind the
control-set rules in A1. Latches: all eight in a half or none. Carry:
`CARRY8`, eight bits per slice, splittable into two 4-bit chains
(carry-in at bit 0 and at the midpoint). Muxes: F7MUX (pairs), F8MUX
(bottom/top), F9MUX — four 8:1, two 16:1 or one 32:1 per slice. SRL:
any SLICEM LUT is an `SRLC32E` (or two SRL16), cascading to 256 deep
within the slice via MC31/Q31. Distributed RAM per SLICEM up to 512
bits: `RAM32X1S`, `RAM32M16` (octal), `RAM64X1S/D`, `RAM64M8`,
`RAM128X1S`, `RAM256X1D`, `RAM512X1S` and the width variants in UG574.

**Block RAM.** `RAMB36E2` = 36 Kb, or two `RAMB18E2`. TDP widths 32K×1
… 1K×36 (36 Kb), 16K×1 … 1K×18 (18 Kb); SDP 512×72 (36 Kb) / 512×36
(18 Kb). WRITE_FIRST / READ_FIRST / NO_CHANGE — **all three now allowed
in SDP mode** (change from 7-series). Byte-wide write enables
(`WEA[3:0]`, `WEBWE[7:0]`; not in ECC mode). Optional output registers.
**Built-in data cascade** bottom-up within the BRAM column, without
fabric, within one clock region (cascade output only). 64-bit SECDED ECC
per 36 Kb block (64-bit SDP only). Hard `FIFO18E2`/`FIFO36E2` with
asymmetric ports (×4/×9/×18/×36/×72), standard and FWFT, synchronous
reset, cascadable. `SLEEP` pin with data retention; unused blocks are
power-gated at 18 Kb granularity.

**UltraRAM (`URAM288`, UltraScale+ only).** 288 Kb, 4K×72, single
clock, two ports each doing one read *or* write per cycle (internally
single-port cells, A then B within a cycle), **fixed 72-bit width**,
byte-wide write enables, SECDED ECC per port, no `INIT` (zero after
configuration), cascade of data/address/control bottom-up "unlimited in
a single column within an SLR" (16 URAM per clock region per column;
crossing clock regions costs extra pipeline registers, crossing columns
costs fabric), **up to four pipeline stages per port** (input, output,
`IREG_CAS`/`OREG_CAS`), `SLEEP` plus auto-sleep. Presence varies by
part: Kintex/Virtex UltraScale none; Artix UltraScale+ none; Spartan
UltraScale+, Kintex UltraScale+ (KU3P has none), Zynq UltraScale+ MPSoC
(ZU2/ZU3/ZU6/ZU9 have none) some; Virtex UltraScale+ and RFSoC all —
DS890 per part. Inference: `ram_style = "ultra"` on a single-clock,
uninitialised memory whose output reset (if any) is to zero; the
`cascade_height` attribute and `-max_uram_cascade_height` bound the
chain; UG901's URAM default chain limit is eight.

**DSP48E2.** 27×18 two's-complement multiplier (A input 30 bits, A:B
48), **27-bit pre-adder** (A ± D, D register), 48-bit three-input
ALU with 96-bit accumulate across two slices, SIMD dual-24 / quad-12,
**wide XOR** (eight 12-bit up to one 96-bit; 192-bit over two slices —
`use_dsp = "logic"`), pattern detector (convergent rounding, counter
auto-reset, overflow/underflow, 96-bit AND/NOR), cascades
ACIN/BCIN/PCIN/CARRYCASCIN, registers AREG/BREG 0–2 (A1/A2, B1/B2 with
`ACASCREG`/`BCASCREG`), DREG, ADREG, MREG, PREG, CREG and the control
registers. **No native INT8 mode.** INT8 packing rule (WP486): pack two
8-bit signed weights *through the pre-adder* into the 27-bit path as
`p = (a << 18) + b` (a on the D port shifted, b on the A port, or vice
versa), put the shared 8-bit activation on the 18-bit B port; the
45-bit product is `(a·c << 18) + b·c`, two fields of two's-complement
terms. The shift is 18 (any S with 16 ≤ S ≤ 19 fits the 27-bit port;
WP486 chooses 18), leaving **two guard bits** above the 16-bit low
product, so at most **seven** packed products can be accumulated inside
the DSP before the low field can corrupt the high one; WP486 spends one
extra DSP per seven for 14 MACs per 8 DSPs, i.e. 1.75× — or unpack every
cycle in fabric and accumulate outside (`shared/DesignPatterns.md`,
"Packed multiply"), which removes the bound. The low field is signed:
add its sign bit back into the high field when unpacking. Fully
pipelined DSP48E2 Fmax is in the family data sheet (DS923 lists it per
speed grade and voltage; cascades crossing a clock-region centre at the
low-voltage grade may run below it).

**Clocking.** Per clock region: **24 `BUFGCE`, 8 `BUFGCTRL`, 4
`BUFGCE_DIV`**, sharing the region's 24 routing tracks; 24 horizontal
and 24 vertical routing plus 24 + 24 distribution tracks; `BUFG_GT` per
GT quad (24, with `BUFG_GT_SYNC`; divide 1–8). BUFH/BUFR/BUFMR/BUFIO are
**removed** (UG1026 retargets BUFH→BUFG/BUFGCE, BUFIO→BUFG,
BUFR/BUFMR→`BUFGCE_DIV`). CMT = **one MMCM + two PLLs**, one per I/O
bank: `MMCME3`/`PLLE3` on UltraScale, `MMCME4`/`PLLE4` on UltraScale+
(same primitives, E4 suffix). Clock region: 60 CLBs tall with the
horizontal clock spine at the centre, 24 DSP48E2 and 12 RAMB36 per
column, 52 I/O per bank, four GTs pitch-matched.

**SSI / SLR.** Stacked-silicon parts (UG570 table): Kintex UltraScale
KU085/KU115; Virtex UltraScale VU125/VU160/VU190/VU440; Virtex
UltraScale+ VU5P/VU7P/VU9P (3 SLRs), VU11P (3), VU13P (4), VU35P (2),
VU37P (3) and the HBM parts. Crossing rule (UG949): on UltraScale+ map a
register-to-register crossing to a Laguna `TX_REG` driving a Laguna
`RX_REG` directly (on UltraScale only one side can be Laguna); six
TX/RX registers per Laguna site, paired 120 rows apart; mark the two
cells with `set_property USER_SLL_REG TRUE [get_cells {tx rx}]`
(ignored if the net does not cross or fans out to more than one SLR);
three stages for wide buses above 250 MHz. Available SLLs per boundary:
`get_property NUM_TOP_SLLS [get_slrs SLR0]` — no fixed figure in the
guides.

**I/O / SERDES.** Banks are HP, HR **and HD** (HD on Artix/Spartan
UltraScale+ and Kintex UltraScale+ Gen 2). HR 1.2–3.3 V without DCI; HP
up to 1.8 V with DCI/ODELAY; 52 pins per bank. `ISERDESE3`/`OSERDESE3`:
1:2 or 1:4 SDR, 1:4 or 1:8 DDR — **no 1:10/1:14**; higher ratios use the
bit-slice logic (`RX/TX_BITSLICE`, native mode) which brings its own
auto-derived clocks (A7). Transceivers: Kintex UltraScale GTH (some
GTY); Virtex UltraScale GTH + GTY; Kintex UltraScale+ GTH/GTY (Gen 2
GTY); Virtex UltraScale+ GTY plus GTM (58 G) on some; Artix UltraScale+
GTH/GTY; Spartan UltraScale+ GTH; Zynq UltraScale+ MPSoC GTH (+GTY on
larger EG/EV) plus four PS-GTR; RFSoC GTY — counts per part in DS890.

**Speed grades / voltage** (DS890 table). UltraScale: −1/−2 at 0.95 V,
−3E at 1.0 V, Kintex −1LI at 0.95 or 0.90 V. UltraScale+: −1/−2 at
**0.85 V**, −3E at 0.90 V, −1LI/−2LE at 0.85 or **0.72 V**, RFSoC
−1LI/−2LI at 0.72 V. "E"/"I" are temperature grades, not speed; a
"−1L" part at the low voltage performs roughly like the base grade at
nominal voltage (DS892 note). The 0.72 V operating point is where the
DSP cascade and URAM Fmax footnotes apply.

**Family-specific design advice.** Eight LUTs and `CARRY8` per slice
halve the slice count of a wide adder relative to 7-series, and F9
gives a 32:1 mux in one slice — but the two-reset/four-enable slice
means a register group with a third reset net or a fifth enable net
spills into another slice: group by control set. The 27-bit port is
what makes two-per-DSP INT8 packing work with guard bits (7-series has
none); the wide XOR makes CRC/parity/LFSR cheap in DSPs. URAM (where
present) is the buffer for anything above a few Mb — 72-bit fixed,
single-clock, no init, so plan the width and the pipeline (4 stages)
in `vharch`. BRAM cascade is free within a column and clock region;
`cascade_height` is the timing/power lever. 24 BUFGCE per region is
generous, but every BUFGCE_DIV must share CE/RST with its siblings
(A5). SSI parts: register both sides, plan SLR assignment per block in
the architecture, keep no SLR above ~85 % of any resource (A9, A10).
Migration from 7-series: UG1026 (buffers, SelectIO, DSP48E1→E2 are
compatible; RAM SDP write modes gain NO_CHANGE).

### B3. Versal adaptive SoC (AI Core, AI Edge, Prime, Premium, HBM; Gen 2)

Guides: AM005 (CLB), AM004 (DSP58), AM007 (memory), AM003 (clocking),
PG313 (NoC and integrated DDR controller), AM009 / AM020 (AI Engine /
AIE-ML), AM011 (TRM), PG352 (CIPS), UG1387 (Versal design methodology),
UG1344 (libraries), DS950 (overview / product tables), DS957/DS958 etc.
(family data sheets).

**CLB / slice.** A CLB is **four slices, 32 LUT6 and 64 flip-flops** —
four times an UltraScale CLB (8 LUTs + 16 FFs per slice). LUTs are
dual-output (one 6-input or two 5-input with shared inputs). Carry is
**`LOOKAHEAD8`**, eight bits per slice; it generates only the odd carry
outputs and the LUTs generate the even ones, and chains may start at bit
0 or 4. **`MUXF7`/`MUXF8`/`MUXF9` are gone**; wide muxes are built from
LUTs using a dedicated LUT→LUT cascade (O6 into the next LUT's A5
input, A→B→…→H within the slice). Exactly 50 % of a CLB's LUTs are
LUTRAM/SRL-capable (SLICEM: four logic LUTs plus four LUTRAM or SRL);
SRL32 or two SRL16 per LUT, 64-bit RAM per LUT. Control sets are coarser
in clock/reset (4 clocks, 4 SR, 16 CE per CLB; clock and SR shared by
the 8 LUT/FF pairs on one carry chain; CE per 4 flops; Q1 and Q2 share
CE — unlike UltraScale) — group registers by reset/enable more
deliberately than on UltraScale. **IMUX registers**: registers embedded
at the interconnect/CLB boundary (192 IMUX + 64 bypass registers per
CLB, also at hard-block inputs), with CE and sync/async reset but no set
and no init-to-1; used for hold fixing and as free pipeline stages. Not
present on the first-generation VC1902/VC1802/VC1702/VC1502/VE1752/
VM1802/VM1502/VM1402/VM1302 nor on the Gen 2 series — check AM005 for
the part; do not design a pipeline that depends on them.

**Block RAM.** `RAMB36E5` (36 Kb: 4K×9, 2K×18, 1K×36, 512×72 SDP) and
`RAMB18E5` (18 Kb, up to 512×36 SDP); TDP/SDP/ROM; cascade
(`CASCADE_ORDER`, CASDIN/CASDOUT); one 64-bit ECC per 36 Kb block
(standard / encode-only / decode-only); registered or latched output plus
optional output register. AM007 lists no hard FIFO primitive — use
`xpm_fifo_*`.

**UltraRAM.** `URAM288E5` / `URAM288E5_BASE`: 288 Kb, 4K×72, single clock,
two ports each one operation per cycle, up to four pipeline stages,
column-height cascade, ECC; typically 24 per clock region per column;
present on most Versal devices (DS950 per part). Other on-chip memory:
Accelerator RAM (XRAM, 4 MB with ECC, three 256-bit AXI ports from the
PL, some AI Edge parts) and Multiport RAM (MPRAM, Premium VP1902 only).
External DDR4/LPDDR4/DDR5/LPDDR5 is reached through the integrated
memory controllers (DDRMC) on the NoC — not through soft controllers in
fabric.

**DSP58.** 27×24 two's-complement multiply with 27-bit pre-add
(`A` 34, `B` 24, `C` 58, `D` 27 bits), **58-bit** ALU/accumulator
(116-bit by cascading two), SIMD dual-24 / quad-12, 58-bit logic unit,
wide XOR up to 116 bits, 23-bit right shift, backwards compatible with
DSP48E2. Modes (attribute `DSP_MODE`, default `INT24`):
- **`INT8` — native**: a three-element dot product with accumulate or
  post-add, `a·b = a0·b0 + a1·b1 + a2·b2`, with `a_i` 9-bit signed and
  `b_i` 8-bit signed, from six *independent* inputs (unsigned 8-bit
  operands by zeroing the sign bit). **Three INT8 products per DSP58,
  no shared operand required, no designer-side packing or shift.**
  Whether a given RTL sum-of-three-products infers this mode is a
  UG901 (Versal DSP inference) question for the tool version in use;
  instantiating `DSP58` with `DSP_MODE = "INT8"` is the certain route.
  Verify the DSP count and mode in the utilisation report either way.
- **`DSPFP32`**: floating-point multiply-accumulate; multiplicand and
  multiplier binary32 or binary16, adder always binary32,
  round-to-nearest-even only. No bfloat16 in the DSP58 (bfloat16 exists
  in AIE-ML, not in the fabric DSP).
- **`DSPCPLX`**: 18×18 complex multiply-accumulate using two adjacent
  DSP58s, optional conjugation.
Cascades ACOUT/BCOUT/PCOUT/MULTSIGNOUT/CARRYCASCOUT; programmable input,
product and output pipelining as before.

**Clocking.** No CMT: clock generation is split into `MMCME5` + `DPLL`
blocks (near XPIO banks, extra DPLLs near HDIO and GT columns), `XPLL`
(two per XPIO bank, four outputs, no fractional; `X5PLL` on Gen 2) and
the global clock buffers `BUFGCTRL` / `BUFGCE` / `BUFGCE_DIV` (plus
`BUFG_GT`, `BUFG_PS` for up to 12 PS clocks, `BUFG_FABRIC` for
high-fanout *non-clock* nets — higher jitter, no deskew — and the
`MBUFG*` leaf-dividing variants). `MMCME5`: sigma-delta fractional
divide, two deskew phase detectors, no inverted outputs. Clock regions
carry 24 horizontal distribution tracks (24 clocks per region), 12
horizontal and 24 vertical routing tracks; GC pins: 4 per XPIO bank, 2
per HDIO bank.

**NoC.** A hard, statically routed (by the Vivado NoC compiler at design
time) packet network: NMUs (ingress, AXI 32–512-bit or AXI4-Stream
128–512-bit, with asynchronous CDC and rate matching to the fabric
clock) and NSUs (egress) as `NMU512`/`NSU512` for PL, `NMU128`/`NSU128`
fixed 128-bit for CIPS and AI Engines, `DDRMC` NSUs and HBM NMU/NSU;
4×4 full-duplex packet switches with eight virtual channels and
credit-based flow control; horizontal NoC of four channels and vertical
NoC of two. It is configured in a block design (CIPS + NoC IP), never
inferred from HDL, and it replaces the AXI interconnect for memory and
PS traffic (WP562). Design consequence: the fabric does not route
memory traffic across the die; give each fabric master its own NMU with
a registered AXI boundary, size bursts for the 128-bit packet, and treat
the NMU clock crossing as the CDC it is.

**AI Engines.** Out-of-fabric VLIW SIMD vector processors in a tiled
array (AIE in AI Core/Premium; AIE-ML in AI Edge and some AI Core/HBM;
AIE-ML v2 in AI Edge Gen 2), 32 KB data memory per AIE tile (AIE-ML
doubles it and adds memory tiles, adds bfloat16, doubles INT8/16
throughput, drops native INT32/FP32), programmed in C/C++ through Vitis
(ADF graphs, UG1076/UG1079). PL interface: per column six streams AIE→PL
and eight PL→AIE, each 64-bit configurable as 32/64 or paired to 128
bits, AXI4-Stream at the PL clock with an asynchronous crossing in the
interface tile; nominal AIE clock ~1 GHz (grade-dependent). For a VHDL
designer the AI Engine array is a peer accelerator reached through
AXI4-Stream PLIOs and the NoC; the compute stays there, the PL does
pre/post-processing, DMA and glue.

**PS / boot.** The CIPS IP is mandatory to boot (PMC runs the PLM);
Gen 1 PS: dual Cortex-A72 + dual Cortex-R5F; Gen 2: Cortex-A78AE /
Cortex-R52. PS–PL AXI: `M_AXI_FPD`, `M_AXI_LPD` (PS→PL), `S_AXI_FPD`,
`S_AXI_LPD`, `S_CCI_FPD`/`S_AXI_GP2` (ACE-Lite), `S_ACE_FPD` (full
ACE), `S_ACP_FPD` — all with a maximum data width of **128 bits**; there
are no Zynq-style `S_AXI_HP*` ports, PL-to-DDR bandwidth goes through
NoC NMUs. PL clocks `PL0_REF_CLK…` and PL resets are configured in CIPS.

**Speed grades / voltage.** Ordering code = speed (−1/−2/−3) + voltage
class (L/M/H) + static-power screen (S standard / L low) + temperature
(E/I/Q/M); Vivado's device string encodes speed, voltage (`LP`, `MP`,
`HP`, `MHP`, `LHP`, `MM`, `LLI`), temperature (`-i/-e/-m`) and screen
(`-S/-L`), e.g. `-2MP-e-S`. VCCINT: H 0.88 V, M 0.80 V, L 0.70 V (LLI
0.725 V); `MHP`/`LHP` are overdrive. The letter "P" in `-2MP` is not
documented as "production" — do not expand it. Per-family tables in
DS957 (AI Core), DS958 (AI Edge), etc.

**Family-specific design advice.** Design methodology changes when hard
blocks exist: memory bandwidth, PS traffic and cross-die transport move
to the NoC (fabric AXI interconnect shrinks to local glue); dense INT8
inference belongs in AI Engines or DSP58 `INT8` mode (3 products/DSP,
no packing arithmetic), FP32 in `DSPFP32`; the 58-bit accumulator
removes most guard-bit gymnastics. `-global_retiming` is on by default
for Versal — write resetless datapath registers so it can work. Wide
muxes cost LUT cascades, not F7/F8 — budget a LUT level per 2:1 beyond
what one LUT6 absorbs. Read `LOOKAHEAD8` logic levels as 1–2 LUT delays.
Control sets are coarser: plan reset/enable groups per 8-FF carry
group. UG1387 "Avoid Unnecessary Pipelining" — the CLB is bigger and the
interconnect (and, where present, IMUX registers) faster; measure before
adding stages. `power_opt_design` is not available.

### B4. Zynq-7000 and Zynq UltraScale+ MPSoC — PS/PL boundary (brief)

- **Zynq-7000** (UG585, PG082 `processing_system7`): two 32-bit AXI
  general-purpose masters (`M_AXI_GP0/1`, PS→PL), two 32-bit GP slaves
  (`S_AXI_GP0/1`), four high-performance slaves (`S_AXI_HP0–3`, 32- or
  64-bit, to DDR/OCM through FIFOs), one 64-bit `S_AXI_ACP` (coherent
  through the L2). Four PL clocks `FCLK_CLK0–3` (0.1–250 MHz, each
  optionally on a BUFG) and resets `FCLK_RESET0–3_N`. Treat every
  `FCLK` as an independent clock domain unless the wizard derives them
  from the same PLL and you constrain them as related; treat
  `FCLK_RESETn` as an asynchronous, active-low reset to be synchronised
  per domain and inverted into the house active-high form (A4). HP ports
  are 64-bit max: bandwidth to DDR is HP-port count × 64 bits × clock —
  size DMA widths to match, register the AXI boundary, and keep AXI
  address/data paths off the critical path with register slices.
- **Zynq UltraScale+ MPSoC** (UG1085 Table 35-1, PG201
  `zynq_ultra_ps_e`): PS→PL masters `M_AXI_HPM0/1_FPD` and
  `M_AXI_HPM0_LPD` (32/64/128-bit); PL→PS slaves `S_AXI_HPC0/1_FPD`
  (coherent via CCI, **128-bit only**), `S_AXI_HP0–3_FPD` (32/64/128),
  `S_AXI_LPD` (32/64/128), `S_AXI_ACP_FPD` (128), `S_AXI_ACE_FPD` (128,
  two-way coherent). AXI4 with bursts limited to 16 beats (AXI3 inside
  the PS); each slave interface has separate read and write PL clocks
  with asynchronous crossings inside the PS. Four PL clocks `PL_CLK0–3`
  from independent generators (`PL_REF_CLKx`); PL resets are the EMIO
  GPIO bits [95:92] presented as `pl_resetn0–3`. PS-sourced clocks enter
  the PL as ordinary clock ports; the PS IP inserts a `BUFG` per PL
  clock (PG201, `C_FCLK_CLK0_BUF`-style parameters). Same rules: each
  PS clock is its own domain, `pl_resetn` is asynchronous and
  per-domain synchronised, the 128-bit HP/HPC path is the DDR bandwidth
  unit. Full-power-domain (FPD) vs. low-power-domain (LPD) ports have
  different latencies and power states; put latency-sensitive control
  on LPD and bulk data on HP/HPC.
- **Versal**: see B3 — no HP ports; NoC.
- In `vharch`, the PS is a fixed peer: its ports, clocks and resets are
  the IP's external interface, its AXI widths and clock rates are
  requirements, and the PS block design (Vivado IP integrator) is
  `VENDOR_IP` (`shared/VendorPolicy.md`), wrapped behind a project entity
  where practical.

### B5. Comparison table (datapath designer's parameters)

| Parameter | 7-series | UltraScale | UltraScale+ | Versal |
|---|---|---|---|---|
| LUT | LUT6 (or 2×LUT5 shared inputs) | LUT6 | LUT6 | LUT6, with LUT→LUT cascade |
| LUTs / FFs per slice | 4 / 8 (2 slices per CLB) | 8 / 16 (1 slice per CLB) | 8 / 16 | 8 / 16 (4 slices per CLB: 32 / 64) |
| Control sets per slice | 1 clk, 1 SR, 1 CE (8 FFs) | 2 clk, 2 SR, 4 CE | 2 clk, 2 SR, 4 CE | per CLB: 4 clk, 4 SR, 16 CE; Q1/Q2 share CE |
| Carry primitive | `CARRY4` (4 b/slice) | `CARRY8` (8 b, splittable) | `CARRY8` | `LOOKAHEAD8` (8 b, odd carries; starts at 0 or 4) |
| Wide mux | F7/F8: 16:1 per slice | F7/F8/F9: 32:1 per slice | F7/F8/F9 | none — LUT cascade |
| SRL per LUT / per slice | SRL32; 128 deep | SRL32; 256 deep | SRL32; 256 deep | SRL32; 50 % of LUTs SRL/LUTRAM-capable |
| LUTRAM per SLICEM | 256 b | 512 b | 512 b | 64 b per LUT, 16 of 32 LUTs per CLB |
| DSP | `DSP48E1` 25×18, 25-b pre-add, 48-b ALU | `DSP48E2` 27×18, 27-b pre-add, 48-b ALU, 96-b XOR | `DSP48E2` | `DSP58` 27×24, 27-b pre-add, 58-b ALU, 116-b XOR, FP32/FP16, complex 18×18 (2 DSPs) |
| INT8 products per DSP | 2 (designer-packed, shared operand, S = 16–17, no guard bits) | 2 (designer-packed, shared operand, S = 18, 2 guard bits → ≤ 7 in-DSP accumulations) | 2 (as UltraScale) | **3 native** (`DSP_MODE = INT8`, 9×8 terms, independent operands, dot-product + accumulate) |
| Block RAM | `RAMB36E1` 36 Kb, SDP ×72, no NO_CHANGE in SDP, cascade 64K×1 only | `RAMB36E2` 36 Kb, SDP ×72, all write modes in SDP, column cascade | `RAMB36E2` | `RAMB36E5` 36 Kb, SDP ×72, cascade, no hard FIFO |
| Hard FIFO | `FIFO18E1/36E1` | `FIFO18E2/36E2` | same | none (XPM) |
| URAM | none | none | `URAM288` 288 Kb 4K×72, part-dependent | `URAM288E5` 288 Kb 4K×72, most parts |
| Clocks per region | 12 (BUFH lines); 32 BUFG per device/SLR | 24 (24 BUFGCE + 8 BUFGCTRL + 4 BUFGCE_DIV per region) | 24 | 24 distribution tracks; BUFGCE/BUFGCTRL/BUFGCE_DIV + BUFG_PS/BUFG_FABRIC |
| Clock generation | CMT = 1 MMCME2 + 1 PLLE2 | CMT = 1 MMCME3 + 2 PLLE3 | CMT = 1 MMCME4 + 2 PLLE4 | no CMT: MMCME5 + DPLL, XPLL per XPIO bank |
| SERDES max ratio | 8 SDR / 14 DDR (paired) | 4 SDR / 8 DDR | 4 SDR / 8 DDR | XPHY bit-slice logic (see the Versal SelectIO guide) |
| Core voltage (base grades) | 1.0 V | 0.95 V (−3E 1.0 V) | 0.85 V (−3E 0.90 V; L grades 0.72 V) | L 0.70 / M 0.80 / H 0.88 V classes |
| SSI / SLR | Virtex-7 largest parts (DS180) | KU085/KU115, VU125–VU440 | VU5P–VU13P, VU35P/37P, HBM | check DS950 per part |
| Hard NoC / DDR | no | no | no | yes (PG313) |
| Retiming default | off | off | off | `-global_retiming` on |

Per-part counts (DSPs, BRAM/URAM blocks, buffers, SLRs, transceivers,
I/O): DS180 (7-series), DS890 (UltraScale/UltraScale+), DS950 and the
XMP product selection guides (Versal).

---

## Part C — Loading and cross-references

Load alongside this skill:

- `skills/vivado-gotchas/SKILL.md` — the silent-failure catalogue for
  the same tool; every "see gotchas" pointer above resolves there.
- `shared/TimingAndResources.md` — vendor-neutral timing-closure
  fundamentals and the ways designs fail them; this skill assumes it.
- `shared/DesignPatterns.md` — the RTL patterns (elastic stage, FIFO,
  CDC forms, packed multiply, masked reduction) the inference rules above
  are written for.
- `shared/CdcPolicy.md` — CDC classification and completion gate; A6 is
  its Vivado implementation.
- `shared/VendorPolicy.md` — portability classes; every attribute,
  primitive or XPM use above must be classified under it.
- `shared/SynthesizableVHDL.md` — the synthesizable/tool-dependent/
  simulation-only split; Vivado's VHDL-2008 subset (A2) is the
  "tool-dependent" boundary for this target.
- `shared/FpgaInitialization.md` and `shared/TsfpgaCodingConventions.md`
  — the resetless-by-default policy that A4 grounds in GSR.
- `shared/TsfpgaModules.md` — module layout that A13's
  `scoped_constraints/` and `module_*.py` build projects live in.

Skills that should load this one: `vharch` (clock/reset/CDC/hard-block
planning, SLR and NoC decisions), `vhdesign` (inference template and
attribute choices in the proposal), `vhfill` (writing the templates),
`vhsynth` (interpreting a Vivado report and choosing the fix).

## Sources

Verified 2026-09 against these AMD documents (docs.amd.com unless noted);
where a document's statement differed from the expectation it replaced
it, and the text above says so.

- UG949 UltraFast Design Methodology Guide for FPGAs and SoCs, v2026.1
  (2026-06-23) — resets, clocking, CDC, constraints, baselining, timing
  closure, utilisation, control sets, floorplanning, SLR, power, debug,
  OOC.
- UG901 Vivado Design Suite User Guide: Synthesis, v2026.1 (2026-07-08)
  — synthesis attributes (complete list of 33), `synth_design` options,
  HDL coding techniques (RAM/ROM/SRL/DSP/FSM templates), VHDL-2008/2019
  support.
- UG903 Vivado Design Suite User Guide: Using Constraints, v2026.1 —
  constraint ordering, scoping, exception priority, `-datapath_only`,
  auto-derived clocks, I/O delay.
- UG906 Vivado Design Suite User Guide: Design Analysis and Closure
  Techniques, v2026.1 (CDC rule table from the 2021.1 edition) —
  `report_cdc` rules, methodology checks, QoR assessment.
- UG912 Vivado Properties Reference, v2026.1 — `PROCESSING_ORDER`,
  `SEVERITY`.
- UG1292 UltraFast Design Methodology Timing Closure Quick Reference,
  v2024.2 (also 2019.2, 2020.1) — directive sweeps, QoR score.
- UG904 (implementation), UG905 (hierarchical design, 2021.2), UG907
  (power), UG938 (design analysis tutorial), 2026.1 — incremental flow,
  OOC context constraints, `power_opt_design`.
- UG974 UltraScale Architecture Libraries Guide and UG953 7 Series
  Libraries Guide, v2026.1; PG382 XPM CDC Generator — XPM_CDC, XPM_MEMORY,
  XPM_FIFO lists and parameters.
- UG474 7 Series FPGAs Configurable Logic Block User Guide, v1.9
  (2025-04-01).
- UG479 7 Series DSP48E1 Slice User Guide, v1.10 (2018-03-27).
- UG473 7 Series FPGAs Memory Resources User Guide, v1.14 (2019-07-03).
- UG472 7 Series FPGAs Clocking Resources User Guide, v1.14 (2018-07-30).
- UG471 7 Series FPGAs SelectIO Resources User Guide, v1.10 (2018-05-08).
- DS180 7 Series FPGAs Data Sheet: Overview, v2.6.1 (2020-09-08) —
  product tables, speed grades, transceivers.
- UG585 Zynq 7000 SoC Technical Reference Manual, v1.15 (2026-02-06);
  PG082 Processing System 7 v5.3 Product Guide — PS/PL ports, FCLK.
- UG574 UltraScale Architecture Configurable Logic Block User Guide,
  v1.6 (2025-01-22) (some detail from the v1.5 PDF).
- UG579 UltraScale Architecture DSP48E2 Slice User Guide, v1.11
  (2021-08-30); WP486 Deep Learning with INT8 Optimization on Xilinx
  Devices, v1.0.1 (2017-04-24).
- UG573 UltraScale Architecture Memory Resources User Guide, v1.14
  (2025-11-18) (some detail from the v1.9 PDF).
- UG572 UltraScale Architecture Clocking Resources User Guide, v1.11
  (2025-05-29) (some detail from the v1.7 PDF); UG1026 UltraScale
  Architecture Migration Methodology Guide, v1.5.
- UG571 UltraScale Architecture SelectIO Resources User Guide, v1.16;
  UG570 UltraScale Architecture Configuration User Guide, v1.9.1 (SSI
  table).
- DS890 UltraScale Architecture and Product Data Sheet: Overview, v4.10
  (2026-05-21); DS892 (Kintex UltraScale) v1.20; DS893 (Virtex
  UltraScale) v1.13; DS923 (Virtex UltraScale+) v1.20; XMP103
  UltraScale+ Product Selection Guide v2.8.
- UG1085 Zynq UltraScale+ Device Technical Reference Manual, v2.5
  (2025-03-21); PG201 Zynq UltraScale+ Processing System v3.5.
- AM005 Versal Adaptive SoC Configurable Logic Block Architecture
  Manual, v1.4 (2025-05-14).
- AM004 Versal ACAP DSP Engine Architecture Manual, v1.2.1 (2022-09-11).
- AM007 Versal Adaptive SoC Memory Resources Architecture Manual, v1.2.1
  (2026-06-05).
- AM003 Versal Adaptive SoC Clocking Resources Architecture Manual, v1.6
  (2026-06-09).
- PG313 Versal Adaptive SoC Programmable Network on Chip and Integrated
  Memory Controller Product Guide, v1.1 (2026-06-23); WP562 (2025-03-10);
  UG1273 Versal Design Guide, 2026.1 — NoC.
- AM009 Versal AI Engine Architecture Manual, v1.4 (2026-02-18); AM020
  AIE-ML Architecture Manual, v1.5 (2026-02-18); UG1076/UG1079 2026.1.
- AM011 Versal Adaptive SoC Technical Reference Manual, v1.9
  (2026-03-06); PG352 CIPS v3.4 (2025-06-11); UG1305 2026.1 — PMC, PS/PL.
- UG1387 Versal Adaptive SoC System and Solution Planning Methodology
  Guide, 2026.1 (2026-07-22); UG1788 Versal Timing Closure Quick
  Reference; UG1344 Versal Architecture Libraries Guide, 2026.1.
- DS950 Versal Architecture and Product Data Sheet: Overview, v2.11
  (2026-08-03); DS957 (AI Core) v1.10; DS958 (AI Edge) v1.11; XMP452/
  XMP453/XMP463/XMP464/XMP465 product selection guides.
- tsfpga 13.3.0 source (`tsfpga/module.py`, `constraint.py`,
  `vivado/project.py`, `vivado/build_result_checker.py`, `vivado/tcl.py`)
  and tsfpga.com API reference; hdl-modules 6.x source and
  hdl-modules.com (`resync`, `fifo` modules and their
  `scoped_constraints/`).

Not verified from a primary source and therefore stated as "check the
guide": exact BRAM/URAM `SLEEP` wake-up latencies, the NoC clock
frequency, the numeric DSP inference size threshold (UG901 publishes
none), SLL capacity per SLR boundary, and any per-part resource count.
Corrections made because a source disagreed with the expectation: no
`retiming` on/off attribute (UG901); no `xpm_cdc_low_latency_handshake`
(UG974/UG953); no per-resource utilisation table in UG949; the
active-high control-signal rule is UG901's, not UG949's; Versal CLB is
four slices with `LOOKAHEAD8` and no MUXF7/F8/F9; DSP58 INT8 mode is
three 9×8 terms, not two 8×8; DSPFP32 has no bfloat16; the Versal NoC
guide is PG313; UltraScale slices have 2 SR / 4 CE groups, URAM has
byte-write enables, ISERDESE3 stops at 1:8; 7-series low-voltage grades
are 0.95 V / 0.9–1.0 V by family, not a flat 0.9 V; tsfpga scopes
constraints with `read_xdc -ref`, not `SCOPED_TO_REF`, and hdl-modules
renamed `resync_slv_level_coherent` to `resync_twophase`.
