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

- entities, architectures, signals, ports, generics, **and constants**:
  `lower_snake_case`, no prefix (`data_width`, `memory_depth`, not
  `g_data_width` / `C_DATA_WIDTH` / `c_data_width`).
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

This changes the following previously-documented defaults:

- `CodingStyle.md`'s "constants: `C_UPPER_SNAKE_CASE`" → plain
  `lower_snake_case`, matching everything else.
- `CodingStyle.md`'s "types: `t_*`" / "subtypes: `st_*`" → `_t` suffix.
- `CodingStyle.md`'s "instances: `u_*`" → `_inst` suffix.
- `CodingStyle.md`'s "processes: `p_*`" → no prefix, descriptive name.
- `ModernVHDL.md`/`FpgaInitialization.md` code examples using `C_MAX_*`,
  `t_state`, `p_regs` → lowercase constants, `_t`-suffixed types, unprefixed
  process labels.

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
