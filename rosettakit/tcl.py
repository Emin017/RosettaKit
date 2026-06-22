from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TypeAlias

from rosettakit.diagnostics import Diagnostic
from rosettakit.errors import BuildError, UnsafeRawError, ValidationError


TclInputValue: TypeAlias = object


@dataclass(frozen=True)
class Scalar:
    """A scalar Tcl value rendered as one safely quoted word."""

    value: TclInputValue


@dataclass(frozen=True)
class PathValue:
    """A Tcl value that represents a filesystem path."""

    value: str


@dataclass(frozen=True)
class ListValue:
    """A Tcl list value rendered with the Tcl `list` command."""

    values: tuple[TclInputValue, ...]


@dataclass(frozen=True)
class VarRef:
    """A reference to a Tcl variable rendered as `$name`."""

    name: str


@dataclass(frozen=True)
class Expr:
    """A Tcl expression rendered as `[expr {...}]`."""

    expression: str


@dataclass(frozen=True)
class CommandSubstitution:
    """A Tcl command substitution rendered as `[command arg ...]`."""

    command: str
    args: tuple[TclInputValue, ...]


@dataclass(frozen=True)
class Raw:
    """Raw Tcl text that bypasses escaping and requires explicit build opt-in."""

    text: str


TclValue: TypeAlias = Scalar | PathValue | ListValue | VarRef | Expr | CommandSubstitution | Raw


@dataclass(frozen=True)
class Condition:
    """A rendered Tcl condition plus diagnostics for values used to build it."""

    text: str
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class Comment:
    """A Tcl comment node."""

    text: str
    origin: str | None = None


@dataclass(frozen=True)
class BlankLine:
    """A blank Tcl output line."""

    origin: str | None = None


@dataclass(frozen=True)
class Set:
    """A Tcl `set` command node."""

    name: str
    value: TclValue
    scalar_api: bool = True
    origin: str | None = None


@dataclass(frozen=True)
class Command:
    """A generic Tcl command node."""

    name: str
    args: tuple[TclValue, ...]
    origin: str | None = None


@dataclass(frozen=True)
class If:
    """A Tcl `if` node with a nested body."""

    condition: Condition
    body: list[TclNode]
    origin: str | None = None


@dataclass(frozen=True)
class RawLine:
    """A raw Tcl line that bypasses escaping and requires explicit build opt-in."""

    text: str
    origin: str | None = None


TclNode: TypeAlias = Comment | BlankLine | Set | Command | If | RawLine


def word(value: TclInputValue) -> Scalar:
    """Create a scalar Tcl word that RosettaKit quotes safely when rendered.

    Use this for single Tcl values passed to `Script.set` or command arguments.
    Non-string Python values are converted with `str(...)` during rendering.
    """
    return Scalar(value)


def path(value: str) -> PathValue:
    """Create a filesystem path value for Tcl output.

    Path values render as one safely quoted Tcl word and participate in path
    diagnostics such as empty-path and quoted-path warnings.
    """
    return PathValue(value)


def list_value(values: Iterable[TclInputValue]) -> ListValue:
    """Create a Tcl list value rendered as `[list item ...]`.

    Prefer `Script.set_list` when assigning a variable to a Tcl list. This helper
    is useful when a list must be passed as a value object.
    """
    return ListValue(tuple(values))


def var(name: str) -> VarRef:
    """Reference an existing Tcl variable as `$name`.

    The variable name is inserted without quoting; empty names are reported by
    validation and rejected during rendering.
    """
    return VarRef(name)


def expr(expression: str) -> Expr:
    """Create a Tcl expression substitution rendered as `[expr {...}]`.

    The expression text is inserted into the braced Tcl expression body. Pass
    trusted expression text rather than unescaped user input.
    """
    return Expr(expression)


def call(command: str, *args: TclInputValue) -> CommandSubstitution:
    """Create a Tcl command substitution rendered as `[command arg ...]`.

    Arguments are rendered through RosettaKit value quoting. The command name is
    used as provided, so keep it controlled by the caller.
    """
    return CommandSubstitution(command, args)


def raw(text: str) -> Raw:
    """Create raw Tcl value text that bypasses all escaping.

    Raw values are an escape hatch for hand-written Tcl snippets. Builds fail on
    raw content unless `allow_unsafe_raw=True` is passed.
    """
    return Raw(text)


