from __future__ import annotations

from pathlib import Path

from rosettakit import cmdfile


def build_env_file() -> str:
    env = cmdfile.CommandFile(prefix="")
    env.comment("Sizer environment")
    env.option("set_db", "design_process_node 130")
    env.blank_line()
    env.option("set_db", "design_netlist_file build/gcd.v")
    return env.build()


def write_example(path: Path = Path("examples/out/sizer/design.env_file")) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_env_file(), encoding="utf-8")
    return path


if __name__ == "__main__":
    write_example()
