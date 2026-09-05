---
name: vharch
description: Decompose an IP requirement into VHDL submodules, interfaces, requirement files, and a top-level VHDL skeleton
allowed-tools: Read, Write, Bash, Grep, Glob
---
> **Path note:** `shared/*.md` files live in the skills' `shared/` directory — a *sibling* of this skill's directory (resolve against the skills root, e.g. `<skills-root>/shared/CodingStyle.md`), not inside the skill directory.
> **Layout note:** `ddoc/`, `rtl/`, `doc/`, `lib/` are the conventional tsfpga layout. When the project uses a different layout (e.g. `modules/<name>/{src,test,doc}`), follow the project's layout and keep the same file-naming conventions (`<ip>_arch.md`, `<module>_req.md`, `<module>.md`, `<module>.vhd`).


# VHDL Architect

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

## MCP preference

Before inventing a new block, use `corvidex-mcp` when available:
1. `repository_status`
2. `search_knowledge` for relevant standards/design guidance
3. `search_vhdl` / `search_hdl` for reusable or precedent entities
4. `get_source` for exact candidate implementations

If unavailable, search `lib/`, `rtl/`, `doc/`, and `ddoc/` locally with Read/Glob/Grep.

## Input

A top-level requirement such as `ddoc/<ip>_req.md`.

## Outputs

- `ddoc/<ip>_arch.md` — canonical structural source of truth.
- `ddoc/<submodule>_req.md` — one per new submodule.
- `rtl/<ip>_top.vhd` — structural top-level VHDL skeleton.

## Workflow

### 1. Re-run safety

If `ddoc/<ip>_arch.md` exists, treat it as authoritative. Regenerate derived structural artifacts from it rather than inventing a new architecture.

Before overwriting `rtl/<ip>_top.vhd`, inspect whether integration logic has been added or `--@` markers were resolved. If it is no longer a pure skeleton, do not clobber it silently.

### 2. Analyze requirements

Extract:
- top-level entity name
- generics
- ports and types
- clock/reset domains
- protocols
- performance requirements
- functional blocks

Check `lib/` documentation (and any vendored dependency, e.g. `hdl-modules`) before designing a new block. Reuse existing documented entities when appropriate; see `shared/ReusableRTL.md` ("Reuse before authoring new RTL") — a thin wrapper around an existing module is allowed and preferred over a fork or a rewrite.

