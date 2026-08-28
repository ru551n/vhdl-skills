# Resolved vs Unresolved Type Policy

## Default

Default project preference: **unresolved types**.

Preferred unresolved VHDL-2008 types:

```vhdl
std_ulogic
std_ulogic_vector
u_unsigned
u_signed
```

Resolved equivalents:

```vhdl
std_logic
std_logic_vector
unsigned
signed
```

## Ask before locking the project policy

Before establishing a project-wide resolved/unresolved convention, ask the user
which policy they want when that preference is not already known.

Suggested question:

```text
Vilken signaltyp-policy vill du använda?
- unresolved (default): std_ulogic/std_ulogic_vector/u_unsigned/u_signed
- resolved: std_logic/std_logic_vector/unsigned/signed
```

If the user does not provide a preference and interaction is not possible,
use **unresolved** as the default.

Once the project policy is known, follow it consistently.

## Why unresolved is the default

Unresolved types turn unintended multiple drivers into an error instead of
silently invoking a resolution function.

This is especially useful for:
- control signals
- FSM state-associated flags
- counters and arithmetic state
- internal datapaths
- ready/valid interfaces
- registers that should have exactly one driver

## When resolved types are appropriate

Use resolved types when resolution is intentional or required, for example:
- bidirectional `inout` ports
- tri-state buses
- wired/shared signals
- external/vendor interfaces that require resolved types
- legacy components/packages with resolved port types
- toolchain limitations

Do not use a resolved type merely out of habit.

## Arithmetic

If unresolved policy is selected:

```vhdl
signal count : u_unsigned(7 downto 0);
```

If resolved policy is selected:

```vhdl
signal count : unsigned(7 downto 0);
```

Both use `ieee.numeric_std`.

The existing numeric-type policy still applies:
- natural/integer/constrained integer are valid for counters and bounded values
- vectors should not be used as numeric state unless the representation itself matters

## Interfaces

For internal interfaces, follow the project policy.

At external boundaries, interoperability may override the internal convention.
Convert once at the boundary instead of spreading conversions throughout RTL.

## Consistency rule

Do not mix resolved and unresolved versions of the same conceptual interface
without a clear boundary reason.

If conversion is necessary, make that boundary visible and document it.
