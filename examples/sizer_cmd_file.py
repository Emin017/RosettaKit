from __future__ import annotations

from pathlib import Path

from rosettakit import cmdfile


def build_cmd_file() -> str:
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
    return cmd.build()


def write_example(path: Path = Path("examples/out/sizer/design.cmd_file")) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_cmd_file(), encoding="utf-8")
    return path


if __name__ == "__main__":
    write_example()
