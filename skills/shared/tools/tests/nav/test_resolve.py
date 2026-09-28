"""--name and --pos resolution, with a stand-in for the LSP session."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from vhdl_tools.nav import NavError
from vhdl_tools.nav.resolve import (
    Position,
    existing_file,
    find_hits,
    hit_at,
    identifier_at,
    not_found_message,
    parse_pos,
    position_params,
    resolve_one,
)
from vhdl_tools.nav.symbols import Hit

ROOT = Path("/proj")


def sym(name: str, container: str, file: str, line: int, col: int = 7) -> dict:
    return {
        "name": name,
        "kind": 2,
        "containerName": container,
        "location": {
            "uri": f"file:///proj/{file}",
            "range": {"start": {"line": line, "character": col}, "end": {"line": line, "character": col + 3}},
        },
    }


class FakeSession:
    def __init__(self, symbols: list[dict]) -> None:
        self.symbols = symbols
        self.queries: list[str] = []

    def request(self, method: str, params: Any) -> Any:
        assert method == "workspace/symbol"
        self.queries.append(params["query"])
        return self.symbols


SYMBOLS = [
    sym("entity 'leaf'", "lib_a", "lib_a/leaf.vhd", 5),
    sym("constant 'VitalDefaultPortFlag'", "ieee.Vital_Memory", "ieee/memory_p.vhdl", 318),
    sym("entity 'dup'", "lib_b", "lib_b/dup.vhd", 0),
    sym("entity 'dup'", "lib_a", "lib_a/dup.vhd", 0),
    sym("package 'pkg_a'", "lib_a", "lib_a/pkg_a.vhd", 3, 8),
    sym("package body 'pkg_a'", "lib_a", "lib_a/pkg_a.vhd", 8, 13),
    sym("instance 'leaf_inst'", "lib_b.top", "lib_b/top.vhd", 16, 2),
]


def test_find_hits_is_exact_and_sends_the_bare_identifier():
    session = FakeSession(SYMBOLS)
    found = find_hits(session, "lib_a.leaf")
    assert session.queries == ["leaf"]
    assert [(h.kind, h.name, h.library) for h in found.hits] == [("entity", "leaf", "lib_a")]
    assert not found.truncated


def test_find_hits_sorted_and_kind_filter():
    found = find_hits(FakeSession(SYMBOLS), "dup")
    assert [h.library for h in found.hits] == ["lib_a", "lib_b"]
    assert find_hits(FakeSession(SYMBOLS), "pkg_a", kind="package").hits[0].kind == "package"


def test_find_hits_substring_stays_in_own_libraries():
    found = find_hits(FakeSession(SYMBOLS), "lea", substring=True, libraries=["lib_a", "lib_b"])
    assert sorted(h.name for h in found.hits) == ["leaf", "leaf_inst"]
    assert all(h.library != "ieee" for h in found.hits)


def test_find_hits_reports_the_cap():
    many = [sym(f"signal 's{i}'", "lib_a.x", "lib_a/x.vhd", i) for i in range(200)]
    assert find_hits(FakeSession(many), "s1").truncated


def test_resolve_one_prefers_package_over_body():
    hit = resolve_one(FakeSession(SYMBOLS), "pkg_a", ROOT, ["lib_a"])
    assert (hit.kind, hit.line) == ("package", 3)


def test_resolve_one_ambiguous_lists_candidates():
    with pytest.raises(NavError) as exc:
        resolve_one(FakeSession(SYMBOLS), "dup", ROOT, ["lib_a", "lib_b"])
    message = str(exc.value)
    assert "ambiguous" in message
    assert "lib_a/dup.vhd:1" in message and "lib_b/dup.vhd:1" in message


def test_resolve_one_not_found_names_libraries():
    with pytest.raises(NavError) as exc:
        resolve_one(FakeSession(SYMBOLS), "nothing", ROOT, ["lib_a", "lib_b"])
    assert str(exc.value) == not_found_message("nothing", ["lib_a", "lib_b"])
    assert "2 libraries: lib_a, lib_b" in str(exc.value)


def test_not_found_message_shortens_long_library_lists():
    libs = [f"l{i}" for i in range(12)]
    message = not_found_message("x", libs, kind="entity")
    assert message.startswith("No entity named x ")
    assert "12 libraries: l0, l1, l2, l3, l4, l5, l6, l7, l8, l9, ..." in message


def test_hit_at_matches_location_or_falls_back():
    session = FakeSession(SYMBOLS)
    hit = hit_at(session, Path("/proj/lib_b/dup.vhd"), 0, "dup")
    assert hit.library == "lib_b"
    fallback = hit_at(session, Path("/proj/other.vhd"), 4, "dup")
    assert fallback == Hit("", "dup", "", Path("/proj/other.vhd"), 4, 0)


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "lib_b").mkdir()
    (tmp_path / "lib_b" / "top.vhd").write_text(
        "entity top is\n"
        "  leaf_inst : entity lib_a.leaf\n"
        "  -- just a comment\n"
    )
    monkeypatch.chdir(tmp_path / "lib_b")
    return tmp_path


def test_parse_pos_with_column(project):
    pos = parse_pos("top.vhd:2:28", project)
    assert pos == Position((project / "lib_b" / "top.vhd").resolve(), 1, 27)


def test_parse_pos_relative_to_root_when_not_in_cwd(project):
    pos = parse_pos("lib_b/top.vhd:1", project)
    assert (pos.line, pos.col) == (0, 7)  # 'top', skipping the keyword 'entity'


def test_parse_pos_without_column_takes_first_identifier(project):
    assert parse_pos("top.vhd:2", project).col == 2  # the label 'leaf_inst'


def test_parse_pos_not_on_identifier_shows_caret(project):
    with pytest.raises(NavError) as exc:
        parse_pos("top.vhd:2:12", project)
    assert "not on an identifier" in str(exc.value)
    assert str(exc.value).endswith("\n  " + " " * 11 + "^")


def test_parse_pos_errors(project):
    with pytest.raises(NavError, match="expected FILE:LINE"):
        parse_pos("top.vhd", project)
    with pytest.raises(NavError, match="has 3 lines"):
        parse_pos("top.vhd:9", project)
    with pytest.raises(NavError, match="no identifier"):
        parse_pos("top.vhd:3", project)
    with pytest.raises(NavError, match="no file"):
        parse_pos("gone.vhd:1", project)


def test_existing_file_and_identifier_at(project):
    path = existing_file("lib_b/top.vhd", project)
    assert path == (project / "lib_b" / "top.vhd").resolve()
    assert identifier_at(path, 1, 28) == "leaf"
    assert identifier_at(path, 1, 11) == ""


def test_position_params():
    params = position_params(Position(Path("/proj/a.vhd"), 3, 4))
    assert params == {"textDocument": {"uri": "file:///proj/a.vhd"}, "position": {"line": 3, "character": 4}}


def test_find_hits_substring_accepts_package_qualifier():
    symbols = [sym("constant 'ram_style_auto'", "common.types_pkg", "common/types_pkg.vhd", 9)]
    found = find_hits(FakeSession(symbols), "types_pkg.ram_style", substring=True, libraries=["common"])
    assert [h.name for h in found.hits] == ["ram_style_auto"]
