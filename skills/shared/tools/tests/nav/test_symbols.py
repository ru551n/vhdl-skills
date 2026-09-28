"""Parsing vhdl_ls symbol replies and matching names."""

from __future__ import annotations

from pathlib import Path

from vhdl_tools.nav.symbols import (
    Hit,
    hit_from_symbol,
    kind_matches,
    locations,
    matches_name,
    nodes_from_document_symbols,
    parse_symbol_name,
    prefer_declarations,
    split_name,
)


def _hit(kind: str, name: str, container: str, line: int = 0) -> Hit:
    return Hit(kind, name, container, Path(f"/p/{name}.vhd"), line, 7)


def test_parse_quoted_names():
    assert parse_symbol_name("entity 'fifo'") == ("entity", "fifo", "")
    assert parse_symbol_name("package body 'axi_pkg'") == ("package body", "axi_pkg", "")
    assert parse_symbol_name("record type 'axi_m2s_r_t'") == ("record type", "axi_m2s_r_t", "")
    assert parse_symbol_name("port 'clk' : in") == ("port", "clk", ": in")


def test_parse_subprograms_and_literals():
    assert parse_symbol_name("function add1[NATURAL return NATURAL]") == (
        "function",
        "add1",
        "[NATURAL return NATURAL]",
    )
    assert parse_symbol_name("procedure WRITELINE[TEXT, LINE]") == (
        "procedure",
        "WRITELINE",
        "[TEXT, LINE]",
    )
    assert parse_symbol_name("idle[return state_t]") == ("literal", "idle", "[return state_t]")
    assert parse_symbol_name("something odd") == ("", "something odd", "")
    assert parse_symbol_name("if statement") == ("", "if statement", "")


def test_parse_unlabelled_process():
    assert parse_symbol_name("process") == ("process", "", "")


def test_hit_from_symbol():
    hit = hit_from_symbol(
        {
            "name": "entity 'fifo'",
            "kind": 2,
            "containerName": "fifo",
            "location": {
                "uri": "file:///proj/modules/fifo/src/fifo%20x.vhd",
                "range": {"start": {"line": 64, "character": 7}, "end": {"line": 64, "character": 11}},
            },
        }
    )
    assert hit == Hit("entity", "fifo", "fifo", Path("/proj/modules/fifo/src/fifo x.vhd"), 64, 7)
    assert hit.library == "fifo"
    nested = Hit("type", "state_t", "lib_a.pkg_a", Path("/p"), 4, 7)
    assert nested.library == "lib_a"


def test_nodes_from_document_symbols():
    def rng(a: int, b: int) -> dict:
        return {"start": {"line": a, "character": 2}, "end": {"line": b, "character": 9}}

    nodes = nodes_from_document_symbols(
        [
            {
                "name": "architecture 'rtl'",
                "range": rng(13, 34),
                "selectionRange": rng(13, 13),
                "children": [
                    {"name": "instance 'leaf_inst'", "range": rng(16, 24), "selectionRange": rng(16, 16)},
                ],
            }
        ]
    )
    assert len(nodes) == 1
    arch = nodes[0]
    assert (arch.kind, arch.name, arch.line, arch.start_line, arch.end_line) == ("architecture", "rtl", 13, 13, 34)
    inst = arch.children[0]
    assert (inst.kind, inst.name, inst.line, inst.col, inst.end_line) == ("instance", "leaf_inst", 16, 2, 24)
    assert nodes_from_document_symbols(None) == []


def test_locations_accepts_every_shape():
    loc = {"uri": "file:///a/x.vhd", "range": {"start": {"line": 5, "character": 7}, "end": {"line": 5, "character": 9}}}
    link = {
        "targetUri": "file:///a/y.vhd",
        "targetRange": {"start": {"line": 0, "character": 0}, "end": {"line": 9, "character": 0}},
        "targetSelectionRange": {"start": {"line": 3, "character": 1}, "end": {"line": 3, "character": 4}},
    }
    assert locations(loc) == [(Path("/a/x.vhd"), 5, 7)]
    assert locations([loc, link]) == [(Path("/a/x.vhd"), 5, 7), (Path("/a/y.vhd"), 3, 1)]
    assert locations(None) == []
    assert locations([]) == []


def test_split_name():
    assert split_name("fifo") == (None, "fifo")
    assert split_name("fifo.fifo") == ("fifo", "fifo")
    assert split_name("lib_a.pkg_a.add1") == ("lib_a.pkg_a", "add1")
    assert split_name("work.mid") == (None, "mid")
    assert split_name("WORK.mid") == (None, "mid")


def test_kind_matches():
    assert kind_matches("entity", "entity")
    assert kind_matches("record type", "type")
    assert kind_matches("array type", "TYPE")
    assert not kind_matches("package body", "package")
    assert not kind_matches("subtype", "type")


def test_matches_name_exact_and_qualified():
    leaf = _hit("entity", "leaf", "lib_a")
    add1 = _hit("function", "add1", "lib_a.pkg_a")
    assert matches_name(leaf, "leaf")
    assert matches_name(leaf, "lib_a.leaf")
    assert matches_name(leaf, "work.leaf")
    assert not matches_name(leaf, "lib_b.leaf")
    assert not matches_name(leaf, "lea")
    assert matches_name(add1, "lib_a.pkg_a.add1")
    assert matches_name(add1, "lib_a.add1")


def test_matches_name_is_case_insensitive():
    leaf = _hit("entity", "leaf", "lib_a")
    assert matches_name(leaf, "LEAF")
    assert matches_name(leaf, "Lib_A.Leaf")
    upper = _hit("type", "SEVERITY_LEVEL", "std.standard")
    assert matches_name(upper, "severity_level")


def test_prefer_declarations_drops_matching_bodies_only():
    pkg = _hit("package", "pkg_a", "lib_a", 3)
    body = _hit("package body", "pkg_a", "lib_a", 8)
    other_body = _hit("package body", "pkg_b", "lib_a", 1)
    assert prefer_declarations([pkg, body]) == [pkg]
    assert prefer_declarations([body]) == [body]
    assert prefer_declarations([pkg, other_body]) == [pkg, other_body]
