# VHDL Coding Style

Read `ModernVHDL.md` first. This file contains the concise coding rules.

## Baseline

Default synthesizable language: **VHDL-2008**.

VHDL-2019 is opt-in only after the complete active toolchain is verified.

Use:

```vhdl
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
```

Do not use:
- `std_logic_arith`
- `std_logic_unsigned`
- `std_logic_signed`

## Naming

Read `HouseStyle.md` — it is authoritative for concrete naming,
derived from auditing the real `tsfpga`/`hdl-modules` source this project
vendors and reuses. Summary:

- entities, architectures, signals, ports, generics, **and constants**:
  `lower_snake_case`, no prefix (not `C_UPPER_SNAKE_CASE`, not `g_*`/`c_*`)
- types and subtypes: suffix `_t` (not a `t_*`/`st_*` prefix)
- enum literals: lowercase
- instances: suffix `_inst` (`dut` for a single DUT in a testbench), not a
  `u_*` prefix
- processes: a plain descriptive name, not a `p_*` prefix
- generate blocks: a descriptive name; a `g_` prefix is acceptable here
  specifically to disambiguate from a same-named signal, but do not extend
  that habit to generics or constants
- architecture name: `a` for RTL, `tb` for testbenches (not `rtl`)

Choose names by intent, not by temporary implementation.

## Types

Use the narrowest semantic type that fits:
- enum for FSM state
- boolean for internal predicates
- natural/positive/constrained integers for bounded counters
- unsigned/signed for arithmetic
- std_logic_vector for opaque packed bits
- std_ulogic(_vector) for proven single-driver internal conventions
- std_logic(_vector) for resolved/external interoperability

Prefer explicit width conversions and `resize`.

## Combinational

Prefer concurrent assignments for simple logic.

Use:

```vhdl
comb : process(all)
begin
  next_state <= state;
  ...
end process;
```

for non-trivial combinational logic.

Every combinational output must receive a value on every path.

## Sequential

Canonical style:

```vhdl
regs : process(clk)
begin
  if rising_edge(clk) then
    if reset = '1' then
      state <= idle;
      valid <= '0';
    elsif ce = '1' then
      state <= next_state;
      valid <= next_valid;
    end if;
  end if;
end process;
```

Reset only state that functionally requires initialization. Default is
resetless (declaration initial values, `FpgaInitialization.md`); when a
runtime-restorable reset is genuinely needed, use active-high synchronous
`reset`, not active-low `rst_n` — see `HouseStyle.md` "Reset
policy".

Prefer clock enables over gated clocks.

## FSM

Use an enumerated type:

```vhdl
type state_t is (idle, run, done);
signal state, next_state : state_t;
```

Do not manually encode unless encoding is part of an explicit implementation requirement.

## Interfaces

For ready/valid:
- transfer = `valid and ready`
- producer keeps payload stable while stalled
- latency and backpressure semantics must be documented

Records are encouraged internally when they improve clarity and tool support is
known. Prefer scalar/vector ports at uncertain vendor/IP boundaries.

## CDC

Never treat CDC as ordinary wiring.

Use an explicit, documented structure suitable for the crossing class:
synchronizer, handshake/toggle, async FIFO, reset synchronizer, etc.

## Assertions

Use static/elaboration-time assertions for invalid generic combinations where
supported, and runtime assertions/checkers for important invariants.

## Direction markers

See `HouseStyle.md` "Comment markers" for the `--@` convention.

## Verdicts

VUnit tests use VUnit's own check/reporting mechanisms.

Only standalone fallback testbenches use exactly one:
- `[FINISH] PASS`
- `[FINISH] FAIL`

## Mandatory arithmetic rule

Arithmetic means `numeric_std`.

If a value is used as a number, its normal internal type should be:
- `unsigned`
- `signed`
- `natural` / `integer` / a constrained subtype

Do not keep numeric state in `std_logic_vector`.

Good:

```vhdl
signal credits : unsigned(7 downto 0);

credits <= credits + 1;
```

Bad:

```vhdl
signal credits : std_logic_vector(7 downto 0);

credits <= std_logic_vector(unsigned(credits) + 1);
```

The second form is permitted only at a genuine representation/interface boundary, not as the normal internal coding style.

Legacy packages `std_logic_arith`, `std_logic_unsigned`, and `std_logic_signed` are forbidden.

## Counter types

Counters may be `natural`, constrained `integer`, or `unsigned`.

Prefer the type that expresses the contract:

```vhdl
signal packet_count : natural range 0 to max_packets := 0;
signal signed_delta : integer range -127 to 127 := 0;
signal phase_count  : unsigned(15 downto 0) := (others => '0');
```

Do not force counters to vectors when their bit representation is irrelevant.

## Initialization versus reset

Read `FpgaInitialization.md`.

On a verified FPGA target, declaration initial values may be used instead of a
reset branch when reset existed only for power-up initialization.

Example:

```vhdl
signal state : state_t := idle;
signal count : natural range 0 to max_count := 0;
```

Do not use this optimization for unknown targets or when runtime reset behavior
is required.

## Pipeline relative-stage naming

See `HouseStyle.md` "Pipeline relative-stage naming" for the
full `_pN`/`_mN` convention (moved there — it's a naming rule, not a
language-level one).

## Resolved/unresolved types

Read `TypeResolutionPolicy.md`.

Default is unresolved:
- `std_ulogic`
- `std_ulogic_vector`
- `u_unsigned`
- `u_signed`

But ask the user before locking a project-wide policy when their preference is
not already known. If they choose resolved types, consistently use:
- `std_logic`
- `std_logic_vector`
- `unsigned`
- `signed`

## Internal protocol records

Read `InterfaceRecords.md`.

Use typed records for cohesive internal interfaces where appropriate.
Directional record pairs such as `*_m2s` / `*_s2m` are preferred when they
make signal ownership clear.

Do not force record ports across vendor/tool boundaries that require flat
signals.

## Portability level

Read `VendorPolicy.md`.

Default to `PORTABLE_VHDL`. Vendor attributes, primitives, and IP require an
explicit reason and should be isolated behind a local boundary where practical.

## Synthesizability boundary

Read `SynthesizableVHDL.md`.

Do not allow simulation-only constructs in production RTL. Verification code
may use the full language/tool capabilities appropriate for simulation.

## Generic design

Read `ReusableRTL.md`.

Use semantic generic types and named constants. Avoid unexplained magic numbers
and generics that merely expose internal implementation details.
