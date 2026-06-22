from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from rosettakit.diagnostics import Diagnostic
from rosettakit.errors import BuildError, UnsafeRawError, ValidationError


CommandFileValue: TypeAlias = object


class ValueType(Enum):
    """Value category used for command-file validation diagnostics."""

    SCALAR = "scalar"
    PATH = "path"


@dataclass(frozen=True)
class Comment:
    """A command-file comment node."""

    text: str
    origin: str | None = None


@dataclass(frozen=True)
class BlankLine:
    """A blank command-file output line."""

    origin: str | None = None


@dataclass(frozen=True)
class Flag:
    """A command-file flag node rendered without a value."""

    name: str
    origin: str | None = None


@dataclass(frozen=True)
class Option:
    """A command-file option node rendered with one value."""

    name: str
    value: CommandFileValue
    value_type: ValueType
    omit_empty: bool
    origin: str | None = None


@dataclass(frozen=True)
class RawLine:
    """A raw command-file line that requires explicit build opt-in."""

    text: str
    origin: str | None = None


CommandFileNode: TypeAlias = Comment | BlankLine | Flag | Option | RawLine


class CommandFile:
    """Mutable command-file document that preserves insertion order."""

    def __init__(self, *, prefix: str = "-") -> None:
        """Create an empty command-file document.

        `prefix` is prepended to flags and option names. Use `prefix=""` for
        command-like env files that do not use dashed option names.
        """
        self.prefix = prefix
        self._nodes: list[CommandFileNode] = []

    @property
    def nodes(self) -> tuple[CommandFileNode, ...]:
        """Return an immutable snapshot of command-file nodes."""
        return tuple(self._nodes)

    def comment(self, text: str, *, origin: str | None = None) -> None:
        """Append one or more comment lines.

        Newline-separated text is emitted as separate comment lines. `origin` is
        attached to diagnostics produced from this node.
        """
        self._nodes.append(Comment(text, origin))

    def blank_line(self, *, origin: str | None = None) -> None:
        """Append a blank line to the command file."""
        self._nodes.append(BlankLine(origin))

    def flag(self, name: str, *, origin: str | None = None) -> None:
        """Append a flag line such as `-useOpenSTA`."""
        self._nodes.append(Flag(name, origin))

    def option(
        self,
        name: str,
        value: CommandFileValue,
        *,
        value_type: ValueType = ValueType.SCALAR,
        omit_empty: bool = False,
        origin: str | None = None,
    ) -> None:
        """Append one option line with a quoted value.

        Set `value_type=ValueType.PATH` for filesystem paths so validation can
        report empty paths and path quoting diagnostics. `omit_empty=True`
        suppresses the line when the value is an empty string.
        """
        self._nodes.append(Option(name, value, value_type, omit_empty, origin))

    def options(
        self,
        name: str,
        values: Iterable[CommandFileValue],
        *,
        value_type: ValueType = ValueType.SCALAR,
        omit_empty: bool = False,
        origin: str | None = None,
    ) -> None:
        """Append one option line for each value in `values`."""
        for value in values:
            self.option(
                name,
                value,
                value_type=value_type,
                omit_empty=omit_empty,
                origin=origin,
            )

    def raw_line(self, text: str, *, origin: str | None = None) -> None:
        """Append a raw command-file line that bypasses escaping.

        Raw lines are an escape hatch for hand-written output. Builds fail on
        raw content unless `allow_unsafe_raw=True` is passed.
        """
        self._nodes.append(RawLine(text, origin))

    def validate(self) -> list[Diagnostic]:
        """Return diagnostics for this command file without rendering text."""
        return CommandFileBuilder().validate(self)

    def build(self, *, allow_unsafe_raw: bool = False) -> str:
        """Validate and render this command file as text.

        Raises `ValidationError` for blocking diagnostics and `UnsafeRawError`
        when raw content is present without `allow_unsafe_raw=True`.
        """
        return CommandFileBuilder(allow_unsafe_raw=allow_unsafe_raw).build(self)


