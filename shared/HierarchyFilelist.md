# VHDL Hierarchy and Compile-Order Filelist

## Goal

Build a complete VHDL source set for a top entity, including packages and reusable `lib/` dependencies, in dependency-safe compile order.

## Search roots

1. `rtl/`
2. `lib/`
3. project-specific source folders explicitly named by the user

## Procedure

1. Locate the top entity source.
2. Read its context clauses and architecture.
3. Collect referenced packages (`use work.<pkg>.all`) and direct entity instantiations (`entity work.<name>`).
4. Recursively resolve every project package/entity.
5. Detect cycles or unresolved dependencies and stop with a clear report.
6. Emit files in compile order:
   - packages before package bodies/users
   - leaf entities before parent entities when practical
   - top entity last
7. Preserve library assignment if the project uses libraries other than `work`.

## Filelist format

Default `rtl.f` contains one VHDL path per line, dependency-first:

```text
../../lib/common/common_pkg.vhd
../../lib/foo_fifo/foo_fifo.vhd
../../rtl/foo_ctrl.vhd
../../rtl/foo_proc.vhd
../../rtl/foo_top.vhd
```

## GHDL

Analyze in filelist order:

```bash
while read -r f; do
  ghdl -a --std=08 "$f" || exit 1
done < rtl.f
```

Then elaborate the top:

```bash
ghdl -e --std=08 <top_entity>
```

## MCP-first dependency discovery

If `vunit-mcp` is available and the project has a VUnit `run.py`:

1. Call `vunit_status`.
2. Use `vunit_list_files` for project compile order.
3. For one testcase, use `vunit_test_dependencies` for the minimal ordered dependency set.
4. Only use the manual dependency procedure above when VUnit is unavailable or the sources are not registered in the project.

If `corvidex-mcp` is available, it may be used to locate package/entity sources, but the authoritative VUnit compile order should still come from `vunit_list_files` for a VUnit project.
