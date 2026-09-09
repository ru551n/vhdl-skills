# CDC Policy

Clock-domain crossing is a high-risk design area and must be treated as an
architectural concern, not as ordinary signal wiring.

## Primary rule

Prefer **predefined, proven CDC modules** whenever suitable ones are available.

Preferred source order:

1. Existing project-local CDC primitive/module already used and verified.
2. Proven reusable CDC module from the project's own HDL library or dependency set.
3. Vendor-provided CDC primitive/library intended for the target family.
4. A newly implemented custom CDC structure only when no suitable proven block exists.

Do not create a custom synchronizer, pulse bridge, handshake, or asynchronous
FIFO merely because it is easy to code.

## If no predefined module exists

Explicitly highlight this to the user before treating the CDC implementation as
complete.

State:
- which signals cross
- source/destination clock domains
- crossing class
- why no predefined module was available
- proposed implementation pattern
- required constraints
- residual verification risk

A custom CDC implementation should be treated as requiring extra review.

## CDC classification

Every crossing must be classified, for example:

- asynchronous single-bit level
- event/pulse
- multi-cycle control
- coherent multi-bit data
- ready/valid transaction
- asynchronous stream
- reset crossing
- mesochronous/plesiochronous/synchronous-derived clocks

Do not apply a generic 2-FF synchronizer without first classifying the crossing.

## Common structures

### Single-bit level

Use a proven multi-stage synchronizer when the signal semantics allow it.

Rules:
- usually 2+ destination-domain stages
- never use the first synchronizer stage in functional logic
- mark the synchronizer appropriately for the target flow when required
- ensure the input changes slowly enough relative to destination sampling

### Event/pulse

A short pulse may disappear between destination clocks.

Prefer an existing:
- pulse synchronizer
- toggle synchronizer
- request/acknowledge bridge

The implementation must account for event rate and back-to-back events.

### Coherent multi-bit data

Never independently synchronize each bit of a coherent bus.

Use:
- handshake with held-stable data
- asynchronous FIFO
- dual-clock RAM
- another proven coherent transfer mechanism

### Streaming data

Prefer a proven asynchronous FIFO or vendor asynchronous streaming bridge.

### Reset crossing

Reset assertion/deassertion semantics must be considered per domain.

When an asynchronous reset is used, prefer asynchronous assertion with
domain-local synchronized deassertion if required by the architecture/target.

## Constraints are part of the CDC implementation

If the toolchain supports CDC/timing constraints, the CDC is **not complete**
until the required constraints/attributes have been defined and reviewed.

Examples may include:
- synchronizer attributes such as `ASYNC_REG`
- clock-group declarations
- false-path constraints
- max-delay / datapath-only constraints
- bus-skew constraints
- vendor CDC primitive constraints
- scoped XDC/SDC constraints shipped with a reusable CDC block

Use only constraints that match the actual CDC structure.

Never add a broad false-path simply to silence timing analysis.

## Constraint availability

If the selected CDC module ships with constraints, use them unless the target
flow explicitly requires an equivalent alternative.

If the tool supports constraints but a required CDC structure has none:
- highlight this to the user
- define the required constraint strategy
- do not silently continue as though RTL alone is sufficient

If the toolchain has no relevant constraint mechanism available:
- state that explicitly
- document the limitation
- increase simulation/formal/review scrutiny

## Vendor/proven CDC IP

For FPGA designs, vendor CDC macros/primitives are often preferable because
they may provide:
- known implementation structures
- placement guidance
- synthesis attributes
- timing constraints
- CDC analysis recognition

Examples include vendor asynchronous FIFO generators, reset synchronizers,
clock-domain macros, and parameterized synchronizer libraries.

Do not assume vendor IP is automatically correct for every crossing; choose it
according to the crossing semantics.

## CDC verification

CDC verification should include, where available:
- static CDC analysis
- synthesis/implementation warnings
- timing constraint checks
- assertions around handshake/data stability
- stress tests with unrelated clock periods/phases
- reset sequencing tests
- overflow/underflow testing for asynchronous FIFOs

Simulation alone cannot prove metastability safety.

## Architecture documentation

For every CDC boundary document:
- source clock
- destination clock
- frequency/relationship
- signal/protocol
- crossing class
- chosen predefined module/primitive
- why the structure is suitable
- required constraints/attributes
- reset behavior
- verification method
- any remaining assumptions

## Completion gate

A CDC path is `DONE` only when:
- the crossing is classified
- a suitable proven/predefined structure is used, or custom implementation is explicitly highlighted
- required constraints are present when supported
- clock/reset assumptions are documented
- verification/static analysis has been performed where available

Otherwise report it as `BLOCKED`, `NEEDS_REVIEW`, or equivalent rather than
silently marking the design complete.


## Project-owned CDC blocks are preferred

