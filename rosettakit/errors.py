from __future__ import annotations

from collections.abc import Sequence

from rosettakit.diagnostics import Diagnostic


class ScriptDslError(Exception):
    """Base class for RosettaKit script DSL errors."""


class ValidationError(ScriptDslError):
    def __init__(self, backend: str, diagnostics: Sequence[Diagnostic]) -> None:
        self.backend = backend
        self.diagnostics = tuple(diagnostics)
        details = "; ".join(_format_diagnostic(item) for item in self.diagnostics)
        super().__init__(f"{backend} validation failed: {details}")


class BuildError(ScriptDslError):
    """Raised when a builder cannot render a document."""


class UnsafeRawError(ValidationError):
    def __init__(self, backend: str, diagnostics: Sequence[Diagnostic]) -> None:
        super().__init__(backend, diagnostics)


def _format_diagnostic(diagnostic: Diagnostic) -> str:
    if diagnostic.origin:
        return f"{diagnostic.code} at {diagnostic.origin}: {diagnostic.message}"
    return f"{diagnostic.code}: {diagnostic.message}"
