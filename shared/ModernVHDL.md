# Modern VHDL Development Profile

This profile defines the default engineering policy for these skills.

## Language revision

### Production baseline: VHDL-2008

Use VHDL-2008 for synthesizable RTL unless the project explicitly selects a
different revision.

Reasons:
- broad simulator/synthesis support
- useful modern constructs such as `process(all)`, generic packages,
  unconstrained array elements, improved generate syntax and output-port reads
- good compatibility across GHDL, VUnit and current FPGA vendor flows

### VHDL-2019: opt-in

Use VHDL-2019 only when all active tools in the requested flow have been
verified to support every construct being used.

Do not upgrade a project to VHDL-2019 merely because one simulator accepts it.

A project may declare:

```text
VHDL_STANDARD=2008
```

or:

```text
VHDL_STANDARD=2019
```

The selected revision must be propagated consistently through simulation,
lint/analysis and synthesis.

## Type discipline

Prefer types that express intent.

- `boolean` for internal true/false state when it is not an external logic pin
- enumerated types for FSM state
- `natural`, `positive`, constrained integer subtypes for bounded counters and indices
- `unsigned` and `signed` for arithmetic vectors
- `std_logic_vector` for opaque packed bits/protocol payloads
- `std_ulogic` / `std_ulogic_vector` for intentionally single-driver internal
  signals when the project/toolchain convention supports them
- `std_logic` / `std_logic_vector` where resolution or external interoperability
  is required

Never use vector arithmetic through implicit or legacy packages.

Prefer explicit conversions at domain boundaries rather than spreading casts
through the implementation.

## Interfaces

Prefer strongly typed records for internal interfaces when they improve
readability and are accepted by the project toolchain.

At external IP/vendor/tool boundaries, default to conventional scalar/vector
ports unless record ports are already proven compatible with:
- synthesis
- IP packaging
- constraints
- simulation
- downstream integration

For ready/valid style streaming interfaces:
- producer owns `valid` and payload
- consumer owns `ready`
- transfer occurs exactly when `valid = '1' and ready = '1'`
- payload remains stable while stalled unless the protocol explicitly permits otherwise
- latency and backpressure behavior belong in the interface contract

## Sequential logic

Use canonical synchronous processes:

```vhdl
p_regs : process(clk)
begin
  if rising_edge(clk) then
    if rst_n = '0' then
      ...
    elsif ce = '1' then
      ...
    end if;
  end if;
end process;
```

Prefer clock enables over fabric-gated clocks.

Do not reset every datapath register by habit. Reset:
- architectural/control state that requires a defined post-reset value
- protocol-visible valid/state bits
- safety-critical state required by the specification

Avoid resetting large datapaths/RAM pipelines unless functionally required;
unnecessary reset logic can hurt area, timing, RAM/DSP inference and retiming.

## Reset policy

Reset behavior must be explicit per clock domain:
- polarity
- synchronous/asynchronous assertion
- synchronous/asynchronous deassertion
- required reset duration
- post-reset protocol behavior

Default project convention may be synchronous active-low `rst_n`, but a
requirement or target-library constraint overrides that default.

For asynchronous external resets crossing into a synchronous domain, prefer
an explicitly designed reset synchronizer when appropriate. Never assume an
asynchronous reset may be deasserted safely without domain-specific handling.

## Combinational logic

Use `process(all)` for non-trivial combinational processes in VHDL-2008+.

Assign complete defaults first, then override them. Avoid accidental storage.

Prefer concurrent assignments for simple expressions and muxes.

Use `case` for decoded state/opcode logic when it improves completeness and
reviewability.

## Arithmetic

Use `ieee.numeric_std`.

Make width changes explicit:
- `resize(...)`
- explicit slicing
- explicit `signed(...)` / `unsigned(...)`
- explicit result-width policy

Document whether overflow:
- wraps
- saturates
- raises/checks
- is impossible by construction

Do not rely on implicit integer/vector width assumptions.

Use `fixed_pkg` only when the active simulator and synthesis backend support
the required usage; otherwise use explicit signed/unsigned fixed-point
conventions with documented binary point.

## FSMs

Prefer enumerated state types.

Default to:
- one sequential state register process
- combinational next-state/output process

A one-process FSM is acceptable when it is clearer and consistent with project
conventions.

Define behavior for illegal/corrupt state when the implementation or safety
requirements warrant it.

Do not hand-encode state values unless synthesis/CDC/safety requirements make
encoding part of the contract.

## Clock-domain crossing

Every clock crossing must be classified.

Examples:
- single-bit level
- pulse/event
- multi-bit data
- ready/valid stream
- asynchronous FIFO
- reset crossing

