"""Finding, reading, checking and writing vhdl_ls.toml."""

from __future__ import annotations

from pathlib import Path

import pytest

from vhdl_tools.nav import NavError
from vhdl_tools.nav.config import (
    empty_libraries,
    find_config,
    library_files,
    read_libraries,
    write_init,
)


def _touch(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_find_config_searches_upward(tmp_path):
    config = _touch(tmp_path / "vhdl_ls.toml")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert find_config(deep) == config.resolve()


def test_find_config_explicit_file_or_directory(tmp_path):
    config = _touch(tmp_path / "proj" / "vhdl_ls.toml")
    assert find_config(tmp_path, str(config)) == config.resolve()
    assert find_config(tmp_path, str(config.parent)) == config.resolve()


def test_find_config_explicit_wrong_path(tmp_path):
    other = _touch(tmp_path / "other.toml")
    with pytest.raises(NavError, match="expected a vhdl_ls.toml"):
        find_config(tmp_path, str(other))


def test_find_config_missing_points_to_init(tmp_path):
    with pytest.raises(NavError, match="vhdl-tools nav init"):
        find_config(tmp_path)


def test_read_libraries(tmp_path):
    config = _touch(
        tmp_path / "vhdl_ls.toml",
        '[libraries]\nlib_a.files = ["a/*.vhd"]\nlib_b.files = ["b/*.vhd", "c/**/*.vhd"]\n'
        "lib_b.is_third_party = false\n",
    )
    assert read_libraries(config) == {"lib_a": ["a/*.vhd"], "lib_b": ["b/*.vhd", "c/**/*.vhd"]}


def test_read_libraries_bad_toml(tmp_path):
    config = _touch(tmp_path / "vhdl_ls.toml", "[libraries\n")
    with pytest.raises(NavError, match="cannot read"):
        read_libraries(config)


def test_library_files_relative_recursive_and_env(tmp_path, monkeypatch):
    config = _touch(tmp_path / "vhdl_ls.toml")
    a = _touch(tmp_path / "a" / "x.vhd")
    deep = _touch(tmp_path / "c" / "d" / "e" / "y.vhd")
    _touch(tmp_path / "a" / "notes.txt")
    monkeypatch.setenv("NAV_TEST_DIR", str(tmp_path / "c"))
    assert library_files(config, ["a/*.vhd"]) == [a]
    assert library_files(config, ["c/**/*.vhd"]) == [deep]
    assert library_files(config, ["$NAV_TEST_DIR/**/*.vhd"]) == [deep]
    assert library_files(config, [str(tmp_path / "a" / "*.vhd")]) == [a]


def test_empty_libraries(tmp_path):
    config = _touch(tmp_path / "vhdl_ls.toml")
    _touch(tmp_path / "a" / "x.vhd")
    libs = {"lib_a": ["a/*.vhd"], "ghost": ["nope/*.vhd"]}
    assert empty_libraries(config, libs) == ["ghost"]


def test_init_tsfpga_layout(tmp_path):
    _touch(tmp_path / "modules" / "fifo" / "src" / "fifo.vhd")
    _touch(tmp_path / "modules" / "common" / "test" / "tb.vhd")
    (tmp_path / "modules" / "empty").mkdir()
    path, names = write_init(tmp_path)
    assert path == tmp_path / "vhdl_ls.toml"
    assert names == ["common", "fifo"]
    libs = read_libraries(path)
    assert libs["fifo"] == ["modules/fifo/**/*.vhd", "modules/fifo/**/*.vhdl"]
    assert library_files(path, libs["common"]) == [tmp_path / "modules" / "common" / "test" / "tb.vhd"]


def test_init_flat_layout(tmp_path):
    _touch(tmp_path / "rtl" / "top.vhd")
    path, names = write_init(tmp_path)
    assert names == ["lib"]
    assert read_libraries(path) == {"lib": ["**/*.vhd", "**/*.vhdl"]}


def test_init_explicit_tsfpga_without_modules(tmp_path):
    _touch(tmp_path / "rtl" / "top.vhd")
    with pytest.raises(NavError, match="modules/<name>/"):
        write_init(tmp_path, "tsfpga")


def test_init_never_overwrites(tmp_path):
    _touch(tmp_path / "rtl" / "top.vhd")
    existing = _touch(tmp_path / "vhdl_ls.toml", "# mine\n")
    with pytest.raises(NavError, match="already exists"):
        write_init(tmp_path)
    assert existing.read_text() == "# mine\n"


def test_init_without_vhdl(tmp_path):
    with pytest.raises(NavError, match="no .vhd or .vhdl files"):
        write_init(tmp_path)


def test_init_missing_directory(tmp_path):
    with pytest.raises(NavError, match="no directory"):
        write_init(tmp_path / "nope")
