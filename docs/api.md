# Checked endpoint contracts and generated API projects

Toolchain 0.7.0 / source language 0.5 adds explicit endpoint declarations. The compiler derives request/result codecs, a native dispatcher, pure client helpers and [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html) documentation from one checked graph. This does not make an ordinary client-to-server function call legal.

## Declare an endpoint

```nex
module example_api;
import "std/api.nex" as api;

pub struct Create { text: str; }
pub struct Row { id: i64; text: str; }

endpoint create_row("POST", "/api/rows", 201) = create;

server fn create(context: api::Context, input: Create) -> result<Row> {
  if len(input.text) == 0 { return err("VALIDATION", "Text is required"); }
  return ok(Row(1, input.text));
}
```

Syntax is `endpoint NAME("METHOD", "/api/path"[, SUCCESS_STATUS]) = handler;`. A handler is an ordinary non-test server function with `std::api::Context` first, optional typed input second, and `result<Output>` as its result. Context has exactly `user: str` and `request_id: str`; the authenticated host supplies it. A client request body cannot replace it. Effects remain explicit on the handler and are propagated into generated dispatch functions.

Endpoints are public transport contracts even when their local implementation function is private. Cross-module handler references use ordinary import aliases and require a public handler. Input/output structures and their exposed field types must be public. Scalars, strings, nested lists/results and recursive immutable records use the same strict wire semantics as `decode_json`; arbitrary JSON numbers, unknown fields, duplicates and malformed Unicode are rejected.

Operation names are unique across the loaded API; a name must also be distinct from functions/structures in its declaring module. An endpoint is not callable in a source expression. Supported methods are GET/POST/PUT/PATCH/DELETE. GET has context only. Routes are fixed normalized `/api/` paths of at most 256 ASCII bytes using letters, digits, `/`, `_`, `-` and `.`; empty/dot traversal segments are rejected. A method/path pair is unique. Success defaults to 200 and may be any 2xx except bodyless 204/205. Query parameters, path templates, streaming/file bodies and inferred overloads are not implemented by this contract.

## Inspect and generate

```sh
nex check service.nex --json
nex api service.nex --json
nex context --symbol create_row --json
nex api service.nex --directory generated --json
```

Without `--directory`, `api` returns `nex.api/1`: endpoint identities, methods/routes/statuses, checked handler signatures/effects, wire input/result schemas and generated helper names. `context` includes the declaration, handler source, imports and referenced structures. Endpoint nodes have stable local IDs, content hashes and edges to handlers in the graph. Revision identity includes endpoint contracts; changes to a route or handler affect the checked program revision.

`nex apply` accepts an endpoint replacement in the existing revision-checked `replacements` format. It can change endpoint and function definitions together; the whole candidate must still typecheck before commit. Changes do not rewrite working files. Use `--revision HEAD` for subsequent graph commands, and export to materialize a revised project. Adding/removing declarations still uses the source/export workflow.

Generation requires a new or empty output directory. Both candidate projects are checked before final output, and a temporary sibling directory is renamed into place only when generation succeeds. The output contains:

- `server/`: complete frozen original sources, generated typed routers/entry, vendored dependencies, project manifest and lock. Build its reported entry with `--target server`.
- `client/api.nex`: pure `request_OPERATION` and `response_OPERATION` helpers. Client models keep their original nominal module names in `client/models/MODULE/PATH.nex`. Only required model declarations are extracted from application modules. Captured standard/package dependencies retain their public client/shared surface and reachable private helpers/types; server/test declarations and unused private code are removed, including from overridden libraries. Unneeded imports/files and text outside retained declarations are excluded.
- `api.json`: exact NEX endpoint/wire descriptors.
- `openapi.json`: OpenAPI 3.1.1 paths, operation names, bearer authentication and schemas. Wire i64 uses an exact canonical signed-64-bit decimal-string pattern. NEX's additional UTF-8, duplicate-key and aggregate resource checks remain authoritative.

Generated output is an editable materialization for building, not another source of truth. Regenerate from reviewed source changes. Captured dependencies are pinned. When importing the SDK into another project, use its extracted model files instead of loading another physical copy of the same nominal module. Use a matching language/standard-library version and lock dependencies. Source packages containing different files with the same logical module remain rejected.

## Native request behavior

Run the generated server using the authentication, SQLite, static asset and TLS options in `docs/server.md`. Every application route still requires bearer authentication, and storage remains partitioned by the host's principal. The generated dispatcher:

1. Selects the declared method/path and rejects undeclared query/body data.
2. Strictly decodes the optional input and calls the checked handler with host context.
3. Encodes `result<Output>`: success uses the declared success status, handler errors use 422. The payload is tagged, for example `{"ok":{"id":"1","text":"saved"}}`.
4. Returns typed errors for invalid input (400), method mismatch (405) and unknown endpoint (404).

Non-success statuses roll back request transactions. Host authentication/limits/traps retain their own status/body boundary and do not masquerade as typed success. A handler's explicit error code/message is public API data; native trap diagnostics remain sanitized. Generated routing does not replace application authorization rules or validation such as text lengths.

