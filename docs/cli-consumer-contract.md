---
status: current
applies_to: "toolchain 0.281.0; language 0.30"
owner: repository
---

# Proposed 1.0 CLI contract for a native project

`nex.cli-consumer/1` is a proposed contract for tools that create, check, test
and run an ordinary 0.30 project. The 1.0 release and compatibility promise are
pending. The profile names the fields an integration can read from each
successful invocation with `--json`. Its identifier belongs to this profile.
Each command retains its own response format.

| Invocation (append `--json`) | Required response fields | How a consumer uses them |
| --- | --- | --- |
| `nex describe --field project_languages` | `schema` = `"nex.discovery/1"`, `kind` = `"field"`, `field` = `"project_languages"`, `toolchain` string, `value` array of strings | Read the toolchain version and check that `value` contains `"0.30"`. |
| `nex init DIR --language-version 0.30` | `ok` = `true`, `directory` string | Open `nex.json` in the returned directory and use its declared `entry`. |
| `nex check` | `ok` = `true`, `revision` string of 64 lowercase hexadecimal digits | Pin a subsequent invocation with `--revision`. |
| `nex test` | `ok` = `true`, `tests` array of objects, each with `name` string, `ok` boolean and `native` boolean | Locate a declared test by its qualified name and check that it passed and ran natively. The profile covers native projects with ordinary unit tests. |
| `nex eval` | `ok` = `true`, `stdout` string, `value` JSON integer for an `i64` entry | Read captured program output and the signed 64-bit return value. Choose an integer-preserving JSON decoder for large values. |
| `nex run` | `ok` = `true`, `stdout` and `stderr` strings, `exit_code` JSON integer | Read the native process streams and exit code. |

Check the CLI process exit status before decoding a success response. Read
strings as UTF-8 and preserve embedded newlines in captured output. Consumers
ignore unrecognized object members, including members of individual test rows.
They look up test names and supported versions by value. The full discovery
schema and the project manifest have their own versioned producer contracts.
[Discovery schema](../llm/discovery.schema.json) · [Project schema](../llm/project.schema.json)

The executable check creates a separate project with each SDK, writes the same
program using a 0.30 cell and checks that both revisions match. It verifies the
native test, the printed result `42`, the return value `0` and a revision-pinned
`i64` result of `9223372036854775807`. It then adds unknown fields to the real
responses and tries a missing field, a value of the wrong JSON type and an
incorrect result of the right type for each command.

On macOS ARM64, published beta 0.280.1 and candidate 0.281.0 produced the
same revision and results. Each accepted seven added members and rejected
all 18 incompatible mutations. [Recorded cross-SDK run](evidence/cli-consumer-0.280.1-to-0.281.0-2026-11-23.json)

```sh
python3 -B tools/sdk_compat_cli.py --baseline /path/to/beta/bin/nex \
  --candidate /path/to/candidate/bin/nex --output build/cli-compatibility-run
```

Use a new output directory for each run. [Executable consumer and evidence checks](../tools/sdk_compat_cli.py)
