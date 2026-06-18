from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from rosettakit.diagnostics import Diagnostic
from rosettakit.errors import BuildError, UnsafeRawError, ValidationError


@dataclass(frozen=True)
class Scalar:
    value: Any


@dataclass(frozen=True)
class PathValue:
    value: str


@dataclass(frozen=True)
class ListValue:
    values: tuple[Any, ...]


@dataclass(frozen=True)
class VarRef:
    name: str


@dataclass(frozen=True)
class Expr:
    expression: str


@dataclass(frozen=True)
class CommandSubstitution:
    command: str
    args: tuple[Any, ...]


@dataclass(frozen=True)
class Raw:
    text: str


@dataclass(frozen=True)
class Condition:
    text: str


@dataclass(frozen=True)
class Comment:
    text: str
    origin: str | None = None


@dataclass(frozen=True)
class BlankLine:
    origin: str | None = None


@dataclass(frozen=True)
class Set:
    name: str
    value: Any
    scalar_api: bool = True
    origin: str | None = None


@dataclass(frozen=True)
class Command:
    name: str
    args: tuple[Any, ...]
    origin: str | None = None


@dataclass(frozen=True)
class If:
    condition: Condition
    body: list[Any]
    origin: str | None = None


@dataclass(frozen=True)
class RawLine:
    text: str
    origin: str | None = None


def word(value: Any) -> Scalar:
    return Scalar(value)


def path(value: str) -> PathValue:
    return PathValue(value)


def list_value(values: Iterable[Any]) -> ListValue:
    return ListValue(tuple(values))


def var(name: str) -> VarRef:
    return VarRef(name)


def expr(expression: str) -> Expr:
    return Expr(expression)


def call(command: str, *args: Any) -> CommandSubstitution:
    return CommandSubstitution(command, args)


def raw(text: str) -> Raw:
    return Raw(text)


def file_isdirectory(value: Any) -> Condition:
    return Condition(f"[file isdirectory {TclBuilder().render_value(value)}]")


class Script:
    def __init__(self) -> None:
        self._nodes: list[Any] = []
        self._stack: list[list[Any]] = [self._nodes]

    @property
    def nodes(self) -> tuple[Any, ...]:
        return tuple(self._nodes)

    def comment(self, text: str, *, origin: str | None = None) -> None:
        self._current().append(Comment(text, origin))

    def blank_line(self, *, origin: str | None = None) -> None:
        self._current().append(BlankLine(origin))

    def set(self, name: str, value: Any, *, origin: str | None = None) -> None:
        self._current().append(Set(name, _coerce_value(value), True, origin))

    def set_path(self, name: str, value: str, *, origin: str | None = None) -> None:
        self.set(name, path(value), origin=origin)

    def set_list(self, name: str, values: Iterable[Any], *, origin: str | None = None) -> None:
        self._current().append(Set(name, list_value(values), False, origin))

    def set_expr(self, name: str, expression: str, *, origin: str | None = None) -> None:
        self.set(name, expr(expression), origin=origin)

    def command(self, name: str, *args: Any, origin: str | None = None) -> None:
        self._current().append(Command(name, tuple(_coerce_value(arg) for arg in args), origin))

    def file_mkdir(self, value: Any, *, origin: str | None = None) -> None:
        self.command("file", "mkdir", value, origin=origin)

    @contextmanager
    def if_not(self, condition: Condition, *, origin: str | None = None):
        body: list[Any] = []
        self._current().append(If(Condition(f"!({condition.text})"), body, origin))
        self._stack.append(body)
        try:
            yield self
        finally:
            self._stack.pop()

    def raw_line(self, text: str, *, origin: str | None = None) -> None:
        self._current().append(RawLine(text, origin))

    def validate(self) -> list[Diagnostic]:
        return TclBuilder().validate(self)

    def build(self, *, allow_unsafe_raw: bool = False) -> str:
        return TclBuilder(allow_unsafe_raw=allow_unsafe_raw).build(self)

    def _current(self) -> list[Any]:
        return self._stack[-1]


