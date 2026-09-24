# VHDL Skills

Skills, subagents and a command-line tool for agentic VHDL/FPGA development.
Packaged as a Claude Code plugin, and installable into Maki or any agent that
reads Agent Skills.

## Skills

| Skill | Use it for |
| --- | --- |
| `vhdesign` | Architecture and module design before RTL: submodules, interfaces, clocking, reset, CDC, AXI4-Stream, skeletons |
| `vhfill` | Writing or changing synthesizable RTL, and checking it compiles, elaborates and passes its tests |
| `vhtest` | Writing, repairing and running testbenches and VUnit projects, including VUnit 4 to 5 migration |
| `vhdebug` | Finding the root cause of a failing or hanging simulation |
| `vhsynth` | Synthesis, resource counts, timing closure, Vivado builds and reports |
| `vhdoc` | Documenting or explaining VHDL modules and IPs |
| `vhflow` | Taking a whole IP through every phase, tracked in `flow_status.md` |

Each `SKILL.md` is short. It says when the skill applies and points at
reference files that the agent reads only for the sections a task needs.
Every skill works on a plain repository; the `ddoc/`, `issue/` and
`flow_status.md` flow files are used only when they exist or `vhflow` is
driving.

## Contents

```text
vhdl-skills/
├── .claude-plugin/            # plugin.json and marketplace.json
├── skills/
│   ├── vh*/                   # the seven skills
│   └── shared/                # reference docs, plus:
│       ├── bin/vhdl-tools     #   VUnit, synthesis and waveform command-line tool
│       ├── speja.yaml         #   house layout for speja, the optional formatter
│       └── tools/             #   its Python source, tests and command reference
├── agents/                    # designer, coder, tester, debugger, synthesizer, documentation, orchestrator
├── evals/                     # skill-trigger evals for `claude plugin eval`
├── validate.sh
└── SETUP.md                   # requirements and corvidex-mcp setup
```

`vhdl-tools` replaces the vunit-mcp, tsfpga-mcp and peeper-mcp servers: it
runs VUnit compiles, tests and reports, Yosys/GHDL synthesis and tsfpga
Vivado builds and reports, and VCD/FST waveform measurements. The command
reference is in `skills/shared/tools/README.md`.

## Install

Requirements are in `SETUP.md`. In short: `uv`, plus GHDL/NVC, Yosys or
Vivado as the task needs, and VUnit in the HDL project's own environment.

Install it as a Claude Code plugin; that is the only supported way:

```text
/plugin marketplace add ru551n/vhdl-skills
/plugin install vhdl@vhdl-skills
```

Skills are namespaced as `vhdl:<skill>`. If you registered vunit-mcp,
tsfpga-mcp or peeper-mcp yourself, remove those registrations; the plugin
no longer uses them. corvidex-mcp is optional and registered separately, see
[SETUP.md](SETUP.md).

## Validate and evaluate

```bash
./validate.sh                                   # structure, descriptions, references, manifests
claude plugin eval .                            # skill-trigger evals, with and without the plugin
uv run --project skills/shared/tools pytest     # vhdl-tools tests
```

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
- AXI4/AXI4-Lite/AXI4-Stream interfaces follow `shared/Axi4.md` (handshake, burst/boundary, ordering, no-loss).
- VUnit 5 is the default verification framework; `shared/Vunit.md` is authoritative for its API.
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
