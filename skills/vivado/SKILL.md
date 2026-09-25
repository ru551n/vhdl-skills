---
name: vivado
description: Use when the target is an AMD/Xilinx device built with Vivado and the answer depends on it: Vivado inference templates and synthesis attributes, XDC timing and CDC constraints, Vivado timing closure, reading a Vivado timing, utilization or DRC report and judging whether to trust it, tsfpga Vivado builds, querying a built design's paths, logic depth, fanout or hierarchy from its checkpoint, or family specifics (7-series, UltraScale/UltraScale+, Versal, Zynq PS/PL). Typical requests include "will Vivado infer a BRAM here", "write the XDC for this CDC", "why does the Vivado build fail timing", "is this timing estimate real", "which DSP does UltraScale+ have", "what drives this high-fanout net in the build".
---

# AMD/Xilinx with Vivado

The vendor layer for AMD/Xilinx. The other skills are vendor-neutral and hand over to this one
when the target is an AMD part built with Vivado; it adds how their rules map onto Vivado and the
devices. It does not replace them: portable RTL is still `vhfill`'s, resource and timing reasoning
still `vhsynth`'s.

## Before you start

- `shared/` means the `shared/` folder next to this skill's folder (`../shared/`). The two files
  below are large: run `grep -n '^#' <File>.md` and read only the sections the task touches.
- The project's own conventions and constraints win over anything here.
- Anything below `PORTABLE_VHDL` (an attribute, a primitive, XPM, IP) is classified and justified
  under `shared/VendorPolicy.md` before it is used.

## What is where

- `VivadoDesign.md`: what to write so Vivado does what you mean.
  - Part A, methodology: UltraFast principles, inference templates (A2), synthesis attributes
    (A3), resets (A4), clocking (A5), CDC and its constraints (A6, A6.1), XDC (A7), timing
    closure (A8), resources (A9), floorplanning (A10), power (A11), debug hooks (A12), tsfpga
    integration (A13).
  - Part B, devices: 7-series (B1), UltraScale and UltraScale+ (B2), Versal (B3), the Zynq PS/PL
    boundary (B4), and a comparison table (B5).
- `VivadoGotchas.md`: how Vivado and tsfpga fail silently: post-synthesis hooks, the XDC
  command subset, a `create_clock` that makes no clock, out-of-context Fmax blind spots, timing
  fixes that change inference elsewhere, DSP48 template sensitivity. **Read it before trusting
  any Vivado number.**

## Tools

`vhdl-tools synth` runs a tsfpga project's Vivado builds and retrieves their reports
(`project-build`, `project-get-timing-report`, `project-get-utilization-report`,
`project-get-drc-report`); `shared/ToolPolicy.md` §4 has the commands. The report commands need a
`vivado` executable. Never report a timing or resource number that no build produced, and label
each one as a synthesis estimate or a routed result.

`vhdl-tools vivado` answers questions about a design that is already built, without rebuilding
it. Every command names a checkpoint (`--dcp`, e.g. `<run>/synth_1/<top>.dcp` or
`impl_1/<top>_routed.dcp`). The first command opens it in a background Vivado; later ones, from
any agent, reuse that session and answer in well under a second.

| Command | Use |
|---|---|
| `hierarchy --dcp D [--node INST] [--depth N]` | Instance tree with LUT, FF, SRL, RAMB and DSP counts: ask this first |
| `tcl --dcp D --script TCL` | Any Vivado Tcl; `--script -` reads it from stdin |
| `stop [--dcp D]` | Free the session's memory (several GB on a large design) |

What `tcl` is for, with the Tcl that answers it:
- Worst paths: `get_timing_paths -max_paths 10` with `SLACK`, `LOGIC_LEVELS`, `STARTPOINT_PIN`,
  `ENDPOINT_PIN`; full detail with `report_timing -from A -to B -return_string`.
- Logic depth: `report_design_analysis -logic_level_distribution -return_string`, or
  `get_timing_paths -filter {LOGIC_LEVELS >= 8}`.
- Fanout: `report_high_fanout_nets -max_nets 20 -return_string`, `FLAT_PIN_COUNT` on a net,
  `all_fanout -flat -endpoints_only [get_pins P]` (and `all_fanin -startpoints_only`).
- Structure: walk with `-of_objects` (cell, pins, net, pins, cells), filter with `-filter` on
  `REF_NAME`, `PRIMITIVE_GROUP`, `IS_PRIMITIVE`, `DIRECTION`; `ORIG_REF_NAME` is a hierarchical
  cell's RTL module.

Rules:
1. Use `-return_string` on `report_*` commands; a report printed to Vivado's console is lost.
2. Output is cut at 200 lines. Count first (`llength`), then narrow by hierarchy prefix or type.
3. Names are post-synthesis (`sig_reg[3]`, generated LUT names), and registers can be absorbed
   into DSP48s, SRLs or LUTRAM. A missing RTL signal is not proof the logic is gone.
4. An empty `SLACK` means the path is unconstrained (no clock on it), common on out-of-context
   synth checkpoints. Only a checkpoint built with its XDC gives real slack.
5. A rebuilt checkpoint gets a fresh session on the next command; object names from before the
   rebuild may no longer exist.

## Hand-offs

- Vendor-neutral RTL, testbenches and synthesis spikes: `vhfill`, `vhtest`, `vhsynth`.
- Timing and resource rules that hold on every vendor: `shared/TimingAndResources.md`; CDC
  classification: `shared/CdcPolicy.md` (this skill has its Vivado constraints).
