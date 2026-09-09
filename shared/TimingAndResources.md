# Timing Closure and Resource Usage — Design Guidelines

Vendor-neutral rules for designing RTL that closes timing and lands on the
intended resources. Read this before architecting a datapath (`vharch`,
`vhdesign`), before implementing one (`vhfill`), and before trusting any
synthesis number (`vhsynth`). Each rule states the mechanism behind it;
the mechanism is what makes the rule general.

## 1. Only a top-level build is a timing result

An out-of-context build of a leaf entity times **register-to-register**
paths inside that leaf. A combinational cone whose start point is one of
the leaf's input ports is not such a path and is never timed. A leaf whose
real work is a deep cone hanging off its configuration or data inputs will
report a high Fmax while being the critical path of the design that
instantiates it, because inside the parent that cone is fed by registers
the leaf build never saw.

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
- Constrain harness pins with zero input/output delay, **not** false paths.
  A false path on a real pin is a clock-domain-crossing hole, and a
  correctly configured flow rejects it.
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
