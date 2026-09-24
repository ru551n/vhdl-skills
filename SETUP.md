# Setup

## Requirements

- [`uv`](https://docs.astral.sh/uv/). `vhdl-tools` runs through it and installs its own Python dependencies on first use.
- Whatever the task needs from these system tools: GHDL or NVC for simulation, Yosys with the GHDL plugin and compiled GHDL std/ieee libraries for open-source synthesis, Vivado for AMD builds and reports.
- VUnit, installed in the HDL project's own environment. `vhdl-tools` uses the project's VUnit and Python, not a bundled copy.
- Waveform recording from VUnit needs the `--wave` flag (VUnit PR #1101) in the project's VUnit. Without it GHDL still records but NVC does not.
- Waveform measurements use pywellen, which ships Linux and macOS wheels only.

`skills/shared/tools/README.md` has the full command reference and configuration.

## corvidex-mcp (optional)

Semantic search and exact code navigation over the project's VHDL, docs and code. The plugin does not register it, so every session does not pay for its tools; the skills use it when it is connected and fall back to plain search when it is not. Register it yourself:

```bash
claude mcp add corvidex-mcp -- uvx --from git+https://github.com/ru551n/corvidex-mcp.git corvidex-mcp
```

Configure its repository index in `~/.config/corvidex/config.toml`. With no
`[[repositories]]` entry there, the repository is auto-named
`<dirname>-<8 hex hash>` (for example `my_fpga-582e8509`), not the plain
directory name. Read the real name from `repository_status` before passing
`repository=` to any tool.

If your launcher runs the server with `uv` instead of `uvx`, use
`uv --project DIR run ...`, not `uv --directory DIR run ...`. The latter
changes the server's working directory, so corvidex silently indexes its
own source tree instead of the target project. `CORVIDEX_MCP_PROJECT_DIR`
overrides the project directory when the launcher command can't be edited.
Confirm with `repository_status` that the indexed repository is the target
project.

## Failure-debug chain

1. `vhdl-tools vunit` runs the failing test with a waveform and returns the report, log and waveform path.
2. `vhdl-tools wave` measures signal values, latencies and clocks in that waveform.
3. `corvidex-mcp`, or plain search, traces the source.