def file_isdirectory(value: TclInputValue) -> Condition:
    """Create a Tcl condition for `[file isdirectory value]`.

    The value is rendered with RosettaKit quoting and any value diagnostics are
    carried into the condition for later validation.
    """
    diagnostics = tuple(_validate_value(value, origin=None, scalar_api=False))
    return Condition(f"[file isdirectory {TclBuilder().render_value(value)}]", diagnostics)


class Script:
    """Mutable Tcl script document that preserves insertion order."""

    def __init__(self) -> None:
        """Create an empty Tcl script document."""
        self._nodes: list[TclNode] = []
        self._stack: list[list[TclNode]] = [self._nodes]

    @property
    def nodes(self) -> tuple[TclNode, ...]:
        """Return an immutable snapshot of top-level Tcl nodes."""
        return tuple(self._nodes)

    def comment(self, text: str, *, origin: str | None = None) -> None:
        """Append one or more Tcl comment lines.

        Newline-separated text is emitted as separate comment lines. `origin` is
        attached to diagnostics produced from this node.
        """
        self._current().append(Comment(text, origin))

    def blank_line(self, *, origin: str | None = None) -> None:
        """Append a blank line to the script."""
        self._current().append(BlankLine(origin))

    def set(self, name: str, value: TclInputValue, *, origin: str | None = None) -> None:
        """Append a Tcl `set name value` command.

        Scalar values are quoted as one Tcl word. Use `set_list` for Tcl lists so
        validation can distinguish list assignment from scalar assignment.
        """
        self._current().append(Set(name, _coerce_value(value), True, origin))

    def set_path(self, name: str, value: str, *, origin: str | None = None) -> None:
        """Append a Tcl `set` command whose value represents a filesystem path."""
        self.set(name, path(value), origin=origin)

    def set_list(
        self,
        name: str,
        values: Iterable[TclInputValue],
        *,
        origin: str | None = None,
    ) -> None:
        """Append a Tcl `set` command whose value is rendered as a Tcl list."""
        self._current().append(Set(name, list_value(values), False, origin))

    def set_expr(self, name: str, expression: str, *, origin: str | None = None) -> None:
        """Append a Tcl `set` command whose value is rendered as `[expr {...}]`."""
        self.set(name, expr(expression), origin=origin)

    def command(self, name: str, *args: TclInputValue, origin: str | None = None) -> None:
        """Append a generic Tcl command with safely rendered arguments.

        The command name is emitted as provided. Each argument is converted to a
        RosettaKit value and rendered as one Tcl word or value expression.
        """
        self._current().append(Command(name, tuple(_coerce_value(arg) for arg in args), origin))

    def file_mkdir(self, value: TclInputValue, *, origin: str | None = None) -> None:
        """Append `file mkdir value` with the directory value safely rendered."""
        self.command("file", "mkdir", value, origin=origin)

    @contextmanager
    def if_not(self, condition: Condition, *, origin: str | None = None) -> Iterator[Script]:
        """Append an `if {!(condition)}` block and yield this script for its body."""
        body: list[TclNode] = []
        self._current().append(
            If(Condition(f"!({condition.text})", condition.diagnostics), body, origin)
        )
        self._stack.append(body)
        try:
            yield self
        finally:
            self._stack.pop()

    def raw_line(self, text: str, *, origin: str | None = None) -> None:
        """Append a raw Tcl line that bypasses escaping.

        Raw lines are an escape hatch for hand-written Tcl. Builds fail on raw
        content unless `allow_unsafe_raw=True` is passed.
        """
        self._current().append(RawLine(text, origin))

    def validate(self) -> list[Diagnostic]:
        """Return diagnostics for this script without rendering text."""
        return TclBuilder().validate(self)

    def build(self, *, allow_unsafe_raw: bool = False) -> str:
        """Validate and render this script as Tcl text.

        Raises `ValidationError` for blocking diagnostics and `UnsafeRawError`
        when raw content is present without `allow_unsafe_raw=True`.
        """
        return TclBuilder(allow_unsafe_raw=allow_unsafe_raw).build(self)

    def _current(self) -> list[TclNode]:
        return self._stack[-1]


