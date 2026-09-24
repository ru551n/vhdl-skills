---
name: vivado
description: Use when the target is an AMD/Xilinx device built with Vivado and the answer depends on it — Vivado inference templates and synthesis attributes, XDC timing and CDC constraints, Vivado timing closure, reading a Vivado timing, utilization or DRC report and judging whether to trust it, tsfpga Vivado builds, or family specifics (7-series, UltraScale/UltraScale+, Versal, Zynq PS/PL). Typical requests include "will Vivado infer a BRAM here", "write the XDC for this CDC", "why does the Vivado build fail timing", "is this timing estimate real", "which DSP does UltraScale+ have".
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

## Hand-offs

- Vendor-neutral RTL, testbenches and synthesis spikes: `vhfill`, `vhtest`, `vhsynth`.
- Timing and resource rules that hold on every vendor: `shared/TimingAndResources.md`; CDC
  classification: `shared/CdcPolicy.md` (this skill has its Vivado constraints).
