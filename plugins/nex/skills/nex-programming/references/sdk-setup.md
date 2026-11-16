# Select a NEX SDK

Read this when `nex` is missing, a project selects another SDK, or a new user
asks how to start. Installation choices belong to the user and the project.

- Use the project's configured executable or SDK first. Locate it with
  `command -v nex` in a POSIX shell or `Get-Command nex` in PowerShell.
- If none is installed, use the official
  [installation guide](https://github.com/sae-ru/NEX/blob/main/docs/getting-started.en.md)
  ([Russian](https://github.com/sae-ru/NEX/blob/main/docs/getting-started.ru.md))
  and [releases](https://github.com/sae-ru/NEX/releases). Choose an actual
  published artifact for the host. Availability of source code for a platform
  does not establish that a portable SDK exists for it.
- For a source build, follow that checkout's README and prerequisite versions.
  Do not silently replace an existing SDK or change global configuration.

Use an absolute executable path if more than one SDK is available. In
PowerShell, invoke a quoted path with `&`. Discover the selected compiler before
using language features; compiler fallback and a project's explicit source
language can differ.

For a new project, the ordinary flow is:

```sh
nex describe --kind index --json
nex init my-app
cd my-app
nex guide --kind prompt --json
nex guide --kind quick --json
nex check --json
nex test --json
nex run --json
```

The scoped discovery and guide steps depend on the installed SDK; use the
fallbacks in SKILL.md when needed. SDK native compilation can require external
host tools; use `nex doctor --json` and the matching installation guide to diagnose
missing prerequisites. The plugin does not install LLVM, Node or platform SDKs.

Keep authored `.nex` files, `nex.json`, build manifests, dependency locks, tests,
assets and required authored host code under version control. Preserve graph
history with the SDK's documented export/snapshot workflow if it is part of the
project. Do not add generated build output or a live graph database indiscriminately;
use the SDK's project/source-control guidance for the selected graph format.

If only documentation is available, explain that executable validation has not
been performed; do not report a successful build from reading examples.
