---
name: rosettakit-dsl
description: Build or migrate typed EDA script documents with the RosettaKit Python DSL, including RossetaKit misspellings. Use when generating Tcl fragments, Yosys global_var.tcl files, Sizer cmd/env files, or command files from Python; replacing ad hoc string concatenation with rosettakit.tcl or rosettakit.cmdfile; validating quoting, diagnostics, raw-content policy, and generated text compatibility.
---

# RosettaKit DSL

Use RosettaKit to compose typed script documents in Python and build tool-facing
text. Keep the boundary narrow: RosettaKit builds text only. Do not make it parse
Tcl, execute EDA tools, manage workspaces, or spawn subprocesses.

## Workflow

1. Locate the active RosettaKit package before editing. Prefer the repo-local
   copy or declared dependency over memory, and read its `README.md`,
   `pyproject.toml`, and touched modules when behavior may have changed.
2. Choose the backend:
   - Use `rosettakit.tcl.Script` for Tcl fragments, Yosys `global_var.tcl`,
     variable assignments, Tcl lists, command substitutions, directory creation,
     and simple `if` blocks.
   - Use `rosettakit.cmdfile.CommandFile` for flag/option files, Sizer
     `cmd_file`/`env_file` outputs, repeated options, and prefix-controlled
     command-like text.
3. Model document structure with RosettaKit nodes and value helpers. Avoid
   assembling output with f-strings, joins, or manual escaping at the call site.
4. Add `origin=` values when generated fields map back to a source config. Use
   `document.validate()` to inspect diagnostics before `document.build()`.
5. Treat generated text as a compatibility surface. Preserve line order,
   indentation, quoting style, and final newlines unless the requested change
   intentionally changes the output contract.
6. Verify with generated-output assertions or snapshots. For Tcl output, run
   `tclsh` when available. In a RosettaKit repo, prefer `uv sync`,
   `uv run pytest`, and `uv run ruff check`.

## Tcl Guidance

- Use `script.set(name, value)` for scalar Tcl words, `script.set_path(...)` for
  filesystem paths, `script.set_list(...)` for Tcl lists, and
  `script.set_expr(...)` for trusted expressions.
- Use `tcl.word(...)`, `tcl.path(...)`, `tcl.list_value(...)`, `tcl.var(...)`,
  `tcl.expr(...)`, `tcl.call(...)`, and `tcl.file_isdirectory(...)` instead of
  hand-written substitutions.
- Use `script.command(...)`, `script.file_mkdir(...)`, `script.comment(...)`,
  `script.blank_line(...)`, and `with script.if_not(...):` for document nodes.
- Avoid `tcl.raw(...)` and `script.raw_line(...)`. Use them only to preserve a
  known hand-written Tcl fragment, keep the unsafe surface small, and build with
  `allow_unsafe_raw=True` only after explicit review and tests.
- Prefer first-party Tcl verification for generated scripts that can run without
  the target EDA tool.

## Command-File Guidance

- Use `CommandFile(prefix="-")` for dashed option files and
  `CommandFile(prefix="")` for command-like env files.
- Use `cmd.flag(...)` for valueless switches, `cmd.option(...)` for one value,
  and `cmd.options(...)` for repeated options that must preserve input order.
- Mark paths with `value_type=cmdfile.ValueType.PATH`. Use `omit_empty=True` for
  optional path fields whose empty value should suppress the line.
- Keep the default Tcl-word dialect when consumers accept quoted values. Use
  `cmdfile.PLAIN_DIALECT` only when the consumer requires plain
  whitespace-delimited tokens; expect validation to reject values that need
  quoting.
- Do not place line breaks inside command-file option values. Split them into
  explicit nodes or redesign the artifact.

## Migration Discipline

- Replace ad hoc text generation at the document boundary, not unrelated tool
  behavior.
- Keep static, hand-maintained Tcl scripts outside RosettaKit unless they need
  typed parameter generation.
- When migrating existing outputs, first capture the current generated text,
  then make RosettaKit produce equivalent text before adding intentional changes.
- Do not silently pass unsafe raw content through validation to preserve old
  behavior; surface it in tests and code review.

## Reference

Read `references/rosettakit-api.md` for current API examples, diagnostics, and
verification patterns when implementing or reviewing RosettaKit DSL code.
