# tsfpga module framework — creating modules and using `get_modules()`

Authoritative for any project whose `run.py` discovers RTL/testbenches via
`tsfpga.module.get_modules()` (the "module-based" layout), as opposed to a
plain `VUnit.from_argv()` project that hand-adds libraries/files (see
`shared/Vunit.md` §2 for that simpler case). This doc is the tsfpga-specific
layer on top of `Vunit.md`, not a replacement for it — everything in
`Vunit.md` (test phases, `pre_config`/`post_check` signatures, backpressure
policy, TDD workflow) still applies once `run.py` hands files to VUnit.

Distinct from the `tsfpga-mcp` MCP server's own skill (`tsfpga-mcp` skill,
tools `tsfpga_status`/`tsfpga_inspect`/`tsfpga_targets`/`tsfpga_synthesize`):
that skill is scoped to **synthesis** of already-written sources. This doc
covers the **module/build framework** (`tsfpga.module`, `run.py`) used to
organize and simulate a project's RTL *before* anything reaches synthesis.

## 1. Module folder layout

One folder per module under a `modules/` root (name is arbitrary, but
`get_modules(modules_folder=...)` scans exactly one directory level):

```
modules/
  <name>/
    src/                     # RTL, one library per module (library_name == folder name)
    test/                    # testbenches (tb_<name>.vhd, ...) for this module
    doc/                     # req/proposal/rendered docs for this module
    module_<name>.py         # optional: subclass of tsfpga.module.BaseModule
    readme.rst               # optional, hdl-modules convention
```

- The **library name VUnit sees is the folder name**, not `work` and not
  anything declared inside the VHDL itself. `get_modules()` maps
  `modules/<name>/` → `module.library_name == "<name>"`.
- `src/` and `test/` are both compiled into that same one library per
  module — there is no separate library for tests.
- `module_<name>.py` is entirely optional. A module with no such file still
  gets picked up by `get_modules()`; it just has no custom `setup_vunit`
  (i.e. no per-test generic matrices/`pre_config`/`post_check` — VUnit's
  automatic testbench discovery from `test_runner_setup(` still applies).

## 2. `module_<name>.py` / `BaseModule`

```python
from __future__ import annotations
from typing import TYPE_CHECKING
from tsfpga.module import BaseModule

if TYPE_CHECKING:
    from vunit.ui import VUnit

class Module(BaseModule):
    def setup_vunit(self, vunit_proj: VUnit, **kwargs) -> None:
        tb = vunit_proj.library(self.library_name).test_bench("tb_<name>")
        for test in tb.get_tests():
            self.add_vunit_config(
                test=test,
                name="cfg_name",
                generics={...},
                pre_config=pre_config,   # optional
                post_check=post_check,   # optional
            )
```

- The class **must be named `Module`** (that's what `get_modules()` imports
  by convention) and subclass `BaseModule`.
- `self.library_name` is the folder name — use it, don't hardcode the
  string, so renaming the folder doesn't silently desync from a stale
  literal.
- `add_vunit_config` is the module-framework's wrapper around VUnit's own
  `test.add_config(...)` — same `generics`/`pre_config`/`post_check`
  semantics as `Vunit.md` §2 documents for plain VUnit, just reached via
  `self.` instead of the raw `vunit_proj` object.
- Keep any Python reference/golden model (e.g. `canny_model.py`) importable
  from both `run.py`'s process and the module's own `module_<name>.py` —
  put it next to `run.py` (repo root) or in a real installed/`PYTHONPATH`
  location, not nested inside a module folder that only that one module's
  `sys.path` would see.
- Closures over a `for` loop variable inside `setup_vunit` (e.g. looping
  over multiple stall configs) must **bind the loop variable as a default
  arg** (`def pre_config(..., _stall_name: str = stall_name): ...`), same
  classic Python late-binding trap as anywhere else — otherwise every
  config's `pre_config`/`post_check` closes over the loop's *final* value.

## 3. `run.py` with `get_modules()`

```python
from pathlib import Path
from tsfpga.module import get_modules
from vunit import VUnit

ROOT = Path(__file__).resolve().parent

vu = VUnit.from_argv()
vu.add_vhdl_builtins()
vu.add_osvvm()                      # needed if anything uses OSVVM RandomPType
vu.add_verification_components()    # needed if anything uses VUnit VCs / hdl-modules bfm

modules = get_modules(modules_folder=ROOT / "modules")

# Dependency-only modules (e.g. a vendored library like hdl-modules): add
# their source/sim files but do not re-run their own testbenches here.
modules_no_test = get_modules(
    modules_folder=ROOT / "some_vendor_lib" / "modules",
    names_avoid={"some_module_that_wont_compile_here"},
)

for module in modules + modules_no_test:
    vunit_library = vu.add_library(module.library_name, allow_duplicate=True)
    simulate_this_module = module not in modules_no_test

    for hdl_file in module.get_simulation_files(include_tests=simulate_this_module):
        vunit_library.add_source_file(hdl_file.path)

    if simulate_this_module:
        module.setup_vunit(vunit_proj=vu)

vu.main()
```