## Typed client commands

```nex
let work: net::Command = api::request_create_row(
  request_id, runtime_token, model::Create(text), "created", 5000
);
```

Request helpers return immutable `typed_request` commands with a compiler-generated result schema. The actual HTTP body contains only the encoded input; the schema stays in the client. The browser adapter strictly checks successful response bodies against that schema **before** creating an application response event. Invalid success data becomes `E_JSON` with a sanitized message. No invalid payload reaches update as a successful body.

`response_OPERATION(event) -> result<Output>` checks the envelope, transport failure, expected success status and tagged result. It preserves explicit handler errors and falls back to `HTTP_STATUS` errors for host responses that are not typed endpoint data. Unexpected successful statuses or an error result with a success status return `E_API_PROTOCOL`. These helpers are pure and agree across interpreter/native/TypeScript execution; they do not perform I/O themselves.

Application state still owns unique request IDs, loading state, stale-response rejection and sign-out/re-entry. Use the optional `commands` entry from `docs/web.md`; cancellation, timeout/body/pending limits and uncertain mutation outcomes remain unchanged. Typed command control data uses a strict `std::net::TypedPayload` envelope. Result schemas are bounded to 256 KiB, 1,024 record definitions, 1,024 fields per record, depth 64 and 10,000 descriptor nodes; invalid descriptors reject the complete batch before any action. The existing 1 MiB command envelope limit includes schema/body escaping.

## Complete example

From the repository root, generate before building the client:

```sh
./build/nex api examples/api/service.nex --directory examples/api/generated --json
./build/nex test examples/api/client.nex --target web --json
./build/nex build examples/api/client.nex --target web --profile release --json
./build/nex build examples/api/generated/server/_nex_api_server.nex --target server --profile release --json
```

The generated entry path is reported in the result; do not assume it when an original source already uses that filename. Provision tokens with `nex token`, then launch the server with `--auth`, `--database` and `--static DIST`. The client demonstrates persistent task CRUD using generated helpers and extracted shared models. Generated example directories are excluded from SDK installation; run the generator there before building that example.

Language 0.4 revisions require explicit `nex migrate`; their source bundles and earlier history are retained. `endpoint` is contextual at the top level, so old function/local names remain valid. The 0.4 browser `Command` and `Response` layouts are unchanged; ordinary `net::request` calls remain supported. To add typed helpers to an archived project, export it, review/update its standard-library sources/lock and regenerate the API under 0.5.

## Language 0.6 enum models

Public enum input/output models generate `nex.wire/2` descriptors, extracted NEX enum declarations and OpenAPI oneOf branches with exact case/fields objects. Payload i64 values remain decimal strings. The native dispatcher rejects unknown cases, duplicate/unknown/missing fields and wrong payload types before handler execution. Typed browser requests validate successful enum results before delivering events. Old wire/1 scalar/record descriptors remain accepted by the browser adapter. Regenerate clients after migration rather than mixing nominal definitions from duplicate physical model files.

Language 0.7 concrete generic models retain full nominal argument identities in wire/2. Extraction writes each original public struct/enum template once, imports required type arguments (including phantom arguments), and prints checked type applications in generated helper signatures. Server and browser projects are rechecked after projection; derived instance declarations never appear as duplicate source definitions. Generic endpoint handlers themselves must be wrapped by a concrete server handler.

Language 0.8 model extraction retains builtin parameter bounds in each original public struct/enum declaration; generated projects recheck those bounds. A generated bounded model cannot be instantiated with a disallowed type. Wire encoding of concrete values is unchanged.

Language 0.11 numeric models use f64 as a finite JSON number with OpenAPI type number / format double and x-nex-type f64. The checked wire codec enforces binary64 rounding/finite-value rules at the native/browser boundary; OpenAPI format annotations do not replace runtime validation. i64 retains its exact canonical string encoding.

Language 0.13 bytes models use canonical padded base64 JSON strings. OpenAPI
marks them with `contentEncoding: base64`, `contentMediaType:
application/octet-stream` and `x-nex-type: bytes`; the runtime enforces alphabet,
padding and unused-bit rules. Encoding and result wrappers count against the
JSON/body limits. Generated models retain the primitive type; they do not expose
mutable typed arrays. Nominal wire descriptor objects keep their existing meaning.

Language 0.16 model extraction retains constructor parameter arities, custom
bounds and associated type projections. Application model modules carry the
required type-only traits and selected implementation heads/associated aliases,
including transitive bound witnesses. They preserve nominal module/type argument
identities and recheck model bounds. Method signatures, method bindings and their
function bodies are omitted from this model-only projection; importing an
extracted model does not provide the original trait's callable API. Import a
reviewed client/shared library for that API. No server method is replaced by a
stub. Concrete wire layouts continue to come from the original checked graph.

This source-0.16 adapter is under validation. Full current regression, installed
SDK/platform checks and trait-bearing captured library projection remain pending;
the descriptor and `STATUS.md` retain that scope.