class TclBuilder:
    """Renderer and validator for RosettaKit Tcl scripts."""

    backend = "tcl"

    def __init__(self, *, indent: str = "    ", allow_unsafe_raw: bool = False) -> None:
        """Create a Tcl builder with indentation and raw-content policy."""
        self.indent = indent
        self.allow_unsafe_raw = allow_unsafe_raw

    def build(self, script: Script) -> str:
        """Validate and render a `Script` into Tcl text."""
        diagnostics = self.validate(script)
        raw_diagnostics = [item for item in diagnostics if item.code == "unsafe-raw"]
        blocking = [item for item in diagnostics if item.code not in {"unsafe-raw", "quoted-path"}]
        if raw_diagnostics and not self.allow_unsafe_raw:
            raise UnsafeRawError(self.backend, raw_diagnostics)
        if blocking:
            raise ValidationError(self.backend, blocking)
        return "".join(self._render_node(node, level=0) for node in script.nodes)

    def validate(self, script: Script) -> list[Diagnostic]:
        """Return diagnostics for a `Script` without rendering text."""
        diagnostics: list[Diagnostic] = []
        for node in script.nodes:
            diagnostics.extend(self._validate_node(node))
        return diagnostics

    def render_value(self, value: TclInputValue) -> str:
        """Render one Tcl input value as Tcl text."""
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

    def _render_node(self, node: TclNode, *, level: int) -> str:
        prefix = self.indent * level
        if isinstance(node, Comment):
            return "".join(
                f"{prefix}# {_escape_comment_line(line)}\n"
                for line in _comment_lines(node.text)
            )
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

    def _validate_node(self, node: TclNode) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if isinstance(node, Set):
            if not node.name:
                diagnostics.append(
                    Diagnostic("empty-variable-name", "variable name is required", node.origin)
                )
            diagnostics.extend(
                _validate_value(node.value, origin=node.origin, scalar_api=node.scalar_api)
            )
        elif isinstance(node, Command):
            if not node.name:
                diagnostics.append(
                    Diagnostic("empty-command-name", "command name is required", node.origin)
                )
            for arg in node.args:
                diagnostics.extend(_validate_value(arg, origin=node.origin, scalar_api=False))
        elif isinstance(node, If):
            if not node.condition.text:
                diagnostics.append(
                    Diagnostic("empty-condition", "condition is required", node.origin)
                )
            for item in node.condition.diagnostics:
                diagnostics.append(_diagnostic_with_origin(item, node.origin))
            for child in node.body:
                diagnostics.extend(self._validate_node(child))
        elif isinstance(node, RawLine):
            diagnostics.append(
                Diagnostic("unsafe-raw", "raw Tcl line requires explicit opt-in", node.origin)
            )
        elif isinstance(node, (Comment, BlankLine)):
            pass
        else:
            diagnostics.append(
                Diagnostic("unsupported-node", f"unsupported Tcl node {type(node).__name__}")
            )
        return diagnostics


def _coerce_value(value: TclInputValue) -> TclValue:
    if isinstance(value, (Scalar, PathValue, ListValue, VarRef, Expr, CommandSubstitution, Raw)):
        return value
    return Scalar(value)


def _diagnostic_with_origin(diagnostic: Diagnostic, origin: str | None) -> Diagnostic:
    if diagnostic.origin or origin is None:
        return diagnostic
    return Diagnostic(diagnostic.code, diagnostic.message, origin)


def _validate_value(
    value: TclInputValue,
    *,
    origin: str | None,
    scalar_api: bool,
) -> list[Diagnostic]:
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
        diagnostics.append(
            Diagnostic("empty-variable-name", "variable reference name is required", origin)
        )
    elif isinstance(value, CommandSubstitution):
        if not value.command:
            diagnostics.append(Diagnostic("empty-command-name", "command name is required", origin))
        for arg in value.args:
            diagnostics.extend(_validate_value(arg, origin=origin, scalar_api=False))
    elif isinstance(value, Raw):
        diagnostics.append(
            Diagnostic("unsafe-raw", "raw Tcl value requires explicit opt-in", origin)
        )
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


def _escape_comment_line(line: str) -> str:
    return line.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
