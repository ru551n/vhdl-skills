# FPGA Power-Up Initialization Policy

## Purpose

FPGA configuration-time initialization may replace reset logic **only** when the
target FPGA architecture and synthesis/implementation flow guarantee the
required power-up value.

This optimization is about configuration/power-up state. It does not replace a
functional runtime reset requirement.

## Decision rule

A register may use a VHDL declaration initial value instead of a reset branch
only when **all** of the following are true:

1. The exact FPGA family/device is known.
2. The exact synthesis/implementation backend is known.
3. Vendor documentation or a verified project synthesis experiment confirms
   that declaration initial values are implemented in hardware for that
   family/flow.
4. The register only needs a defined value after FPGA configuration/power-up.
5. No requirement needs that state to be restored later by:
   - soft reset
   - watchdog recovery
   - subsystem restart
   - interface reset
   - partial reconfiguration boundary behavior
   - fault recovery
6. Removing the reset does not violate protocol, safety, CDC, or system startup
   requirements.
7. Simulation and implemented-hardware startup semantics remain aligned.

If any condition is unknown, keep/reset the state using the normal project
reset strategy.

## VHDL pattern

When power-up initialization is verified:

```vhdl
signal count : natural range 0 to C_MAX_COUNT := 0;
signal state : t_state := IDLE;
signal valid : std_logic := '0';

p_regs : process(clk)
begin
  if rising_edge(clk) then
    ...
  end if;
end process;
```

This is preferred over adding reset solely to obtain the same configuration-time
initial state:

```vhdl
p_regs : process(clk)
begin
  if rising_edge(clk) then
    if rst_n = '0' then
      count <= 0;
      state <= IDLE;
      valid <= '0';
    else
      ...
    end if;
  end if;
end process;
```

provided the target/flow satisfies the decision rule above.

## Reset is still required when it has runtime semantics

Keep reset logic when the design specification says reset must restore state
after configuration.

Examples:
- a bus peripheral must respond to a software-controlled peripheral reset
- a protocol link has a reset/retrain sequence
- a watchdog restarts a subsystem
- a state machine must recover without reconfiguring the FPGA
- safety logic requires an operational reset path

Initial values cannot perform those functions.

## Datapath guidance

If a datapath register has no externally observable value until a corresponding
`valid`/state bit says its contents are meaningful, it often needs neither
reset nor initial value.

Prefer initializing/resetting the validity/control state rather than wide
datapath registers when the architecture permits it.

Example:

```vhdl
signal data_q  : std_logic_vector(255 downto 0);
signal valid_q : std_logic := '0';
```

If `data_q` is never consumed while `valid_q = '0'`, initializing/resetting
`data_q` may be unnecessary.

## Target capability policy

Do not use a guessed universal family list as proof.

### AMD/Xilinx with Vivado

Current Vivado flows support VHDL register declaration initial values and map
them to FPGA configuration/global initialization behavior. These may therefore
be used when the selected AMD/Xilinx device is supported by the active Vivado
flow and no runtime reset semantics are required.

Still verify special resources and flows such as:
- partial reconfiguration
- unusual primitive instantiation
- externally controlled startup
- imported netlists
- third-party synthesis

### Intel/Altera with Quartus

Quartus documentation describes FPGA register power-up behavior and conversion
of HDL default/initial values to power-up settings. However, implementation of
non-default/non-zero values and optimization may be family/tool dependent.

Treat this as `SUPPORTED_WITH_TOOLCHAIN_VERIFICATION`, not blanket permission.
Verify the exact family and Quartus synthesis result before removing reset.

### Lattice, Gowin, Microchip and other FPGA families

Treat register declaration initialization as `UNKNOWN` until the exact family
and synthesis flow are verified.

RAM/primitive initialization support is not sufficient evidence that arbitrary
fabric flip-flop declaration initialization has the required semantics.

Use vendor documentation or a small synthesis/implementation proof.

## Capability states

Record one of:

- `VERIFIED_SUPPORTED`
- `SUPPORTED_WITH_TOOLCHAIN_VERIFICATION`
- `VERIFIED_UNSUPPORTED`
- `UNKNOWN`

Recommended project record:

```yaml
fpga_initialization:
  vendor: AMD
  family: Artix-7
  device: xc7a35t...
  synthesis: Vivado
  version: ...
  register_declaration_init: VERIFIED_SUPPORTED
  evidence: vendor documentation / synthesis check
```

## Verification experiment

When documentation is unclear, synthesize a minimal register:

```vhdl
signal q : std_logic := '1';

process(clk)
begin
  if rising_edge(clk) then
    q <= d;
  end if;
end process;
```

Inspect the synthesized primitive/netlist/report for the target device and
confirm that the intended INIT/power-up property is actually retained.

Do not infer support merely because RTL simulation starts at the declared value.

## Architecture documentation

When reset is omitted because configuration initialization is used, document:
- exact target family/device
- synthesis backend
- initialization capability status/evidence
- which registers rely on power-up initialization
- why no runtime reset is required
- behavior during soft reset/reconfiguration/fault recovery

This is an architectural decision, not a cosmetic coding-style choice.
