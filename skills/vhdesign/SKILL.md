---
name: vhdesign
description: Use when planning or designing VHDL/FPGA hardware before RTL is written — breaking an IP or requirement into submodules and interfaces, writing an architecture document or module design proposal, choosing clocking, reset, CDC or AXI4-Stream strategy, or creating an entity or top-level skeleton. Typical requests include "design a module that...", "how should I architect...", "split this into blocks", "write a proposal/spec for...".
---

# VHDL Design

## Before you start

- `shared/` means the `shared/` folder next to this skill's folder (`../shared/`). Those docs are large: run `grep -n '^#' shared/<Doc>.md` and read only the sections the task touches.
- The project's own conventions win. If the repository has a style guide, CLAUDE.md/AGENTS.md rules, or existing modules to copy, follow them over `shared/HouseStyle.md`.
- Flow files are optional. If `ddoc/`, `*_req.md`, `*_proposal.md` or `flow_status.md` exist, use and update them. Otherwise work from the request and the source files, answer in the reply, and create flow files only when the user asks or `vhflow` is driving.
- Tools: `corvidex-mcp` when connected, for precedent search; `vhdl-tools` (`shared/bin/vhdl-tools`) for quick synthesis spikes. `shared/ToolPolicy.md` has the commands and fallbacks. Never report a result no tool produced.

## Pick the mode

| Request | Read (this skill's folder) | Produces |
|---|---|---|
| An IP or multi-block design: submodules, interfaces, clock/reset domains, top-level skeleton | `architecture.md` | architecture doc, per-module requirements, `<ip>_top` skeleton |
| One module: dataflow, FSMs, widths, latency, entity/architecture backbone | `module.md` | proposal, module doc, backbone with `--@` markers |

Read both when a module design shows that the architecture itself must change.

## References by topic

- Naming, reset style, architecture names: `shared/HouseStyle.md`
- Structure that closes timing (registered configuration boundaries, balanced trees, leaf Fmax is only an upper bound): `shared/TimingAndResources.md`
- AXI4 / AXI4-Stream selection and mandatory rules: `shared/Axi4.md`
- CDC: `shared/CdcPolicy.md`; reset versus initial values: `shared/FpgaInitialization.md`
- Reuse and decomposition: `shared/ReusableRTL.md`; patterns: `shared/DesignPatterns.md`
- AMD/Xilinx targets: the `vivado` skill

## Ask the user instead of defaulting

- the reset strategy for any domain whose state must be cleared at runtime
- resolved versus unresolved types, when the project has no convention yet
- the target device or family, when it changes inference or initialization
- any CDC crossing without a proven existing synchronizer
