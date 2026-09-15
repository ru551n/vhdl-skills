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
| `max_fanout` | integer (`-1` = none) | register or signal | local replication of a medium-fanout control net; never globally, never on resets/clock enables that place_design should handle — UG949 prefers manual or hierarchical replication for the largest nets. **Measured negative data point**: applying it to a 3356-load clock-enable net made WNS *worse* by ~190 ps rather than better — the tool-driven replicas were not obviously better placed than the single net they replaced. UG949's own ranking (manual/hierarchical replication above this attribute) is not just a style preference; verify with a full build before keeping it, don't assume the attribute is free upside. |
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
   `shared/HouseStyle.md`, "Reset policy", and the decision
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
   (`shared/HouseStyle.md`).
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

#### A6.1 Reliable CDC constraints — the Vivado recipe (after L. Vik / hdl-modules)

**Instantiate a ready-made block; do not write these constraints per
crossing.** The `hdl-modules` `resync_*`/`asynchronous_fifo` blocks ship
every constraint and waiver below as scoped files, and XPM_CDC macros ship
their own. Hand-writing them is only for building or reviewing a library
block, and the result must reproduce this recipe exactly.

The vendor-neutral error-mode analysis is in `shared/CdcPolicy.md`,
"Reliable CDC techniques"; this is the exact XDC/Tcl that closes each
mode in Vivado, as shipped in `hdl-modules`'
`modules/resync/scoped_constraints/*.tcl` and
`modules/fifo/scoped_constraints/asynchronous_fifo.tcl`. Copy the
patterns, not the file names.

**Ship every constraint scoped to the CDC entity.** `read_xdc -ref
<entity> <file>.tcl` applies the file to every instance and lets it use
`get_ports`/`get_cells`/`get_nets` *relative to that entity*, as if it were
the top — no hierarchy navigation, no breakage when the block is moved.
tsfpga does this for any file under a module's `scoped_constraints/`
directory (A13). Inside such a file `get_timing_paths` does not work
(critical warning), which is why the clocks are found through the ports:

```tcl
# Clock periods, with a safe fallback when a clock cannot be found at this
# stage (not created yet, or driven by an IP core / non-trivial source).
set clk_in  [get_clocks -quiet -of_objects [get_ports "clk_in"]]
set clk_out [get_clocks -quiet -of_objects [get_ports "clk_out"]]
if {${clk_in} != ""}  { set clk_in_period  [get_property "PERIOD" ${clk_in}]  } else { set clk_in_period  2 }
if {${clk_out} != ""} { set clk_out_period [get_property "PERIOD" ${clk_out}] } else { set clk_out_period 2 }
set min_period [expr {min(${clk_in_period}, ${clk_out_period})}]
```

The 2 ns fallback (500 MHz) is deliberately *tighter* than any real clock,
so an unfound clock errs toward over-constraining, never toward an
unbounded path.

**Latency bound: `set_max_delay -datapath_only`, value = `min_period`.**

```tcl
set first_sync [get_cells "data_in_p1_reg"]          ;# first async_reg stage
set_max_delay -datapath_only -from ${clk_in} -to ${first_sync} ${min_period}
```

Why `-datapath_only`: `set_max_delay -help` recommends it for asynchronous
crossings, and without the flag the command has been observed to *fail*
on derived clocks and clocks from IP cores. It also removes clock
skew/jitter/pessimism from the check, so the real latency can exceed one
period — expect up to about two destination cycles. If both clocks
genuinely cannot be found, fall back to `set_false_path -setup -hold -to
${first_sync}` and accept arbitrary latency; that is the only time a
false path belongs on a synchroniser, and the block should report it.

**Per topology — the exact objects and commands:**

| Topology (hdl-modules block) | Constraints | `report_cdc` waiver |
|---|---|---|
| Single-bit level (`resync_level`) | `set_max_delay -datapath_only -from <clk_in or source FF> -to <first async_reg>` = `min_period` | none needed |
| Pulse (`resync_pulse`) | same bound on `level_in_reg → level_out_m1_reg`; **and on the optional feedback** `level_out_reg → level_out_feedback_m1_reg` | none |
| Gray counter (`resync_counter`) | `set_bus_skew -from <gray regs> -to <first sync regs>` = **`clk_in_period`** (≤ 1 bit in transition per sample) **plus** `set_max_delay -datapath_only` = `min_period` on the same pairs | `CDC-6` "Multi-bit synchronized with ASYNC_REG": safe because Gray + skew bound |
| Two-phase / handshake (`resync_twophase`, `_handshake`) | `set_max_delay -datapath_only` on the **data** regs (`*_sampled_reg* → *_int_reg*`) and on **both** level directions | `CDC-15` "Clock enable controlled CDC": the CE *is* the mechanism |
| LUTRAM two-phase / FIFO (`resync_twophase_lutram`, `asynchronous_fifo` with LUTRAM) | both level bounds as above, **plus** `set_false_path -setup -hold -from ${clk_in} -through [get_nets "read_data*"]` — LUTRAM reads are combinational; the pointer logic, not timing, protects the read | `CDC-1` (intentional 1-bit circuit), `CDC-26` (read/write collision — pointers guarantee none) |
| Level sampled on a strobe (`resync_level_on_signal`) | `set_false_path -setup -hold -through <data_in net> -to <data_out reg>` — data is guaranteed stable when the strobe samples it | `CDC-15` / `CDC-17` (CE- or MUX-controlled) |

Every waiver carries the structural reason in `-description`; a waiver
without one is a hidden bug. Use `-quiet` on the `get_pins` in a waiver so
an optional path (a disabled feedback, an absent output register) does not
error.

**The RTL side that the constraints assume** (`hdl-modules` `resync_*`):
`async_reg` on every stage of the chain; `dont_touch` on the source-domain
register that feeds the chain, so synthesis cannot merge it into a LUT
and reintroduce the glitch mode; an optional `enable_input_register`
generic that inserts that register when the caller's driver is
combinational — and when it is *off*, the block must fall back to
`set_false_path` because there is no `clk_in` register to bound from.

**Never do at project level:** `set_clock_groups -asynchronous` or a
domain-to-domain `set_false_path`. Both have higher priority than
`set_max_delay` and silently cancel every bound above (A6, UG903
priority). A crossing with no CDC block must *fail* timing; that is how it
is found.

