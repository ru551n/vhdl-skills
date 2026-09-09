# Timing Closure and Resource Usage — Design Guidelines

Vendor-neutral rules for designing RTL that closes timing and lands on the
intended resources. Read this before architecting a datapath (`vharch`,
`vhdesign`), before implementing one (`vhfill`), and before trusting any
synthesis number (`vhsynth`). Each rule states the mechanism behind it;
the mechanism is what makes the rule general.

## Fundamentals — the timing-closure checklist

Apply these while writing the RTL, not after the first failing build. Each
is cheap at design time and expensive to retrofit.

**Register at entity boundaries.**
- Register every output of an entity by default. A leaf whose outputs are
  combinational hands its logic depth to whatever instantiates it, and its
  own out-of-context timing becomes meaningless (§1).
- No combinational path from an input port to an output port unless the
  entity's documentation says so explicitly (a pass-through ready is the
  usual legitimate case). Composition must never create a through-path
  nobody designed.
- Where an input feeds a deep cone, register the input too. One register
  each side of a boundary costs two cycles of latency and buys independent
  timing of every module.

**Budget logic depth per stage, and check it.**
- Derive a per-stage budget from the target period and the part: a 6-input
  LUT plus its routing costs a roughly fixed fraction of a period at a
  given speed grade, so a target clock implies a maximum number of LUT
  levels between registers. Write the budget down (e.g. "≤ 6 levels at
  this clock") and split any stage that exceeds it.
- Read the **logic-level histogram** in the timing report, not only the
  worst path. A stage with many levels is the structural target; the
  worst-slack path is merely its current representative and will be
  replaced by the next one when fixed.
- Carry chains count: a wide adder or comparator is one level of LUT plus
  a carry chain whose length is the operand width. Split adders wider than
  the budget allows across stages, or use the DSP block's own adder.

**Pipeline arithmetic and wide selection.**
- Multipliers: use the block's internal pipeline registers (input, product,
  output). An unregistered product leaving a DSP block is a guaranteed
  worst path.
- Wide muxes: a mux is log2(inputs) levels for the data, and its
  **select** is the late-arriving signal. Register the select one cycle
  early rather than computing it in the same stage as the mux.
- Dynamic shifts (barrel shifters) and dynamic-width operations are deep;
  pipeline them or decompose by fixed stages.
- Compare against **terminal-count flags**, not wide counters: `done_q`
  set when the counter reaches its last value, rather than a wide equality
  in every consumer.
- **A self-updating value with a multi-op body is the same problem in
  disguise.** A burst/credit/pointer register whose next value is
  computed as `subtract → clamp/min → divide` (or similar) in the same
  cycle it is used stacks that whole chain into one level budget, and it
  recurs anywhere a "how much is left, and what do I ask for next" value
  is maintained. Split it: register the subtraction, then derive the
  clamp/divide from the registered result on the following cycle — cheap
  whenever the value is consumed far less often than every cycle (a burst
  request that itself covers many beats, for instance). Where the divide
  exists only to round to a size limit, check first whether that limit
  can be a fixed power-of-two granularity instead: a compare-and-shift
  replaces most of the chain's depth outright.

**Structure registers so the tool can move them.**
- Registers with no reset and no clock enable can be retimed and
  replicated freely. Reset and enable on a datapath register prevent that.
- Reset only control (`valid`, state, counters). Never reset data,
  memories or pipeline payload; they are qualified by `valid`.
- Use synchronous reset. Asynchronous reset on wide buses blocks retiming
  and needs its own release synchronisation.

**Fan-out is a timing path.**
- Every control net — `valid`, enable, reset, configuration — that reaches
  more than a few tens of endpoints at a high clock needs replication.
  Register a copy near each consumer group, or provide a register and let
  the tool replicate it; a single flip-flop driving thousands of endpoints
  is a path of its own (§8).
- Clock enables are control nets too. A pipeline-wide `pipe_en` is the
  right backpressure idiom (§5) and it needs the same replication.

**Memories and lookup.**
- Use the block RAM's **output register**. It costs one cycle and removes
  the RAM's clock-to-out plus routing from the following stage. Never put
  logic between a RAM's data output and the first register.
- Read-address generation is itself a stage: register the address, then
  read, then register the data. A three-stage read is normal.

