# VHDL RTL Design Project

Synthesizable design code is VHDL-2008. The `vhdl` skills cover design, implementation, testing, debugging, synthesis and documentation.

## Core rules

1. Synthesizable RTL is VHDL-2008 (`.vhd`). Use VHDL-2019 only after every tool in the flow is verified for the constructs used.
2. Use `ieee.std_logic_1164` and `ieee.numeric_std`; never `std_logic_arith`, `std_logic_unsigned` or `std_logic_signed`. Arithmetic uses `unsigned`, `signed` or constrained integers.
3. Clocked logic uses `rising_edge(clk)`.
4. Resetless by default, using declaration initial values. When state must be restorable at runtime, use a synchronous active-high `reset` (the skills' `shared/HouseStyle.md`).
5. Architecture names are `a` for RTL and `tb` for testbenches, unless the project says otherwise.
6. Prefer direct entity instantiation: `foo_inst : entity work.foo`.
7. `--@` marks unfinished design-direction code; resolve every marker before RTL is done.
8. AXI4 and AXI4-Stream interfaces follow the skills' `shared/Axi4.md`.
9. Verification is VUnit 5 by default; the skills' `shared/Vunit.md` is authoritative for the VUnit API.
10. Never report a compile, simulation, waveform, synthesis, timing or power result that no tool produced.
11. Only one agent compiles, simulates or synthesizes in a working tree at a time.
12. Do not silently overwrite filled RTL or hand-owned requirement sections.

## Tools

- `vhdl-tools` (the skills' `shared/bin/vhdl-tools`) runs VUnit, synthesis and Vivado reports, and waveform measurements. `shared/tools/README.md` lists every command.
- `corvidex-mcp`, when connected, answers semantic search and exact code-navigation questions. `shared/ToolPolicy.md` has the routing rules.

## Skills

| Skill | Use it for |
|---|---|
| `vhdesign` | architecture and module design before RTL |
| `vhfill` | writing or changing RTL |
| `vhtest` | writing, repairing and running testbenches and VUnit projects |
| `vhdebug` | finding the root cause of a failing simulation |
| `vhsynth` | synthesis, resources, timing closure and Vivado |
| `vhdoc` | documenting or explaining VHDL |
| `vhflow` | taking a whole IP through every phase |

## Optional flow layout

When the full flow is used, `vhflow` keeps this layout. An existing project layout wins.

```text
flow_status.md
ddoc/            <ip>_req.md, <ip>_arch.md, <module>_req.md, <module>_proposal.md
doc/             <module>.md, <ip>.md
rtl/             <ip>_top.vhd, <module>.vhd
tb/              run.py and VUnit testbenches
issue/<ip>/      run and debug reports
synth/<module>/  synthesis reports
```
