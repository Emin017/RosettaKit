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
