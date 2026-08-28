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
