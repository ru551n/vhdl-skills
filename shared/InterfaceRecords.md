# Interface Record Policy

Use records for related internal protocol signals when doing so improves
clarity and the active toolchain supports the interface style.

## Directional records

For bidirectional protocols, prefer directional records such as:

```text
*_m2s
*_s2m
```

where:
- `m2s` = master/producer to slave/consumer
- `s2m` = slave/consumer to master/producer

Use the project's terminology (`source/sink`, `request/response`, etc.) if that
is clearer than master/slave naming.

Example:

```vhdl
type t_stream_m2s is record
  valid : std_ulogic;
  data  : std_ulogic_vector(31 downto 0);
  last  : std_ulogic;
end record;

type t_stream_s2m is record
  ready : std_ulogic;
end record;
```

If the project selects resolved types, use their resolved equivalents.

## Where records are preferred

Good candidates:
- internal ready/valid streams
- register buses
- request/response interfaces
- AXI-like internal wrappers
- grouped configuration/status signals
- testbench BFMs

## Where flat ports may be better

Prefer scalar/vector ports when:
- interfacing directly to vendor IP
- tool/IP packaging requires flat ports
- external integration tooling cannot consume records cleanly
- the existing project convention is deliberately flat
- language/tool compatibility is uncertain

Use a thin wrapper to convert between flat external ports and typed internal
records when useful.

## Packages

Put shared interface record types in a focused package.

Avoid a single giant global package containing unrelated protocol types.