class TclBuilder:
    backend = "tcl"

    def __init__(self, *, indent: str = "    ", allow_unsafe_raw: bool = False) -> None:
        self.indent = indent
        self.allow_unsafe_raw = allow_unsafe_raw

    def build(self, script: Script) -> str:
        diagnostics = self.validate(script)
        raw_diagnostics = [item for item in diagnostics if item.code == "unsafe-raw"]
        blocking = [item for item in diagnostics if item.code not in {"unsafe-raw", "quoted-path"}]
        if raw_diagnostics and not self.allow_unsafe_raw:
            raise UnsafeRawError(self.backend, raw_diagnostics)
        if blocking:
            raise ValidationError(self.backend, blocking)
        return "".join(self._render_node(node, level=0) for node in script.nodes)

    def validate(self, script: Script) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for node in script.nodes:
            diagnostics.extend(self._validate_node(node))
        return diagnostics

    def render_value(self, value: Any) -> str:
        value = _coerce_value(value)
        if isinstance(value, Scalar):
            return _quote_tcl_word(str(value.value))
        if isinstance(value, PathValue):
            return _quote_tcl_word(value.value)
        if isinstance(value, ListValue):
            return "[list " + " ".join(self.render_value(item) for item in value.values) + "]"
        if isinstance(value, VarRef):
            if not value.name:
                raise BuildError("empty Tcl variable reference")
            return f"${value.name}"
        if isinstance(value, Expr):
            return f"[expr {{{value.expression}}}]"
        if isinstance(value, CommandSubstitution):
            words = [value.command, *(self.render_value(arg) for arg in value.args)]
            return "[" + " ".join(words) + "]"
        if isinstance(value, Raw):
            return value.text
        raise BuildError(f"unsupported Tcl value: {value!r}")

    def _render_node(self, node: Any, *, level: int) -> str:
        prefix = self.indent * level
        if isinstance(node, Comment):
            return "".join(f"{prefix}# {line}\n" for line in _comment_lines(node.text))
        if isinstance(node, BlankLine):
            return "\n"
        if isinstance(node, Set):
            return f"{prefix}set {node.name} {self.render_value(node.value)}\n"
        if isinstance(node, Command):
            args = " ".join(self.render_value(arg) for arg in node.args)
            line = f"{node.name} {args}" if args else node.name
            return f"{prefix}{line}\n"
        if isinstance(node, If):
            body = "".join(self._render_node(child, level=level + 1) for child in node.body)
            return f"{prefix}if {{{node.condition.text}}} {{\n{body}{prefix}}}\n"
        if isinstance(node, RawLine):
            return f"{prefix}{node.text}\n"
        raise BuildError(f"unsupported Tcl node: {node!r}")

    def _validate_node(self, node: Any) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if isinstance(node, Set):
            if not node.name:
                diagnostics.append(Diagnostic("empty-variable-name", "variable name is required", node.origin))
            diagnostics.extend(_validate_value(node.value, origin=node.origin, scalar_api=node.scalar_api))
        elif isinstance(node, Command):
            if not node.name:
                diagnostics.append(Diagnostic("empty-command-name", "command name is required", node.origin))
            for arg in node.args:
                diagnostics.extend(_validate_value(arg, origin=node.origin, scalar_api=False))
        elif isinstance(node, If):
            if not node.condition.text:
                diagnostics.append(Diagnostic("empty-condition", "condition is required", node.origin))
            for child in node.body:
                diagnostics.extend(self._validate_node(child))
        elif isinstance(node, RawLine):
            diagnostics.append(Diagnostic("unsafe-raw", "raw Tcl line requires explicit opt-in", node.origin))
        elif isinstance(node, (Comment, BlankLine)):
            pass
        else:
            diagnostics.append(Diagnostic("unsupported-node", f"unsupported Tcl node {type(node).__name__}"))
        return diagnostics


def _coerce_value(value: Any) -> Any:
    if isinstance(value, (Scalar, PathValue, ListValue, VarRef, Expr, CommandSubstitution, Raw)):
        return value
    return Scalar(value)


def _validate_value(value: Any, *, origin: str | None, scalar_api: bool) -> list[Diagnostic]:
    value = _coerce_value(value)
    diagnostics: list[Diagnostic] = []
    if isinstance(value, PathValue):
        if value.value == "":
            diagnostics.append(Diagnostic("empty-path", "path value is required", origin))
        elif _needs_quoting(value.value):
            diagnostics.append(Diagnostic("quoted-path", "path requires Tcl quoting", origin))
    elif isinstance(value, ListValue):
        if scalar_api:
            diagnostics.append(
                Diagnostic("list-through-scalar-api", "use set_list for Tcl list values", origin)
            )
        for item in value.values:
            diagnostics.extend(_validate_value(item, origin=origin, scalar_api=False))
    elif isinstance(value, VarRef) and not value.name:
        diagnostics.append(Diagnostic("empty-variable-name", "variable reference name is required", origin))
    elif isinstance(value, CommandSubstitution):
        if not value.command:
            diagnostics.append(Diagnostic("empty-command-name", "command name is required", origin))
        for arg in value.args:
            diagnostics.extend(_validate_value(arg, origin=origin, scalar_api=False))
    return diagnostics


def _quote_tcl_word(text: str) -> str:
    if text == "":
        return "{}"
    if not _needs_quoting(text):
        return text
    if "{" not in text and "}" not in text and "\n" not in text and "\r" not in text:
        return "{" + text + "}"
    return "".join(_escape_unbraced_char(char) for char in text)


def _needs_quoting(text: str) -> bool:
    return text == "" or any(char.isspace() or char in "{}[]$;\\\"" for char in text)


def _escape_unbraced_char(char: str) -> str:
    replacements = {
        " ": "\\ ",
        "\t": "\\t",
        "\n": "\\n",
        "\r": "\\r",
        "\\": "\\\\",
        "{": "\\{",
        "}": "\\}",
        "[": "\\[",
        "]": "\\]",
        "$": "\\$",
        ";": "\\;",
        '"': '\\"',
    }
    return replacements.get(char, char)


def _comment_lines(text: str) -> list[str]:
    return text.splitlines() or [""]