Rules:
- never independently synchronize bits of a coherent multi-bit bus
- use 2+ stage synchronizers only for appropriate single-bit signals
- use handshake/toggle/event synchronization for pulses as appropriate
- use asynchronous FIFOs for sustained multi-bit streams across unrelated clocks
- mark/document synchronizer registers for the target flow when needed
- keep CDC structures recognizable to synthesis and CDC analysis tools
- add constraints/attributes only when they are justified by the target flow

CDC intent must be documented in architecture/module docs.

## Generics and reusable structures

Prefer generics for:
- widths
- depths
- feature options
- bounded implementation choices

Reject invalid generic combinations early using static assertions where
portable.

Prefer packages for shared:
- types
- constants
- conversion functions
- protocol helpers

Generic packages are useful in VHDL-2008 but should be used only when all
active tools support the chosen pattern.

Avoid enormous "utility packages" that create unnecessary dependencies.

## Assertions

Use assertions for executable design assumptions where synthesis/tool support
is appropriate.

Good candidates:
- legal generic combinations
- impossible control combinations
- protocol invariants
- bounds/overflow assumptions
- mutually exclusive enables

Simulation-only assertions are encouraged in testbench/checker code.

PSL or other formal properties are optional enhancements, not a mandatory
dependency. If a project already uses formal verification, preserve and extend
that framework rather than introducing a second one.

## Verification

Prefer VUnit for automated VHDL verification.

Tests should be:
- deterministic by default
- seed-reporting when randomized
- self-checking
- independently runnable
- named after behavior/requirement, not implementation details
- able to produce useful logs and optional waveforms

Use randomized testing when it increases state/input-space coverage, but always
record the seed needed to reproduce a failure.

Prefer checkers/scoreboards/reference models over manual waveform inspection.

Use waveform analysis for diagnosis, not as the primary pass/fail mechanism.

Functional/code coverage may be enabled when the selected simulator supports it.
Coverage percentage alone is never proof of requirement completeness.

If the project already uses OSVVM, UVVM or another verification framework,
integrate with it rather than replacing it solely to satisfy these skills.

## Synthesis portability

Write inference-friendly RTL.

Prefer recognizable templates for:
- RAM
- ROM
- DSP arithmetic
- shift registers
- clock enables
- synchronizers

Keep vendor attributes isolated and documented.

Portable synthesis through GHDL/Yosys is useful for structural/resource
feedback, but vendor implementation remains authoritative for:
- FPGA primitive mapping
- place and route
- WNS/TNS
- clocking
- routing congestion
- power
- device-specific design rules

## Timing intent

A functionally correct RTL design is not complete without known timing intent.

Architecture/module docs should identify:
- clock domains and nominal/required frequency
- input/output timing assumptions where relevant
- intended pipeline latency
- false/multicycle/asynchronous relationships only when genuinely applicable

Do not create timing exceptions to hide failing paths.

## Tool hygiene and reproducibility

Prefer:
- repository-controlled scripts/configuration
- explicit compile order
- explicit VHDL standard
- pinned or recorded tool versions in CI
- non-interactive regression/synthesis commands
- generated artifacts outside source directories when practical

Do not depend on GUI-only state for reproducible verification or synthesis.

## Lint/static checks

Before declaring implementation complete:
- compile/analyze all affected VHDL with warnings enabled where practical
- eliminate unintended latches and multiple drivers
- inspect width/range warnings
- inspect unused/unconnected signals when meaningful
- check generated/source dependency order
- keep the language server/static analyzer clean where the project uses one

A compiler warning is not automatically a bug, but unexplained warnings should
not accumulate.

## Documentation contract

Documentation must capture design intent, not restate syntax.

At minimum document:
- purpose
- generics
- ports/interfaces
- clock/reset domains
- behavior
- handshake/backpressure
- latency
- arithmetic width/overflow semantics
- CDC
- important implementation choices
- verification strategy
- synthesis/timing assumptions

## Mandatory numeric_std arithmetic policy

All arithmetic RTL must use `ieee.numeric_std`.

Required baseline:

```vhdl
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
```

Forbidden legacy/non-standard arithmetic packages:

```vhdl
use ieee.std_logic_arith.all;
use ieee.std_logic_unsigned.all;
use ieee.std_logic_signed.all;
```

### Declaration rule

If a signal is conceptually numeric and participates in arithmetic, ordering, numeric resize, accumulation, counting, addressing, threshold comparison, multiplication, division, or numeric shifts, declare it as `unsigned`, `signed`, or a suitably constrained integer subtype.

Do **not** declare a numeric datapath signal as `std_logic_vector` merely because it is a vector.

Preferred:

