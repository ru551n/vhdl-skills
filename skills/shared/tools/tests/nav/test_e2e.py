"""vhdl-tools nav against the fixture project and a real vhdl_ls."""

from __future__ import annotations

from vhdl_tools import cli


def test_nav_group_is_registered(capsys):
    assert "nav" in cli.GROUPS


def test_find_exact_filters_fuzzy_hits(nav):
    code, out = nav("find", "--name", "leaf")
    assert code == 0
    assert out.splitlines() == ["entity leaf  [lib_a]  lib_a/leaf.vhd:6", "1 hit"]


def test_find_same_name_in_two_libraries(nav):
    code, out = nav("find", "--name", "dup")
    assert code == 0
    assert "[lib_a]  lib_a/dup.vhd:1" in out
    assert "[lib_b]  lib_b/dup.vhd:1" in out
    assert out.rstrip().endswith("2 hits")


def test_find_substring_stays_in_project(nav):
    code, out = nav("find", "--name", "lea", "--substring")
    assert code == 0
    assert "entity leaf" in out
    assert "Vital" not in out


def test_find_nothing_is_not_an_error(nav):
    code, out = nav("find", "--name", "nothing_here")
    assert code == 0
    assert out.startswith("No declaration named nothing_here in the library map (2 libraries: lib_a, lib_b)")


def test_find_standard_library_name(nav):
    code, out = nav("find", "--name", "std_ulogic", "--kind", "type")
    assert code == 0
    assert "std_logic_1164" in out.lower()


def test_def_by_name(nav):
    code, out = nav("def", "--name", "lib_a.leaf", "--context", "2")
    assert code == 0
    assert out.splitlines() == [
        "entity leaf  [lib_a]  lib_a/leaf.vhd:6",
        "6  entity leaf is",
        "7    generic (",
        "8      width : positive := 8",
    ]


def test_def_name_case_insensitive(nav):
    code, out = nav("def", "--name", "Lib_A.LEAF", "--context", "0")
    assert code == 0
    assert out.splitlines()[0] == "entity leaf  [lib_a]  lib_a/leaf.vhd:6"


def test_def_by_pos(nav, fixture_dir, monkeypatch):
    monkeypatch.chdir(fixture_dir)
    code, out = nav("def", "--pos", "lib_b/top.vhd:28:29", "--context", "0")
    assert code == 0
    assert out.splitlines()[0] == "entity mid  [lib_b]  lib_b/mid.vhd:6"


def test_def_from_subdirectory_without_config(nav, fixture_dir, monkeypatch):
    monkeypatch.chdir(fixture_dir / "lib_b")
    code, out = nav("def", "--pos", "top.vhd:17:30", "--context", "0", config=None)
    assert code == 0
    assert out.splitlines()[0] == "entity leaf  [lib_a]  lib_a/leaf.vhd:6"


def test_def_ambiguous(nav):
    code, out = nav("def", "--name", "dup")
    assert code == 1
    assert out.startswith("Error: dup is ambiguous")
    assert "lib_a/dup.vhd:1" in out and "lib_b/dup.vhd:1" in out


def test_def_needs_name_or_pos(nav):
    code, out = nav("def")
    assert code == 1
    assert "exactly one of --name or --pos" in out


def test_refs_skip_declaration_lines(nav):
    code, out = nav("refs", "--name", "lib_a.leaf")
    assert code == 0
    assert out.splitlines() == [
        "lib_b/mid.vhd",
        "     16:28  leaf_inst : entity lib_a.leaf",
        "lib_b/top.vhd",
        "     17:28  leaf_inst : entity lib_a.leaf",
        "2 references in 2 files",
    ]


def test_refs_with_declaration(nav):
    code, out = nav("refs", "--name", "lib_a.leaf", "--with-decl")
    assert code == 0
    assert "architecture rtl of leaf is" in out
    assert out.rstrip().endswith("4 references in 3 files")


def test_show_entity(nav):
    code, out = nav("show", "--name", "leaf")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "entity leaf  [lib_a]  lib_a/leaf.vhd:6"
    assert "    q : out std_ulogic_vector(width - 1 downto 0)" in lines
    assert lines[-1] == "end entity;"


def test_show_package_lists_declarations(nav):
    code, out = nav("show", "--name", "pkg_a")
    assert code == 0
    assert out.splitlines() == [
        "package pkg_a  [lib_a]  lib_a/pkg_a.vhd:4",
        "  type state_t  L5",
        "  function add1[NATURAL return NATURAL]  L6",
    ]


def test_show_function(nav):
    code, out = nav("show", "--name", "add1")
    assert code == 0
    assert out.splitlines()[0] == "function add1[NATURAL return NATURAL]  [lib_a.pkg_a]  lib_a/pkg_a.vhd:6"
    assert "return natural" in out


def test_warning_for_library_without_files(nav, fixture_copy):
    config = fixture_copy / "vhdl_ls.toml"
    config.write_text(config.read_text() + 'ghost.files = ["nope/*.vhd"]\n')
    code, out = nav("find", "--name", "leaf", config=fixture_copy)
    assert code == 0
    assert out.startswith("Warning: no files match the globs of ghost")
    assert "entity leaf  [lib_a]" in out


def test_missing_config_is_a_clean_error(nav_cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out = nav_cli("find", "--name", "leaf", config=None)
    assert code == 1
    assert out.startswith("Error: No vhdl_ls.toml in")
    assert "vhdl-tools nav init" in out


def test_missing_vhdl_ls_is_a_clean_error(nav_cli, tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_LS", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    code, out = nav_cli("find", "--name", "leaf")
    assert code == 1
    assert out.strip() == (
        "Error: vhdl_ls not found (checked $VHDL_LS, PATH, ~/.cargo/bin). Install: cargo install vhdl_ls"
    )
