"""Index layout and instantiation parsing, without vhdl_ls."""

from __future__ import annotations

from vhdl_tools.nav.index import build_index, declared_text, instance_target, span
from vhdl_tools.nav.symbols import Node


def N(kind, name, line, col, start, end, children=(), detail=""):
    return Node(kind, name, detail, line, col, start, end, list(children))


def test_span():
    assert span(4, 4) == "[5]"
    assert span(4, 9) == "[5-10]"


def test_declared_text():
    assert declared_text("    clk : in std_ulogic;", 4) == "in std_ulogic"
    assert declared_text("    q : out std_ulogic_vector(width - 1 downto 0)", 4) == (
        "out std_ulogic_vector(width - 1 downto 0)"
    )
    assert declared_text("    width : positive := 8", 4) == "positive := 8"
    assert declared_text("    level : out natural range 0 to depth := 0; -- note", 4) == (
        "out natural range 0 to depth := 0"
    )
    assert declared_text("  port (a, b : in bit);", 11) == "in bit"
    assert declared_text("  process (clk)", 2) == ""


def test_instance_target_forms():
    lines = [
        "  u1 : entity lib_a.leaf",
        "    generic map (width => 8)",
        "    port map (clk => clk);",
        "  u2 : leaf port map (clk);",
        "  u3 : configuration lib.cfg_top;",
        "  u4 : entity work.mid(rtl) port map (clk);",
    ]
    assert instance_target(N("instance", "u1", 0, 2, 0, 2), lines) == ("entity", "lib_a.leaf", 0, 20)
    assert instance_target(N("instance", "u2", 3, 2, 3, 3), lines) == ("component", "leaf", 3, 7)
    assert instance_target(N("instance", "u3", 4, 2, 4, 4), lines) == ("configuration", "lib.cfg_top", 4, 25)
    assert instance_target(N("instance", "u4", 5, 2, 5, 5), lines) == ("entity", "work.mid", 5, 19)
    assert instance_target(N("instance", "u5", 0, 2, 0, 0), ["  u5"]) is None


def test_build_index():
    lines = [
        "library ieee;",
        "use ieee.std_logic_1164.all;",
        "entity e is",
        "  generic (ram_type : ram_style_t := auto);",
        "  port (clk : in std_ulogic;",
        "        q : out std_ulogic := '0');",
        "end entity;",
        "architecture a of e is",
        "  signal x, y : bit;",
        "  signal z : bit;",
        "begin",
        "  g : if true generate",
        "    u : entity work.leaf port map (clk);",
        "  end generate;",
        "  process begin wait; end process;",
        "end architecture;",
    ]
    entity = N("entity", "e", 2, 7, 2, 6, [
        N("signal", "ram_type", 3, 11, 3, 3),  # an unresolved generic type, as vhdl_ls reports it
        N("port", "clk", 4, 8, 4, 4, detail=": in"),
        N("port", "q", 5, 8, 5, 5, detail=": out"),
    ])
    arch = N("architecture", "a", 7, 13, 7, 15, [
        N("signal", "x", 8, 9, 8, 8),
        N("signal", "y", 8, 12, 8, 8),
        N("signal", "z", 9, 9, 9, 9),
        N("generate", "g", 11, 2, 11, 13, [N("instance", "u", 12, 4, 12, 12)]),
        N("process", "", 14, 2, 14, 14, [N("", "if statement", 14, 10, 14, 14)]),
    ])
    assert build_index("e.vhd", [entity, arch], lines) == "\n".join([
        "e.vhd  16 lines",
        "context [1-2]: ieee.std_logic_1164.all",
        "entity e [3-7]",
        "  generics:",
        "    ram_type : ram_style_t := auto [4]",
        "  ports:",
        "    clk : in std_ulogic [5]",
        "    q : out std_ulogic [6]",
        "architecture a of e [8-16]",
        "  signals: x, y [9]; z [10]",
        "  generate g [12-14]",
        "    instance u : entity work.leaf [13]",
        "  process [15]",
    ])
