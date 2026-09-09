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

When a design has generics that change the elaborated hardware (array
widths, parallelism factors, buffer depths), consider exposing the
actual elaborated values as a dedicated read-only status register,
distinct from any build-time/generation-time constants used by test or
software generators. Software reading the same generic value at runtime
(instead of trusting a value baked in at its own build time) can detect
a mismatch between the bitstream it is running against and its own
assumptions. Keep this register purely observational (no side effects on
read) and pack multiple small generic values into byte/sub-fields of one
word rather than spending a register per field.

## Parameterized resource/throughput scaling generic

When a single generic (e.g. a parallelism/replication factor) is the
intended way to trade hardware resources for throughput or latency:

- Keep it a single top-level generic that propagates through the
  hierarchy via the generic propagation map, not a value re-derived or
  hardcoded at multiple levels.
- Build a small closed-form cost/throughput model (cycles-per-unit-work
  as a function of the generic, clock frequency, target work size) as
  code, not just prose in a design doc. Pin it with regression tests that
  assert concrete numbers for each configuration the project actually
  ships or plans to ship (not just symbolic bounds) — this catches silent
  drift between the model and the RTL/architecture as both evolve.
- Treat "does configuration X meet the target budget" as a regression
  test assertion, and record the margin (headroom or shortfall) rather
  than only a pass/fail, so a later change that erodes headroom is
  visible before it flips the test.
- Do not assume every configuration must meet every target; it is valid
  for a smaller/cheaper configuration to knowingly miss an aspirational
  target as long as that shortfall is asserted explicitly rather than
  silently unverified.

## CDC single-bit level

For an asynchronous level entering a domain, use a documented 2+ stage
synchronizer when the signal semantics permit it.

Do not use the first synchronizer stage in functional logic.

Prefer a ready-made block. Error modes and the constraint that closes each
(flip-flop-driven input, `async`-marked chain, datapath-only max-delay bound
of the smaller period, no false path): `shared/CdcPolicy.md`, "Reliable CDC
techniques".

## CDC event/pulse

Do not assume a narrow pulse will be observed by another clock domain.

Use:
- pulse stretch if timing guarantees suffice
- toggle synchronizer
- request/ack handshake
depending on event rate and semantics.

Prefer a ready-made block. A toggle synchronizer loses *both* pulses when
two arrive within about two destination periods (pulse overload); the
feedback-gated variant guarantees at least one arrives. Never reconstruct an
event count from output pulses. Details: `shared/CdcPolicy.md`, "Reliable
CDC techniques".

## Async FIFO

Use for sustained coherent multi-bit data between unrelated clocks.

Synchronize Gray-coded pointers, not the payload bus bit-by-bit.

Prefer a ready-made FIFO. Pointers need a bus-skew bound of one source
period *and* a datapath-only max-delay bound; depth must be a power of two;
register the binary-to-Gray stage; a LUTRAM read path is the one legitimate
false path. Details and the clock-skew caveat: `shared/CdcPolicy.md`,
"Reliable CDC techniques".

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

## Per-command configuration boundary

An engine that runs for many cycles per command must receive **registered,
pre-computed** configuration, never the controller's raw descriptor
register. Derive geometry (output dimensions, tap counts, plane lengths,
stride products) once at command start in a sequential setup phase; put a
register stage on every engine's `cfg_*` inputs. A combinational cone that
begins at the descriptor register is a timing failure waiting for a top-level
build to reveal it. See `shared/TimingAndResources.md` §2.

## Lossless two-stage read path

Shared registered memory output feeding a per-consumer output register:
- capture into the consumer's register **unconditionally** the cycle the
  beat lands, so the shared register is borrowed for exactly one cycle and
  no consumer can head-of-line-block another
- issue a read only when a slot is **provably** free for the returning beat
  under every consumer behaviour (`L + I − A ≤ 1`)
- give each consumer a landing (skid) register; it is the losslessness
  mechanism, and any prefetch term in the issue rule is throughput only —
  test the two properties separately

Document the invariant in the issue-rule comment, not in the header.

## Position-boundary flag instead of out-of-band clear

Do not clear an accumulator from outside the pipeline when a new item is
accepted; that races the previous item's tail. Send a `first` flag down the
pipeline with the data and have the accumulate stage **load** instead of
add when it sees it. `0 + x = x`, so the change is bit-exact, and consecutive
items overlap without a drain state.

## Multi-buffered assembly with a reservation queue

A stage that assembles an item over several cycles and presents it for
several more should hold N buffers, N chosen from
`max(work_cycles, ceil(reservation_cycles / N))` per item. Any interlock
that protects the source (a row-bank aliasing guard) must key on the
**oldest** in-flight item, not the one being launched — keep a small queue
of the guard value pushed at launch and popped at acceptance. Re-derive the
interlock when N changes; the single-buffer form is usually too coarse to
survive, and dropping it must be proven by a mutation test at every depth.

## Balanced, masked reduction

Never write a wide reduction as a linear chain. Build a balanced tree, mask
inactive leaves (for a variable tap count, mask with the identity of the
operation: minimum for max, zero for sum), and pipeline the tree when its
depth exceeds the cycle budget. Commutative integer operations keep the
result bit-exact regardless of tree shape.

## Packed multiply

When one operand is broadcast across several products, pack two narrow
products into one multiplier: `A = x_hi·2^S + x_lo`, `P = A·y`, split P.
Take S from the multiplier's real port widths, keep S small enough that the
packed operand fits, and **unpack every cycle before summing** so the only
overflow condition is a single product. Pin the resulting multiplier count
in a build checker; it is the packing's structural signature.
