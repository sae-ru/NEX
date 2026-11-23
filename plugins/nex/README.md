# NEX Developer Tools

[Русский](README.ru.md) · [NEX](https://github.com/sae-ru/NEX) · [Publishing](PUBLISHING.md)

An MIT-licensed skill and plugin for writing applications in **NEX — Neural
Execution Language**. It discovers the installed compiler's capabilities,
retrieves focused language guides and symbol context, then checks a coherent
change with the compiler and relevant tests.

**Plugin version: 0.1.1.** This is independent of the NEX SDK/source-language
version. This GitHub package is available for installation; an OpenAI directory
listing has not been submitted or approved.

[Download the catalog ZIP](https://github.com/sae-ru/NEX/raw/refs/heads/main/plugins/releases/nex-developer-tools-0.1.1.zip)
and check its [SHA256](../releases/nex-developer-tools-0.1.1.sha256).

## Install the skill from GitHub

In Codex, ask:

```text
Use $skill-installer to install nex-programming from
https://github.com/sae-ru/NEX/tree/main/plugins/nex/skills/nex-programming
```

Then start a task with:

```text
Use $nex-programming to create a small NEX application with source tests.
Use my installed SDK and explain how to run the result.
```

If the new skill is not visible, restart Codex. A manual alternative is to copy
the entire `skills/nex-programming` directory into `.agents/skills/` in an
application repository, or `~/.agents/skills/` for a user-wide installation.
Preserve the references, example and license with `SKILL.md`. Do not install
both a standalone copy and the plugin unless you intend to maintain both.

## Install the GitHub plugin

With a current Codex CLI, add the repository marketplace:

```sh
codex plugin marketplace add sae-ru/NEX --ref main
```

Open the desktop Plugins view, select **NEX Developer Tools** as the marketplace
source, and install **NEX Developer Tools**. Clients exposing `codex plugin add`
can instead run:

```sh
codex plugin add nex-developer-tools@nex-plugins
```

Use `codex plugin --help` to check the commands available in your client. The
GitHub marketplace is separate from the public OpenAI directory. It does not
change workspace/admin installation policies.

For a local checkout, `codex plugin marketplace add /absolute/path/to/NEX` uses
the same `.agents/plugins/marketplace.json`. Installation is opt-in; the
marketplace declares availability, not automatic installation.

## Requirements and behavior

- Install a NEX SDK separately using the
  [installation guide](https://github.com/sae-ru/NEX/blob/main/docs/getting-started.en.md).
  The plugin does not bundle a compiler or add commands to PATH.
- Run it where Codex has a local executor and access to the application project.
  The catalog package declares `requires_local_executor: true`.
- Existing projects retain their selected language and dependency pins. The
  skill asks the compiler for exact features instead of assuming a fixed version.
- It supports NEX application work. Contributions to the C++ compiler follow
  the NEX repository's contributor instructions.
- It adds no MCP server, authentication, telemetry or hosted service. Source
  and command output remain subject to the normal data handling of the user's
  chosen coding agent. Running the user's application can have its own effects.
- Backend, GPU/NPU, platform and deployment support depend on the selected SDK
  and its acceptance evidence. No overall token saving is asserted by this package.

## Prepare a catalog ZIP

From the NEX repository root, with Python 3.9 or newer:

```sh
python3 tools/package_codex_plugin.py --output /absolute/path/to/artifacts
```

This creates `nex-developer-tools-0.1.1.zip`, an inventory and a SHA256 file.
The ZIP has `plugin.json` at its root and includes only the explicitly listed
plugin files. See [PUBLISHING.md](PUBLISHING.md) for verification, submission
steps and the remaining publisher-owned actions.

Plugin packaging does not rebuild or qualify the NEX compiler or SDK.
