# VHDL RTL project instructions

Use VHDL-2008 as the portable production baseline. Use VHDL-2019 only when the project explicitly opts in and every active tool in the flow is verified for the constructs used.

Core conventions:
- `ieee.std_logic_1164` and `ieee.numeric_std`; no `std_logic_arith`, `std_logic_unsigned` or `std_logic_signed`
- `unsigned` / `signed` for arithmetic
- resetless by default (declaration initial values); when a runtime-restorable reset is needed, use synchronous active-high `reset = '1'` (see `shared/HouseStyle.md`)
- `rising_edge(clk)`
- architecture name `a` (RTL) / `tb` (testbench) unless the project says otherwise
- prefer direct entity instantiation
- preserve hand-owned requirement sections
- `--@` marks unfinished design-direction code and must be removed once implemented
- AXI4/AXI4-Stream interfaces follow `shared/Axi4.md`
- VUnit 5 is the default verification framework; `shared/Vunit.md` is authoritative for its API

Use the skills under `.maki/skills/`:
- `vhdesign` — architecture and module design before RTL
- `vhfill` — writing or changing RTL
- `vhtest` — writing, repairing and running testbenches
- `vhdebug` — root cause of a failing simulation
- `vhsynth` — synthesis, resources, timing, Vivado
- `vhdoc` — documenting or explaining VHDL
- `vhflow` — a whole IP through every phase

Tools:
- `.maki/skills/shared/bin/vhdl-tools` runs VUnit, synthesis, Vivado reports and waveform measurements; `.maki/skills/shared/tools/README.md` lists every command. It needs `uv`.
- `corvidex-mcp` (configured in `.maki/mcp.toml`) for semantic search and exact code navigation; routing in `shared/ToolPolicy.md`.
- Never claim a compile, test, waveform, synthesis, timing or power result without a real tool run.
- Only one agent compiles, simulates or synthesizes in a working tree at a time.

Subagent use:
- for long multi-module flows (a full IP through `vhflow`), delegate self-contained phases to subagents
- `flow_status.md` is the handoff contract; the main agent owns it and the final report
- a subagent's summary is not evidence; verify the real artifacts and tool results before treating a phase as done

Maki defers large MCP toolsets behind `tool_search`; search for the corvidex tool you need rather than assuming it is already loaded.
