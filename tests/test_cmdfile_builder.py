from __future__ import annotations

import pytest

from rosettakit import cmdfile
from rosettakit.errors import UnsafeRawError, ValidationError


def test_command_file_builds_sizer_cmd_file_like_output() -> None:
    cmd = cmdfile.CommandFile(prefix="-")
    cmd.flag("useOpenSTA")
    cmd.option("top", "gcd_core")
    cmd.option("def", "build out/input.def", value_type=cmdfile.ValueType.PATH)
    cmd.option("v", "", value_type=cmdfile.ValueType.PATH, omit_empty=True)
    cmd.option("sdc", "constraints/main clock.sdc", value_type=cmdfile.ValueType.PATH)
    cmd.options("lef", ["tech/sky130.lef", "macro lef/sram.lef"], value_type=cmdfile.ValueType.PATH)
    cmd.options("lib", ["lib/slow.lib", "lib/fast corner.lib"], value_type=cmdfile.ValueType.PATH)
    cmd.option("outputPath", ".")
    cmd.option("def_out_path", "out/final.def", value_type=cmdfile.ValueType.PATH)

    assert cmd.build() == (
        "-useOpenSTA\n"
        "-top gcd_core\n"
        "-def {build out/input.def}\n"
        "-sdc {constraints/main clock.sdc}\n"
        "-lef tech/sky130.lef\n"
        "-lef {macro lef/sram.lef}\n"
        "-lib lib/slow.lib\n"
        "-lib {lib/fast corner.lib}\n"
        "-outputPath .\n"
        "-def_out_path out/final.def\n"
    )


def test_command_file_builds_env_file_like_output() -> None:
    env = cmdfile.CommandFile(prefix="")
    env.comment("Sizer environment")
    env.option("set_db", "design_process_node 130")
    env.blank_line()
    env.option("set_db", "design_netlist_file build/gcd.v")

    assert env.build() == (
        "# Sizer environment\n"
        "set_db {design_process_node 130}\n"
        "\n"
        "set_db {design_netlist_file build/gcd.v}\n"
    )


def test_default_path_values_report_nonblocking_quoted_path_diagnostics() -> None:
    cmd = cmdfile.CommandFile(prefix="-")
    cmd.option(
        "def",
        "build out/input.def",
        value_type=cmdfile.ValueType.PATH,
        origin="unit.def",
    )

    assert [(item.code, item.origin) for item in cmd.validate()] == [
        ("quoted-path", "unit.def"),
    ]
    assert cmd.build() == "-def {build out/input.def}\n"


def test_plain_dialect_renders_safe_values_without_quoting() -> None:
    cmd = cmdfile.CommandFile(prefix="-", dialect=cmdfile.PLAIN_DIALECT)
    cmd.flag("useOpenSTA")
    cmd.option("top", "gcd_core")
    cmd.option("def", "build/input.def", value_type=cmdfile.ValueType.PATH)
    cmd.options("lib", ["lib/slow.lib", "lib/fast.lib"], value_type=cmdfile.ValueType.PATH)

    assert cmd.validate() == []
    assert cmd.build() == (
        "-useOpenSTA\n"
        "-top gcd_core\n"
        "-def build/input.def\n"
        "-lib lib/slow.lib\n"
        "-lib lib/fast.lib\n"
    )


def test_plain_dialect_rejects_path_values_with_whitespace() -> None:
    cmd = cmdfile.CommandFile(prefix="-", dialect=cmdfile.PLAIN_DIALECT)
    cmd.option(
        "def",
        "build out/input.def",
        value_type=cmdfile.ValueType.PATH,
        origin="unit.def",
    )

    diagnostics = cmd.validate()
    assert [(item.code, item.origin) for item in diagnostics] == [
        ("unquoted-value-needs-quoting", "unit.def"),
    ]
    assert (
        diagnostics[0].message
        == "plain command-file values cannot contain whitespace or quoting characters"
    )
    with pytest.raises(ValidationError, match="unquoted-value-needs-quoting"):
        cmd.build()


def test_plain_dialect_rejects_scalar_values_with_whitespace() -> None:
    cmd = cmdfile.CommandFile(prefix="-", dialect=cmdfile.PLAIN_DIALECT)
    cmd.option("top", "gcd core", origin="unit.top")

    assert [(item.code, item.origin) for item in cmd.validate()] == [
        ("unquoted-value-needs-quoting", "unit.top"),
    ]
    with pytest.raises(ValidationError, match="unit.top"):
        cmd.build()


