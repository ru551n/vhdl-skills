# Interface Record Policy

Directional `*_m2s_t` / `*_s2m_t` records are the DEFAULT for related or
complex internal signal groups, not merely an option to reach for when it
"improves clarity". Fall back to flat ports only for the cases listed under
"Where flat ports may be better" below.

## Directional records

For bidirectional protocols, use directional records such as:

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
type stream_m2s_t is record
  valid : std_ulogic;
  data  : std_ulogic_vector(31 downto 0);
  last  : std_ulogic;
end record;

type stream_s2m_t is record
  ready : std_ulogic;
end record;
```

If the project selects resolved types, use their resolved equivalents.

## Unconstrained elements, constrained at declaration

When a record field's width depends on entity generics (e.g. a runtime-sized
channel count or lane count), declare the field as an unconstrained
`std_ulogic_vector` (VHDL-2008) and constrain it where the object is
declared (signal, port, generic-sized), not in the type itself:

```vhdl
type window_m2s_t is record
  valid : std_ulogic;
  data  : std_ulogic_vector;   -- unconstrained; sized at declaration
end record;

-- entity port, constrained via a generic:
port (
  m_window_m2s : out window_m2s_t(data(width - 1 downto 0))
);

-- signal, constrained via a locally computed width:
signal window : window_m2s_t(data(window_data_width(k, tile_channels) - 1 downto 0));
```

This also works for arrays of such records
(`type r_vec_t is array (natural range <>) of r_t;`, each element
constrained independently at declaration).

Tooling caveat (measured 2026-09, spike in /tmp, --std=08): GHDL
7.0.0-dev (v6.0.0.r418.g753dfcf0b) and nvc 1.23-devel
(1.22.0.r66.gef5084a94) both fully accept unconstrained record elements in
package types, entity ports constrained by a generic, signals constrained
at declaration, reading/writing/slicing/indexing the field (including
passing it to a function), arrays-of-records with per-element
constraints, and elaborate+run a testbench driving such a port. Re-check
exact tool versions before relying on this on another toolchain; if the
toolchain doesn't support it, fall back to a fixed-width record element
sized by a package constant (e.g. a compile-time max width with unused
high bits), which is fully portable at the cost of always paying for the
worst-case width.

## Where records are preferred

Good candidates:
- internal ready/valid streams
- register buses
- request/response interfaces
- AXI-like internal wrappers
- grouped configuration/status signals
- testbench BFMs

Records group *heterogeneous* signals that belong to one interface. For
*homogeneous* repetition — N identical lanes, taps, columns or channels — use an
array of the element type instead of a wide packed `std_logic_vector`, and an
array of records for N identical interfaces. See "Aggregate representation" in
`ModernVHDL.md`; packing lanes into a flat vector makes runtime-indexed access a
dynamic slice, which GHDL synthesis rejects even though simulation passes.

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
