# VHDL RTL Design Project

## Project Overview

This is a VHDL RTL project. Synthesizable design code uses VHDL-2008. The project contains RTL,
reusable library entities/packages, design requirements, generated documentation, testbenches,
simulation artifacts, issue/debug reports, and synthesis outputs.

## Project Structure

```text
.
├── CLAUDE.md
├── flow_status.md
├── ddoc/
│   ├── <ip>_req.md
│   ├── <ip>_arch.md
│   ├── <module>_req.md
│   └── <module>_proposal.md
├── doc/
│   ├── <module>.md
│   └── <ip>.md
├── lib/
│   ├── <module>.vhd
│   ├── <module>.md
│   └── <package>.vhd
├── rtl/
│   ├── <ip>_top.vhd
│   └── <module>.vhd
├── tb/
│   ├── <module>/
│   │   ├── <module>_tb.vhd
│   │   └── Makefile
│   └── <ip>/
│       ├── Makefile
│       ├── script/
│       │   └── rtl.f
│       ├── tb_pkg.vhd
│       ├── tb_<name>.vhd
│       ├── tc_list.md
│       └── sim/<tc>/
├── issue/<ip>/
│   ├── issue_NNN_<tcname>.md
│   ├── debug_NNN_<tcname>.md
│   ├── run_summary.md
│   └── debug_summary.md
├── synth/<module>/
│   ├── vhsynth.tcl
│   ├── utilization.rpt
│   ├── timing_summary.rpt
│   ├── power.rpt
│   └── synth_report.md
└── prj/
```

## MCP-first tool policy

Read `shared/McpToolPolicy.md` before tool-dependent phases.

Preferred:
- `vhdl-rag-mcp` for semantic VHDL/docs/code retrieval
- `vunit-mcp` for VUnit project discovery, compilation, tests and logs
- `peeper-mcp` for waveform measurements and plots
- `tsfpga-mcp` for GHDL+Yosys synthesis/resource summaries

Use local tools only when the corresponding MCP server/tool is unavailable, unhealthy, or unsuitable for the specific requested result.

## Core Rules

1. Synthesizable RTL is VHDL-2008 (`.vhd`).
2. Use `ieee.std_logic_1164.all` and `ieee.numeric_std.all`.
3. Never use Synopsys arithmetic compatibility packages (`std_logic_arith`, `std_logic_unsigned`, `std_logic_signed`).
4. Prefer direct entity instantiation: `u_x : entity work.foo(rtl)`.
5. Architecture name defaults to `rtl`.
6. Clocked logic uses `if rising_edge(clk) then`.
7. Reset is synchronous active-low by default unless the requirement explicitly says otherwise.
8. Use `--@` direction markers in generated backbones. `vhfill` must remove/resolve all of them.
9. Every `rtl/<module>.vhd` must have `doc/<module>.md`.
10. Reusable library modules must carry adjacent documentation.
11. Do not silently overwrite filled RTL or hand-owned functional specification sections.
12. Prefer available MCP servers according to `shared/McpToolPolicy.md`.
13. Never report compile, simulation, waveform, synthesis, timing, utilization, or power results unless the corresponding tool actually ran.
14. AXI4/AXI4-Stream interfaces follow `shared/Axi4.md`.
15. Verification is VUnit-5 by default; VUnit API rules (phases, gate locks, seeds, `check_pkg`) are authoritative in `shared/Vunit.md`.

## VHDL Design Workflow

```text
ddoc/<ip>_req.md
  ├─[vharch]────► ddoc/<ip>_arch.md + ddoc/<submodule>_req.md + rtl/<ip>_top.vhd
  ├─[vhdesign]──► ddoc/<module>_proposal.md + doc/<module>.md + rtl/<module>.vhd
  ├─[vhfill]────► completed rtl/<module>.vhd + tb/<module>/
  ├─[vhflow]────► flow_status.md
  ├─[vhsynth]───► synth/<module>/
  ├─[vhtestgen]─► tb/<ip>/
  ├─[vhunit]────► tb/<ip>/ run.py + testbenches (authoring/migration)
  ├─[vhtestrun]─► issue/<ip>/
  ├─[vhdebug]───► issue/<ip>/debug_*.md
  └─[vhdoc]─────► doc/<ip>.md
```

## Available Skills

| Skill | Purpose |
|---|---|
| `vharch` | Decompose an IP requirement and generate VHDL top skeleton + module requirements |
| `vhdesign` | Generate proposal, documentation, and VHDL entity/architecture backbone |
| `vhfill` | Implement VHDL, analyze/elaborate/simulate |
| `vhexplain` | Generate documentation from VHDL source |
| `vhdoc` | Aggregate module docs into an IP integration document |
| `vhsynth` | Synthesize with tsfpga-mcp (GHDL + Yosys); local Yosys+GHDL fallback |
| `vhtestgen` | Generate self-checking VHDL-2008 testbench project/testcases |
| `vhunit` | Author, repair, migrate VUnit runners (`run.py`) and testbenches (VUnit 4→5) |
| `vhtestrun` | Run regression and report failures |
| `vhdebug` | Trace failed signals and diagnose root cause |
| `vhflow` | Scan and orchestrate the full flow |

## Available Agents

`vhdl-architect`, `vhdl-designer`, `vhdl-coder`, `vhdl-documentation`,
`vhdl-synthesizer`, `vhdl-tester`, `vhdl-debugger`, `vhdl-orchestrator`.

Modern language policy: VHDL-2008 is the portable production baseline; VHDL-2019 is opt-in only after all active tools are verified.