Key points, each a real gotcha hit while building this project:

- **`add_osvvm()` and `add_verification_components()` are not implied by
  `add_vhdl_builtins()`.** If any reused module (e.g. hdl-modules'
  `bfm`/`axi_stream_fifo`) or any testbench needs OSVVM's `RandomPType` or
  VUnit's verification-component packages (`bus_master_pkg`,
  `axi_slave_pkg`, `com_pkg`, ...), both must be called explicitly *before*
  the module loop, or compilation fails deep inside a dependency with a
  confusing "package not found" error that doesn't obviously point back to
  a missing `run.py` call.
- **`allow_duplicate=True` on `add_library`** — needed because
  `get_modules()` can be called more than once against different
  `modules_folder` roots (own modules + a vendored dependency tree), and
  nothing guarantees the library-name sets are disjoint in general; safe to
  always pass it in a multi-`get_modules()`-call `run.py`.
- **`names_avoid={...}`** excludes specific module folders by name from a
  `get_modules()` scan — the tool for excluding a vendored module that
  doesn't compile in this project's environment (e.g. an entity that
  needs a real vendor `unisim`/`unimacro` library GHDL doesn't provide),
  without having to fork or edit the vendored tree.
- **`include_tests=False` for dependency-only modules**: pulls in only
  `src/` (and non-test `sim/`), not `test/` — use this for a vendored
  library whose own testbenches are that library's own concern, not
  something this project's `run.py` should re-run every time.
- **Cross-module instantiation inside RTL must use
  `library <other_module_name>; entity <other_module_name>.<entity_name>`**,
  never `entity work.<entity_name>`. Because every module folder becomes
  its own same-named VUnit library (not a shared `work`), a structural
  top-level module wiring together several sibling modules needs an
  explicit `library`/`entity` clause per instantiated sibling. This is the
  single most likely first mistake when writing a first structural
  top-level in this convention — the compile error (unresolved component/
  entity) doesn't obviously point at "wrong library prefix" as the cause.
- **Keep `run.py` (not `build.py` or any other name)** if any MCP tooling
  in the flow (e.g. `vunit-mcp`, `VUNIT_MCP_RUN_SCRIPT`) defaults to
  looking for `run.py` specifically.

## 4. Other framework-adjacent gotchas found in practice

- **hdl-modules' `fifo.vhd` asserts the RAM depth must be a power of two**
  at elaboration/run time — not documented anywhere obvious in its own
  module doc. If a project's own sizing logic derives a FIFO depth from a
  non-power-of-two quantity (e.g. `2*image_width + margin`), round it up
  with a local `next_pow2` helper before passing it as a generic to any
  reused `fifo`/`axi_stream_fifo` instance.
- **OSVVM's `RandSlv(Size)` returns a `(1 to Size)`-ranged
  `std_logic_vector`**, not `(Size-1 downto 0)` — reindex explicitly
  (`v(1 to Size)` or a `to_downto`-style conversion) before using it as if
  it were a normal descending-range vector; assigning it directly to a
  `(Size-1 downto 0)` signal is a range mismatch, not silently reinterpreted.
- **VUnit's `check_axi_stream`/`axi_stream_slave` silently skips TDATA
  comparison when `data_length` is not a multiple of 8** — the check
  loop is gated by a `tkeep`-derived byte range that never executes a body
  for a data width like 11 or 2 bits. A testbench relying on this check for
  a narrow, non-byte-multiple `tdata` width will pass even when the DUT's
  data is wrong; verify narrow-width AXI-Stream checks with an
  independent assertion or a golden-model comparison instead of trusting
  `check_axi_stream` alone in that case.
- **Golden-model / reference-model integration tests for a pipeline with
  cumulative per-stage border effects**: size the stimulus comfortably
  past twice the cumulative border width, and inspect the model's own
  precomputed "expected" output for non-trivial content before trusting a
  pass — a too-small frame can make "expected" vacuously all-zero/trivial,
  passing "for free" without ever comparing a real value. See `Vunit.md`
  §"Python reference models" for the general `pre_config`/`post_check`
  pattern this applies to.

## 5. Known MCP-toolchain limitation (as of this project)

`vunit-mcp` cannot currently drive a `tsfpga`-module-based `run.py`: its
own Python subprocess does not have `tsfpga` importable
(`ModuleNotFoundError: No module named 'tsfpga.module'`), even when the
project's own `python3 run.py` works fine locally. Confirmed by direct
reproduction, not just inferred. Until the `vunit-mcp` server's Python
environment is made to match the target project's (i.e. has `tsfpga`,
and by extension anything else the project's `run.py` imports, installed
alongside VUnit — or is pointed at the project's own interpreter/venv),
fall back to local `python3 run.py` for compile/test/regression on any
tsfpga-module-based project. This is an environment/packaging gap in the
`vunit-mcp` server, not a bug in the module-framework itself.
