# Synthesizable vs Simulation-Only VHDL

Treat every construct as one of:
- synthesizable RTL
- verification/simulation-only
- tool-dependent synthesis

Legal VHDL is not automatically synthesizable.

Production RTL must use constructs supported by the active synthesis toolchain.
Do not allow simulation-only behavior to leak into RTL, including typical uses
of `wait for`, `after`, unrestricted file I/O, TextIO-driven functionality,
dynamic allocation/access types, and arbitrary delay modeling.

Tool-dependent constructs must be explicitly verified.

Simulation-only constructs are encouraged when they improve verification:
timing delays, file I/O, randomized stimulus, BFMs, scoreboards, assertions,
logging, and waveform control.

Before RTL is complete:
- confirm no simulation-only constructs leaked into production RTL
- verify tool-dependent constructs with the active toolchain
- investigate synthesis warnings about ignored behavior

## Traps that pass one gate and fail another

Analysis, elaboration, simulation and synthesis are independent gates;
passing three says nothing about the fourth.

- **`unsigned * natural` doubles the width.** `numeric_std`'s
  `"*"(UNSIGNED, NATURAL)` converts the natural to `L'length` bits and
  returns `L'length + R'length`. `out_w64 := in_w64 * 2` therefore
  produces a 128-bit result assigned into a 64-bit variable; analysis
  accepts it and only a running simulation reports the bound check. Route
  products through a helper that resizes explicitly.
- **Conditional expressions are range-checked on both arms.** With a
  generic of 1 the index subtype is `0 to 0`, and
  `0 when idx = N-1 else idx + 1` has an unreachable arm whose `idx + 1`
  is still statically checked by a synthesis front end. Every simulation
  passed; only the netlist build failed. Compute the next index in a
  wider intermediate and convert.
- **A free-running memory read port ignores your pipeline freeze.** A
  registered read with no clock enable keeps advancing while a
  clock-enabled pipeline that consumes it is held, and re-pairs data with
  the wrong entry. Give the port the same enable, or re-present the held
  address while frozen. Visible only in a backpressure test with more than
  one item in flight.
- **Assertion severity is a tool setting, not a language guarantee.** A
  VUnit/GHDL run stops on severity `error` by default, so an
  `error`-severity assertion written to "report and keep going" stops the
  simulation, and a config that lowers the stop level to `failure` lets an
  `error` pass unnoticed. Use `failure` for contract violations that no
  legitimate caller can produce, and expose the severity as a generic where
  a test needs to provoke it.
- **Generated constants are the source of truth.** Where an ISA, register
  map or sizing constant is generated, change the generator's input and
  regenerate. A hand-edited generated file is silently reverted by the next
  run.
- **A synthesis attribute is a mapping instruction, not a fix.** RTL that
  only works because of a `ram_style`/`use_dsp`/`max_fanout`-class
  attribute simulates identically with or without it, so the dependency
  is invisible until a different tool, a different version, or a project
  default change removes it and the design silently re-maps into fabric,
  a different inference, or an unbounded fan-out net. Write RTL whose
  correct mapping is the tool's unforced default; see
  `shared/TimingAndResources.md`, "Prefer better RTL to synthesis settings
  and attributes." Clock-domain-crossing attributes are the deliberate
  exception — there the attribute is the structure, not a workaround for
  its absence.
