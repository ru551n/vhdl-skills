# VHDL Module Documentation Contract

Every module document must be useful without opening the RTL.

Required sections:

1. `# <module>`
2. **Purpose** — concise behavioral summary.
3. **Entity and architecture** — entity name and implemented architecture name (normally `rtl`).
4. **Generics** — name, type, default, meaning, constraints.
5. **Ports** — name, mode (`in/out/inout`), type/width, description.
6. **Clocking and reset** — clock domains, active edge, reset polarity, sync/async behavior.
7. **Interfaces/protocols** — handshake rules, ordering, backpressure.
8. **Functional behavior** — externally visible behavior.
9. **Timing/latency** — cycle latency, throughput, pipeline boundaries.
10. **Registers/configuration** — if applicable.
11. **Dependencies** — packages/entities and source locations.
12. **Implementation notes** — notable synthesis/architecture details that integration or verification needs.
13. **Verification notes** — key corner cases and assertions.

Documentation must describe the **as-built** implementation after `vhfill`, not stale design intent.