When a project already has its own proven CDC library, prefer those blocks over
vendor IP/macros provided that:
- the block matches the crossing semantics
- it has been reviewed/verified
- its constraints/attributes are known and maintained
- it is portable enough for the current target

Vendor IP is a fallback when the project library does not provide a suitable
block, or when the target requires device-specific CDC resources.

Do not replace a proven project CDC block with vendor IP merely because vendor
IP exists.

## Reliable CDC techniques — error modes and the rules that close them

Vendor-neutral distillation of Lukas Vik's *Reliable FPGA CDC Constraints*
series (parts 1–5) and the `hdl-modules` `resync_*` / `asynchronous_fifo`
blocks that implement it. Read this when choosing or reviewing a CDC block;
the Vivado form of every constraint below is in `vivado-design` §A6.1.

**Use a ready-made module first — always.** Everything below explains
*why* the proven blocks are built the way they are and what their
constraints protect against, so that you can choose the right one and
review it. It is not a licence to hand-roll a crossing: the "Primary rule"
above still governs. A project or library block (`hdl-modules` `resync_*`,
`asynchronous_fifo`), then a vendor macro, then — only when neither fits
the crossing class — a custom structure that is explicitly flagged for
review and reproduces every rule here.

The governing idea: **every CDC topology has a fixed, enumerable set of
error modes, and a crossing is reliable only when the RTL structure and
the timing constraints together eliminate every one of them.** A design
therefore keeps a library of proven CDC black boxes, each shipping its own
constraints, and instantiates one per crossing. The design itself carries
no per-path timing exceptions. A path that crosses domains without a CDC
block is *supposed* to fail timing — that failure is the detection
mechanism, not a nuisance to constrain away.

### Rules that apply to every topology

1. **The crossing input is driven by a flip-flop, never by a LUT.**
   Combinational logic (an XOR, a binary-to-Gray conversion, a mux) can
   glitch when its input arrival times differ by routing, and the
   destination synchroniser may sample the transient. This is a separate
   failure from metastability and happens independently of it. If the
   source is combinational, add one source-domain register before the
   chain and accept the cycle of latency. (Static analysis flags a
   LUT-driven synchroniser input as a critical violation.)
2. **Two or more destination-domain registers, marked with the tool's
   synchroniser attribute, packed together, only the last stage used.**
   The attribute maximises metastability-recovery time and stops the tool
   from optimising, retiming or replicating the chain.
3. **Bound the latency with a maximum-delay constraint, never a false
   path.** A false path removes the crossing from analysis entirely, so
   its latency is undefined, build-dependent, and can be arbitrarily large
   — a synchroniser whose output arrives many cycles late is a
   functional bug the simulator cannot show. Bound the path with a
   *datapath-only* maximum delay equal to **the smaller of the two clock
   periods**. The resulting latency is then between almost nothing (short
   route, aligned edges) and roughly two destination periods (long route,
   misaligned edges), and no longer depends on the placer.
4. **Never apply blanket exceptions between clock domains** — no
   domain-to-domain false path, no "asynchronous clock group". They
   exclude *every* path between the domains from analysis, so latency,
   bus skew and phase behaviour are all uncontrolled and build-dependent,
   and they override the per-crossing bounds the CDC blocks carry.
5. **Scope constraints to the CDC entity**, so they apply to every
   instance automatically and reference cells relative to the entity
   rather than by full hierarchical path.

### Single-bit level

For semi-static "level" signals that change rarely. Error modes and what
closes each:

| # | Error mode | Cause | Closed by |
|---|---|---|---|
| 1 | Pulse shortening | Destination not sufficiently faster than source; a change narrower than a destination period is missed | Semantics: only use for signals that hold long enough |
| 2 | Pulse widening | A one-cycle source pulse becomes multi-cycle in the destination; desynchronises anything that counts cycles | Semantics: never use for pulses, handshakes or data qualifiers |
| 3 | Latency | Unconstrained route delay is undefined and build-dependent | Maximum-delay bound (rule 3) |
| 4 | Intra-word correlation | Parallel instances on the bits of a bus arrive with different latencies; the bus is incoherent | Never synchronise a bus bit-by-bit; use a counter, handshake or FIFO topology |
| 5 | Glitches | LUT-driven input sampled mid-transient | Flip-flop-driven input (rule 1) |

### Event / pulse

Topology: the source converts each pulse into a **toggle of a level**;
the level crosses through a single-bit level synchroniser; the
destination detects the level's edge and emits one pulse. Because the
toggle register is inside the block, this input *may* be LUT-driven.

