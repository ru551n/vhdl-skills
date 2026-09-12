# tsfpga / hdl-modules Coding Conventions

This document is the concrete naming/style reference derived from auditing the
**real source** of the two upstream libraries this project vendors and reuses
(`shared/ReusableRTL.md` "Reuse before authoring new RTL"):

- `tsfpga` (Lukas Vik) — build/module framework, example modules.
- `hdl-modules` (Lukas Vik) — reusable RTL building blocks (fifo, axi,
  axi_lite, axi_stream, common, math, resync, register_file, ...).

Both are checked out as git submodules (`tsfpga/`, `hdl-modules/`) in
projects that vendor them, so their actual source is always available to
verify against directly (or via `corvidex-mcp`'s `get_source`) — this
document summarizes that source, it does not replace looking at it.

`shared/CodingStyle.md` and `shared/ModernVHDL.md` are still authoritative
for language-level rules (VHDL revision, type policy, sequential/
combinational patterns, CDC, etc.). This document is authoritative for the
**concrete naming and file-layout conventions** used by both upstream
libraries, and any new project that vendors/reuses them should follow suit
so that project RTL is stylistically indistinguishable from the vendored
libraries it composes with.

## Evidence

Counts are from a survey of `hdl-modules/modules/**/*.vhd` (187 files) and
`tsfpga/tsfpga/examples/modules/**/*.vhd` (30 files), current as of this
audit. Re-run the greps below against the checked-out submodules to
refresh if the upstreams drift.

| Convention | Evidence |
|---|---|
| Architecture named `a` (RTL) / `tb` (testbench) | 106× `architecture a`, 69× `architecture tb`, 0× any other name |
| No process name prefix | top labels: `main`, `assign`, `assertions`, `handle_input`, ... — never `p_*` |
| Instance label suffix `_inst` (or `dut` for a single DUT in a TB) | `axi_address_fifo_inst`, `handshake_pipeline_inst`, `fifo_wrapper_inst`, `dut` |
| Types/subtypes suffixed `_t` (not prefixed `t_`/`st_`) | `state_t`, `fifo_addr_t`, `mem_t`, `word_t`, `register_t` |
| Constants/generics: plain `lower_snake_case`, no `C_`/`c_`/`g_` prefix | generics `width`, `depth`, `almost_full_level`; constants `memory_depth`, `data_width`, `reg_index` |
| Enum literals: lowercase | `(idle, start, wait_for_address_transactions, running)`, `(ready, busy, done)` |
| Default unresolved types | `u_unsigned`/`u_signed` used 56× in `fifo/`; `std_ulogic_vector` outnumbers `std_logic_vector` ~10:1 project-wide (485 vs 47 in hdl-modules, 65 vs 15 in tsfpga examples) |
| Reset: active-high `reset`, synchronous, mostly omitted | only 5 of 84 `hdl-modules/**/src/*.vhd` files declare a `reset` port at all; where present: `reset : in std_ulogic := '0'` with a doc comment "Active-high synchronous reset."; the rest rely on declaration initial values (`shared/FpgaInitialization.md`) |

## Naming (supersedes conflicting bullets in `CodingStyle.md`/`ModernVHDL.md`)

- entities, architectures, signals, ports, generics, constants, **and
  process/subprogram-local `variable`s**: `lower_snake_case`, no prefix
  (`data_width`, `memory_depth`, `export_base`, not `g_data_width` /
  `C_DATA_WIDTH` / `c_data_width` / `v_export_base`). A local `variable`
  gets no special marker distinguishing it from a signal or constant --
  name it for what it holds, the same as everything else.
- types and subtypes: suffix `_t` (`state_t`, `fifo_addr_t`), not a `t_`/`st_`
  prefix. A subtype used as an address/index range may instead use a
  descriptive `_range` name (`bram_addr_range`) when that reads better than
  a `_t` type.
- enum literals: lowercase, descriptive (`idle`, `running`, `wait_for_ar_done`),
  never `ALL_CAPS`.
- process labels: a plain descriptive name, no `p_` prefix (`main`, `assign`,
  `ctrl`, `handle_input`). Pick a name that describes what the process does,
  not that it is a process.
- instance labels: suffix `_inst` (`fifo_inst`, `handshake_pipeline_inst`),
  no `u_` prefix. In a testbench with exactly one DUT, name it `dut` (or
  `dut_<variant>` when multiple DUT configurations coexist in one TB).
- generate blocks: a descriptive name is fine; a `g_` prefix is acceptable
  here specifically since it disambiguates a generate label from a same-named
  signal, but is not required practice upstream — do not extend the `g_`
  habit to generics or constants.
- pipeline-stage signals: `_p1`/`_p2`/.../`_m1`/`_m2`/... relative-stage
  coordinates — see "Pipeline relative-stage naming" below for the full
  convention (11 real `_p1` instances in `hdl-modules/modules/common/src/
  axi_stream_protocol_checker.vhd`).
- directional record types/ports: suffix `_m2s`/`_s2m` (`stream_m2s_t`,
  `m_axi_m2s`), or the project's own directional terminology
  (`source`/`sink`, `request`/`response`) when that reads clearer than
  master/slave naming — see `shared/InterfaceRecords.md` for when a
  directional record is the right tool versus flat ports.
- registered vs. combinational signals: suffix `_q` for a signal driven from
  inside a clocked process (a register/latched value — `busy_q`, `cnt_cmd_q`),
  with no suffix for a signal that is purely combinational (`effective_in_addr`,
  driven by a plain concurrent assignment). **Project-specific, not evidenced
  upstream** (`_q` does not appear anywhere in the audited `tsfpga`/
  `hdl-modules` source — unlike every other bullet here, this one has no
  upstream precedent to point to) — adopted in this project's own RTL because
  the distinction is load-bearing where it is easy to get wrong: a validation
  check that must see a same-cycle relocated address, for instance, breaks
  silently if that address is accidentally registered (`_q`) instead of
  combinational, one cycle later than the check expects. Do not use `_q` for
  anything that is not itself the direct target of a clocked signal
  assignment (`<=` inside `if rising_edge(clk) then`).

This changes the following previously-documented defaults:

- `CodingStyle.md`'s "constants: `C_UPPER_SNAKE_CASE`" → plain
  `lower_snake_case`, matching everything else.
- `CodingStyle.md`'s "types: `t_*`" / "subtypes: `st_*`" → `_t` suffix.
- `CodingStyle.md`'s "instances: `u_*`" → `_inst` suffix.
- `CodingStyle.md`'s "processes: `p_*`" → no prefix, descriptive name.
- `ModernVHDL.md`/`FpgaInitialization.md` code examples using `C_MAX_*`,
  `t_state`, `p_regs` → lowercase constants, `_t`-suffixed types, unprefixed
  process labels.
- `CodingStyle.md`'s former "Pipeline relative-stage naming" and "Direction
  markers" sections moved here verbatim (this is now the one copy); both
  files still point at each other for the design-level context each retains
  (`FpgaInitialization.md`, `TypeResolutionPolicy.md`, `CdcPolicy.md`, etc.).

## Pipeline relative-stage naming

Pipeline signal names use **relative stage coordinates** around the signal
that is the local semantic reference point.

- `_p1`, `_p2`, `_p3`, ... mean one, two, three, ... registered stages
  **after** the reference signal (`p` = plus).
- `_m1`, `_m2`, `_m3`, ... mean one, two, three, ... stages **before** the
  reference signal (`m` = minus).
- The unsuffixed name is the local reference stage (`0`).

```vhdl
signal sample_m2 : signed(15 downto 0);
signal sample_m1 : signed(15 downto 0);
signal sample    : signed(15 downto 0);
signal sample_p1 : signed(15 downto 0);
signal sample_p2 : signed(15 downto 0);
```

Conceptually:

```text
sample_m2 -> sample_m1 -> sample -> sample_p1 -> sample_p2
    -2           -1          0          +1          +2
```

The coordinate is relative to the **chosen semantic reference signal**, not
necessarily relative to an entity input or the first register in the module.

Signals that describe the same transaction/sample must use matching stage
coordinates:

```vhdl
signal data_p2  : unsigned(31 downto 0);
signal valid_p2 : std_logic;
signal last_p2  : std_logic;
signal tag_p2   : tag_t;
```

Keep the functional name when the meaning changes rather than renaming every
transformed value to the same base name merely to show pipeline depth:

```vhdl
signal multiplicand : signed(15 downto 0);
signal product_p1   : signed(31 downto 0);
signal rounded_p2   : signed(15 downto 0);
signal result_p3    : signed(15 downto 0);
```

`_mN` is useful when logic is described relative to a sampled/reference
point — FIR taps, alignment windows, delayed observations, or any notation
that naturally has values before and after a reference sample:

```vhdl
y <= coeff_m1 * sample_m1 +
     coeff    * sample +
     coeff_p1 * sample_p1;
```

The names describe relative alignment, not physical time travel — an `_m1`
signal must still be implemented from data actually available in the
hardware architecture.

For long, repetitive pipelines, an indexed array with a documented coordinate
mapping may be clearer than many individual `_pN` declarations (use negative
array indices only when the complete active toolchain is verified to support
them cleanly):

```vhdl
type sample_pipe_t is array (integer range <>) of signed(15 downto 0);
signal sample_pipe : sample_pipe_t(-2 to 3);
```

Rules:

- Do not mix `_dN`, `_r`, `_rr`, `_regN`, `_stageN`, and `_pN` for the same
  relative-delay concept in one module.
- Prefer `_pN`/`_mN` for externally visible names, debug signals, and short
  pipelines where relative alignment matters.
- Pipeline coordinates must remain consistent for data, valid, sideband and
  control signals.
- Document the chosen stage-0 reference when it is not obvious.
- When retiming changes physical register placement, update names if their
  architectural relative-stage meaning changes.

## Comment markers

`--@` marks unfinished design-direction code that still needs a decision or
an implementation:

```vhdl
--@ implement skid-buffer backpressure
```

A filled/complete module must not retain unresolved `--@` markers — treat
one as a signal that the module isn't actually done yet, not decoration.

## Declaration and port-map formatting

Do not column-align the `:`/`:=`/`=>` delimiter across a block of port,
generic, or signal declarations, or across a port map/generic map — one
space either side, ragged columns left where they fall (confirmed real
upstream practice, not just a preference: `hdl-modules/modules/fifo/src/
fifo.vhd`'s own `generic`/`port` blocks and `fifo_wrapper.vhd`'s `port map`
are both unaligned despite widely varying identifier lengths):

```vhdl
port (
  clk : in std_ulogic;
  write_ready : out std_ulogic := '1';
  write_valid : in std_ulogic;
  write_data : in std_ulogic_vector(width - 1 downto 0)
);
```

not

```vhdl
port (
  clk         : in std_ulogic;
  write_ready : out std_ulogic := '1';
  write_valid : in std_ulogic;
  write_data  : in std_ulogic_vector(width - 1 downto 0)
);
```

Same for port maps/generic maps:

```vhdl
port map (
  clk_write => clk_write,
  write_ready => write_ready,
  write_almost_full => almost_full
);
```

Aligned columns look tidy the day they're written but rot the moment any one
name changes length, forcing a whitespace-only diff across every other line
in the block just to re-align — not worth the churn, and not what upstream
actually does.

## Architecture naming

Use `a` for a synthesizable RTL architecture and `tb` for a testbench
architecture. Do not use `rtl` (a common convention in *other* VHDL
ecosystems, but not this one) unless a specific requirement says otherwise.

```vhdl
architecture a of fifo is
begin
  ...
end architecture;
```

```vhdl
architecture tb of tb_fifo is
begin
  ...
end architecture;
```

A third name, `model`, is reserved for a behavioral stand-in used in
place of a not-yet-implemented `a` architecture — see `shared/Vunit.md`
§"Stub-first top-level integration testing" for when and how. Keep it in
its own file (`<module>_model.vhd`), never appended to the same file as
`a`.

```vhdl
architecture model of fifo is
begin
  ...
end architecture;
```

## Reset policy

Default: **resetless**, using declaration initial values for power-up state
(see `shared/FpgaInitialization.md` for the decision rule — this is exactly
the case upstream is optimizing for; the large majority of `hdl-modules`
source files have no reset port at all).

This default only applies when the architecture actually supports it —
i.e. every register's declaration initial value already gives the correct
power-up/idle state, with no runtime re-initialization requirement. It is
a per-module decision, not a blanket rule to apply without checking: during
architecture design (`vharch`'s "Reset policy decision") or when migrating
existing RTL, ask the user rather than silently stripping/adding a reset
port whenever the correct choice is not already evident from the
requirement.

When a design genuinely needs a runtime-restorable reset (soft
reset/watchdog/interface reset semantics, not just power-up
initialization), use a single **active-high, synchronous** `reset` port,
not an active-low `rst_n`:

```vhdl
port (
  clk : in std_ulogic;
  -- Active-high synchronous reset.
  reset : in std_ulogic := '0';
  ...
);
```

```vhdl
main : process(clk)
begin
  if rising_edge(clk) then
    if reset then
      state <= idle;
    elsif ce then
      state <= next_state;
    end if;
  end if;
end process;
```

This supersedes `CodingStyle.md`/`ModernVHDL.md`'s previously-stated default
of synchronous active-low `rst_n`. A project may still choose `rst_n` when
a specific external requirement mandates it (e.g. integrating third-party
IP that exposes an active-low reset), but that must be a documented,
deliberate exception, not the default.

## Type resolution default

Default to unresolved types (`std_ulogic`, `std_ulogic_vector`,
`u_unsigned`, `u_signed`) per `shared/TypeResolutionPolicy.md`; this is
confirmed as the overwhelming majority convention upstream (~90% of vector
ports/signals), not just a theoretical default. Use resolved types
(`std_logic(_vector)`, `unsigned`, `signed`) only at a genuine
resolution/external-interoperability boundary.

## Port/generic documentation comments

Document non-obvious generics and ports with a `--` comment directly above
the declaration, referencing other identifiers with double backticks/single
quotes so they read well both in the source and in generated documentation:

```vhdl
generic (
  -- Set to true in order to use 'read_last' and 'write_last'
  enable_last : boolean := false
);
port (
  -- '1' if FIFO is not full
  write_ready : out std_ulogic := '1'
);
```

Use a bare `--# {{}}` comment line to separate logically distinct groups of
ports (e.g. one group per interface: clock, one per AXI-Stream channel,
config/status), which downstream documentation tooling (`shared/
ModuleDocContract.md`) can render as a visual break:

```vhdl
port (
  clk : in std_ulogic;
  --# {{}}
  write_ready : out std_ulogic := '1';
  write_valid : in std_ulogic;
  --# {{}}
  read_ready : in std_ulogic;
  read_valid : out std_ulogic := '0'
);
```

## File header banner

Upstream files open with a project copyright/link banner comment before the
`library`/`use` clauses. A project that is not itself `tsfpga`/`hdl-modules`
should not copy that copyright text, but the same *shape* — a short banner
block, optionally followed by a longer module-purpose comment above the
`entity` declaration referencing the module's requirement/proposal docs — is
a useful convention to keep for consistency with vendored code:

```vhdl
-- Generic AXI4-Stream 3x3 sliding-window generator over a continuous
-- raster-scan stream. See modules/canny_window3x3/doc/canny_window3x3_req.md
-- and modules/canny_window3x3/doc/canny_window3x3_proposal.md.
entity canny_window3x3 is
```

## Known deltas as of this audit

The following were found in this project's own `modules/*/src/*.vhd` at
audit time and have **not yet been migrated** to the conventions above
(migrating them is a separate, deliberate follow-up — see the audit
summary for the affected files and the risk of touching reset polarity
in already-passing RTL/testbenches):

- Generics prefixed `g_` (`g_img_width`, `g_data_width`) — should be
  unprefixed.
- Constants prefixed `c_` (`c_lane_width`, `c_fifo_depth`) — should be
  unprefixed.
- Reset is active-low `rst_n` — should be active-high `reset` (or omitted
  where only power-up initialization is required).
- Architecture named `rtl` — should be `a`.

Already-conforming, no change needed:

- Process labels have no prefix already (`assemble_window`, `row_taps`, ...).
- Instance labels already use the `_inst` suffix (or `dut`).
- Types already use the `_t` suffix (`state_t`, `taps9_t`, `magnitude_t`).
