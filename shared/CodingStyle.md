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

- entities, architectures, signals, ports, generics: `lower_snake_case`
- constants: `C_UPPER_SNAKE_CASE`
- types: `t_*`
- subtypes: `st_*`
- instances: `u_*`
- processes: `p_*`
- generate blocks: `g_*`

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
p_comb : process(all)
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
p_regs : process(clk)
begin
  if rising_edge(clk) then
    if rst_n = '0' then
      state <= IDLE;
      valid <= '0';
    elsif ce = '1' then
      state <= next_state;
      valid <= next_valid;
    end if;
  end if;
end process;
```

Reset only state that functionally requires initialization.

Prefer clock enables over gated clocks.

## FSM

Use an enumerated type:

```vhdl
type t_state is (IDLE, RUN, DONE);
signal state, next_state : t_state;
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

`--@` marks unfinished design-direction code.

Example:

```vhdl
--@ implement skid-buffer backpressure
```

A filled module must not retain unresolved `--@` markers.

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
signal packet_count : natural range 0 to C_MAX_PACKETS := 0;
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
signal state : t_state := IDLE;
signal count : natural range 0 to C_MAX := 0;
```

Do not use this optimization for unknown targets or when runtime reset behavior
is required.

## Pipeline relative-stage naming

Pipeline signal names use **relative stage coordinates** around the signal that
is the local semantic reference point.

- `_p1`, `_p2`, `_p3`, ... mean one, two, three, ... registered stages **after**
  the reference signal (`p` = plus).
- `_m1`, `_m2`, `_m3`, ... mean one, two, three, ... stages **before** the
  reference signal (`m` = minus).
- The unsuffixed name is the local reference stage (`0`).

Example:

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

### Alignment

Signals that describe the same transaction/sample must use matching stage
coordinates.

```vhdl
signal data_p2  : unsigned(31 downto 0);
signal valid_p2 : std_logic;
signal last_p2  : std_logic;
signal tag_p2   : t_tag;
```

If `data_p2` is aligned with `valid_p2`, they represent the same relative stage.

### Functional transformations

Keep the functional name when the meaning changes.

```vhdl
signal multiplicand : signed(15 downto 0);
signal product_p1   : signed(31 downto 0);
signal rounded_p2   : signed(15 downto 0);
signal result_p3    : signed(15 downto 0);
```

Do not rename every transformed value to the same base name merely to show
pipeline depth.

### Negative stages

`_mN` is useful when logic is described relative to a sampled/reference point,
for example FIR taps, alignment windows, delayed observations, or algorithms
whose notation naturally has values before and after a reference sample.

Example:

```vhdl
y <= coeff_m1 * sample_m1 +
     coeff    * sample +
     coeff_p1 * sample_p1;
```

The names describe relative alignment, not physical time travel. An `_m1`
signal must still be implemented from data that is actually available in the
hardware architecture.

### Long homogeneous pipelines

For long repetitive pipelines, an indexed array may be clearer than many
individual declarations:

```vhdl
type t_sample_pipe is array (integer range <>) of signed(15 downto 0);
signal sample_pipe : t_sample_pipe(-2 to 3);
```

Then the index has the same semantic coordinate:

```vhdl
sample_pipe(-2)
sample_pipe(-1)
sample_pipe(0)
sample_pipe(1)
sample_pipe(2)
sample_pipe(3)
```

Use negative array indices only when supported cleanly by the complete active
toolchain; otherwise use named `_mN` / `_pN` signals or a zero-based storage
array with documented coordinate mapping.

### Rules

- Do not mix `_dN`, `_r`, `_rr`, `_regN`, `_stageN`, and `_pN` for the same
  relative-delay concept.
- Prefer `_pN` / `_mN` for externally visible names, debug signals, and short
  pipelines where relative alignment matters.
- Pipeline coordinates must remain consistent for data, valid, sideband and
  control signals.
- Document the chosen stage-0 reference when it is not obvious.
- When retiming changes physical register placement, update names if their
  architectural relative-stage meaning changes.

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