**Control structure.**
- One-hot or otherwise sparse encoding for FSMs whose outputs drive wide
  logic; register FSM outputs (Moore) rather than decoding state into the
  datapath combinationally.
- Decode early: turn a multi-bit mode or opcode into per-consumer one-bit
  registered flags at the point the mode is set, not in every consumer
  every cycle (§2). The symptom to look for is one wide field (an opcode,
  a mode) compared against a dozen-plus literals scattered across a
  controller's validation and dispatch logic — each comparison is cheap
  alone, but together they are a wide field with high combinational
  fan-out into many unrelated cones. Decode the whole set into one-hot
  flags once, registered at the same cycle the field is latched, and have
  every site test its flag instead of the raw field.

**Handshake stages.**
- Every inter-stage link is registered-ready or a skid buffer. A
  combinational `ready` chain across stages is a path that grows with the
  pipeline length (`shared/DesignPatterns.md`, "Ready/valid elastic
  stage").

**Close timing by structure before any place-and-route lever.**
- Exhaust the RTL levers first: the block-RAM output register on every
  memory whose clock-to-out feeds a failing path, a pipeline or elastic
  stage where a route is simply too long, fan-out registers near the
  consumers. Only then pblocks, implementation directives and post-route
  physical optimisation.
- Closure that depends on a directive or a floorplan is fragile — it
  evaporates on the next netlist change — while closure from structure
  survives. The target is positive slack with default directives. If a
  path still needs a place-and-route lever, that path is a finding about
  the design; record which ones and why structure could not close them.

**Prefer structure to constraints.**
- A multi-cycle or false-path constraint is a claim about the design that
  the tool cannot check. Fix the structure first; use such a constraint
  only when the path is genuinely multi-cycle by design, document why in
  the RTL, and keep the constraint next to the design that needs it.

**Prefer better RTL to synthesis settings and attributes.**
- A synthesis attribute or a project-wide synthesis setting changes how
  the tool maps what you wrote; it does not change what you wrote. Reach
  for it only after the structural fix has been tried and shown
  insufficient, and attach it to the specific object it corrects (a
  signal, an instance), never as a project-wide default that silently
  changes every entity's mapping.
- An attribute that suppresses a warning, forces an inference decision,
  or overrides a fan-out/replication choice is a sign the RTL made that
  decision ambiguous. Fix the RTL so the tool's default choice is already
  correct, and the attribute becomes unnecessary rather than load-bearing.
- Treat every attribute in the source as a debt: it must be commented
  with the reason it is there and the structural fix that would remove
  it, so a later reader does not mistake a workaround for a requirement.
- **This does not apply to clock-domain crossings.** There, the
  vendor/library attribute (`ASYNC_REG`, an XPM `_CDC_` macro's own
  generics, a `set_max_delay -datapath_only` next to the crossing) is not
  a workaround for missing structure — it *is* the structure, the only
  way to tell the tool a path is an intentional asynchronous crossing
  rather than a timing failure. Use it there without hesitation, and see
  `shared/CdcPolicy.md`.

**When a fix works, search the whole design for the same pattern before
the next build.** A timing report shows the current worst path, not
every path with the same defect — a duplicated block (two DMA engines
built from one template, two lanes of the same pipeline) reproduces
whatever anti-pattern the template has in every copy, and an unconverted
sibling of a just-fixed multiply-into-an-accumulator conversion sits at
nearly the same slack as the one already fixed. Fixing one instance and
re-running synthesis finds the next one only after paying for a full
build; grepping the source for the pattern's signature (the same
variable names, the same operator shape, every instantiation of the same
generic entity) finds all of them in one pass. A design that plateaus —
several independent paths sitting within a few hundred picoseconds of
each other after a fix — is usually exactly this: one anti-pattern,
several unfixed copies, not several unrelated problems.

The sections that follow are the ways designs fail these rules without
anyone noticing.

## 1. Only a top-level build is a timing result

An out-of-context build of a leaf entity times **register-to-register**
paths inside that leaf. A combinational cone whose start point is one of
the leaf's input ports is not such a path and is never timed. A leaf whose
real work is a deep cone hanging off its configuration or data inputs will
report a high Fmax while being the critical path of the design that
instantiates it, because inside the parent that cone is fed by registers
the leaf build never saw.

