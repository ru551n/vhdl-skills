# Reusability and Generic Design Policy

## Reuse before authoring new RTL

Before writing a new entity, search the repository (`lib/` /
`modules/*/src/` / any vendored dependency such as `hdl-modules`) for an
existing module that already does the job, or most of it. This applies to
whole modules (FIFOs, AXI-Stream primitives, CDC helpers, arithmetic
building blocks, ...) and to shared packages/record types
(`shared/InterfaceRecords.md`).

- Prefer instantiating an existing module unmodified over re-implementing
  its behavior.
- A **thin wrapper** around an existing module is allowed and preferred
  over a fork or a rewrite when the existing module's generics/ports don't
  line up exactly with the new context (width slicing, port renaming,
  bundling a fixed generic configuration, adapting a record to flat ports
  or vice versa per `shared/InterfaceRecords.md`). Keep the wrapper thin:
  it should not duplicate or reimplement logic that the wrapped module
  already provides.
- Only write new RTL for the genuinely new behavior; do not re-derive
  primitives (FIFOs, handshake joins/forks, CDC synchronizers, packing
  functions, ...) that already exist in the project or its vendored
  dependencies.
- Record the reuse decision in the architecture/proposal doc's submodule
  table (`new` / `reuse` / `new, generic wrapper around <module>`) so the
  choice is auditable, per `vharch`'s submodule table convention.

## Prefer modular decomposition

Decompose functionality into small, single-responsibility submodules rather
than one large monolithic entity — this applies to genuinely new behavior
just as much as it does to reused behavior. A modular design is easier to
test (each submodule gets its own focused testbench under the TDD loop, see
`Vunit.md` §15), easier to reuse in future designs, easier to reason about
and document, and easier to close timing on piece by piece.

Guidance:

- Give each module one clearly-scoped responsibility (e.g. in a pixel
  pipeline: a windowing stage, a filter-coefficient stage, a
  thresholding stage, a hysteresis stage — as separate modules — rather
  than one monolithic top-level datapath).
- Prefer composing small modules over well-defined interfaces (AXI4-Stream
  per `Axi4.md`, or interface records per `InterfaceRecords.md`) over
  inlining their logic into a larger entity.
- A submodule boundary is justified when the block: has independently
  testable/verifiable behavior; could plausibly be reused in a different
  design; or isolates a clock/reset/CDC domain.
- Avoid over-fragmentation: do not split out a "module" that is just wiring
  plus a single register with no independent behavior or reuse value —
  that adds interface/documentation overhead without benefit. Use judgment;
  the goal is testable, reusable units, not a line-count target.
- `<ip>_top` entities should be structural: instantiate submodules and wire
  up interfaces, with no significant standalone datapath logic implemented
  directly at the top level.
- Record the decomposition rationale in the architecture doc's submodule
  table (`vharch` step 3, "responsibility" column) so the granularity
  choice is auditable, alongside the reuse (`new`/`reuse`/`new, generic
  wrapper around <module>`) decision.

## Generics

Use generics when they represent real architectural degrees of freedom.
Do not genericize everything.

Good candidates include data/address width, FIFO depth, channels/lanes, feature
enables, protocol widths, and pipeline depth when genuinely supported.

Prefer semantic types:

```vhdl
generic (
  data_width : positive := 32;
  depth      : positive := 16
);
```

Use `positive`, `natural`, booleans, enums, and constrained subtypes where they
express intent better than unconstrained integers.

Avoid magic numbers:
- generics for external configuration
- package constants for project-wide invariants
- local constants for derived values

Compute derived values once and name them.

Reusable IP should document generics and valid ranges, clock/reset behavior,
latency, throughput, flow control, CDC assumptions, and initialization behavior.

Avoid generics that merely expose internal implementation details or create
large untested configuration matrices.
