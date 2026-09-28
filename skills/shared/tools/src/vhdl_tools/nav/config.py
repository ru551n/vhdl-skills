"""The project's vhdl_ls.toml: find it, read its libraries, check them, write one.

nav never edits an existing vhdl_ls.toml. Globs resolve relative to the file's
directory with ``**`` recursive, as vhdl_lang does.
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from vhdl_tools.nav import NavError

CONFIG_NAME = "vhdl_ls.toml"

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def find_config(start: Path, explicit: str | None = None) -> Path:
    """``--config`` (a vhdl_ls.toml or a directory holding one), else the
    nearest vhdl_ls.toml in ``start`` or a parent."""
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_dir():
            path = path / CONFIG_NAME
        if path.name != CONFIG_NAME or not path.is_file():
            raise NavError(
                f"--config {explicit}: expected a {CONFIG_NAME} file or a directory holding one"
            )
        return path.resolve()
    start = start.resolve()
    ignored = None
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            if _catch_all(directory):
                ignored = candidate
                continue
            return candidate
    skipped = (
        f" ({ignored} was ignored: a map in your home directory or / covers every "
        f"VHDL file below it, which makes each lookup slow; pass --config {ignored} "
        "to use it anyway.)"
        if ignored
        else ""
    )
    raise NavError(
        f"No {CONFIG_NAME} in {start} or any parent directory.{skipped} "
        "Create one: vhdl-tools nav init"
    )


def _catch_all(directory: Path) -> bool:
    """A map here would cover every VHDL file on the machine (or the user's)."""
    directory = directory.resolve()
    return directory == Path.home().resolve() or directory == Path(directory.anchor)


def read_libraries(config: Path) -> dict[str, list[str]]:
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise NavError(f"cannot read {config}: {exc}") from exc
    libraries = data.get("libraries", {})
    return {
        name: [str(pattern) for pattern in spec.get("files", [])]
        for name, spec in libraries.items()
        if isinstance(spec, dict)
    }


def library_files(config: Path, patterns: list[str]) -> list[Path]:
    files: set[Path] = set()
    for pattern in patterns:
        pattern = os.path.expandvars(os.path.expanduser(pattern))
        if not os.path.isabs(pattern):
            pattern = str(config.parent / pattern)
        files.update(Path(p) for p in glob.glob(pattern, recursive=True) if os.path.isfile(p))
    return sorted(files)


def empty_libraries(config: Path, libraries: dict[str, list[str]]) -> list[str]:
    return [name for name, patterns in libraries.items() if not library_files(config, patterns)]


def _has_vhdl(directory: Path) -> bool:
    return any(directory.rglob("*.vhd")) or any(directory.rglob("*.vhdl"))


def _key(name: str) -> str:
    return name if _BARE_KEY.fullmatch(name) else json.dumps(name)


def write_init(directory: Path, layout: str = "auto") -> tuple[Path, list[str]]:
    """Write ``directory/vhdl_ls.toml`` listing the project's own libraries."""
    if not directory.is_dir():
        raise NavError(f"no directory {directory}")
    if _catch_all(directory):
        raise NavError(
            f"nav init does not write a map in your home directory or / ({directory}): "
            "it would cover every VHDL file below it. Run it in the project's root."
        )
    target = directory / CONFIG_NAME
    if target.exists():
        raise NavError(f"{target} already exists; nav init never overwrites it")
    modules_dir = directory / "modules"
    modules = (
        sorted(d for d in modules_dir.iterdir() if d.is_dir() and _has_vhdl(d))
        if modules_dir.is_dir()
        else []
    )
    if layout == "auto":
        layout = "tsfpga" if modules else "flat"
    if layout == "tsfpga":
        if not modules:
            raise NavError(
                f"--layout tsfpga: no modules/<name>/ directories with VHDL files in {directory}"
            )
        libraries = {
            m.name: [f"modules/{m.name}/**/*.vhd", f"modules/{m.name}/**/*.vhdl"] for m in modules
        }
    else:
        if not _has_vhdl(directory):
            raise NavError(f"no .vhd or .vhdl files under {directory}")
        libraries = {"lib": ["**/*.vhd", "**/*.vhdl"]}
    lines = [
        "# Written by vhdl-tools nav init. The standard libraries (std, ieee) come",
        "# from vhdl_ls's library directory; add third-party libraries by hand.",
        "[libraries]",
    ]
    for name, patterns in libraries.items():
        lines.append(f"{_key(name)}.files = [{', '.join(json.dumps(p) for p in patterns)}]")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target, list(libraries)
