# VHDL Skills

Skills and policies for agentic modern VHDL development, with ready-made
integrations for **Maki** and **Claude Code**.

The canonical skill and policy text lives here, once. `install.sh`
materializes the directory layout expected by the selected agent into any
target project.

## Skills

| Skill | Purpose |
| --- | --- |
| `vhflow` | Scan and orchestrate the complete MCP-first VHDL RTL design flow |
| `vharch` | Decompose an IP requirement into submodules, interfaces, and a top-level skeleton |
| `vhdesign` | Generate a design proposal, module documentation, and entity/architecture backbone |
| `vhfill` | Implement VHDL-2008 from an approved proposal; elaborate and simulate with GHDL |
| `vhdebug` | Diagnose regression failures using VUnit logs, waveform analysis, and RAG-assisted tracing |
| `vhtestgen` | Generate VUnit-first self-checking VHDL-2008 test projects (GHDL fallback) |
| `vhtestrun` | Run regressions via vunit-mcp; collect reports, logs, and waveforms |
| `vhsynth` | Synthesize with yosynth-mcp (GHDL + Yosys); local Yosys+GHDL fallback |
| `vhdoc` | Aggregate module documentation into an IP-level integration document |
| `vhexplain` | Generate or refresh module documentation from an entity/architecture |

## Design goals

- VHDL-2008 production baseline; VHDL-2019 opt-in after toolchain verification.
- `numeric_std` arithmetic.
- `natural`/`integer`/constrained integers are valid numeric implementation types.
- Unresolved types by default, but the user is asked before a project policy is locked.
- FPGA declaration initialization may replace power-up-only reset when the exact
  family/toolchain is verified.
- Pipeline coordinates use `_mN` / `_pN`.
- Internal protocol records are encouraged where useful.
- Portable inference first; explicit portability classification.
- Strict separation between synthesizable RTL and simulation-only verification.
- AXI4/AXI4-Lite/AXI4-Stream interfaces follow the `shared/Axi4.md` policy (handshake, burst/boundary, ordering, no-loss).
- Generics only for real architectural parameters.

## CDC policy

CDC is never treated as routine wiring. Preferred source order:

1. existing proven project-local CDC blocks
2. proven reusable blocks from project libraries/dependencies
3. vendor CDC IP/macros
4. new custom CDC implementation, only as a last resort

Constraints/attributes are part of the implementation when the toolchain
supports them. Custom/unconstrained CDC paths are always highlighted to the
user.

## Repository layout

```text
vhdl-skills/
├── skills/                    # Canonical SKILL.md files (one directory per skill)
├── shared/                    # Canonical policies and reference docs
├── integrations/
│   ├── maki/
│   │   ├── AGENTS.md
│   │   └── mcp.toml
│   └── claude/
│       ├── CLAUDE.md
│       └── agents/            # Subagent definitions
├── install.sh
├── uninstall.sh
├── validate.sh
├── MCP_SETUP.md
├── LICENSE
└── NOTICE
```

## Install

### Maki

```bash
./install.sh --target maki --project /path/to/project --with-mcp
```

Installs:

```text
AGENTS.md
.maki/skills/
.maki/mcp.toml
```

### Claude Code

```bash
./install.sh --target claude --project /path/to/project
```

Installs:

```text
CLAUDE.md
.claude/skills/
.claude/agents/
```

MCP server registration for Claude Code remains CLI/user-config driven; see
`MCP_SETUP.md`.

### Both

```bash
./install.sh --target both --project /path/to/project --with-mcp
```

### Copy vs symlink

Default is `copy`, which makes the target project self-contained. For active
development of this repository itself:

```bash
./install.sh --target maki --project ../my-design --mode link --with-mcp
```

`link` symlinks back to this repository so edits are immediately visible.

## Optional MCP servers

The skills work without MCP but are designed around a recommended set of
servers, including the intended failure-debug chain:

| Server | Repo | Role in the flow |
| --- | --- | --- |
| **vhdl-rag-mcp** | [ru551n/vhdl-rag-mcp](https://github.com/ru551n/vhdl-rag-mcp) | RAG index over project sources/docs for cross-reference |
| **vunit-mcp** | [ru551n/vunit-mcp](https://github.com/ru551n/vunit-mcp) | Run VUnit tests, collect reports/logs/waveforms |
| **waver-mcp** | [ru551n/waver-mcp](https://github.com/ru551n/waver-mcp) | Waveform inspection for measured signal evidence |
| **yosynth-mcp** | [ru551n/yosynth-mcp](https://github.com/ru551n/yosynth-mcp) | GHDL + Yosys synthesis and resource summary |

Debug chain: `vunit-mcp` (fail + record) → `waver-mcp` (waveform evidence) →
`vhdl-rag-mcp` (source cross-reference); synthesis via `yosynth-mcp`.
Setup commands and the full architecture are in `MCP_SETUP.md`.

## Validate

```bash
./validate.sh
```

Checks that all skills and integration files are present.

## Type resolution

Default is unresolved VHDL-2008 types (`std_ulogic`, `std_ulogic_vector`,
`u_unsigned`, `u_signed`). Skills ask the user before establishing a
project-wide convention when the preference is not already known. Resolved
mode (`std_logic`, `std_logic_vector`, `unsigned`, `signed`) is fully
supported.

## License

MIT — see `LICENSE`. This project is an independent VHDL adaptation inspired
by [rtl-skills](https://github.com/phamcuong21478/rtl-skills) (Apache-2.0);
see `NOTICE` for attribution.