---
name: vhdesign
description: Generate a VHDL design proposal, module documentation, and entity/architecture backbone from a module requirement
allowed-tools: Read, Write, Bash, Grep, Glob
---


# VHDL Designer

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

## MCP preference

Use `vhdl-rag-mcp` when available to ground design decisions:
- search docs for coding/architecture conventions
- search VHDL for analogous entities/processes/packages
- cross-reference key interface symbols
- retrieve exact source with `get_source` before adopting a pattern

Local project files and the requirement/proposal remain authoritative for the module being designed.

## Input

`ddoc/<module>_req.md`

Derive `<module>` by removing a trailing `_req`.

## Outputs

- `ddoc/<module>_proposal.md`
- `doc/<module>.md`
- `rtl/<module>.vhd`

## Preconditions

Stop if the requirement file does not exist. Do not design from a module name alone.
Do not operate on the IP `_top` entity; the top integration skeleton belongs to `vharch`.

## Re-run safety

Classify `rtl/<module>.vhd`:

- missing → fresh
- contains unresolved `--@` markers → backbone, safe to regenerate
- filled logic and no `--@` markers → stop before destructive regeneration; reconcile incrementally unless user explicitly requests overwrite

Preserve non-empty `## Implementation Notes (vhfill)` in the proposal.

## Step 1 — Proposal

The proposal must capture:
- requirements summary
- interface copied exactly from the structural requirement section
- clock/reset behavior
- architecture and dataflow
- state machines
- algorithms
- numeric types and widths
- latency/throughput
- corner cases
- selected patterns from `shared/DesignPatterns.md`
- AXI4/AXI4-Stream protocol decisions per `shared/Axi4.md` when the module exposes them
- verification plan
- `## Implementation Notes (vhfill)` section, initially empty

Do not rename or reinterpret ports/generics fixed by `vharch`.

## Step 2 — Module documentation

Generate `doc/<module>.md` according to `shared/ModuleDocContract.md`.

## Step 3 — VHDL backbone

Generate valid VHDL-2008 that analyzes as far as practical while leaving explicit direction markers for implementation.

Use:
- required IEEE packages
- exact entity generics/ports
- `architecture rtl`
- type/signal declarations already decided by proposal where useful
- direct entity instantiations for known submodules
- `--@` implementation markers

Example:

```vhdl
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity foo is
  port (
    clk   : in  std_logic;
    rst_n : in  std_logic;
    req   : in  std_logic;
    done  : out std_logic
  );
end entity foo;

architecture rtl of foo is
  type t_state is (IDLE, BUSY);
  signal state_q : t_state;
begin

  --@ Implement synchronous FSM and done pulse per proposal §3.

end architecture rtl;
```

The backbone must not contain a fake implementation that merely compiles but violates the proposal.

## Numeric type gate

Before accepting a design or implementation:

1. Confirm `ieee.numeric_std` is used for arithmetic.
2. Reject imports of:
   - `ieee.std_logic_arith`
   - `ieee.std_logic_unsigned`
   - `ieee.std_logic_signed`
3. Review every arithmetic datapath/control value:
   - counters
   - addresses
   - accumulators
   - thresholds
   - lengths/depths
   - arithmetic operands/results
   - numeric state used in `<`, `>`, `<=`, `>=`
4. Prefer the declared type `unsigned`, `signed`, or a constrained integer subtype.
5. Treat `std_logic_vector` as an opaque representation/interface type, not the default arithmetic type.
6. Keep conversions at clear representation boundaries and avoid cast-heavy arithmetic.
7. Make numeric resizing/narrowing explicit and document overflow/truncation behavior.

Flag an implementation for revision when repeated expressions such as:

```vhdl
std_logic_vector(unsigned(x) + 1)
```

appear on an internal state signal that should simply have been declared `unsigned`.

## Reset minimization and initial values

For each sequential state class decide:

1. Must it be restored during runtime?
   - yes → keep appropriate reset behavior
2. Does it only need a known configuration-time value?
   - yes → use declaration initialization only if FPGA initialization capability is verified
3. Is its value irrelevant until a valid/control bit becomes active?
   - yes → consider neither reset nor initialization

Do not reset wide datapaths just because nearby control state is reset.

## Pipeline naming gate

For pipelined designs, establish the semantic stage-0 reference and use the
shared `_mN` / `_pN` convention consistently.

Verify that data, valid, sideband and control signals that belong to the same
transaction have matching relative-stage coordinates.

## CDC design rule

Do not hand-code CDC structures by default.

Prefer project/vendor/proven predefined CDC modules. Integrate their associated
constraints where available.

If no suitable predefined block exists, mark the custom CDC path as
`NEEDS_REVIEW` and surface it clearly to the user before implementation is
considered final.

## Interface record rule

For internal multi-signal protocols, consider directional typed records
(`*_m2s` / `*_s2m` or equivalent terminology).

Use wrappers to preserve flat vendor/external interfaces when necessary.

## Generic design gate

For reusable blocks use semantic generic types, replace magic numbers with named
constants/generics where appropriate, define valid ranges, and avoid unsupported
configuration matrices.

## Vendor-specific design gate

Before using a vendor attribute, primitive, or IP, check whether portable
inference is sufficient, classify the portability level, document why
escalation is required, and isolate the dependency where practical.
