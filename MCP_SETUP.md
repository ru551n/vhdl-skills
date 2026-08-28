# Recommended MCP setup

These servers are optional but preferred by the skills.

## vhdl-rag-mcp

Repository:
https://github.com/ru551n/vhdl-rag-mcp

Claude Code example from the upstream project:

```bash
claude mcp add vhdl-rag-mcp -- uvx --from git+ssh://git@github.com/ru551n/vhdl-rag-mcp.git vhdl-rag-mcp
```

Configure its repository index in `~/.config/vhdl-rag/config.toml`.

## vunit-mcp

Repository:
https://github.com/ru551n/vunit-mcp

Point the server at the VUnit project directory using its documented `VUNIT_MCP_PROJECT_DIR` configuration.
Install the upstream `skills/vunit-mcp` skill beside this project's skills when desired.

## waver-mcp

Repository:
https://github.com/ru551n/waver-mcp

Typical stdio command:

```bash
uvx --from "git+https://github.com/ru551n/waver-mcp.git" waver-mcp
```

## yosynth-mcp

Repository:
https://github.com/ru551n/yosynth-mcp

Typical stdio command:

```bash
uvx --from "git+https://github.com/ru551n/yosynth-mcp.git" yosynth-mcp
```

Requires working Yosys and the GHDL Yosys plugin for VHDL synthesis.

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
            waver-mcp
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
    └── yosynth-mcp -> GHDL + Yosys synthesis/resource summary
```

Vendor implementation/timing/power remains a vendor-tool task, e.g. Vivado.
