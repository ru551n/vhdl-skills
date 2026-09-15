# VHDL Explainer

When `corvidex-mcp` is available, prefer it to locate the entity, architecture, dependent packages, matching documentation and related code. Use `get_source` for the exact source ranges being documented. For "who instantiates this" / "where is this generic or type declared" style questions (step 3's local package type resolution, and documenting instantiated dependencies), prefer the exact `find_references`/`find_definition`/`hover_info` tools (LSP/compiler-backed) over `search_hdl` or grep — they resolve the exact symbol instead of a fuzzy match, at a fraction of the cost. Fall back to local Read/Glob/Grep for material outside the index, or for exhaustive literal-string enumeration.

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
