# VHDL Designer

## MCP preference

Use `corvidex-mcp` when available to ground design decisions:
- search docs for coding/architecture conventions
- search VHDL for analogous entities/processes/packages (`search_hdl` — conceptual discovery)
- cross-reference key interface symbols — prefer `find_references`/`find_definition`/`find_symbol` (LSP/compiler-backed exact resolution) over `search_hdl` or a local grep once the exact symbol name is already known, e.g. confirming every caller of a generic/record type this design will reuse or extend; see `shared/ToolPolicy.md`'s routing table
- retrieve exact source with `get_source` before adopting a pattern

Local project files and the requirement/proposal remain authoritative for the module being designed.

Before designing new logic, check `shared/ReusableRTL.md` ("Reuse before authoring new RTL"): search `lib/`/`modules/*/src/`/vendored dependencies for an existing module first. A thin wrapper around an existing module is allowed and preferred over a fork or a rewrite.

If the module being designed is a top-level (`<ip>_top`) or otherwise bundles more than one distinct responsibility, prefer splitting it into smaller single-responsibility submodules per `shared/ReusableRTL.md` ("Prefer modular decomposition") rather than implementing a monolithic entity — flag this back to `vhdesign` (a new architecture/submodule-table decision) rather than silently absorbing extra responsibility into one module's VHDL backbone.

## Input

The module's requirement: `ddoc/<module>_req.md` when it exists (derive `<module>` by removing the trailing `_req`), otherwise the requirement as the user stated it.

## Outputs

- a design proposal: `ddoc/<module>_proposal.md` when flow files are in use, otherwise in the reply or wherever the user asks
- module documentation: `doc/<module>.md`, or the project's own documentation location
- the VHDL backbone, in the project's source layout (`rtl/<module>.vhd` in the conventional layout)

## Preconditions

Stop and ask when there is no requirement at all, written or stated. Do not design from a module name alone.
Do not operate on the IP `_top` entity; the top-level skeleton comes from `architecture.md`.

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
- the timing-closure and resource rules in `shared/TimingAndResources.md` — in particular: no engine cone may start at a controller's descriptor register (per-command configuration is computed once at command start and handed over registered), reductions are balanced trees, and a leaf's standalone Fmax is an upper bound only
- AXI4/AXI4-Stream protocol decisions per `shared/Axi4.md` — any streaming interface defaults to AXI4-Stream with backpressure (`TREADY`) unless the architecture doc explicitly justifies omitting it
- verification plan
- `## Implementation Notes (vhfill)` section, initially empty

Do not rename or reinterpret ports/generics fixed by `vhdesign`.

## Step 2 — Module documentation

Generate `doc/<module>.md` according to `shared/ModuleDocContract.md`.

## Step 3 — VHDL backbone

Generate valid VHDL-2008 that analyzes as far as practical while leaving explicit direction markers for implementation.

Use:
- required IEEE packages
- exact entity generics/ports
- `architecture a` (see `shared/HouseStyle.md`)
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
    clk   : in  std_ulogic;
    reset : in  std_ulogic := '0';
    req   : in  std_ulogic;
    done  : out std_ulogic
  );
end entity foo;

architecture a of foo is
  type state_t is (idle, busy);
  signal state_q : state_t;
begin

  --@ Implement synchronous FSM and done pulse per proposal §3.

end architecture a;
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

When the target is an AMD/Vivado part, load `shared/VivadoDesign.md`
before this gate: it holds the inference templates, attribute semantics,
reset/clocking/CDC methodology and per-family device facts the proposal
must be written against.
