---
name: vhexplain
description: Generate or refresh module documentation by analyzing a VHDL entity and architecture
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.


# VHDL Explainer

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

When `vhdl-rag-mcp` is available, prefer it to locate the entity, architecture, dependent packages, matching documentation and related code. Use `get_source` for the exact source ranges being documented. Fall back to local Read/Glob/Grep.

## Input

A `.vhd` source file or entity name.

## Workflow

1. Locate the entity source and selected architecture.
2. Read context clauses, packages, entity generics/ports, architecture declarations, processes, assignments and instantiated entities.
3. Resolve local project package types when required to explain the public interface.
4. Produce documentation following `shared/ModuleDocContract.md`.
5. Save to `doc/<module>.md` for project RTL, or adjacent to a reusable `lib` module when that is the project convention.

Explain:
- generic constraints/defaults
- port types and vector ranges
- clock/reset semantics
- combinational vs registered outputs
- FSMs and datapaths
- handshake rules
- exact latency if derivable
- instantiated dependencies
- notable assertions/generates
- any simulation-only code

Do not infer guarantees the RTL does not establish. Mark uncertainty explicitly.
