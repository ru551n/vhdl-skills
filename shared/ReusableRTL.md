# Reusability and Generic Design Policy

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