The reverse move also happens, and both directions are real: a leaf's
standalone Fmax can *fall* across a change that improves the top-level
result, because the leaf synthesis estimate has no visibility into how
its neighbours' registers land. Never use a leaf's own Fmax delta as a
pass/fail regression gate on its own — check the top-level, in-context
number.

- Treat a leaf's standalone Fmax as an **upper bound**. It can rule a leaf
  out; it can never rule a leaf in.
- Register a **top-level build target from the first milestone**. Leaf
  **area** from out-of-context builds is usable (flip-flops, block RAM and
  DSP blocks are additive across a composition, LUTs slightly conservative);
  leaf **timing** is not.
- If the real top has more port bits than the part has pins, build a
  pinnable wrapper for timing: drive every input from its own flip-flop (a
  seeded shift register), reduce every output through two register stages
  to one pin, and register reset. Every path in the design under test is
  then a true register-to-register path, nothing can be constant-propagated
  or trimmed, and the harness sits beside the design in the hierarchy
  rather than inside its row of the utilization report.
- **No DUT port ever connects to a pin directly**, in the harness or in
  a real top. Every port goes through an internal buffered register, and
  the pad-facing registers are packed into the I/O blocks (`IOB = TRUE`),
  so a register-to-pad hop carries no fabric route and no uncompensated
  clock-insertion delay. A harness whose *own* pad paths fail is an unfair
  harness: its worst-negative-slack is about the wrapper, not the design.
  Report the harness paths' slack separately and quote the
  register-to-register number as the design's result.
- A pad path may need a short pipeline between the IOB-packed register and
  the design's own port — up to a couple of stages is fine, and cheap
  relative to a mis-timed harness. But a run of two or more flip-flops
  with identical clock, no reset, no enable and no logic between them is
  exactly the pattern the tool auto-detects as a shift register (SRL): it
  will pack them into one SRL primitive with a different placement and
  clock-to-out profile than discrete flip-flops, and an SRL cell cannot
  itself be packed into an IOB. If those stages are latency padding, not
  an intentional shift register, mark every stage with the vendor's
  "keep as flip-flops" attribute (e.g. `shreg_extract = "no"`) and confirm
  in the post-synthesis/route report that no SRL cell appears on the path.
- Constrain harness pins with a realistic input/output delay relative to
  the clock, **not** false paths. A false path on a real pin is a
  clock-domain-crossing hole, and a correctly configured flow rejects it.
  "Realistic" is not the same as zero: with no MMCM the clock's own
  insertion delay (IBUF + route + global buffer, easily several
  nanoseconds) is uncompensated, and `set_output_delay 0` charges every
  bit of it to the pad while crediting the receiver with none — a
  requirement no design at that frequency can meet, and it will report
  as the design's own worst path when the fault is the constraint.
  Model the actual receiver: an output delay of the clock's measured
  insertion delay minus a real external setup allowance, and — as a
  *separate* number — a minimum delay of the receiver's hold requirement
  (usually near zero), never the same negative value reused for both;
  reusing it turns the minimum bound into an unmeetable hold constraint.
- Read the slack progression from synthesis through placement to routing.
  If it barely moves, the problem is **logic depth**, which RTL can fix and
  which synthesis-only slack is a good enough proxy to iterate on. If it
  collapses only after routing, it is **congestion or fan-out**, which is a
  placement and replication problem. Confirm with a full route at the end
  either way.

## 2. Per-command configuration must never be computed per cycle

A controller's command or descriptor register consumed **combinationally**
by the engines it controls is the most common way a design that looks fine
leaf by leaf fails at the top. Configuration-derived values — output
dimensions, tap counts, plane lengths, stride products, address bounds —
change once per command, yet they end up recomputed every cycle inside the
per-beat datapath, and the cone from the descriptor register to the
datapath registers becomes the worst path in the design.

- Compute derived configuration **once, at command start, sequentially**,
  over as many cycles as it needs. A command runs for thousands of cycles;
  a few cycles of setup latency are free. One extra logic level on a
  per-beat path is not.
- Put a **register stage on every engine's configuration boundary**. No
  engine's combinational cone may begin at the controller's descriptor
  register.
- Never form a runtime **product of configuration values** in a datapath.
  If a product changes only at a row or command boundary, maintain it in a
  register at that boundary and update it by addition per step.
