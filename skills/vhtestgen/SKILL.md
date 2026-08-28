---
name: vhtestgen
description: Generate a VUnit-first self-checking VHDL-2008 test project, with standalone GHDL fallback
allowed-tools: Read, Write, Bash, Grep, Glob
---

# VHDL Test Generator

Read `shared/ModernVHDL.md` and `shared/CodingStyle.md`; they are authoritative for language revision and modern RTL practice.


Read `shared/McpToolPolicy.md`.

## Preferred verification architecture

Use **VUnit** by default.

If `vunit-mcp` is available:
1. call `vunit_status`
2. inspect project with `vunit_export_json`, `vunit_list_tests`, and `vunit_list_files`
3. preserve the existing `run.py` conventions
4. add tests in the same project style
5. validate discovery with `vunit_list_tests`

If VUnit is not present in the project and `vunit-mcp` is unavailable, a standalone GHDL testbench may be generated instead.

## Inputs

Use:
- `ddoc/<ip>_arch.md`
- module/IP docs
- top entity
- requirements
- register/protocol docs
- relevant precedent from `vhdl-rag-mcp` when available

## Recommended VUnit structure

```text
run.py
tb/
├── tb_<ip>.vhd
├── tb_pkg.vhd
└── ...
```

Project-specific structures may differ; follow the existing VUnit project.

## VUnit testbench rules

- VHDL-2008
- `library vunit_lib; context vunit_lib.vunit_context;`
- `runner_cfg` generic
- `test_runner_setup` and `test_runner_cleanup`
- self-checking VUnit checks
- deterministic timeout
- named test cases via `run("...")`
- reusable procedures/packages when helpful
- no requirement for a custom `[FINISH]` token

Example skeleton:

```vhdl
library ieee;
use ieee.std_logic_1164.all;

library vunit_lib;
context vunit_lib.vunit_context;

entity tb_foo is
  generic (runner_cfg : string);
end entity;

architecture tb of tb_foo is
begin
  main : process
  begin
    test_runner_setup(runner, runner_cfg);

    while test_suite loop
      if run("reset") then
        check_equal(1, 1);
      elsif run("nominal") then
        check_equal(1, 1);
      end if;
    end loop;

    test_runner_cleanup(runner);
    wait;
  end process;
end architecture;
```

## Test plan

Cover:
- reset/default state
- nominal flow
- legal min/max values
- handshake/backpressure
- boundary/wrap/saturation
- specified error cases
- latency/pipeline behavior
- register access where present
- concurrent interface behavior where relevant

Maintain `tb/<ip>/tc_list.md` if the project uses that artifact, mapping test names to requirements.

## Waveform readiness

For tests likely to need signal-level debug, design them so `vunit_run_tests` can be invoked with waveform recording. Waveform files are consumed by `waver-mcp`.

## Fallback standalone tests

Only when VUnit is unsuitable/unavailable:
- generate standalone VHDL-2008 TB
- use assertions
- emit exactly one `[FINISH] PASS` or `[FINISH] FAIL`
- terminate via `std.env.finish`


## Modern verification rules

- Prefer independent named VUnit testcases.
- Use deterministic tests by default.
- For randomized tests, record/report the seed and make failure reproducible.
- Prefer scoreboards/reference models over checking implementation-internal signals.
- Test protocol invariants: stability under stall, ordering, no loss/duplication.
- Test reset during relevant traffic/state when allowed by the requirement.
- Test min/max/boundary generic configurations when practical.
- Add functional coverage only when it has a clear requirement mapping.
- Preserve existing OSVVM/UVVM infrastructure rather than replacing it.
- Generate waveforms for diagnosis, not as the primary pass/fail mechanism.

## CDC verification tests

When CDC logic is present:
- vary source/destination clock periods and relative phases
- exercise reset sequencing in both domains
- stress back-to-back events/transactions
- test FIFO overflow/underflow protections where relevant
- use assertions/checkers for handshake/data-stability assumptions

Simulation complements but does not replace static CDC/timing analysis.

## Generic configuration coverage

Exercise representative generic configurations: minimum valid, default/common,
boundary values, and enabled/disabled feature variants where applicable.