Prefer a modular decomposition over a monolithic block, including for newly
authored (non-reused) functionality: see `shared/ReusableRTL.md` ("Prefer
modular decomposition") for the single-responsibility, testable-unit
criteria and the `<ip>_top` structural-only rule.

`shared/Axi4.md` is authoritative for protocol selection and the mandatory rules. Any streaming data interface (samples, pixels, symbols, words with no addressing) defaults to AXI4-Stream with backpressure (`TREADY`) implemented at every inter-stage link unless the source is provably unable to stall (see `shared/Axi4.md`, "Mandatory default for streaming data") — decide and record this explicitly in the architecture doc, do not leave it implicit.

### 3. Define architecture

Write `ddoc/<ip>_arch.md` with:
- intent
- top-level generic table
- top-level port table
- submodule table (`name | responsibility | new/lib-reuse | source`) — apply
  `shared/ReusableRTL.md`'s modular-decomposition criteria when drawing
  submodule boundaries, not just its reuse criteria
- Mermaid block diagram
- inter-module interface table
- generic propagation map
- clock/reset domain map
- non-obvious boundary rationale

### 4. Generate module requirement files

Each new module gets `ddoc/<module>_req.md`.

Split generated structure from hand-owned functionality with:

```html
<!-- functional-spec: hand-owned below this line -->
```

Above marker:
- responsibility
- generics
- ports
- protocols
- clock/reset requirements

Below marker:
- `## Functional Description`
- behavior, corner cases and performance requirements

On re-run, preserve the hand-owned section exactly.

### 5. Generate VHDL top skeleton

Create `rtl/<ip>_top.vhd`.

Requirements:
- VHDL-2008 context clauses
- entity with architecture-defined generics/ports
- `architecture rtl`
- internal `signal` declarations
- direct entity instantiations using `entity work.<module>(rtl)`
- `generic map` and `port map`
- `--@` comments for unresolved integration adaptations
- no functional implementation beyond structural wiring

Example:

```vhdl
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity foo_top is
  generic (
    data_w : positive := 8
  );
  port (
    clk     : in  std_logic;
    rst_n   : in  std_logic;
    s_data  : in  std_logic_vector(data_w-1 downto 0);
    s_valid : in  std_logic;
    m_data  : out std_logic_vector(data_w-1 downto 0);
    m_valid : out std_logic
  );
end entity foo_top;

architecture rtl of foo_top is
  signal ctrl2proc_data  : std_logic_vector(data_w-1 downto 0);
  signal ctrl2proc_valid : std_logic;
begin
  u_ctrl : entity work.foo_ctrl(rtl)
    generic map (
      data_w => data_w
    )
    port map (
      clk     => clk,
      rst_n   => rst_n,
      s_data  => s_data,
      s_valid => s_valid,
      m_data  => ctrl2proc_data,
      m_valid => ctrl2proc_valid
    );

  u_proc : entity work.foo_proc(rtl)
    generic map (
      data_w => data_w
    )
    port map (
      clk     => clk,
      rst_n   => rst_n,
      s_data  => ctrl2proc_data,
      s_valid => ctrl2proc_valid,
      m_data  => m_data,
      m_valid => m_valid
    );
end architecture rtl;
```

### 6. Structural self-check

For each architecture interface row verify:
- exactly one driver unless the protocol explicitly allows otherwise
- all endpoints exist
- modes/types/ranges are compatible
- generic expressions resolve consistently
- every new submodule has a requirement file
- every reused module resolves to a documented source
- every block is instantiated
- every top-level port is connected or intentionally documented as unused

Report changed, unchanged, and orphaned requirement files on re-run.


## Modern architecture checklist

The architecture document must identify, where applicable:
- VHDL revision policy (2008 default, 2019 only if explicitly verified)
- clock domains and target frequencies
- reset strategy per clock domain
- CDC crossings and intended structures
- interface ownership and ready/valid semantics
- pipeline/transaction latency
- arithmetic widths and overflow policy
- RAM/DSP inference intent
- vendor-specific dependencies
- verification hooks/checkers
- synthesis/timing assumptions

Do not defer CDC/reset/interface semantics until implementation.

## FPGA initialization capability decision

Read the shared `FpgaInitialization.md`.

If an FPGA target is known, architecture must decide whether configuration-time
register initialization can be used to reduce reset logic.

Record:
- vendor/family/device
- synthesis backend
- initialization capability state
- evidence
- registers/state classes eligible for initial values
- state that still requires runtime reset

If target/family is not known, do not assume initialization support.

## Type policy decision

Before defining project-wide signal types, determine whether the user wants:
- unresolved types (default), or
- resolved types.

If this preference is not already known, ask the user before locking the
architecture convention.

Document the selected policy.

## CDC architecture gate

Read the shared `CdcPolicy.md`.

For every CDC boundary:
1. classify the crossing
2. search first for an existing/predefined proven CDC module
3. identify its required constraints/attributes
4. document clock/reset assumptions
5. if no suitable predefined module exists, highlight this explicitly to the user

Do not approve an architecture containing an unclassified or unconstrained CDC
path when the active toolchain provides a relevant constraint mechanism.

## Portability target

Prefer `PORTABLE_VHDL`. If vendor-specific behavior is needed, classify it as
`VENDOR_ATTRIBUTE`, `VENDOR_PRIMITIVE`, or `VENDOR_IP` and document why.

## Reusability scope

Make true architectural degrees of freedom generic. Keep incidental
implementation details local.