- Configuration that reaches many consumers (hundreds of clock enables) is
  a fan-out problem as well as a depth problem; register it close to the
  consumers, or let the tool replicate a register you have provided.
- **Bound the arithmetic before registering it.** An unconstrained
  general-purpose integer type synthesises a multiplier or divider sized
  for its full range, not for the values the design ever produces —
  `kernel_h * kernel_w` on a 32-bit `natural` builds a 32-bit multiplier
  for a product that never exceeds a few hundred. Narrow the subtype
  first; only add a register if depth remains after narrowing. Registering
  an oversized combinational block first just moves the same logic behind
  a flip-flop and can silently change behaviour if anything downstream
  relied on the value being combinationally live within the cycle — check
  any testbench that varies the configuration beat-by-beat before turning
  a same-cycle read into a registered one; if it breaks a legitimate
  contract, narrow the type and leave the timing combinational instead.
- **A ready chain across several modules is the same failure with the
  fix at the wrong end.** The signature looks like congestion — long
  routes, many hierarchy crossings — but the actual cause is usually a
  combinational `ready` or clock-enable derived from a descriptor or
  status register several levels up and fanned out to hundreds of
  consumers at the bottom. Read the endpoint type before reaching for a
  floorplan: if it is a clock enable or a `ready` pin and the path spans
  more than one or two entities, the fix is a skid/elastic register at
  the hierarchy boundary that breaks the chain, not placement.

## 3. Reductions are trees, not chains

A reduction written as a linear chain — one compare or add after another,
described as a "single combinational stage" — has depth proportional to its
width and does not scale. Write reductions as balanced trees, mask inactive
leaves with the operation's identity (minimum for max, zero for sum), and
pipeline the tree when its depth exceeds the cycle budget. Commutative
integer operations give a bit-exact result regardless of tree shape; say so
in the comment and prove it with the existing vectors.

## 4. Pipeline the datapath, not the drain

Throughput losses hide in structure, not arithmetic. Measure **cycles per
unit of work** (per output item, per beat) from a waveform under zero stall
before believing any efficiency claim, and re-measure after every
structural change — removing one limit exposes the next.

Structures that silently cost cycles per item:

- An accumulator or state **cleared out of band** when a new item is
  accepted. That clear races the previous item's tail still in the
  pipeline and forces a drain state per item. Send a `first` flag down the
  pipeline with the data and have the accumulate stage **load** instead of
  add when it sees it: `0 + x = x`, so it is bit-exact, and the item
  boundary is just the cycle the flag arrives.
- `ready` asserted **only while the control FSM is idle**. That costs one
  accept cycle per item. Assert it on the last issue cycle of the current
  item so the next one latches in the same cycle.
- A **single-buffered assembly** stage pays its fill latency per item.
  Multi-buffer it, and derive the buffer count from the reservation time:
  N buffers sustain `max(work_cycles, ceil(reservation_cycles / N))` cycles
  per item. Two buffers are not always enough; compute N from the numbers.
- Any interlock that protects the assembly's source must be re-derived for
  N items in flight and must key on the **oldest** in-flight item, not the
  one being launched.

## 5. Freezing a pipeline must freeze everything it reads

A single clock-enable that holds a pipeline is the right backpressure
idiom, but every **free-running read port** the pipeline consumes from
keeps advancing while it is held, and re-pairs data with the wrong entry on
release. Give the read port the same enable, or re-present the last-issued
address while frozen. This is invisible to a stall test with one item in
flight; the test must have several.

The same freeze must extend through every stage you add later. Adding a
second read register (the block-RAM output register from §7, say) to
absorb clock-to-out means the pipeline now drains for one more cycle
after the freeze than "re-present the last address" alone covers — that
trick holds off one stage, not two. Drive the added stage's own clock
enable from the same `pipe_en` the rest of the pipeline uses, not from a
fixed address re-presentation, or a stall will silently mis-pair data
one stage later than before.

## 6. Lossless multi-stage read paths

A read path with a shared registered memory output feeding a per-consumer
output register loses data silently if the issue gate checks only the
output register and ignores a beat already in flight in the memory
register: after a drain the channel issues on consecutive cycles, and the
second beat overwrites the first before the consumer accepts it. The loss
is one beat per consumer stall, with no error and no X.

