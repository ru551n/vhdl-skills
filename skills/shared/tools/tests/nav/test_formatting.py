"""Compact text output."""

from __future__ import annotations

from pathlib import Path

from vhdl_tools.nav.formatting import (
    CAP_NOTE,
    count,
    describe,
    format_context,
    format_hits,
    format_outline,
    format_refs,
    format_tree,
    header,
    hover_text,
    rel,
)
from vhdl_tools.nav.symbols import Hit, Node, TreeNode

ROOT = Path("/proj")


def test_count():
    assert count(1, "hit") == "1 hit"
    assert count(0, "hit") == "0 hits"
    assert count(3, "library", "libraries") == "3 libraries"


def test_rel():
    assert rel(Path("/proj/a/b.vhd"), ROOT) == "a/b.vhd"
    assert rel(Path("/elsewhere/c.vhd"), ROOT) == "/elsewhere/c.vhd"


def test_describe_and_header():
    leaf = Hit("entity", "leaf", "lib_a", Path("/proj/lib_a/leaf.vhd"), 5, 7)
    port = Hit("port", "clk", "lib_a.leaf", Path("/proj/lib_a/leaf.vhd"), 10, 4, ": in")
    add1 = Hit("function", "add1", "lib_a.pkg_a", Path("/proj/lib_a/pkg_a.vhd"), 5, 11, "[NATURAL return NATURAL]")
    assert describe(leaf) == "entity leaf"
    assert describe(port) == "port clk : in"
    assert describe(add1) == "function add1[NATURAL return NATURAL]"
    assert header(leaf, ROOT) == "entity leaf  [lib_a]  lib_a/leaf.vhd:6"


def test_format_hits_aligned():
    hits = [
        Hit("entity", "dup", "lib_a", Path("/proj/lib_a/dup.vhd"), 0, 7),
        Hit("package body", "dup", "lib_b", Path("/proj/lib_b/longer/dup.vhd"), 8, 13),
    ]
    assert format_hits(hits, ROOT) == (
        "entity dup        [lib_a]  lib_a/dup.vhd:1\n"
        "package body dup  [lib_b]  lib_b/longer/dup.vhd:9\n"
        "2 hits"
    )


def test_format_hits_truncated():
    assert format_hits([], ROOT, truncated=True) == f"0 hits\n{CAP_NOTE}"


def test_format_context(tmp_path):
    source = tmp_path / "leaf.vhd"
    source.write_text("\n".join(f"line {n}" for n in range(1, 21)) + "\n")
    assert format_context(source, 9, 2, "TITLE") == "TITLE\n10  line 10\n11  line 11\n12  line 12"
    assert format_context(source, 19, 5, "T") == "T\n20  line 20"


def test_format_refs_grouped(tmp_path):
    a = tmp_path / "a.vhd"
    b = tmp_path / "b.vhd"
    a.write_text("x\n  u1 : entity lib.leaf\n")
    b.write_text("  u2 : entity work.leaf\n")
    text = format_refs([(b, 0, 16), (a, 1, 15)], tmp_path)
    assert text == (
        "a.vhd\n"
        "      2:16  u1 : entity lib.leaf\n"
        "b.vhd\n"
        "      1:17  u2 : entity work.leaf\n"
        "2 references in 2 files"
    )


def test_hover_text_shapes():
    marked = {"contents": {"language": "vhdl", "value": "entity leaf is\nend entity;"}}
    markup = {"contents": {"kind": "markdown", "value": "```vhdl\nfunction f\n```"}}
    listed = {"contents": ["a", {"language": "vhdl", "value": "b"}]}
    assert hover_text(marked) == "entity leaf is\nend entity;"
    assert hover_text(markup) == "function f"
    assert hover_text(listed) == "a\nb"
    assert hover_text(None) == ""


def test_format_outline_skips_parameters_and_literals():
    nodes = [
        Node("package", "pkg_a", "", 3, 8, 3, 6, [
            Node("type", "state_t", "", 4, 7, 4, 4, [Node("literal", "idle", "[return state_t]", 4, 18, 4, 4)]),
            Node("function", "add1", "[NATURAL return NATURAL]", 5, 11, 5, 5, [Node("parameter", "x", "", 5, 16, 5, 5)]),
            Node("port", "clk", ": in", 7, 4, 7, 7),
        ])
    ]
    assert format_outline(nodes) == [
        "package pkg_a  L4",
        "  type state_t  L5",
        "  function add1[NATURAL return NATURAL]  L6",
        "  port clk : in  L8",
    ]


def test_format_tree():
    top = Hit("entity", "top", "lib_b", Path("/proj/lib_b/top.vhd"), 5, 7)
    leaf = Hit("entity", "leaf", "lib_a", Path("/proj/lib_a/leaf.vhd"), 5, 7)
    tree = TreeNode("", "top", top, children=[
        TreeNode("u_leaf", "lib_a.leaf", leaf),
        TreeNode("u_comp", "leaf", leaf, "component"),
        TreeNode("u_bad", "work.gone", None, "unresolved"),
    ])
    assert format_tree(tree, ROOT) == [
        "entity top  [lib_b]  lib_b/top.vhd:6",
        "  u_leaf : entity leaf  [lib_a]  lib_a/leaf.vhd:6",
        "  u_comp : entity leaf  [lib_a]  lib_a/leaf.vhd:6  (component)",
        "  u_bad : work.gone  (unresolved)",
    ]
