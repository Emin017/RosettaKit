from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from rosettakit.diagnostics import Diagnostic
from rosettakit.errors import BuildError, UnsafeRawError, ValidationError


class ValueType(Enum):
    SCALAR = "scalar"
    PATH = "path"


@dataclass(frozen=True)
class Comment:
    text: str
    origin: str | None = None


@dataclass(frozen=True)
class BlankLine:
    origin: str | None = None


@dataclass(frozen=True)
class Flag:
    name: str
    origin: str | None = None


@dataclass(frozen=True)
class Option:
    name: str
    value: Any
    value_type: ValueType
    omit_empty: bool
    origin: str | None = None


@dataclass(frozen=True)
class RawLine:
    text: str
    origin: str | None = None


class CommandFile:
    def __init__(self, *, prefix: str = "-") -> None:
        self.prefix = prefix
        self._nodes: list[Any] = []

    @property
    def nodes(self) -> tuple[Any, ...]:
        return tuple(self._nodes)

    def comment(self, text: str, *, origin: str | None = None) -> None:
        self._nodes.append(Comment(text, origin))

    def blank_line(self, *, origin: str | None = None) -> None:
        self._nodes.append(BlankLine(origin))

    def flag(self, name: str, *, origin: str | None = None) -> None:
        self._nodes.append(Flag(name, origin))

    def option(
        self,
        name: str,
        value: Any,
        *,
        value_type: ValueType = ValueType.SCALAR,
        omit_empty: bool = False,
        origin: str | None = None,
    ) -> None:
        self._nodes.append(Option(name, value, value_type, omit_empty, origin))

    def options(
        self,
        name: str,
        values: Iterable[Any],
        *,
        value_type: ValueType = ValueType.SCALAR,
        omit_empty: bool = False,
        origin: str | None = None,
    ) -> None:
        for value in values:
            self.option(
                name,
                value,
                value_type=value_type,
                omit_empty=omit_empty,
                origin=origin,
            )

    def raw_line(self, text: str, *, origin: str | None = None) -> None:
        self._nodes.append(RawLine(text, origin))

    def validate(self) -> list[Diagnostic]:
        return CommandFileBuilder().validate(self)

    def build(self, *, allow_unsafe_raw: bool = False) -> str:
        return CommandFileBuilder(allow_unsafe_raw=allow_unsafe_raw).build(self)


class CommandFileBuilder:
    backend = "command-file"

    def __init__(self, *, allow_unsafe_raw: bool = False) -> None:
        self.allow_unsafe_raw = allow_unsafe_raw

    def build(self, document: CommandFile) -> str:
        diagnostics = self.validate(document)
        raw_diagnostics = [item for item in diagnostics if item.code == "unsafe-raw"]
        blocking = [item for item in diagnostics if item.code not in {"unsafe-raw", "quoted-path"}]
        if raw_diagnostics and not self.allow_unsafe_raw:
            raise UnsafeRawError(self.backend, raw_diagnostics)
        if blocking:
            raise ValidationError(self.backend, blocking)
        return "".join(self._render_node(document.prefix, node) for node in document.nodes)

    def validate(self, document: CommandFile) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for node in document.nodes:
            diagnostics.extend(self._validate_node(node))
        return diagnostics

    def _render_node(self, prefix: str, node: Any) -> str:
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

    def _validate_node(self, node: Any) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if isinstance(node, Flag):
            if not node.name:
                diagnostics.append(Diagnostic("empty-option-name", "flag name is required", node.origin))
        elif isinstance(node, Option):
            if not node.name:
                diagnostics.append(Diagnostic("empty-option-name", "option name is required", node.origin))
            if _has_line_break(str(node.value)):
                diagnostics.append(
                    Diagnostic("line-break-in-value", "command-file values cannot contain line breaks", node.origin)
                )
            if node.value_type is ValueType.PATH and node.value == "" and not node.omit_empty:
                diagnostics.append(Diagnostic("empty-path", "path value is required", node.origin))
            if node.value_type is ValueType.PATH and node.value != "" and _needs_quoting(str(node.value)):
                diagnostics.append(Diagnostic("quoted-path", "path requires command-file quoting", node.origin))
        elif isinstance(node, RawLine):
            diagnostics.append(
                Diagnostic("unsafe-raw", "raw command-file line requires explicit opt-in", node.origin)
            )
        elif isinstance(node, (Comment, BlankLine)):
            pass
        else:
            diagnostics.append(
                Diagnostic("unsupported-node", f"unsupported command-file node {type(node).__name__}")
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
