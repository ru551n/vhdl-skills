---
name: vhsynth
description: Synthesize a VHDL module or full IP using tsfpga-mcp when available, with local Yosys+GHDL fallback
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.

# VHDL Synthesizer

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

## Backend priority

1. **`tsfpga-mcp`** for portable VHDL synthesis/resource summaries.
2. **local Yosys + GHDL plugin** when MCP is unavailable.

Do not describe `tsfpga-mcp` resource synthesis as vendor timing closure.

`tsfpga-mcp` only reports aggregated resource counts (LUTs, FFs, DSPs, block RAMs, or raw cell
counts for `chip=generic`) — never a per-port netlist dump.

## Inputs

Must know:
- complete source set
- top entity
- target chip/flow (`generic`, `xilinx`, `intel`, `microchip`)
- target family where required
- generic overrides, if any
- for a non-VHDL top: which VHDL entities it instantiates, if any

Never infer a required target, family or generic value.

If the top entity has more than one architecture, ask which one to synthesize — `tsfpga-mcp` has
no architecture-selection parameter, so the only way to pick one is to include only that
architecture's source file in the synthesis source set.

## Preferred workflow — tsfpga-mcp

### 1. Status

Call `tsfpga_status`.

If the GHDL plugin, Yosys flow, or required environment is unavailable, either fix/report configuration or use a fallback backend.

### 2. Inspect sources

Use `tsfpga_inspect` when:
- the top entity is uncertain
- generics need discovery
- multiple architectures are present
- source ambiguity is possible (e.g. a unit declared in both VHDL and Verilog)

Resolve every `Notes:` ambiguity by asking the user before synthesizing.

### 3. Choose target

If the user did not already provide a valid target, call `tsfpga_targets`.

If several materially different targets fit and the choice affects the answer, require an explicit target rather than guessing. `family` is only accepted for `chip=xilinx`/`intel`/`microchip`, never for `chip=generic`.

### 4. Resolve complete source set

Preferred:
- `vunit_list_files` when `vunit-mcp` is available and sources are registered
- otherwise `shared/HierarchyFilelist.md`

All dependencies must be passed because synthesis does not rely on persistent work-library state.

### 5. Synthesize

Use `tsfpga_synthesize` with:
- `sources`, `top`, `chip`
- `family` if required by the chosen chip
- `generics` if supplied (VHDL top only; the type from `tsfpga_inspect` decides interpretation)
- `vhdl_entities` when `top` is a Verilog/SystemVerilog module (or the design has no VHDL top): the VHDL entity names it instantiates
- `discard_ffinit` only for `chip=microchip`, when flip-flop initial values fail legalization

Record the returned:
- backend/flow
- resource counts
- synthesis diagnostics

## Scope

`tsfpga-mcp` and local Yosys+GHDL produce portable synthesis/resource feedback.
Post-route timing, vendor Fmax, site utilization, power estimation, and
place-and-route are out of scope; state that in the report instead of
fabricating results.

## Outputs

Write `synth/<module>/synth_report.md` containing:
- date/backend
- source set/top
- target chip/family
- generics
- synthesis result
- resources
- diagnostics

Backend-specific raw artifacts may be stored beside the report.

Never fabricate synthesis, timing, Fmax, utilization or power.


## Modern synthesis checks

Review synthesis diagnostics for:
- unintended latches
- inferred clocks/gated clocks
- unexpected RAM/DSP inference
- width truncation/constant propagation surprises
- unconstrained or missing clock intent
- high-fanout reset/control issues
- hierarchy unexpectedly optimized away when it matters for debug/constraints

For FPGA sign-off, portable Yosys/GHDL synthesis is an early feedback step.
Vendor implementation remains authoritative for timing closure and device mapping.

## Initialization verification

When RTL relies on declaration initial values instead of reset:
- verify the exact target family/backend
- inspect synthesis output for retained INIT/power-up semantics
- report any initialization dropped, transformed, or unsupported
- fail the portability assumption if the backend cannot prove the required state

A successful RTL compile is not proof of hardware power-up initialization.

## CDC synthesis/implementation checks

For designs containing CDC:
- verify synchronizer attributes survived synthesis
- verify CDC/timing constraints were loaded
- inspect tool CDC/timing warnings
- confirm asynchronous clock relationships are represented correctly
- confirm predefined CDC IP/macros were preserved/implemented as intended

Do not suppress CDC/timing warnings with broad exceptions.

## Vendor inference verification

When vendor attributes/primitives/IP are used, verify intended inference,
inspect ignored/unsupported-attribute warnings, confirm exact family/tool
support, and report any fallback that changes architecture or performance.
