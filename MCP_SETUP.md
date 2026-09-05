# Recommended MCP setup

These servers are optional but preferred by the skills.

## vhdl-rag-mcp

Repository:
https://github.com/ru551n/vhdl-rag-mcp

Claude Code example from the upstream project:

```bash
claude mcp add vhdl-rag-mcp -- uvx --from git+https://github.com/ru551n/vhdl-rag-mcp.git vhdl-rag-mcp
```

Configure its repository index in `~/.config/vhdl-rag/config.toml`.

## vunit-mcp

Repository:
https://github.com/ru551n/vunit-mcp

Point the server at the VUnit project directory using its documented `VUNIT_MCP_PROJECT_DIR` configuration.
Keep `VUNIT_MCP_TIMEOUT` below the per-call timeout of your MCP client (the
shipped Maki config uses 240 s under a 300 s call timeout).
Record waveforms for peeper-mcp by passing `waveform_format` to
`vunit_run_tests` (`vcd` on GHDL, `fst` on NVC).
Install the upstream `skills/vunit-mcp` skill beside this project's skills when desired.

## peeper-mcp

Repository:
https://github.com/ru551n/peeper-mcp

Typical stdio command:

```bash
uvx --from "git+https://github.com/ru551n/peeper-mcp.git" peeper-mcp
```

Reads FST (NVC's default) and VCD (GHDL's default) waveforms directly, so
waveforms recorded by vunit-mcp work without conversion. Linux/macOS only
(pywellen ships no Windows wheels).

## tsfpga-mcp

Repository:
https://github.com/ru551n/tsfpga-mcp

Typical stdio command:

```bash
uvx --from "git+https://github.com/ru551n/tsfpga-mcp.git" tsfpga-mcp
```

Requires working Yosys, the GHDL CLI, the GHDL Yosys plugin, and compiled GHDL
std/ieee libraries (`GHDL_PREFIX` / `TSFPGA_MCP_GHDL_PREFIX`). Install the
upstream `skills/tsfpga-mcp` skill beside this project's skills when desired.

## Recommended combination

The intended failure-debug chain is:

```text
vunit-mcp
  run test + record waveform
       │
       ├── get report/log
       │
       └── get waveform path
               │
               ▼
            peeper-mcp
               │
               ▼
        measured signal evidence
               │
               +── vhdl-rag-mcp
                   source/docs cross-reference
```

Synthesis:

```text
VHDL sources
    │
    ├── vunit-mcp -> source/compile order (when registered)
    │
    └── tsfpga-mcp -> GHDL + Yosys synthesis/resource summary
```

Vendor implementation/timing/power remains a vendor-tool task and is outside
the scope of these skills.
