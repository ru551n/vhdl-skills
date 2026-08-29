---
name: vhsynth
description: Synthesize a VHDL module or full IP using yosynth-mcp when available, with local Yosys+GHDL fallback
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.

# VHDL Synthesizer

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

## Backend priority

1. **`yosynth-mcp`** for portable VHDL synthesis/resource summaries.
2. **local Yosys + GHDL plugin** when MCP is unavailable.

Do not describe `yosynth-mcp` resource synthesis as vendor timing closure.

## Inputs

Must know:
- complete source set
- top entity
- architecture, normally `rtl`
- target chip/flow
- target family where required
- generic overrides, if any

Never infer a required target, architecture, family or generic value.

## Preferred workflow — yosynth-mcp

### 1. Status

Call `yosynth_status`.

If the GHDL plugin, Yosys flow, or required environment is unavailable, either fix/report configuration or use a fallback backend.

### 2. Inspect sources

Use `yosynth_inspect` when:
- the top entity/architecture is uncertain
- generics need discovery
- multiple architectures are present
- source ambiguity is possible

### 3. Choose target

If the user did not already provide a valid target, call `yosynth_targets`.

If several materially different targets fit and the choice affects the answer, require an explicit target rather than guessing.

### 4. Resolve complete source set

Preferred:
- `vunit_list_files` when `vunit-mcp` is available and sources are registered
- otherwise `shared/HierarchyFilelist.md`

All dependencies must be passed because synthesis does not rely on persistent work-library state.

### 5. Synthesize

Use `yosynth_synthesize` with:
- sources
- top
- architecture
- chip
- family if required
- generics if supplied

Record the returned:
- backend/flow
- top-level ports
- resource counts
- synthesis diagnostics

## Scope

`yosynth-mcp` and local Yosys+GHDL produce portable synthesis/resource feedback.
Post-route timing, vendor Fmax, site utilization, power estimation, and
place-and-route are out of scope; state that in the report instead of
fabricating results.

## Outputs

Write `synth/<module>/synth_report.md` containing:
- date/backend
- source set/top/architecture
- target/family/part
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