class CommandFileBuilder:
    """Renderer and validator for RosettaKit command-file documents."""

    backend = "command-file"

    def __init__(self, *, allow_unsafe_raw: bool = False) -> None:
        """Create a command-file builder with the requested raw-content policy."""
        self.allow_unsafe_raw = allow_unsafe_raw

    def build(self, document: CommandFile) -> str:
        """Validate and render a `CommandFile` into text."""
        diagnostics = self.validate(document)
        raw_diagnostics = [item for item in diagnostics if item.code == "unsafe-raw"]
        blocking = [item for item in diagnostics if item.code not in {"unsafe-raw", "quoted-path"}]
        if raw_diagnostics and not self.allow_unsafe_raw:
            raise UnsafeRawError(self.backend, raw_diagnostics)
        if blocking:
            raise ValidationError(self.backend, blocking)
        return "".join(self._render_node(document.prefix, node) for node in document.nodes)

    def validate(self, document: CommandFile) -> list[Diagnostic]:
        """Return diagnostics for a `CommandFile` without rendering text."""
        diagnostics: list[Diagnostic] = []
        for node in document.nodes:
            diagnostics.extend(self._validate_node(node))
        return diagnostics

    def _render_node(self, prefix: str, node: CommandFileNode) -> str:
        if isinstance(node, Comment):
            return "".join(f"# {line}\n" for line in _comment_lines(node.text))
        if isinstance(node, BlankLine):
            return "\n"
        if isinstance(node, Flag):
            return f"{prefix}{node.name}\n"
        if isinstance(node, Option):
            if node.omit_empty and node.value == "":
                return ""
            return f"{prefix}{node.name} {_quote_word(str(node.value))}\n"
        if isinstance(node, RawLine):
            return f"{node.text}\n"
        raise BuildError(f"unsupported command-file node: {node!r}")

    def _validate_node(self, node: CommandFileNode) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if isinstance(node, Flag):
            if not node.name:
                diagnostics.append(
                    Diagnostic("empty-option-name", "flag name is required", node.origin)
                )
        elif isinstance(node, Option):
            if not node.name:
                diagnostics.append(
                    Diagnostic("empty-option-name", "option name is required", node.origin)
                )
            if _has_line_break(str(node.value)):
                diagnostics.append(
                    Diagnostic(
                        "line-break-in-value",
                        "command-file values cannot contain line breaks",
                        node.origin,
                    )
                )
            if node.value_type is ValueType.PATH and node.value == "" and not node.omit_empty:
                diagnostics.append(Diagnostic("empty-path", "path value is required", node.origin))
            if (
                node.value_type is ValueType.PATH
                and node.value != ""
                and _needs_quoting(str(node.value))
            ):
                diagnostics.append(
                    Diagnostic("quoted-path", "path requires command-file quoting", node.origin)
                )
        elif isinstance(node, RawLine):
            diagnostics.append(
                Diagnostic(
                    "unsafe-raw",
                    "raw command-file line requires explicit opt-in",
                    node.origin,
                )
            )
        elif isinstance(node, (Comment, BlankLine)):
            pass
        else:
            diagnostics.append(
                Diagnostic(
                    "unsupported-node",
                    f"unsupported command-file node {type(node).__name__}",
                )
            )
        return diagnostics


def _quote_word(text: str) -> str:
    if text == "":
        return "{}"
    if not _needs_quoting(text):
        return text
    if "{" not in text and "}" not in text and "\n" not in text and "\r" not in text:
        return "{" + text + "}"
    return "".join(_escape_word_char(char) for char in text)


def _needs_quoting(text: str) -> bool:
    return text == "" or any(char.isspace() or char in "{}[]$;\\\"" for char in text)


def _escape_word_char(char: str) -> str:
    replacements = {
        " ": "\\ ",
        "\t": "\\t",
        "\r": "\\r",
        "\n": "\\n",
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


def _has_line_break(text: str) -> bool:
    return "\n" in text or "\r" in text


def _comment_lines(text: str) -> list[str]:
    return text.splitlines() or [""]
