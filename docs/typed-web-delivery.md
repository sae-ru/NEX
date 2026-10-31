# Explicit027 checked browser delivery

Toolchain0.151 develops ordinary027 CLI browser/project delivery. Query
`nex describe --field source_exceptions.typed_payload_development.source027_browser_delivery --json`
and retrieve this guide with `nex guide --kind typed-web-delivery --json`.
Older projects require explicit migration; changing their manifest alone does
not migrate graph state. SDK/platform acceptance remains separate.

`emitTypeScriptDelivery` produces `nex.typescript-map/2` for checked027 programs:
the concrete language, checked revision/source-bundle hash, reachable function
and operation sites, synchronous/generator execution and bounded transfer-contract
count are explicit. The existing `emitTypeScript` development027 API retains its
unarchived `nex.development-typescript/027-3` contract. Earlier languages retain
map1 and their exact generated asset identity. Generation metadata uses
`nex.web/2`; see `llm/typed-web-delivery.schema.json`.

UI title/initial/update/view/commands remain synchronous and pure. Typed handlers
can recover internally without widening those signatures. Each module Worker
selects only its own reachable client/shared closure. Synchronous compute and
structured-task compute support ordered typed/legacy catches, guards, rethrow,
finally and checked callable/data payloads inside the worker. Task mode uses the
generated immutable keyed sourceErrorContracts. Source payloads do not cross
worker messages: uncaught errors become generic E_SOURCE_EXCEPTION. Traps remain
distinct. Wire input/output continues to reject functions and authority; file,
server, IO and FFI grants are not added. Limits/cancel/lifecycle rules remain in
[browser-workers.md](browser-workers.md).

Explicit027 projects support checked capture/replay and static web packaging.
Directory roots such as `.` normalize when the trusted producer maps physical
paths; persisted dot/parent/empty path components are still rejected. A relocated
web package serves only its built assets and requires no NEX compiler or LLM.

`tests/typed_web_delivery.py` builds production UI/Worker projects, checks Node/
reference/native agreement, rejected boundaries, capture/replay/package behavior
and the genuine0.149 language026 source/library/asset fixture.
`tests/typed_web_browser.py GENERATED_PROJECT --variant async|pure --browsers-path CACHE`
tests actual module Workers in Chromium/Firefox/WebKit. Headless engine evidence
does not establish every released browser/device. npm lock and notices are unchanged.

Mac regression and installed SDK evidence are recorded below. Other platforms
and remaining original PLAN work require separate acceptance. Public CLI
selection does not certify those delivery gates.

The [0.152.1 Mac SDK receipt](releases/0.152.1.json) and
[real browser evidence](evidence/sdk-browsers-0.152.1.json) record 126 passed
production UI/Worker tests for both installed SDKs. Compiler, test driver and
preview servers run under the SDK isolation policy. The actual browser processes
use a separate same-machine Playwright server: Firefox also crashed on an empty
page under the outer SDK policy. No additional browser sandbox-disable flags were
added. Released browsers, other OSes, devices and accessibility remain separate.
The installed browser test includes its `workers-browser.spec.js` fixture.
