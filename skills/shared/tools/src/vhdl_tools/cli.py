"""``vhdl-tools <group> <command> [options]`` — one subcommand per tool function.

Options are generated from each tool's pydantic input model (or its plain
parameters): ``snake_case`` -> ``--kebab-case``, bools as ``--x/--no-x``,
lists as ``--x A B`` (repeatable), dicts as a JSON string. ``--json-input``
takes the whole input as JSON; explicit flags override its keys.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import sys
import types
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ValidationError, create_model
from pydantic_core import PydanticUndefined

from .registry import Tool, ToolRegistry, file_lock

#: group -> (tool module, tool-name prefix, one-line help)
GROUPS = {
    "vunit": ("vhdl_tools.vunit.server", "vunit_", "VUnit projects (run.py)"),
    "synth": (
        "vhdl_tools.synth.server",
        "tsfpga_",
        "Yosys+GHDL synthesis and tsfpga project builds",
    ),
    "wave": ("vhdl_tools.wave.server", "peeper_", "VCD/FST waveform measurements"),
    "vivado": (
        "vhdl_tools.vivado.server",
        "vivado_",
        "Query a built Vivado design (.dcp) through a persistent Vivado",
    ),
}


def input_model(fn: Any) -> tuple[type[BaseModel], bool]:
    """The pydantic model for a tool's input, and whether the tool takes it
    as a single ``input`` argument (else its fields are keyword params)."""
    hints = get_type_hints(fn)
    params = list(inspect.signature(fn).parameters.values())
    if len(params) == 1 and params[0].name == "input":
        model = hints["input"]
        if isinstance(model, type) and issubclass(model, BaseModel):
            return model, True
    fields: dict[str, Any] = {
        p.name: (hints[p.name], ... if p.default is p.empty else p.default)
        for p in params
    }
    return create_model(f"{fn.__name__}_input", **fields), False


def _strip_optional(ann: Any) -> Any:
    if get_origin(ann) in (Union, types.UnionType):
        args = [a for a in get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return ann


class _ExtendSplitCommas(argparse.Action):
    """`--x a b`, `--x a,b` and `--x a --x b` all give [a, b]: agents write a list
    every one of those ways."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        items = list(getattr(namespace, self.dest, None) or [])
        items += [p.strip() for v in values for p in v.split(",") if p.strip()]
        setattr(namespace, self.dest, items)


def _add_option(parser: argparse.ArgumentParser, name: str, field: Any) -> None:
    ann = _strip_optional(field.annotation)
    origin = get_origin(ann)
    kwargs: dict[str, Any] = {"dest": name, "default": argparse.SUPPRESS}
    if field.default_factory is not None:
        default: Any = field.default_factory()
    else:
        default = field.default
    help_text = field.description or ""
    if default is PydanticUndefined:
        help_text += " [required]"
    elif default not in (None, [], {}):
        help_text += f" [default: {default}]"
    kwargs["help"] = help_text.strip().replace("%", "%%")
    if ann is bool:
        kwargs["action"] = argparse.BooleanOptionalAction
    elif origin is list and get_args(ann) == (str,):
        kwargs.update(nargs="+", action=_ExtendSplitCommas)
    elif origin is list:
        kwargs.update(nargs="+", action="extend")
    elif origin is dict or (isinstance(ann, type) and issubclass(ann, BaseModel)):
        kwargs.update(type=json.loads, metavar="JSON")
    elif origin is Literal:
        kwargs["choices"] = [str(a) for a in get_args(ann)]
    parser.add_argument("--" + name.replace("_", "-"), **kwargs)


def _add_commands(
    group: argparse.ArgumentParser, registry: ToolRegistry, prefix: str
) -> None:
    commands = group.add_subparsers(dest="command", required=True, metavar="command")
    for tool_name, tool in registry.tools.items():
        doc = inspect.getdoc(tool.fn) or ""
        cmd = commands.add_parser(
            tool_name.removeprefix(prefix).replace("_", "-"),
            help=doc.splitlines()[0] if doc else None,
            description=doc,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        model, _ = input_model(tool.fn)
        for name, field in model.model_fields.items():
            _add_option(cmd, name, field)
        cmd.add_argument(
            "--json-input",
            dest="_json_input",
            type=json.loads,
            metavar="JSON",
            default={},
            help="The whole input as a JSON object; explicit options override it.",
        )
        cmd.set_defaults(_tool=tool)


def run_tool(registry: ToolRegistry, tool: Tool, data: dict[str, Any]) -> int:
    model, wrapped = input_model(tool.fn)
    try:
        validated = model.model_validate(data)
    except ValidationError as exc:
        print(f"Error: invalid input: {exc}", file=sys.stderr)
        return 2
    if wrapped:
        kwargs = {"input": validated}
    else:
        kwargs = {name: getattr(validated, name) for name in model.model_fields}
    with file_lock(tool):
        result = tool.fn(**kwargs)
        if inspect.iscoroutine(result):
            result = asyncio.run(result)
    print(result)
    return 1 if registry.is_error(result) else 0


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = argparse.ArgumentParser(
        prog="vhdl-tools",
        description="VUnit, synthesis, waveform and Vivado design-query tools for HDL projects.",
    )
    groups = parser.add_subparsers(dest="group", required=True, metavar="group")
    registry: ToolRegistry | None = None
    for group_name, (module, prefix, help_text) in GROUPS.items():
        group = groups.add_parser(group_name, help=help_text, description=help_text)
        # Import only the requested group: the others pull in heavy deps.
        if argv and argv[0] == group_name:
            registry = importlib.import_module(module).tools
            group.description = f"{help_text}\n\n{registry.instructions}"
            _add_commands(group, registry, prefix)
    args = parser.parse_args(argv)
    assert registry is not None
    data = dict(args._json_input)
    if not isinstance(args._json_input, dict):
        parser.error("--json-input must be a JSON object")
    reserved = {"group", "command", "_tool", "_json_input"}
    data.update({k: v for k, v in vars(args).items() if k not in reserved})
    sys.exit(run_tool(registry, args._tool, data))