def test_plain_dialect_rejects_empty_scalar_values_unless_omitted() -> None:
    cmd = cmdfile.CommandFile(prefix="-", dialect=cmdfile.PLAIN_DIALECT)
    cmd.option("top", "", origin="unit.top")
    cmd.option("sdc", "", omit_empty=True, origin="unit.sdc")

    diagnostics = cmd.validate()
    assert [(item.code, item.origin) for item in diagnostics] == [
        ("empty-unquoted-value", "unit.top"),
    ]
    assert (
        diagnostics[0].message
        == "empty values cannot be represented as plain whitespace-delimited tokens"
    )
    with pytest.raises(ValidationError, match="empty-unquoted-value"):
        cmd.build()

    omitted = cmdfile.CommandFile(prefix="-", dialect=cmdfile.PLAIN_DIALECT)
    omitted.option("sdc", "", omit_empty=True)
    assert omitted.validate() == []
    assert omitted.build() == ""


@pytest.mark.parametrize("value", ["gcd$core", "gcd[0]", "gcd;core", r"gcd\core", 'gcd"core'])
def test_plain_dialect_rejects_values_with_quoting_characters(value: str) -> None:
    cmd = cmdfile.CommandFile(prefix="-", dialect=cmdfile.PLAIN_DIALECT)
    cmd.option("top", value)

    assert [item.code for item in cmd.validate()] == ["unquoted-value-needs-quoting"]
    with pytest.raises(ValidationError, match="unquoted-value-needs-quoting"):
        cmd.build()


def test_plain_dialect_raw_line_policy_is_unchanged() -> None:
    raw = cmdfile.CommandFile(prefix="-", dialect=cmdfile.PLAIN_DIALECT)
    raw.raw_line("-manual $unsafe", origin="unit.raw")

    assert [(item.code, item.origin) for item in raw.validate()] == [
        ("unsafe-raw", "unit.raw"),
    ]
    with pytest.raises(UnsafeRawError, match="unit.raw"):
        raw.build()
    assert raw.build(allow_unsafe_raw=True) == "-manual $unsafe\n"


def test_unsupported_command_file_dialect_is_blocking() -> None:
    dialect = cmdfile.CommandFileDialect(
        name="future",
        value_quoting=object(),
    )
    cmd = cmdfile.CommandFile(prefix="-", dialect=dialect)
    cmd.option("top", "gcd")

    assert [(item.code, item.origin) for item in cmd.validate()] == [
        ("unsupported-command-file-dialect", None),
    ]
    with pytest.raises(ValidationError, match="unsupported-command-file-dialect"):
        cmd.build()


def test_command_file_rejects_values_with_line_breaks() -> None:
    cmd = cmdfile.CommandFile()
    cmd.option("top", "gcd\n-useOpenSTA", origin="unit.line_break")

    assert [(item.code, item.origin) for item in cmd.validate()] == [
        ("line-break-in-value", "unit.line_break"),
    ]
    with pytest.raises(ValidationError, match="line-break-in-value"):
        cmd.build()


def test_command_file_multiline_comments_prefix_every_line() -> None:
    cmd = cmdfile.CommandFile()
    cmd.comment("note\n-useOpenSTA")

    assert cmd.build() == "# note\n# -useOpenSTA\n"


def test_command_file_diagnostics_and_raw_policy() -> None:
    cmd = cmdfile.CommandFile()
    cmd.option("empty", "", value_type=cmdfile.ValueType.PATH, origin="unit.empty_path")
    cmd.raw_line("-manual $unsafe", origin="unit.raw")

    assert [(item.code, item.origin) for item in cmd.validate()] == [
        ("empty-path", "unit.empty_path"),
        ("unsafe-raw", "unit.raw"),
    ]

    with pytest.raises(ValidationError, match="command-file"):
        cmd.build()

    raw = cmdfile.CommandFile()
    raw.raw_line("-manual $unsafe", origin="unit.raw")
    with pytest.raises(UnsafeRawError, match="unit.raw"):
        raw.build()
    assert raw.build(allow_unsafe_raw=True) == "-manual $unsafe\n"


def test_command_file_builder_can_build_document_directly() -> None:
    cmd = cmdfile.CommandFile(prefix="-")
    cmd.option("top", "gcd")

    assert cmd.nodes == (cmdfile.Option("top", "gcd", cmdfile.ValueType.SCALAR, False),)
    assert cmdfile.CommandFileBuilder().build(cmd) == "-top gcd\n"