- Issue only when a slot is **provably** free for the returning beat under
  every possible consumer behaviour. With L beats held, I a beat landing
  now and A a beat accepted now, require `L + I − A ≤ 1` at issue time.
- Give each consumer its own **landing (skid) register**, so the beat
  always leaves the shared memory register the cycle it lands regardless
  of the consumer. That is also what prevents one stalled consumer from
  head-of-line-blocking another on the same memory.
- Keep **losslessness and throughput as separately tested properties**.
  The landing register provides losslessness; any prefetch term in the
  issue rule provides throughput only. If no test distinguishes them, the
  throughput term can be deleted as "redundant" with every test green.

## 7. Resources: inference is template-sensitive, and leaf sums are incomplete

- A **multi-dimensional array signal indexed by instance** does not infer
  block RAM; it becomes a flip-flop per bit. Declare one memory signal
  **per instance inside the generate**.
- A memory reached through **two textually different accesses** in one
  process (one per requester branch) infers distributed RAM or logic.
  Select address, data and enable into variables first, then do **one**
  array access per port.
- Neither failure is visible in simulation. A design that simulates
  perfectly can be two orders of magnitude larger than intended; only the
  utilization report shows it. A sudden jump in synthesis run time is the
  same signal.
- **Small multiplies fall below the DSP inference threshold** and land in
  fabric. When one operand is broadcast across several products, pack two
  narrow products into one multiplier (see `shared/DesignPatterns.md`,
  "Packed multiply"). Choose the packing shift from the multiplier's real
  port widths, not from a recipe for a different block, and **unpack every
  cycle before any summation** so the overflow bound is a single product,
  independent of kernel size, tile count and geometry.
- The tool may offer to absorb a reduction tree into the multiplier
  cascade as well. Decline when the multiplier budget is the resource being
  protected; a few hundred LUTs are cheaper than a third of the DSP blocks.
- A resource estimate assembled from **leaf builds misses everything that
  has no leaf build** — control, DMA, glue and any datapath nobody
  synthesized standalone. Give every block a build or accept that the
  estimate is a floor. Flip-flops, block RAM and DSP blocks are exactly
  leaf-additive; use that to detect a lost inference in the top-level
  report.
- **Size datapaths separately.** One shared bound (a maximum kernel size,
  a maximum width) that sizes two datapaths inflates the one that needs
  less, and lane cost grows superlinearly with such bounds. Give each
  datapath its own constant.
- A shared stream record's fixed payload width is a **global** constant;
  do not widen it for one wide payload. Carry that payload in a dedicated
  record type.

## 8. Reset and fan-out

A single reset flip-flop reaching tens of thousands of endpoints is a
timing path on its own. Register reset per block or let the tool replicate
a register you provide; keep reset off memory ports so block RAM inference
is unaffected; reset only the control bits that gate consumption
(`valid`), not the data behind them.

## 9. Design for verifiability

- **Analysis and elaboration prove nothing about behaviour.** Compile,
  elaborate, simulate and synthesize are four independent gates; passing
  one says nothing about the next. Functional bugs routinely compile and
  elaborate cleanly; synthesis-only bugs routinely pass every simulation.
- **Mutation-test every new test.** Break the RTL deliberately and confirm
  the specific test fails. Tests that assert nothing are common: random
  data that never exercises the wrong branch, an intermediate clamped to a
  constant, a generated vector that a hard-coded list never runs.
- **Beware shared oracles.** If the design under test and the reference
  model take their addresses or schedule from the same planner, a placement
  bug is self-consistently wrong on both sides and a value comparison cannot
  see it. Assert geometry from a closed-form expectation, and compare
  emitted programs byte-for-byte when a transformation is claimed to be
  free.
- **Assert loudly at the point of violation.** Unrelated upstream faults
  converge on identical downstream symptoms; a severity-`failure` assertion
  where the contract is broken is worth more than any downstream diagnosis.
- **Bit-exactness is the acceptance criterion for a mapping change.**
  Packing multipliers, pipelining, multi-buffering and reordering
  reductions are scheduling or mapping changes; if any expected value moves,
  the change is wrong. Never re-baseline to make it pass.
- **Measure throughput from a waveform**, as cycles per unit of work under
  zero stall, never from a model — and re-measure after every structural
  change.
