---
name: vhdoc
description: Aggregate VHDL module documentation into a complete IP-level integration document
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.
> **Layout note:** `ddoc/`, `rtl/`, `doc/`, `lib/` are the conventional tsfpga layout. When the project uses a different layout (e.g. `modules/<name>/{src,test,doc}`), follow the project's layout and keep the same file-naming conventions (`<ip>_arch.md`, `<module>_req.md`, `<module>.md`, `<module>.vhd`).


# VHDL IP Documentation

Read `shared/ModernVHDL.md`, `shared/CodingStyle.md`, and `shared/HouseStyle.md`; they are authoritative for language revision, modern RTL practice, and concrete naming/style conventions.


Read `shared/McpToolPolicy.md`.

Use `corvidex-mcp` when available to cross-check architecture, module docs, VHDL symbols and related source. Exact current project artifacts remain authoritative. Use `get_source` before quoting or relying on exact implementation behavior. When cross-checking a specific, already-named symbol (e.g. confirming a generic/port referenced in a module doc actually resolves the way the doc claims), prefer the exact `find_definition`/`find_references`/`hover_info` tools (LSP/compiler-backed) over `search_hdl` or grep — reserve `search_hdl`/`search_knowledge` for the conceptual "what covers this topic" lookups. See `shared/McpToolPolicy.md`'s routing table; a concept search that looks thin doesn't mean the topic isn't covered — cross-check with `find_symbol` before concluding that.

## Goal

Build `doc/<ip>.md` from the architecture document and per-module docs.

## Sources

- `ddoc/<ip>_arch.md`
- `doc/<module>.md`
- reused `lib` documentation
- top-level `rtl/<ip>_top.vhd` only when needed to verify integration details

## Required IP document sections

- Purpose and scope
- Top-level entity, generics and ports
- Clock/reset domains
- Architecture/block diagram
- Submodule inventory
- Inter-module protocols
- End-to-end data/control flow
- Register/configuration map if present
- Latency/throughput summary
- Integration guidance
- Synthesis results, only if real `synth_report.md` exists
- Verification status, only from real run summaries
- Known limitations/issues

Prefer module docs over rereading RTL. If a module doc is missing or stale, run/recommend `vhexplain` rather than silently inventing details.

## Portability and generic documentation

Document portability class, vendor/tool/family dependencies, vendor-specific
mechanisms, public generics and valid ranges, unsupported combinations, and
simulation-only support files.