```vhdl
signal count     : unsigned(7 downto 0);
signal delta     : signed(15 downto 0);
signal wr_addr   : unsigned(ADDR_WIDTH-1 downto 0);
signal sample_ix : natural range 0 to C_MAX_SAMPLES-1;
```

Avoid:

```vhdl
signal count   : std_logic_vector(7 downto 0);
signal wr_addr : std_logic_vector(ADDR_WIDTH-1 downto 0);
```

when those signals are used numerically.

### Boundary rule

`std_logic_vector` is appropriate for opaque bit fields, encoded protocol payloads, external buses, and interfaces whose bit pattern is not itself the local numeric semantic type.

Convert at the boundary, once:

```vhdl
signal bus_data : std_logic_vector(15 downto 0);
signal value_u  : unsigned(15 downto 0);

value_u <= unsigned(bus_data);
```

and convert back only when crossing back into an opaque/vector interface:

```vhdl
bus_data <= std_logic_vector(value_u);
```

Avoid repeated casts inside arithmetic expressions.

### Width rule

Numeric width changes must be explicit.

Use:

```vhdl
sum_ext <= resize(a, sum_ext'length) + resize(b, sum_ext'length);
```

rather than relying on implicit result widths.

For narrowing, state the intended policy explicitly:
- truncate
- wrap
- saturate
- round
- assert that overflow is impossible

### Comparison rule

Use numeric types for numeric ordering:

```vhdl
if level_u >= threshold_u then
```

Do not compare opaque bit vectors numerically through ad-hoc casts throughout the RTL.

### Shift rule

Prefer numeric operations on `unsigned`/`signed` and `shift_left`/`shift_right` from `numeric_std` when the shift is semantically numeric. Use concatenation/slicing when the operation is structurally a bit manipulation rather than arithmetic.

## Counter representation policy

Counters do **not** have to be `unsigned`.

Choose based on intent:

Use `natural` / constrained integer when:
- the counter represents a bounded abstract quantity
- no bit-level representation is part of the interface/contract
- wrap behavior is not intended to come from vector overflow
- the toolchain synthesizes the range efficiently

Example:

```vhdl
signal retry_count : natural range 0 to C_MAX_RETRIES := 0;
```

Use `unsigned` when:
- exact bit width matters
- wrap/modulo behavior is intentional
- the value directly maps to an address or packed hardware field
- bit slicing/concatenation is part of the design
- the implementation contract is explicitly binary-width based

Example:

```vhdl
signal phase_acc : unsigned(31 downto 0) := (others => '0');
```

Use `integer` when negative values are semantically valid, preferably with a
constrained range:

```vhdl
signal error_acc : integer range -1024 to 1023 := 0;
```

Do not convert an integer/natural counter to `unsigned` merely to satisfy a
style rule.

## FPGA initialization instead of reset

Read `FpgaInitialization.md`.

When the exact FPGA family and synthesis flow are verified to implement VHDL
declaration initial values, initialization may replace reset logic that exists
**only** to establish configuration-time state.

Do not remove reset that has runtime/system semantics.

## Pipeline relative-stage naming

Use the `_mN` / `_pN` convention defined in `CodingStyle.md`.

The unsuffixed signal is relative stage 0. `_pN` is N stages after it and
`_mN` is N stages before it. Keep transaction data, valid and sideband metadata
on matching coordinates.

## Resolved/unresolved project policy

Read `TypeResolutionPolicy.md`.

Default to unresolved types, but ask the user whether the project should use
unresolved or resolved types before establishing the project convention when
their preference is not already known.

Once selected, keep the policy consistent.

## CDC is a protected design area

Read `CdcPolicy.md`.

Prefer existing/predefined proven CDC modules. Use their supplied constraints
when available. If no suitable predefined module exists, explicitly highlight
the custom CDC requirement to the user before treating the implementation as
complete.

## Typed interface records

Read `InterfaceRecords.md`.

Prefer focused directional records for internal protocol interfaces when they
improve clarity and are supported by the active toolchain. Preserve flat
external interfaces where interoperability requires them.

## Portability classification

Read `VendorPolicy.md`.

Prefer `PORTABLE_VHDL`, escalating only when justified:
`PORTABLE_VHDL -> VENDOR_ATTRIBUTE -> VENDOR_PRIMITIVE -> VENDOR_IP`.

Vendor-specific choices must be explicit and documented.

## Synthesizable versus verification VHDL

Read `SynthesizableVHDL.md`.

Keep production RTL synthesizable for the active toolchain. Use simulation-only
features freely in verification when they improve test quality.

## Reusable RTL and generics

Read `ReusableRTL.md`.

Use generics for real architectural parameters, semantic constrained types, and
named derived constants. Avoid over-generalizing implementation details.
