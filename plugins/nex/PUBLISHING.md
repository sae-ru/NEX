# Publish NEX Developer Tools

Package version: **0.1.1**. Package type: **skills only, local executor required**.
GitHub distribution and public-directory approval are separate. No directory
submission or approval is implied by the files in this repository.

## Build and check the release

1. Run `python3 tools/package_codex_plugin.py --output /absolute/path/to/artifacts`
   from the repository root. Keep the ZIP, `.sha256` and `.inventory.json`
   together. Rebuilding unchanged inputs produces the same ZIP bytes.
   Run `python3 -B tools/package_codex_plugin.py --check` from the checkout root
   to verify that its versioned ZIP, inventory and checksum match the plugin source.
2. Install the skill or plugin in a disposable application environment with a
   separately installed NEX SDK. Check capability/guide discovery, the bundled
   `hello.nex` example and a rejected candidate. Record the actual SDK and host.
3. Try representative agent requests: create a small project with tests; fix a
   diagnostic; change an existing function using symbol context. Also check
   missing SDK behavior and that an unrelated-language task does not select it.
   Compiler smoke checks do not prove an agent followed the skill or saved tokens.
4. Inspect the ZIP inventory and listing metadata. The archive contains only
   plugin instructions, references, example, artwork, documentation and licenses.
   The packager is outside the plugin; no installation script executes on import.

The SVG icons are original vector artwork supplied under MIT. The base listing
and skill instructions are in English; installation instructions are bilingual.

## Submit through OpenAI Platform

The following steps follow the official documentation checked on 2026-11-16:

- [Package format](https://developers.openai.com/plugins/build/plugins)
- [Submit and publish](https://developers.openai.com/plugins/deploy/submission)
- [Desktop execution](https://developers.openai.com/plugins/deploy/desktop-only)
- [Plugin guidelines](https://developers.openai.com/plugins/plugin-guidelines)

1. The publisher selects the OpenAI organization/project and completes developer
   or business identity verification. The manifest uses `sae-ru`, the public
   repository owner, as the proposed publisher label; the portal derives the
   actual directory developer name from the verified identity. Align the label
   with that identity if required, bump the package version and rebuild.
2. Open <https://platform.openai.com/plugins> and upload the release ZIP through
   the skills-only flow. There is no MCP server or application connection to scan.
3. Confirm the imported name, icon, category, descriptions and local-executor
   requirement. `extensions.com.openai.requires_local_executor` is `true`.
   This means desktop-only distribution and local threads, not universal cloud
   execution. If the portal rejects that field or denies submission access,
   follow its support/eligibility instructions; do not remove the requirement
   to misrepresent how the plugin works.
4. Resolve required metadata and skill findings, upload a corrected version if
   needed, then complete the publisher attestations and submit for review.
   Skills-only plugins do not require the MCP app demo and MCP review-case set.
5. Track the portal's review status. After approval, the publisher chooses
   **Publish plugin**. Keep this repository's listing status accurate.

No publisher identity verification, attestations, review or public-directory
publication has been performed by packaging this release. These remain actions
for the account owner. A future MCP integration requires separate eligibility
and packaging work; the present release makes no promise of an in-place MCP upgrade.

## Maintain a release

Increment `plugin.json`'s version when the packaged skill or assets change.
Update the bilingual README version, build the ZIP again and validate the
inventory. Preserve old release archives and evidence as versioned artifacts.
Changes to a bundled skill require a new uploaded package and review outcome.
The installed compiler remains the authority across future NEX versions.
