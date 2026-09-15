---
name: vhdoc
description: Use when documenting or explaining VHDL — writing or refreshing a module's documentation from its entity and architecture, explaining what an existing VHDL block does (ports, latency, FSMs, handshakes), or assembling an IP-level integration document from module docs. Typical requests include "document this module", "explain this entity", "what does this block do", "write the IP doc".
---

# VHDL Documentation

## Before you start

- `shared/` means the `shared/` folder next to this skill's folder (`../shared/`). Read only the sections you need.
- The project's own documentation layout wins; follow existing docs before `shared/ModuleDocContract.md`.
- Flow files are optional. Use `ddoc/` and `doc/` when they exist; otherwise place docs where the project keeps them, or answer in the reply.
- Prefer `corvidex-mcp` when connected; `shared/ToolPolicy.md` has routing and fallbacks.

## Pick the task

| Task | Read (this skill's folder) |
|---|---|
| Document or explain one entity or module from its source | `module-doc.md` |
| Assemble an IP-level integration document from the architecture and module docs | `ip-doc.md` |

When the user asks for an explanation rather than a document, answer in the reply using the checklist in `module-doc.md` and write no file.

## Rules

- State only what the RTL establishes, and mark anything uncertain.
- Include synthesis, timing or verification numbers only from real reports or tool runs.