| # | Error mode | Cause | Closed by |
|---|---|---|---|
| 1 | Widening / shortening | A plain level synchroniser cannot carry a pulse | The toggle topology itself |
| 2 | Latency | A false path on the level makes latency unbounded | Maximum-delay bound on the level path (and on the optional feedback path) |
| 3 | Parallel correlated pulses | Several pulse instances cannot be guaranteed to arrive in the same destination cycle | Never rely on simultaneity across instances |
| 4 | Pulse overload | Two pulses closer together than about two destination periods toggle the level twice before it is sampled; **no** edge is seen and both pulses are lost | Guarantee spacing (destination clock well over 2× source, or pulses known to be rare), or enable the **feedback** variant: the source only toggles when a fed-back level confirms the previous toggle was seen. Feedback guarantees at least one pulse arrives, at the cost of pulse density; pulses can still be dropped |
| 5 | Event counting | Fast-to-slow bandwidth reduction makes loss unavoidable | Never count output pulses to reconstruct an event count; cross a counter instead |

### Counter / Gray-coded pointer

For a value that advances **continuously by exactly ±1**, encoded as Gray so
that only one bit changes per step.

| # | Error mode | Cause | Closed by |
|---|---|---|---|
| 1 | Counter jumps | A step of more than one produces Gray values that never existed as intermediate states | The counter must be continuous; assert ±1 stepping in simulation |
| 2 | Glitches | Binary-to-Gray is combinational; unregistered, it can glitch into the chain | Register the Gray value in the source domain before the chain |
| 3 | Intra-word skew | Bits route with different delays; the destination samples a mixture of old and new bits, i.e. a value the source never held | **Bus-skew bound equal to one source period** across the Gray bits, so at most one bit is in transition at any sample |
| 4 | Latency | Unbounded route delay; in a FIFO this directly costs throughput | Maximum-delay bound (rule 3) |

Gray coding is only sound when the counter wraps at a power of two, so an
asynchronous FIFO's depth must be a power of two.

### Coherent multi-bit data (handshake / two-phase)

The source holds the data stable, toggles a level, and the destination
captures the data (clock-enable controlled) only after the level has
crossed; an acknowledge level returns. Constrain both level directions as
single-bit levels, and put a datapath-only maximum-delay bound on the data
bits from the source hold register to the destination capture register so
the data is guaranteed settled by the time the enable fires. A
clock-enable-controlled capture is *the mechanism* here, not a defect,
even though static analysis warns about it.

### Asynchronous FIFO

Write and read pointers cross as Gray counters (all four counter rules
above, in both directions); the read side asserts *valid* when the crossed
write pointer differs from its own. Two further concerns:

- **Data must be in the memory before the read side can see the pointer.**
  The pointer's crossing latency can be almost zero (rule 3's lower
  bound), while the write-address register and the RAM write port may sit
  under different branches of the clock tree. If clock skew between them
  approaches the pointer's crossing latency, the read side can observe
  the pointer before the write has landed, or during it. Register the
  binary-to-Gray stage (one extra cycle of pointer latency buys skew
  margin), keep the FIFO physically compact, and note that this
  ultimately rests on a **vendor guarantee of clock-tree skew** — which
  exists for some families and not for paths spanning die regions on
  large parts. Treat an asynchronous FIFO's skew assumption as something
  to state, not something proven.
- **Distributed-RAM (LUTRAM) FIFOs read combinationally**, unlike block
  RAM. The only legitimate false path in this whole scheme is from the
  write clock *through the read-data nets* to the read-side register,
  because that path is protected by the pointer logic, not by timing.

### Related (synchronous) clocks

Clocks with a fixed phase relationship — derived from one source at
integer ratios — have no metastability. A correlated configuration or
status word can be sampled directly across such a pair and is "free". But
a pulse or a handshake across a ratio still suffers widening/shortening,
and static tools cannot flag that case; it needs manual review. Never
treat two clocks as related unless the tool sees them as related.

### Build-flow gates

Run **after synthesis and again after implementation**, and abort the
build on either:

- any **unsafe** clock-to-clock interaction — a path between asynchronous
  clocks with no timing exception is a crossing that has no CDC block;
- any **critical** static-CDC violation (unsynchronised single- or
  multi-bit crossing, LUT-driven synchroniser input, fan-out before the
  first stage, mixed clocks into one chain).

Waive a warning only with the structural reason in the waiver text (a
Gray-coded bus, a clock-enable-controlled capture that is the design), so
reports stay readable without hiding a real problem. Expect this to catch
about nine in ten dangerous crossings; the remainder — pulses and
handshakes across *related* clocks — are invisible to static analysis and
must be found in review.

Sources: L. Vik, *Reliable FPGA CDC Constraints* #1 (single-bit level),
#2 (counters and FIFOs), #3 (pulses), #4 (build-tool settings), #5
(asynchronous FIFO), linkedin.com/pulse, 2024; and the `hdl-modules`
`resync` and `fifo` modules with their `scoped_constraints/*.tcl`.