**XPM caveats.** `xpm_cdc_pulse` has no latency bound (build-dependent,
effectively unbounded — error mode #2) and no feedback, so closely spaced
pulses are lost outright (error mode #4). Prefer a pulse block with the
feedback level where pulse loss is unacceptable. `xpm_cdc_gray`,
`xpm_cdc_handshake` and `xpm_fifo_async` are sound for their classes.

**Asynchronous FIFO skew.** The read side may see the crossed write
pointer with near-zero latency while the RAM write port sits on a
different clock-tree branch. AMD publishes a maximum clock-tree skew for
7-series (DS182, clock skew table, under 1 ns) but not an equivalent for
every family, and not for SLR-spanning paths. Keep the FIFO within one
clock region on SSI parts, register the binary-to-Gray stage, and record
the assumption in the architecture doc.

**Build gates, after `synth_design` and again after `route_design`** —
tsfpga runs both; in a bare flow add them to the run hooks:

```tcl
set cdc [report_cdc -return_string -no_header -details -severity "Critical"]
if {[string first "Critical" ${cdc}] != -1} { exit 1 }

set ci [report_clock_interaction -delay_type "min_max" -no_header -return_string]
if {[string first "(unsafe)" ${ci}] != -1} { exit 1 }
```

`report_cdc` severities cannot be adjusted per rule, so a false positive
must be waived at its source with a reason, not globally suppressed.
Together these catch roughly 90 % of dangerous crossings; pulses and
handshakes across *related* clocks are invisible to both and need review.

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
  device − clock delay to the FPGA; min analogous) and `set_output_delay`
  (max = external setup requirement + board data delay + clock delay to
  the FPGA − clock delay to the external device; min = −(external hold
  requirement) + board data delay + the same clock-delay difference),
  against a virtual clock when the external waveform differs. Both
  formulas include "clock delay to the FPGA", i.e. this device's own
  insertion delay (IBUF + route + global buffer) — it is not zero and
  not negligible, so a `0`/`0` shortcut is only ever correct when that
  insertion delay happens to cancel against the external clock delay,
  which a harness with no external device at all does not have.
  `TIMING-18` flags missing I/O delay; `check_timing` lists unconstrained
  endpoints. For a pinnable timing harness, constrain
  realistically rather than with zero delay: with no MMCM the clock's own
  insertion delay is uncompensated and a `0` output delay charges all of
  it to the pad, an unmeetable and misleading constraint — use the
  measured insertion delay less a real setup allowance for max, and a
  genuinely separate near-zero value for min, never the same negative
  number reused for both (`shared/TimingAndResources.md` §1). Never false
  paths on a real pin.
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

**Order of levers, and why it matters here.** Structure first — BRAM
`DOA_REG`/`DOB_REG` output registers, pipeline and elastic stages, fan-out
registers — then attributes, then implementation directives and
`phys_opt_design`, then floorplanning. Vivado's directives and pblocks can
buy a few hundred picoseconds each, but closure that rests on them is lost
on the next netlist change; aim for positive slack with `Default`
directives and treat any path that still needs a directive as a design
finding. And never let the harness decide the number: DUT ports sit behind
registers, pad registers are `IOB = TRUE`, pads carry realistic I/O
delays, and the design's result is the register-to-register WNS
(`shared/TimingAndResources.md` §1). A short pipeline (a stage or two) is
fine between the IOB register and the port if the pad path needs the
margin — but tag every stage `shreg_extract = "no"` (A3) first, since a
same-clock, no-reset, no-enable register run is exactly what triggers SRL
extraction, and an SRL cell has different placement/timing than discrete
flip-flops and cannot be packed into the IOB itself. Confirm no SRL
appears on the path in the post-synthesis utilization report.

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
   **Both are licensed features** and fail outright on a Basic/WebPACK
   license (`[Implflow 47-2944] Your current selected license is
   BASIC`) rather than degrading gracefully — confirm entitlement before
   relying on either in a documented flow. Fallback with no extra
   license: `report_design_analysis -timing -max_paths N`, then group
   the worst N endpoints by owning module/instance by hand — this is
   plain text processing, not a QoR feature, and it is where the real
   leverage usually is regardless of license.
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
| Endpoint is a `/CE` or `/R` pin, not a data input | arithmetic (a subtract-and-compare, a wide reduction) gating a busy/ready/done/reset term | weaken the predicate — test the raw pre-clamp/pre-reduce value if it is provably equivalent, or move the arithmetic off the enable/reset entirely; do not pipeline a clock enable, `shared/TimingAndResources.md` §2 |
| `/CE` endpoint traced back to a *different* engine's combinational valid/state, through a shared arbitration mux, where the two engines never run concurrently | two mutually-exclusive engines combinationally coupled through the mux that picks between them | register the mux's own inputs (each engine's state/valid feeding it), not just its output — otherwise each engine's internal state lands on the other's clock enables even though they never overlap in time |

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

**Logic levels falling is not the same as slack rising.** `report_design_analysis`'s
logic-level count is a synthesis-side proxy; the routed `Data Path Delay`
line splits into `logic` and `route` components, and a fix that lowers
logic levels while leaving (or worsening) the route-delay share can make
WNS *worse* at route, not better — this has happened in practice: a fix
that cut 14 levels to 10 regressed WNS because the path was already
route-dominated and the fix moved the source further away without
removing the dependency that made the net long. Read the logic/route
split on the specific failing path **before** picking a fix class:
logic-dominated → weaken/restructure the logic (this section, #1–#3);
route-dominated → shorten the topology, remove a cross-hierarchy
dependency, or treat it as placement (#5) — pipelining or attribute
changes will not help a delay that is mostly wire.

**The plateau.** Fixing the reported critical path reveals the next one;
several consecutive fixes may move WNS by nothing while being necessary.
Judge a rework by whether its target path is gone from the histogram,
not by the immediate WNS delta; once several paths are within a few
hundred picoseconds of each other, single-path fixes are exhausted and
the remaining question belongs to place-and-route strategies, not to
more RTL iteration. **On a design this dense, "target path gone from the
histogram" is necessary but not sufficient — re-measure the floor
(whatever frequency/WNS is actually shipping) after every change, not
just the stretch target being explored.** A fix that provably deletes
its target path's whole endpoint group can still be a net loss if the
next-worst path it exposes costs more margin elsewhere than the target
group was worth — measured in practice: two different structural fixes
each removed 100+ endpoints from their target family while individually
costing the shipping frequency's margin. On a plateau, judge a rework by
both signals together (target gone AND floor unchanged-or-better), never
by the first alone. The full argument, with a worked progression, is in
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
- **`build_fpga.py`'s non-zero exit on a timing failure is not a build
  error** — a real place-and-route that completes but does not meet
  timing still reports `fail` and a non-zero process exit, same as a
  genuine synthesis/implementation crash would. Read the actual
  `*_timing_summary_routed.rpt` (WNS/TNS/failing endpoints) before
  concluding a run "failed" — a script or agent that treats any non-zero
  exit as "the build broke" will mis-report a design that routed cleanly
  but simply hasn't closed timing yet.

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

#### Design instructions

**1. Timing and logic structure.**
- Budget one pipeline stage as *one LUT level plus one carry chain*.
  `CARRY4` is four bits per slice, so a W-bit add/compare occupies
  `ceil(W/4)` vertically cascaded slices — twice the span of a `CARRY8`
  family for the same width. Budget roughly half the adder width per
  stage that you would on UltraScale at the same period, and confirm
  against `report_design_analysis -logic_level_distribution` rather than
  a rule of thumb; the exact width per nanosecond is speed-grade
  dependent (DS181/DS182/DS183).
- Mux budget: 4:1 fits one LUT6; 16:1 fits one slice as one LUT level
  plus the F7A/F7B/F8 mux stages. Beyond 16:1 costs another LUT level
  *and* an inter-slice route per factor of 16 — register there, or
  replace the mux with a registered one-hot select or a small LUTRAM
  lookup.
- Control-set grouping is the tightest of the three families: one clock,
  one set/reset and one clock enable for all eight storage elements of a
  slice. Every register that carries a different reset or enable net
  therefore takes its own slice. Give each pipeline stage a single
  enable net and a single reset net, and close conditionals on small
  register groups with an `else` instead of inventing an enable (A1).
- Retiming is **off** by default on this family: ask for it with
  `synth_design -global_retiming on`, or move a specific register with
  `retiming_forward`/`retiming_backward`. It is blocked by a reset on
  the register being moved, by `dont_touch`/`mark_debug`, by timing
  exceptions on the path, by instantiated cells, and (for port-driven
  registers) by out-of-context mode.

**2. Registers, reset and enable.**
- Eight flip-flops pack into one slice only while they share one clock,
  one set/reset and one enable. A second reset net or a second enable
  net in the same logical group splits it across slices and puts routing
  between stages of the same pipeline.
- Four of the eight storage elements can be latches, and using one
  makes the other four unusable — treat `[Synth 8-327] inferring latch`
  as a hard error (A2).
- `SRLC32E` has **no reset**: a reset on a delay line replaces up to 32
  taps per LUT with 32 flip-flops and moves the line out of SLICEM.
  Distributed RAM likewise has no array reset. Do not reset delay lines
  or memory arrays; a synchronous reset on the *output register* after a
  memory is permitted where a protocol demands it.
- Never reset block-RAM contents, SRL chains, pipeline payload or the
  DSP48E1 A/B/C/D/M/P registers. An asynchronous reset on any of those
  forces `FDCE`/`FDPE`, which no hard block accepts, so the register
  stays in fabric (A4 §4).
- Use declaration initial values for power-up state; GSR applies them at
  the end of configuration (A4 §1).

**3. Memory.**
- Up to ~64 words, or wide, multi-ported or asynchronously read →
  distributed RAM in SLICEM (256 bits per CLB). Only about one third of
  slices are SLICEM and SRLs compete for the same LUTs, so read `LUTRAMs`
  and `SRLs` separately from `Logic LUTs` (A9). Above that → `RAMB18E1`
  / `RAMB36E1`.
- Choose `RAMB18E1` when the array fits 18 Kb and the port is ≤ ×18
  (×36 in SDP); two RAMB18 share one RAMB36 site, so an 18 Kb choice is
  never wasteful.
- Always write the output register (a second registered stage after the
  read, packed into `DO*_REG`); without it the BRAM clock-to-out is the
  stage delay. Keep logic and any asynchronous reset out of that stage
  (A2).
- Cascade: only the 64K×1 mode cascades in hardware on this family.
  Every other deep memory is muxed in fabric, so build depth from the
  widest word the port allows and register the address decode — do not
  assume a free cascade as on UltraScale.
- Read-during-write: `WRITE_FIRST` is the default and costs nothing but
  forbids the NO_CHANGE power saving; `READ_FIRST` is the cheapest form
  for a stream buffer; `NO_CHANGE` holds the output register and is
  **not available in SDP mode** on 7-series — a simple-dual-port RAM
  cannot be NO_CHANGE here, so `rw_addr_collision = "no"` buys nothing.
- Byte writes: 4 (RAMB36 TDP), 8 (RAMB36 SDP), 2–4 (RAMB18), and not
  with the dual-clock FIFO or ECC modes. Arrange the array in equal 8-,
  9-, 16- or 18-bit columns or each lane becomes its own RAM (A2).
- ECC: one 64-bit SEC-DED per RAMB36, in ×64 SDP only, and mutually
  exclusive with byte writes — an ECC-protected buffer must be written
  64 bits at a time.
- Initialise with a constant aggregate or a `std.textio` read into an
  array of `bit_vector`; the contents survive GSR, so an initialised
  memory needs no reset.
- Use `FIFO18E1`/`FIFO36E1` (or `xpm_fifo_*`) rather than a fabric
  pointer FIFO around a BRAM when the width and depth fit; the hard
  block brings its own pointer logic and, in the dual-clock case, the
  crossing.
- **No UltraRAM.** A buffer beyond a few Mb is external memory, and the
  memory controller is soft (MIG) — budget its fabric, its clocking and
  its own calibration state machine in `vharch`.

**4. DSP.**
- Enable A1/A2 (`AREG = 2`), B1/B2, M and P; the data-sheet DSP48E1
  Fmax is the fully pipelined figure, and `MREG` in particular is what
  splits the multiplier from the adder.
- Pre-adder: `(a ± d) * b`, **signed**, on the 25-bit A path; the D port
  is 25 bits and the pre-added operand may use all 25 including its
  extra carry bit.
- Accumulate in the 48-bit P path, and keep the path from multiply to
  add unconditional — a condition between them drops the whole array
  into fabric. Gate with the DSP's registered clock enable or a
  `first`-flag load instead (A2).
- `use_dsp = "simd"` gives `ONE48`/`TWO24`/`FOUR12` adds, but only with
  the multiplier unused. Use the pattern detector for convergent
  rounding, overflow/underflow and terminal-count auto-reset rather than
  a fabric compare.
- **No wide XOR** on DSP48E1 (that arrives with DSP48E2): CRC, parity
  and LFSR reductions stay in LUTs here.
- Cascades: ACIN/ACOUT 30 bits, BCIN/BCOUT 18, PCIN/PCOUT 48, plus
  CARRYCASCADE and MULTSIGN for a 96-bit accumulate over two blocks.
  Cascades are column-local and do not cross an SLR — a long adder tree
  must be column-local or pipelined through fabric.
- INT8: two products per block by designer-side packing with a **shared**
  activation, shift `16 ≤ S ≤ 17` (because `8 + S ≤ 25`), and **no guard
  bits**. Unpack every cycle, before any accumulation, and add the low
  field's sign back into the high field; never accumulate the packed
  value (A9, `shared/DesignPatterns.md`, "Packed multiply").
- No native INT8 and no floating-point mode: FP is fabric or the
  Floating-Point Operator IP.

**5. Clocking.**
- Buffer per job: `BUFG` for anything global (32 per device, per SLR on
  SSI parts); `BUFH`/`BUFHCE` to keep a clock inside one region and save
  a global line; `BUFR` for a regional clock that needs a divide;
  `BUFIO` only for an I/O-bank-local capture clock (it reaches I/O
  logic, not fabric); `BUFMR`/`BUFMRCE` to extend a regional clock over
  three regions.
- Per-region budget: **12** horizontal clock lines / BUFH — the
  tightest of the three families. Count distinct clocks per region while
  partitioning in `vharch`; more than 12 in one area is a placement
  failure, not a timing one.
- Generate every synchronous rate from one `MMCME2_ADV` (seven outputs,
  fractional divide on CLKOUT0 and CLKFBOUT, CLKOUT6 cascading into
  CLKOUT4 for a large divide, fine/dynamic phase shift) and use the
  `PLLE2_ADV` (six outputs, no fractional divide, no inverted outputs)
  for the plain jitter-filter jobs. One CMT = one MMCM + one PLL per
  clock region. VCO range and the M/D limits are speed-grade dependent
  — check DS181/DS182/DS183 for the part.
- Never divide a clock in fabric: there is no auto-derived clock and no
  buffer behind it (A5, A7).
- Clock-enable idiom: `if rising_edge(clk) then if ce = '1' then`, one
  CE net per wide stage. For power, gate a region at `BUFHCE`/`BUFR`/
  `BUFMRCE` and a whole domain at `BUFGCE` — never in fabric (A11).

**6. IO and SERDES.**
- Pack an I/O register into ILOGIC/OLOGIC with `iob` (RTL) or the `IOB`
  property: the register must be a plain flip-flop with no logic between
  it and the pad, and the packed path must not fan out elsewhere.
- `IDDR` supports OPPOSITE_EDGE, SAME_EDGE and SAME_EDGE_PIPELINED;
  `ODDR` supports OPPOSITE_EDGE and SAME_EDGE. Prefer SAME_EDGE so both
  half-words are available on one rising edge; SAME_EDGE_PIPELINED costs
  a cycle of latency for a relaxed capture.
- `ISERDESE2`/`OSERDESE2` reach 8:1 SDR, and 10:1/14:1 DDR only with
  master/slave pairing (input) or width expansion (output). This is the
  only one of the three families with 1:10/1:14, so an interface built
  on those ratios has no direct UltraScale equivalent (UG1026).
- `IDELAYE2` has 31 taps and requires an `IDELAYCTRL` per bank group fed
  by a reference clock (200 MHz nominal, ≈78 ps per tap); `ODELAYE2`
  exists in HP banks only, so an output-delay interface constrains the
  bank choice before the RTL exists.
- Bank rules that reach the RTL: one `IOSTANDARD` voltage family per
  bank (HR ≤ 3.3 V, HP ≤ 1.8 V), DCI and ODELAY in HP only, clock inputs
  on clock-capable pins, a differential pair on a P/N pin pair in one
  bank. Spartan-7 and Artix-7 have HR banks only. Fix bank and pin
  assignment before writing the I/O logic (A10).

**7. Reset and CDC nuances.**
- GSR sets every sequential cell to its `INIT` at the end of
  configuration, and the release is asynchronous to every user clock —
  apply A4 §6's remedies (clock enables or a synchronised reset on
  state-holding logic, buffer CE gating until MMCM `LOCKED`, a delayed
  release through an `ASYNC_REG` chain).
- XPM_CDC, XPM_MEMORY and XPM_FIFO are available for this family from
  UG953. The default `DEST_SYNC_FF` of 4 is conservative but 7-series
  MTBF at high rates genuinely wants 3–4 stages: measure with
  `report_synchronizer_mtbf` before reducing it (A6).
- `async_reg` keeps a synchroniser chain in one slice — which here means
  eight flip-flops sharing one control set, so give the chain no clock
  enable and no reset.
- No BRAM/URAM `SLEEP` on this family, so no sleep/wake interaction with
  reset sequencing.

**8. Floorplanning and SLR.**
- SLR rules apply only to the largest Virtex-7 parts (DS180 lists the
  SLR count per part); for every other 7-series part, **not applicable**
  — Pblocks only on `CLOCKREGION` ranges and only for a demonstrated
  congestion or locality problem (A10).
- On the SSI parts, register both sides of every crossing with plain
  flip-flops, and note that carry chains, BRAM cascades and DSP cascades
  do **not** cross an SLR: wide arithmetic and memory columns must be
  SLR-local by construction.
- Clock region = 50 CLBs tall, one 50-pin I/O bank, ten RAMB36 and 20
  DSP48E1 per column, one CMT. A block needing more than that per column
  spreads over regions whatever a Pblock says — size Pblocks from those
  numbers.

**9. Migration notes.**
- From Virtex-6 (UG429): the DSP48E1 is the same slice, so DSP RTL and
  instantiations carry over; block RAM is 36 Kb-based with 18 Kb halves
  as before; clock regions are larger, so a design that spanned two
  Virtex-6 regions may fit one here; MMCM topologies usually need no
  change.
- From Spartan-6: the DSP is a different block (DSP48A1, 18×18 with an
  18-bit pre-adder) — re-derive multiplier widths, pre-adder widths and
  any packing for 25×18; `DCM_*` clock managers become MMCM/PLL, so
  retarget every instantiated clock primitive.
- General rule for any migration into this family: inferred RTL moves
  unchanged and instantiated primitives are the work — which is the
  argument for keeping primitives out of RTL in the first place
  (`shared/VendorPolicy.md`).

**10. Common mistakes on this family.**
- Resetting a delay line or a memory output register, losing SRL/LUTRAM
  extraction or the BRAM `DO*_REG`.
- An asynchronous reset on DSP operand registers, which emulates the
  multiplier in fabric (UG949's worked example).
- Expecting `NO_CHANGE` in simple-dual-port mode: unavailable here, so
  the power saving never appears in the report.
- Assuming a free BRAM cascade — only 64K×1 cascades; every other deep
  memory pays a fabric mux level.
- Porting the UltraScale INT8 pack with `S = 18`: `8 + 18 > 25`, so the
  high weight is silently truncated.
- Carrying UltraScale adder widths per stage into a `CARRY4` family and
  failing timing at a lower frequency.
- Exhausting SLICEM (LUTRAM + SRL) while `Logic LUTs` still looks free.
- Placing more than 12 distinct clocks in one clock region.
- Writing `BUFH`/`BUFR`/`BUFIO`/`BUFMR` into RTL that is meant to
  migrate to UltraScale, where none of them exist.

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

#### Design instructions

**1. Timing and logic structure.**
- Budget one pipeline stage as *one LUT level plus one carry chain*.
  `CARRY8` is eight bits per slice, so a W-bit add/compare occupies
  `ceil(W/8)` cascaded slices — half the 7-series span, so roughly
  double the adder width fits one stage at the same period. Confirm with
  `report_design_analysis -logic_level_distribution`; the width per
  nanosecond is speed-grade and voltage dependent (DS892/DS893/DS923),
  and the 0.72 V L grades are a separate operating point.
- A `CARRY8` splits into two independent 4-bit chains (carry-in at bit 0
  and at the midpoint), so two narrow adders share one slice — use it to
  keep two lane-parallel counters together instead of spreading them.
- Mux budget: 4:1 in one LUT6; **32:1 in one slice** as one LUT level
  plus the F7/F8/F9 mux stages. Beyond 32:1 costs a LUT level and an
  inter-slice route per factor of 32 — register there.
- Control-set grouping is the binding constraint on this slice: **two
  clocks and two set/reset nets** (one each per eight-flip-flop half,
  A–D and E–H) and **four clock-enable groups** (per half × per Q1/Q2).
  Synchronous versus asynchronous set/reset is chosen per half; set
  versus reset per flip-flop; and if one register in a CE group uses CE,
  all four must. Group registers by the `(clock, set/reset, enable)`
  triple in the RTL — one enable per stage, not per signal — because a
  group with a third reset net or a fifth enable net spills into another
  slice while its LUTs sit free.
- Retiming is **off** by default: request it with `-global_retiming on`
  or move a specific register with `retiming_forward`/`_backward`. It is
  blocked by a reset on the moved register, by `dont_touch`/`mark_debug`,
  by exceptions on the path, by instantiated cells, and for port-driven
  registers in out-of-context mode.

**2. Registers, reset and enable.**
- Sixteen flip-flops pack into one slice, but under at most two reset
  nets and four enable nets. The cost of a third reset net in a logical
  group is that the group is split across slices, inserting routing
  between stages of the same pipeline; the cost of a fifth enable is the
  same.
- Latches take all eight flip-flops of a half or none: one inferred
  latch costs half a slice (A2).
- `SRLC32E` cascades to **256 deep inside one slice** via MC31/Q31, so
  long delay lines are cheap here — but the SRL still has no reset, so
  never reset one, and an SRL whose intermediate taps are read elsewhere
  cannot be one SRL.
- Distributed RAM reaches 512 bits per SLICEM; the array has no reset.
- Never reset BRAM/URAM contents, SRLs, pipeline payload or the DSP48E2
  A/B/C/D/AD/M/P registers. URAM specifically is only inferable when the
  output reset, if present, is a synchronous reset to zero (A2).
- Use declaration initial values for power-up state rather than a global
  reset (GSR, A4 §1).

**3. Memory.**
- Register files, asynchronous reads and small wide tables → distributed
  RAM (≤ 512 bits per SLICEM). Kb-scale → `RAMB18E2`/`RAMB36E2`. Large
  single-clock buffers whose natural access is 72 bits → `URAM288`
  (UltraScale+ only, and part-dependent; DS890).
- Always add the BRAM output register. On URAM enable the pipeline
  registers — **up to four stages per port** (input, output, `IREG_CAS`,
  `OREG_CAS`) — because the URAM Fmax figure assumes them; put those
  cycles in the latency budget before the RTL is written.
- BRAM cascade is in hardware, bottom-up, **within one BRAM column and
  one clock region**; beyond that Vivado inserts fabric muxing. URAM
  cascades the full column height within an SLR (16 URAM per clock
  region per column), with extra pipeline registers when a chain crosses
  clock regions and fabric when it crosses columns. `cascade_height`
  (and `-max_uram_cascade_height`) shortens a chain for timing or
  lengthens it for power; UG901's default URAM chain limit is eight.
- Read-during-write: **all three modes are now available in SDP as well
  as TDP** (the 7-series restriction is gone), so a simple-dual-port
  buffer can be NO_CHANGE. `WRITE_FIRST` uses the primitive's internal
  bypass and is the timing-safe default; `NO_CHANGE` holds the output
  register and is the low-power choice; `READ_FIRST` is cheapest for a
  stream buffer. For an SDP RAM with a registered read address the
  choice is made by `rw_addr_collision` (A2/A3). URAM's native mode is
  NO_CHANGE.
- ECC: 64-bit SECDED per 36 Kb block in ×64 SDP only and mutually
  exclusive with byte writes; URAM has per-port SECDED **with** byte
  writes, which is the reason to put an ECC-protected byte-addressable
  buffer in URAM.
- URAM rules that constrain the RTL, not just the constraints:
  **single clock** (a dual-clock buffer must be BRAM or must have the
  crossing in front of the URAM), **fixed 72-bit width** (pack the
  payload to a multiple of 72 or waste the remainder), **no `INIT`**
  (an initialised table cannot be URAM), and two ports each performing
  one read *or* one write per cycle, so a read-and-write per cycle
  consumes both ports.
- Prefer `FIFO18E2`/`FIFO36E2` (asymmetric ×4…×72 ports, FWFT,
  synchronous reset, cascadable) or `xpm_fifo_*` over a hand-built
  pointer FIFO.
- `SLEEP` on BRAM and URAM saves power over long idle periods; check
  UG573 for the wake-up latency before designing a duty cycle around it,
  and sequence it from a small FSM rather than a combinational term
  (A11).

**4. DSP.**
- Enable AREG/BREG (1 or 2, with `ACASCREG`/`BCASCREG` consistent),
  DREG and ADREG when the pre-adder is used, MREG and PREG. The
  data-sheet DSP48E2 Fmax is the fully pipelined figure and the
  low-voltage grades carry their own footnotes.
- Pre-adder: `(a ± d) * b`, **signed**, on the **27-bit** A path with a
  27-bit D port. The extra two bits over 7-series are exactly what make
  a two-product INT8 pack fit with guard bits.
- Accumulate in the 48-bit ALU, 96 bits across two slices via
  PCOUT + CARRYCASCOUT + MULTSIGN. Keep the multiply-to-add path
  unconditional and gate with the DSP's registered clock enable or a
  `first`-flag load.
- `use_dsp = "simd"` for dual-24 / quad-12 adds with the multiplier
  unused; `use_dsp = "logic"` for the **wide XOR** (up to 96 bits in one
  slice, 192 across two) — put CRC, parity and LFSR reductions there
  instead of a LUT tree. Use the pattern detector for convergent
  rounding, counter auto-reset, overflow/underflow and the 96-bit
  AND/NOR test.
- INT8 (WP486): two products per block through the **pre-adder** as
  `p = (a << 18) + b` with the shared 8-bit activation on the 18-bit B
  port. The shift of 18 leaves **two guard bits** above the 16-bit low
  product, so at most **seven** packed products may be accumulated
  inside the DSP before the low field corrupts the high one — either
  spend one extra DSP per seven (WP486's 14 MACs per 8 DSPs) or unpack
  every cycle in fabric and accumulate outside, which removes the bound.
  Add the low field's sign bit back into the high field on unpack.
- Cascades ACIN/BCIN/PCIN/CARRYCASCIN are column-local and do not cross
  an SLR; `-cascade_dsp tree|force` shapes an adder tree into them. A
  cascade crossing a clock-region centre at the low-voltage grade may
  run below the data-sheet Fmax — keep a cascade chain region-local or
  break it with a fabric register.

**5. Clocking.**
- Buffer per job: `BUFGCE` for every ordinary global clock (24 per
  region); `BUFGCTRL` only for clock muxing (8 per region), and only
  between asynchronous clocks (A5); `BUFGCE_DIV` for an integer divide
  that must stay phase-related to its parent (4 per region — no CDC and
  no MMCM phase error between the two); `BUFG_GT` (with `BUFG_GT_SYNC`,
  divide 1–8) for transceiver clocks. `BUFCE_LEAF` is the tool-inserted
  leaf-level buffer — do not instantiate it.
- `BUFH`, `BUFR`, `BUFIO` and `BUFMR` **do not exist**: retarget
  BUFH → BUFGCE, BUFIO → BUFGCE, BUFR/BUFMR → `BUFGCE_DIV` (UG1026).
- Per-region budget: 24 clocks, because the region has 24 horizontal and
  24 vertical routing tracks plus 24 + 24 distribution tracks and the
  buffers share them. The buffer count is not the limit — the tracks
  are.
- CMT = **one MMCM + two PLLs** per I/O bank (`MMCME3`/`PLLE3` on
  UltraScale, `MMCME4`/`PLLE4` on UltraScale+). The PLLs are reduced
  relative to 7-series — no phase compensation, no external feedback,
  fewer outputs (UG572 "Key Differences from 7 Series FPGAs") — so put
  anything needing phase shift or deskew on the MMCM and leave the PLLs
  for jitter filtering and I/O clocks. MMCM output frequency can be
  changed dynamically (clock-divide dynamic change, or DRP) without
  resetting the MMCM. VCO range and M/D limits are per speed grade and
  voltage — check DS892/DS893/DS923.
- Parallel `BUFGCE_DIV`s must share CE and RST, or their divided phases
  diverge after a reset (A5).
- Clock-enable idiom unchanged; gate a whole domain at
  `BUFGCE`/`BUFGCE_DIV`/`BUFG_GT` CE for power, never in fabric.

**6. IO and SERDES.**
- Pack an I/O register into the I/O logic with `iob` / `IOB TRUE`;
  the register must be plain and must not fan out beyond the pad path.
- `IDDRE1`/`ODDRE1` replace `IDDR`/`ODDR` with the same capture modes
  but **fewer pins**: IDDRE1 loses CE and S; ODDRE1 loses CE, R and S
  (UG571). An I/O DDR register therefore cannot be enabled or reset —
  put the enable and the reset in the first fabric stage behind it.
- `ISERDESE3`/`OSERDESE3` stop at **1:4 SDR / 1:8 DDR**; there is no
  1:10 or 1:14. Anything faster or wider uses the bit-slice native mode
  (`RX_BITSLICE`, `TX_BITSLICE`, `RXTX_BITSLICE`, `BITSLICE_CONTROL`),
  which brings its own auto-derived clocks (A7) and a documented
  bring-up/reset sequence — design it as an IP block with a state
  machine, not as a primitive drop-in.
- Native and non-native mode I/O may not be mixed freely within a nibble
  (UG571) — assign pins per nibble before writing the I/O logic.
- `IDELAYE3`/`ODELAYE3` support a COUNT (tap) and a TIME (picosecond)
  delay format; the TIME format depends on the calibration flow
  (`BITSLICE_CONTROL`/`IDELAYCTRL` plus a reference clock, UG571 "Delay
  Calibration") — check UG571 for the tap count and reference-clock
  range of the part. ODELAY is HP-bank only.
- Banks are HP, HR **and HD** (HD on Artix/Spartan UltraScale+ and
  Kintex UltraScale+ Gen 2), 52 pins each: HP up to 1.8 V with
  DCI/ODELAY, HR to 3.3 V without DCI, HD lower-rate with no DCI, no
  ODELAY and no bit-slice — never plan a source-synchronous interface on
  an HD bank (A10).

**7. Reset and CDC nuances.**
- GSR behaviour and the startup remedies are unchanged from 7-series
  (A4 §6): synchronise the release, or gate state-holding logic with CE
  until `LOCKED`.
- XPM_CDC, XPM_MEMORY and XPM_FIFO come from UG974. `DEST_SYNC_FF`
  defaults to 4; UltraScale+ tolerates fewer stages for the same MTBF,
  but reduce it only against `report_synchronizer_mtbf`, and never below
  2 (A6).
- `async_reg` forces the chain into one slice — and one slice half here
  is eight flip-flops under a single set/reset net, so a synchroniser
  that carries a reset consumes that half's reset net. Keep synchroniser
  chains resetless and enable-less.
- BRAM/URAM `SLEEP` must be deasserted and the wake-up latency waited
  out before the first access; that sequencing needs its own reset, so
  it belongs in control logic, not the datapath.

**8. Floorplanning and SLR.**
- Applicable on the SSI parts listed above. Map a register-to-register
  SLR crossing onto a Laguna `TX_REG` driving a Laguna `RX_REG`
  directly on UltraScale+ (on UltraScale only one side can be Laguna),
  and mark both cells `USER_SLL_REG TRUE`. Those registers must be plain
  flip-flops — no reset, no clock enable — and must fan out to one SLR
  only, or the property is ignored. Wide buses above 250 MHz need three
  stages (source SLR, Laguna, destination SLR). Query capacity with
  `get_property NUM_TOP_SLLS [get_slrs …]`.
- Carry chains, BRAM cascades, DSP cascades and URAM cascades are all
  column-local and none of them crosses an SLR: partition wide
  arithmetic and large buffers per SLR in the architecture, not in the
  floorplan.
- Clock region: 60 CLBs tall, 24 DSP48E2 and 12 RAMB36 per column, 16
  URAM per column, 52 I/O per bank. Size Pblocks on `CLOCKREGION`
  ranges from those numbers; a block needing more of a hard resource
  than a region holds will spread regardless.
- Keep no SLR above ~85 % of any resource even when the device average
  is comfortable, and root clocks that span SLRs in the centre SLR
  (A9, A10).

**9. Migration notes.**
- From 7-series (UG1026). Inferred RTL migrates unchanged; instantiated
  primitives are the work. `CARRY4` instances map into `CARRY8`
  automatically — convert them only where dense packing matters.
- Clocking: BUFH/BUFR/BUFIO/BUFMR are gone (item 5); PLLs lose phase
  compensation, external feedback and outputs; clock regions become
  rectangular tiles instead of half-device rows; clock-capable (CC) pins
  become global-clock (GC) pins, so re-check pin assignment.
- SelectIO is redesigned: the 1:10/1:14 SERDES ratios disappear in
  favour of bit-slice native mode; IDDR/ODDR become IDDRE1/ODDRE1 with
  fewer control pins; IDELAYE2 → IDELAYE3 with a new calibration flow.
- Memory: SDP gains NO_CHANGE; BRAM gains the hardware column cascade
  and `SLEEP`; FIFO18/36E1 → E2 with asymmetric ports; UltraScale+ adds
  URAM, so revisit any 7-series design that used external memory for a
  few-Mb buffer.
- DSP48E1 → DSP48E2 is backwards compatible, but the pre-adder widens
  25 → 27 bits and the wide XOR is new: re-derive the INT8 pack for
  `S = 18` with guard bits instead of porting the `S ≤ 17` version.
- Control sets loosen from one clock/reset/enable per slice to two
  resets and four enables: a 7-series design that was control-set-bound
  may now pack, and keeping register groups artificially small buys
  nothing.
- Core voltage drops (0.95 V UltraScale, 0.85 V UltraScale+, 0.72 V for
  the L grades) — re-baseline timing rather than scaling the 7-series
  numbers by speed grade.

**10. Common mistakes on this family.**
- `set_clock_groups -asynchronous` across a crossing that contains an
  XPM_CDC macro or a project resync block: it overrides their scoped
  `set_max_delay -datapath_only` and the crossing becomes unbounded
  (A6).
- A third reset net or a fifth enable net inside what was meant to be
  one slice-wide register group.
- Expecting an initialised, dual-clock or non-72-bit memory to become
  URAM: it silently stays BRAM. Check the utilisation report.
- Omitting URAM's up-to-four pipeline cycles from the latency budget, or
  assuming a URAM port can read and write in the same cycle.
- Reusing a 7-series 1:10/1:14 SERDES ratio, or putting a clock enable
  or reset on an `IDDRE1`/`ODDRE1` pin that no longer exists.
- Laguna crossing registers with a reset or a clock enable — not
  packable, so the crossing routes through fabric.
- Assuming a BRAM cascade works across clock regions or columns.
- Accumulating more than seven packed INT8 products inside a DSP.
- Parallel `BUFGCE_DIV`s with independent CE/RST.
- Planning a source-synchronous interface on an HD bank.

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

#### Design instructions

**1. Timing and logic structure.**
- Budget one pipeline stage as *one LUT level plus one carry chain*.
  `LOOKAHEAD8` is eight bits per slice (32 bits of carry per CLB, since
  a CLB is four slices), so a W-bit add occupies `ceil(W/8)` slices as
  on UltraScale — but read the histogram differently: a `LOOKAHEAD8` is
  reported as several logic levels and costs **one to two LUT delays**
  (UG1788/UG1387). Do not pipeline a chain because the level count looks
  high. A chain may start at bit 0 or bit 4, so two narrow adders share
  a slice.
- **There are no `MUXF7`/`MUXF8`/`MUXF9`.** A wide mux is a dedicated
  LUT→LUT cascade (O6 into the next LUT's A5 input, A→B→…→H within the
  slice). One LUT6 still gives 4:1; each further factor of four costs a
  cascade hop instead of a free mux stage. Budget a LUT level per ×4
  beyond the first, and prefer a registered one-hot select, a decoded
  enable, or a small LUTRAM/BRAM lookup over a 16:1 or 32:1 mux that was
  free on UltraScale.
- Control-set grouping: clock and set/reset are **coarser** than
  UltraScale — four clocks and four SR nets per CLB, shared by the eight
  LUT/flip-flop pairs on one carry chain — so a distinct reset net costs
  a whole carry group rather than a slice half. AM005's "Differences
  from Previous Generations" states that "control sets for CLK and SR
  are at a coarser granularity, but CE stays the same"; follow AM005 and
  group registers by clock and reset first, by enable second (the
  architecture note above reads the CE granularity more pessimistically
  — treat CE as unchanged from UltraScale, four groups per slice, and
  verify with `report_control_sets`).
- **IMUX registers**, where the part has them, are registers at the
  interconnect/CLB boundary and at hard-block inputs (192 IMUX plus 64
  bypass per CLB) with CE and synchronous or asynchronous reset but no
  set and no init-to-1. The tools use them for hold fixing and as free
  pipeline stages. Never design a pipeline whose stage count depends on
  them: they are absent on the first-generation parts and on Gen 2
  (check AM005 for the part).
- Retiming: `-global_retiming` defaults to **on** for Versal. Write
  resetless datapath registers so the tool can move them; a reset,
  `dont_touch`, `mark_debug` or a timing exception on a datapath
  register silently disables this family's default optimisation.
- UG1387 "Avoid Unnecessary Pipelining": the CLB is four times larger
  and the interconnect faster, so measure the logic-level histogram
  before adding a stage — an unnecessary stage costs a control set and a
  cycle of latency for nothing.

**2. Registers, reset and enable.**
- A slice holds 8 LUTs and 16 flip-flops; a CLB holds four slices, 32
  LUTs and 64 flip-flops. Because clock and SR are shared across an
  eight-flip-flop carry group, a second reset net costs a whole carry
  group; a distinct enable costs four flip-flops.
- Exactly **half** a CLB's LUTs are SLICEM (LUTRAM/SRL-capable): 16 of
  32 — a better ratio than 7-series (about a third) — but LUTRAM and
  SRLs still compete for the same LUTs, so read `LUTRAMs` and `SRLs`
  separately (A9).
- SRL32 or two SRL16 per SLICEM LUT and 64-bit LUTRAM per LUT; neither
  has a reset. Never reset a delay line or a memory array.
- Never reset BRAM/URAM contents, SRLs, pipeline payload or the DSP58
  registers. On this family the cost is higher than elsewhere, because a
  reset on a datapath register also blocks the default global retiming.
- A register that must come up as '1' cannot live in an IMUX register
  (no set, no init-to-1) — keep it in the slice flip-flops and state
  that dependence where it matters.

**3. Memory.**
- LUTRAM (64 bits per LUT) for register files and asynchronous reads;
  `RAMB18E5`/`RAMB36E5` for Kb-scale; `URAM288E5` for large buffers
  whose natural access is 72 bits (present on most parts, typically 24
  per clock region per column). `rom_style = "ultra"` is available here
  for a large ROM.
- Accelerator RAM (XRAM: 4 MB, ECC, three 256-bit AXI ports, some AI
  Edge parts) and Multiport RAM (MPRAM, Premium VP1902 only) are
  block-design resources reached over AXI, never inferred from HDL.
- **External DDR is reached only through the hard DDRMC on the NoC.** Do
  not plan a soft memory controller in fabric; plan an AXI master and an
  NMU instead.
- Always use the BRAM output register (the block also offers a latched
  output — prefer the registered form). On URAM enable the input and
  output pipeline registers (up to four stages per port) and put those
  cycles in the latency budget.
- Cascade with `CASCADE_ORDER` and CASDIN/CASDOUT on BRAM and with the
  column cascade on URAM; `cascade_height` remains the timing-versus-
  power lever (A3, A11).
- Read-during-write modes and their costs are as UltraScale: all three
  in both TDP and SDP, `WRITE_FIRST` timing-safe by default,
  `NO_CHANGE` lowest power, `READ_FIRST` cheapest for a stream buffer;
  URAM's native mode is NO_CHANGE, single clock, no `INIT`, fixed
  72-bit width.
- ECC is one 64-bit code per 36 Kb block with **standard, encode-only
  and decode-only** variants — the split variants let the encoder and
  the decoder sit at opposite ends of a link, which the earlier families
  cannot do.
- **There is no hard FIFO primitive** (AM007 lists none). Every FIFO is
  `xpm_fifo_sync`/`xpm_fifo_async` or a project block over BRAM/URAM; a
  design that instantiated `FIFO18E2`/`FIFO36E2` must be rewritten.

**4. DSP.**
- Enable the input, product and output pipeline registers as on the
  earlier families; the DSP58 is backwards compatible with DSP48E2, so
  an existing multiply/MAC infers unchanged.
- 27×24 signed multiply with a 27-bit pre-adder (A 34 bits, B 24, C 58,
  D 27) and a **58-bit** accumulator (116 bits by cascading two). The
  wider accumulator removes most guard-bit and saturation gymnastics:
  size the accumulator from the loop bound instead of packing tricks.
- `DSP_MODE = "INT8"` is **native**: a three-term dot product
  `a0·b0 + a1·b1 + a2·b2` with 9-bit signed `a_i` and 8-bit signed
  `b_i` from six *independent* inputs, with accumulate or post-add.
  Three products per DSP, no shared operand, no shift, no guard bits and
  no unpacking — prefer it over any designer-side packing. Whether a
  sum-of-three-products in RTL infers the mode is a UG901 question for
  the tool version in use; instantiating `DSP58` with
  `DSP_MODE = "INT8"` is the certain route. Verify the DSP count and the
  mode in the utilisation report either way.
- `DSPFP32` for floating-point MAC (binary32 or binary16 multiplicand
  and multiplier, adder always binary32, round-to-nearest-even only, and
  **no bfloat16** — bfloat16 lives in AIE-ML, not in the fabric DSP);
  `DSPCPLX` for an 18×18 complex MAC over two adjacent DSP58s.
- Without the multiplier: SIMD dual-24 / quad-12 (`use_dsp = "simd"`), a
  58-bit logic unit, a wide XOR up to 116 bits (`use_dsp = "logic"`) and
  a 23-bit right shift — use them for vector adds, CRC/LFSR and
  fixed-point scaling.
- Cascades ACOUT/BCOUT/PCOUT/MULTSIGNOUT/CARRYCASCOUT are column-local
  as before; keep a cascade chain inside one column.
- Dense INT8/INT16 inference at scale belongs in the **AI Engines**, not
  the DSP column: the fabric DSP is for pre/post-processing and for
  shapes the AIE array cannot take.

**5. Clocking.**
- There is no CMT. Buffer/generator per job (AM003): the **MMCME5** for
  general frequency synthesis, jitter filtering and deskew (sigma-delta
  fractional divide, two deskew phase detectors, no inverted outputs);
  the **DPLL** — one per MMCM block, plus standalone DPLLs near HDIO and
  GT columns — for the same duties when the output feeds the general
  interconnect; the **XPLL** (two per XPIO bank, four outputs, no
  fractional divide; `X5PLL` on Gen 2) for PHY/I/O clocking only.
- Deskew constrains timing *analysis*, not just quality: an MMCM/XPLL
  output is safely timeable against CLKIN for `CLKOUTx_PHASE_CTRL` 00
  or 10 unconditionally, while the deskewing settings 01 and 11 are
  analysable only when the matching phase detector (PD1 or PD2) is
  active, and two deskewed outputs must share the same
  `CLKOUTx_DIVIDE`. Check AM003 "Safe Timing Clocking Topologies for
  MMCM and XPLL" before choosing a deskew topology.
- Buffers: `BUFGCE` for global clocks, `BUFGCTRL` for muxing,
  `BUFGCE_DIV` for a synchronous integer divide, `BUFG_GT` for
  transceiver clocks, `BUFG_PS` for the up-to-12 PS clocks, and the
  `MBUFG*` variants for leaf-level division. `BUFG_FABRIC` is for
  high-fanout **non-clock** nets (higher jitter, no deskew) — use it to
  broadcast a reset or a global enable, never for a clock.
- Per-region budget: 24 horizontal distribution tracks, hence 24 clocks
  per region, plus 12 horizontal and 24 vertical routing tracks. Global
  clock pins: four per XPIO bank, two per HDIO bank — so a clock input
  on an HDIO bank is a scarce resource.
- Clock-enable idiom unchanged, and it matters more here:
  **`power_opt_design` is not available on Versal**, so clock-enable and
  block-RAM enable gating must be written into the RTL rather than
  inserted by the tool (A11).

**6. IO and SERDES.**
- Pack an SDR I/O register into the IOL by instantiating `FDRE`/`FDSE`/
  `FDCE`/`FDPE` with `IOB = TRUE` on the instance (AM010) — the same
  idiom as the earlier families, with the primitive named explicitly.
- DDR: `ODDRE1` supports **only SAME_EDGE** on this family (both bits
  presented on the rising edge, which saves CLB and clock resources);
  IDDR modes are listed in AM010. If the data path uses `ODDRE1` the
  tristate path **must also** use `ODDRE1` — a mixed data/tristate
  registering structure is not allowed.
- High-speed source-synchronous interfaces use the **XPHY**: nine XPHY
  nibbles per XPIO bank, six NIBBLESLICEs each (54 pins per bank), each
  nibbleslice containing a serialiser, a deserialiser, I/O delays and a
  receive FIFO. Delays are trimmed by per-nibble built-in
  self-calibration (BISC) and are adjustable from the PL through the
  nibble's register interface unit (RIU). Check AM010 for the
  serialisation ratios and modes before fixing the fabric bus width.
- Delay resources are the uncalibrated input/output delay primitives
  plus the BISC-managed XPHY delays (AM010): there is no
  `IDELAYCTRL`-plus-reference-clock arrangement to build as on the
  earlier families.
- Bank rules that reach the RTL: XPIO (high-performance, XPHY, 54 pins,
  four GC pins) versus HDIO (lower rate, two GC pins, no XPHY). Decide
  which interface lives in which bank type before writing the I/O logic,
  and never plan a source-synchronous interface on HDIO (A10).

**7. Reset and CDC nuances.**
- Power-up initialisation is driven by the PMC/PLM as it loads the PDI
  rather than by a user-visible GSR net, but the consequence for RTL is
  identical to A4 §6: registers come up at their `INIT` value and the
  release is asynchronous to every user clock, so gate state-holding
  logic with a clock enable or a synchronised reset until the
  MMCM/DPLL has locked. See AM011 "Resets Overview" and UG1273 "Boot and
  Configuration" for the sequence.
- XPM_CDC, XPM_MEMORY and XPM_FIFO are available for this family
  (UG1344), and XPM_CDC is the recommended crossing circuitry.
  XPM_FIFO is also the *only* FIFO macro here, since there is no hard
  FIFO.
- `async_reg` applies as before; because clock and set/reset are shared
  across a carry group, keep synchroniser chains resetless and
  enable-less so a chain can share one group.
- The `-global_retiming on` default interacts with hand-written delay
  lines: `async_reg` implies `dont_touch` and so protects a
  synchroniser, but a plain N-cycle delay whose stage count is
  functionally required is not protected — mark it `dont_touch` or make
  it an SRL.

**8. Floorplanning and SLR.**
- Applicable on the multi-die parts (check DS950 per part). AM005: the
  super-long-line (SLL) connections are now **part of the CLB** rather
  than a dedicated Laguna column, so an SLR crossing is registered in
  ordinary CLB registers. Still register both sides with plain
  flip-flops and still assign blocks with `USER_SLR_ASSIGNMENT` or an
  SLR Pblock, but the placement is less special-cased than the
  UltraScale+ Laguna pairing.
- The NoC changes what floorplanning is for: cross-die and
  to-memory traffic travels over the hard NoC, not the fabric, so
  partition data movement by NMU/NSU access and keep only
  latency-critical fabric-to-fabric paths SLR-local.
- Clock regions carry 24 clocks; URAM is typically 24 per region per
  column. Size Pblocks on `CLOCKREGION` ranges and expect a block that
  needs more of a hard resource than a region holds to spread (A10).

**9. Migration notes.**
- From UltraScale+. Inferred RTL migrates and DSP48E2 code infers DSP58
  unchanged; re-derive INT8 as the native three-term dot product instead
  of a two-per-DSP pack, because the packing arithmetic becomes pure
  overhead.
- `MUXF7`/`MUXF8`/`MUXF9` instances have no equivalent: delete them and
  let the LUT cascade build the mux, then re-check any path that relied
  on a 32:1 mux being one slice.
- `CARRY8` → `LOOKAHEAD8`: inferred adders are unchanged, instantiated
  `CARRY8` must be retargeted.
- Replace `FIFO18E2`/`FIFO36E2` instances with `xpm_fifo_*`.
- Clocking: no CMT, so `MMCME3`/`MMCME4` and `PLLE3`/`PLLE4` instances
  become `MMCME5`/`DPLL`/`XPLL` — the Clocking Wizard is the safe route.
- SelectIO: `ISERDESE3`/`OSERDESE3` and the UltraScale bit-slice become
  the XPHY; `ODDRE1` keeps only SAME_EDGE; `IDELAYE3`/`ODELAYE3` and
  their calibration flow become the uncalibrated delay primitives plus
  BISC.
- `power_opt_design` is gone: move block-RAM enable gating and register
  CE gating into the RTL.
- Retiming turns on by default, so a design that carried resets on
  datapath registers gains nothing until they are removed.
- The PS/NoC boundary replaces the Zynq HP ports: no `S_AXI_HP*`,
  128-bit maximum on PS AXI, and PL-to-DDR bandwidth through NMUs (B4).

**10. Common mistakes on this family.**
- Building a 16:1 or 32:1 mux and expecting the UltraScale F8/F9 cost —
  it is a LUT cascade here.
- Reading `LOOKAHEAD8` logic levels literally and pipelining a path that
  already meets timing (UG1387 "Avoid Unnecessary Pipelining").
- Leaving resets on datapath registers and so defeating the family's
  default global retiming.
- Instantiating `FIFO36E2`, `MUXF8`, `CARRY8`, `IDELAYCTRL` or
  `MMCME4` — none of them exist here.
- Designing a pipeline that assumes IMUX registers, which are absent on
  the first-generation and Gen 2 parts.
- Planning a soft DDR controller, or a fabric AXI interconnect for
  memory and PS traffic, instead of the NoC — and then forgetting that
  the NMU boundary is an asynchronous crossing that needs a registered
  AXI interface and bursts sized for the 128-bit packet.
- Expecting `power_opt_design` to insert block-RAM enable gating.
- Using `ODDRE1` in OPPOSITE_EDGE mode, or mixing an `ODDRE1` data path
  with a non-`ODDRE1` tristate path.
- Carrying an UltraScale reset/enable grouping over unchanged: clock and
  set/reset are coarser here, so the same RTL fragments differently.
- Treating the AI Engine array as fabric — it is a peer accelerator
  reached over AXI4-Stream PLIO and the NoC.

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
| DDR I/O primitive | `IDDR` / `ODDR`, OPPOSITE_EDGE + SAME_EDGE (+ SAME_EDGE_PIPELINED on input) | `IDDRE1` / `ODDRE1`, same modes but no CE/S (ODDRE1 also no R) | same | `ODDRE1` SAME_EDGE only; tristate path must use the same structure |
| I/O delay | `IDELAYE2` 31 taps + `IDELAYCTRL` REFCLK (~78 ps/tap at 200 MHz); `ODELAYE2` HP banks only | `IDELAYE3`/`ODELAYE3`, COUNT or TIME format (TIME needs the calibration flow); ODELAY HP only | same | uncalibrated delay primitives + per-nibble BISC inside the XPHY; no IDELAYCTRL |
| SLR crossing register | Laguna (largest Virtex-7 only) | Laguna, one side of the crossing | Laguna `TX_REG` → `RX_REG`, both sides, `USER_SLL_REG` | SLL is part of the CLB (AM005) — ordinary CLB registers |
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
- `shared/FpgaInitialization.md` and `shared/HouseStyle.md`
  — the resetless-by-default policy that A4 grounds in GSR.
- `shared/TsfpgaModules.md` — module layout that A13's
  `scoped_constraints/` and `module_*.py` build projects live in.

Skills that should load this one: `vharch` (clock/reset/CDC/hard-block
planning, SLR and NoC decisions), `vhdesign` (inference template and
attribute choices in the proposal), `vhfill` (writing the templates),
`vhsynth` (interpreting a Vivado report and choosing the fix).

## Sources

- L. Vik, *Reliable FPGA CDC Constraints* #1 (single-bit level), #2
  (counters and FIFOs), #3 (pulses), #4 (build tool settings), #5
  (asynchronous FIFO), LinkedIn Pulse, 2024 — the error-mode analysis
  and the `set_max_delay -datapath_only` / `set_bus_skew` / scoped-`read_xdc`
  recipe in A6.1; verified against the shipped
  `hdl-modules/modules/{resync,fifo}/scoped_constraints/*.tcl`.

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
- UG429 7 Series FPGAs Migration Methodology Guide, v1.2 (2018-04-04)
  — migration into the 7-series family from Virtex-6/Spartan-6
  (clocking regions, MMCM, block RAM, DSP pointers).
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
  (2025-05-29) (some detail from the v1.7 PDF), "Key Differences from
  7 Series FPGAs" (buffer removals, reduced PLLs, `BUFCE_LEAF`,
  rectangular clock regions, CC→GC pins); UG1026 UltraScale
  Architecture Migration Methodology Guide, v1.5 (CARRY4→CARRY8,
  SelectIO retargeting).
- UG571 UltraScale Architecture SelectIO Resources User Guide, v1.16 —
  IDDRE1/ODDRE1 pin differences, ISERDESE3/OSERDESE3 ratios, bit-slice
  native mode and its bring-up/reset, IDELAYE3/ODELAYE3 delay formats
  and delay calibration, nibble mixing rules;
  UG570 UltraScale Architecture Configuration User Guide, v1.9.1 (SSI
  table).
- DS890 UltraScale Architecture and Product Data Sheet: Overview, v4.10
  (2026-05-21); DS892 (Kintex UltraScale) v1.20; DS893 (Virtex
  UltraScale) v1.13; DS923 (Virtex UltraScale+) v1.20; XMP103
  UltraScale+ Product Selection Guide v2.8.
- UG1085 Zynq UltraScale+ Device Technical Reference Manual, v2.5
  (2025-03-21); PG201 Zynq UltraScale+ Processing System v3.5.
- AM005 Versal Adaptive SoC Configurable Logic Block Architecture
  Manual, v1.4 (2025-05-14), including "Differences from Previous
  Generations" (4× CLB, LUT→LUT cascade, no MUXF7/F8/F9, IMUX
  registers, coarser CLK/SR control sets with CE unchanged, SLL
  connections moved into the CLB).
- AM004 Versal ACAP DSP Engine Architecture Manual, v1.2.1 (2022-09-11).
- AM007 Versal Adaptive SoC Memory Resources Architecture Manual, v1.2.1
  (2026-06-05).
- AM003 Versal Adaptive SoC Clocking Resources Architecture Manual, v1.6
  (2026-06-09), including "Clock Management MMCM, XPLL, and DPLL"
  (which block for which job) and "Safe Timing Clocking Topologies for
  MMCM and XPLL" (`CLKOUTx_PHASE_CTRL` and phase-detector rules).
- AM010 Versal Adaptive SoC SelectIO Resources Architecture Manual,
  2026.1 — XPIO/HDIO banks, XPHY nibbles and NIBBLESLICEs, BISC and
  the RIU, SDR flip-flop packing with `IOB = TRUE`, IDDR/ODDR modes,
  uncalibrated delay primitives.
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
renamed `resync_slv_level_coherent` to `resync_twophase`. Added in the
family design-instruction blocks, against expectation: AM005 states that
on Versal only the CLK and SR control-set granularity is coarser and
"CE stays the same" as UltraScale (the CLB fact paragraph above reads
the CE granularity more pessimistically — B3 follows AM005); Versal
`ODDRE1` supports SAME_EDGE only, and its tristate path must use the
same registering structure (AM010); Versal I/O registers are ordinary
`FDRE`-family primitives packed with `IOB = TRUE`, not a dedicated IOB
flip-flop (AM010); Versal SLL connections live in the CLB rather than a
Laguna column (AM005); UltraScale PLLs are *reduced* relative to
7-series PLLs, not merely renamed (UG572).
