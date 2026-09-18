# VHDL IP Documentation

Use `corvidex-mcp` when available to cross-check architecture, module docs, VHDL symbols and related source. Exact current project artifacts remain authoritative. Use `get_source` before quoting or relying on exact implementation behavior. When cross-checking a specific, already-named symbol (e.g. confirming a generic/port referenced in a module doc actually resolves the way the doc claims), prefer the exact `find_definition`/`find_references`/`hover_info` tools (LSP/compiler-backed) over `search_hdl` or grep — reserve `search_hdl`/`search_knowledge` for the conceptual "what covers this topic" lookups. See `shared/ToolPolicy.md`'s routing table; a concept search that looks thin doesn't mean the topic isn't covered — cross-check with `find_symbol` before concluding that.

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

Prefer module docs over rereading RTL. If a module doc is missing or stale, run/recommend `vhdoc` rather than silently inventing details.

## Portability and generic documentation

Document portability class, vendor/tool/family dependencies, vendor-specific
mechanisms, public generics and valid ranges, unsupported combinations, and
simulation-only support files.
