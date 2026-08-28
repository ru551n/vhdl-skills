# Modern VHDL Design Patterns

Read `ModernVHDL.md` and `CodingStyle.md`.

## Ready/valid elastic stage

A one-entry elastic stage must preserve:
- no loss
- no duplication
- stable payload while `valid='1' and ready='0'`
- throughput of one transfer/cycle when downstream is continuously ready

Document whether the stage is:
- registered-ready
- combinational-ready
- skid-buffered

Do not accidentally create a long combinational ready chain across many stages.

## FIFO

For a synchronous FIFO:
- use pointer/counter widths derived from depth
- define full/empty behavior precisely
- define simultaneous read/write behavior
- assert/guard illegal access if required
- make RAM inference intent clear

For unrelated clocks, use an asynchronous FIFO pattern with Gray-coded pointer
crossing or a proven library implementation. Do not adapt a synchronous FIFO by
independently synchronizing data/control bits.

## Counter

Use `natural`/constrained integer when the bound is modest and tool behavior is
well understood; use `unsigned` when bit-level width/overflow behavior is part
of the implementation contract.

Always define wrap/saturate/error behavior.

## Pipeline

Treat latency as part of the module contract.

Pipeline data and its validity/sideband metadata together.

Avoid resetting pure datapath stages unless required; reset valid/control state
instead where that gives deterministic protocol behavior.

## Clock enable

Prefer:

```vhdl
if rising_edge(clk) then
  if ce = '1' then
    q <= d;
  end if;
end if;
```

over fabric-generated/gated clocks.

## RAM/ROM inference

Use a tool-recognizable synchronous template.

Keep initialization, read-during-write behavior, byte enables and output
registering explicit because they affect inference portability.

Use vendor primitives only when inference cannot express the required behavior.

## Arithmetic pipeline

Separate:
- numeric type
- binary point/scale
- intermediate width
- rounding
- saturation/wrap behavior
- pipeline latency

Do not hide arithmetic policy inside ad-hoc casts.

## Register bank

Separate bus/protocol handling from register semantics.

For each field specify:
- reset value
- access mode
- write behavior
- clear/set side effects
- hardware-vs-software ownership
- reserved-bit behavior

## CDC single-bit level

For an asynchronous level entering a domain, use a documented 2+ stage
synchronizer when the signal semantics permit it.

Do not use the first synchronizer stage in functional logic.

## CDC event/pulse

Do not assume a narrow pulse will be observed by another clock domain.

Use:
- pulse stretch if timing guarantees suffice
- toggle synchronizer
- request/ack handshake
depending on event rate and semantics.

## Async FIFO

Use for sustained coherent multi-bit data between unrelated clocks.

Synchronize Gray-coded pointers, not the payload bus bit-by-bit.

## Reset crossing

Treat asynchronous reset deassertion as a clock-domain crossing concern.

Prefer domain-local synchronized release when required by the target/architecture.

## FSM

Prefer enums and explicit defaults.

Separate Moore/Mealy choices based on interface timing requirements, not style preference.

## Generate

Use VHDL-2008 generate syntax to express compile-time structure cleanly.
Name generate blocks meaningfully.

## Packages and records

Use packages for shared protocol types/helpers and records for related internal
signals when they reduce wiring errors.

Avoid package dependency sprawl.

## Assertions/checkers

Encode assumptions close to the relevant boundary:
- invalid generics
- impossible handshakes
- overflow assumptions
- illegal control combinations

Keep verification-only logic clearly separated when synthesis portability is uncertain.
