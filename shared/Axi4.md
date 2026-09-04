# AXI4 Policy

Authoritative for any module that exposes AXI4 (full, memory-mapped),
AXI4-Lite, or AXI4-Stream. Read `shared/InterfaceRecords.md` for channel
packaging and `shared/CdcPolicy.md` before crossing clock domains.

## Protocol selection

- **AXI4**: memory-mapped access with bursts, IDs, and outstanding
  transactions.
- **AXI4-Lite**: single-beat only; control/status register access. Use it
  when bursts, IDs, and outstanding transactions are not needed.
- **AXI4-Stream**: point-to-point data flow with no addressing; packet
  framing via `TLAST`.

Do not over-select: a single-beat register block is AXI4-Lite, not full
AXI4.

### Mandatory default for streaming data

Any interface that carries a sequence of data words with no addressing
(samples, pixels, symbols, packet bytes, ...) **must** use AXI4-Stream
semantics (`TVALID`/`TREADY`/`TDATA`, `TLAST` framing when packets exist) —
internally as `*_m2s`/`*_s2m` records per `shared/InterfaceRecords.md`, or
flat `t*` ports at boundaries that require it. Do not invent an ad-hoc
valid-only, valid/data-without-ready, or enable-only streaming interface
when AXI4-Stream applies; reuse an existing AXI4-Stream primitive (e.g.
hdl-modules' `axi_stream_pkg`/`axi_stream_fifo`) before hand-rolling one.

**Always implement backpressure (`TREADY`) when at all possible.** Every
inter-stage link in a pipeline needs its own working ready/valid handshake
satisfying rules 20-22 and 26 below (elastic stage: no loss, no
duplication, stable payload while `VALID='1'`/`READY='0'`) — do not
collapse a multi-stage pipeline onto a single global stall/clock-enable
derived from the final consumer unless the requirement or the user
explicitly accepts that simplification and its long-combinational-path
tradeoff. Omit `READY` only when the source is provably unable to ever
stall (e.g. a fixed-rate ADC dump with no way to pause the source) —
document that justification explicitly in the module's architecture/
proposal doc when it applies.

## Memory-mapped rules (AXI4 / AXI4-Lite)

Five channels: `AW`/`W`/`B` for writes, `AR`/`R` for reads.

### Handshake (mandatory on every channel)

1. A transfer occurs on the cycle where `VALID='1'` and `READY='1'`.
2. `VALID` must never be a function of `READY`, and `READY` must never be a
   function of `VALID` — no combinational loop through the handshake.
3. While `VALID='1'` and `READY='0'`, the payload (data, ID, address, and
   attributes) must remain stable until the handshake completes.
4. `VALID` may be deasserted only on a cycle without a completed transfer.
5. After a transfer, new data may be presented from the next cycle.

### Address and burst

6. `AWLEN`/`ARLEN`: burst length up to 256 beats; `AWSIZE`/`ARSIZE`: up to
   4096 bits per beat. AXI4-Lite: exactly one beat per transaction.
7. A burst must not cross a 4 KiB address boundary. A single unaligned
   beat may straddle one (it wraps to the start of the boundary).
8. `INCR`: addresses increase by the transfer size each beat.
9. `FIXED`: every beat targets the same address (narrow/straddling cases).
10. `WRAP`: total burst size (beats × transfer size) must be a power of two,
    the start address aligned to that size, and the burst wraps within the
    window.
11. Unaligned or narrow transfers use `WSTRB` (write) and the slave's
    lane handling (read); the slave must ignore disabled byte lanes.
12. The number of `W` beats must equal `AWLEN+1` for the matching
    transaction; `WLAST` must be `'1'` on exactly the last beat.
13. `B` responses for the same `AWID` must arrive in the order the
    addresses were accepted; `R` beats for the same `ARID` must arrive in
    the order of the address channel. Different IDs may be reordered by the
    slave — a master must order its own same-ID traffic and, when
    reordering is unacceptable, use a single read ID.
14. Outstanding transactions: the slave may accept a new address before
    completing an earlier one (up to the depth it supports); the master
    must track responses per ID.
15. Responses: `OKAY` for success, `DECERR` for decode errors (no slave),
    `SLVERR` for slave errors (timeout, parity, ...). Drive a valid
    response for every accepted transaction; never `X`.
16. Cache and protection attributes must be driven consistently per
    transaction; do not rely on cache behavior in testbenches.

### Reset

17. During reset every interface signal settles to a deterministic value
    (`VALID='0'`, `READY='0'`, responses `OKAY`, no `X` on the fabric).
18. After reset, no in-flight transaction may be assumed; pending
    handshakes are dropped.

### Clock domains

19. An AXI interface never crosses a clock domain by registering the
    signals. Use a proven AXI clock bridge / CDC FIFO with reset
    synchronization per `shared/CdcPolicy.md`.

## AXI4-Stream rules

One channel: `TDATA`, `TKEEP` or `TSTRB`, `TLAST`, `TVALID`, `TREADY`,
plus optional `TID`/`TUSER`.

20. Same handshake as memory-mapped: transfer on `TVALID='1' and
    TREADY='1'`; `TVALID` never a function of `TREADY` (and no
    combinational loop in the other direction); payload stable while
    `TVALID='1'` and `TREADY='0'`.
21. No loss, no duplication: a beat presented with `TVALID='1'` must not be
    dropped while `TREADY='0'`; an accepted beat must not be lost or
    repeated.
22. Packet framing: `TLAST='1'` marks the final beat of a packet. While
    `TLAST='0'`, every subsequent accepted beat belongs to the same packet;
    a new packet starts only after the `TLAST` beat has been accepted.
    Packets are never interleaved.
23. `TKEEP`/`TSTRB` mark active byte lanes for narrow or unaligned data in
    `TDATA`; the receiver ignores inactive lanes. Without them, data is
    interpreted as fully active.
24. One stream channel preserves in-order delivery; there is no ordering
    across separate channels.
25. Optional `TID`/`TUSER` follow the same handshake and stay stable with
    the beat.
26. Idle cycles (both `TVALID` and `TREADY` low) are legal anywhere,
    including inside a packet; an elastic stage follows
    `shared/DesignPatterns.md` (no loss, no duplication, one transfer/cycle
    when continuously ready).

## VHDL conventions

- Channel records per `shared/InterfaceRecords.md` (`*_m2s`/`*_s2m`) for
  internal use; flat ports only when interfacing vendor IP or the project
  convention is flat.
- Bus width, data width, and ID width as generics (e.g.
  `DATA_WIDTH : positive range 32 to 4096 := 32`); power-of-two widths
  checked at elaboration.
- Byte-lane logic (`WSTRB`, `TKEEP`) must cover every lane; no accidental
  narrowing or dropped lanes.
- Burst counters use `numeric_std`; length/size ranges constrained by the
  protocol, not by the design's convenience.

## Testbench / BFM rules

- Drive `VALID` independently of `READY`; never mirror `READY` into
  `VALID`.
- Randomize backpressure, but a held-low `READY` is legal backpressure, not
  a deadlock: the transfer simply does not complete.
- Self-check the 4 KiB boundary rule, beat counts, `WLAST`/`TLAST`
  placement, and same-ID ordering in any AXI4 BFM.
- Never fabricate protocol compliance: check it against the signals or the
  tool result (`backend:` record per `shared/McpToolPolicy.md`).

## Synthesis and debug checks

- No combinational loop in any handshake path; no latches inferred by
  incomplete combinational conditions on `READY`/`VALID`.
- 4 KiB boundary handling verified, including unaligned first/last beats.
- `WSTRB`/`TKEEP` lane coverage verified for every data width.
- Reset outputs deterministic on the whole fabric.
- On failure, use `waver-mcp` to measure `VALID`/`READY` alignment, beat
  counts, and `TLAST`/`WLAST` placement at the failing time rather than
  dumping raw waveform text.