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
