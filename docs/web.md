# NEX browser backend and application contract

The compiler generates TypeScript from the checked NEX graph. The application adapter renders immutable `std/web.nex` view values using React; Vite builds HTML/CSS/JavaScript. LLVM remains the native backend. Browser code does not embed the interpreter, compiler or an LLM. Toolchain 0.6.0 introduced browser HTTP commands; 0.7.0/language 0.5 adds checked endpoint declarations, generated helpers and response validation before event delivery (`docs/api.md`). General source async/await, SSR and Wasm remain unfinished.

## Build and run

Web development requires Node.js 22.18+ and npm. The checked dependency lock currently uses React/React DOM 19.3.1, TypeScript 7.0.2, Vite 8.3.4 and Playwright 1.64.1. These are exact versions in `web/package-lock.json`, rather than `latest` installs. [Vite's compatibility guide](https://vite.dev/guide/) describes its Node requirement; NEX additionally requires Node's TypeScript stripping for differential tests.

```sh
./build/nex check examples/web/main.nex
./build/nex test examples/web/main.nex --target web
./build/nex build examples/web/main.nex --target web --profile release --json
```

The build command installs the locked packages with `npm ci --ignore-scripts`, runs TypeScript checking, then runs Vite. Its JSON result reports `directory`, `dist`, `revision`, `build_key`, profile and cache status. Run `npm --prefix DIRECTORY run preview` using the returned directory, or deploy the contents of `dist` to a static host. Route URLs require a fallback to `index.html`. Hosting/deployment is not performed by the compiler. `-o NEW_DIRECTORY` copies the built assets into a new or empty directory.

For an editable generated project without installing/building dependencies:

```sh
./build/nex web examples/web/main.nex --directory build/generated-web
cd build/generated-web
npm ci --ignore-scripts
npm run dev
```

Generation requires a new or empty directory. Make program changes in NEX and regenerate. The default CSS is a small application stylesheet; asset packaging and an extension mechanism for application-specific CSS/components are pending.

The compiler's build cache checks every produced asset's hash, including source maps; modified or missing assets trigger a rebuild. Stored-revision builds use the archived NEX source bundle. Browser builds additionally need the matching installed web adapter, Node/npm and locked development packages. `NEX_NODE` selects the Node tool used for TypeScript tests, `NEX_NPM` selects npm, and `NEX_NPM_CACHE` selects its package cache. Browser runtime needs none of those development tools. `debug` disables Vite minification; `profile` and `release` retain the default production minification. All three emit source maps for generated TypeScript; the profile mode does not add a profiler.

## Application functions

The entry module defines four ordinary functions:

```nex
module counter;
import "std/web.nex" as web;

struct State { count: i64; }

client fn title() -> str { return "NEX Counter"; }
client fn initial() -> State { return State(0); }

client fn update(state: State, event: web::Event) -> State {
  if event.name == "increment" { return State(state.count + 1); }
  return state;
}

client fn view(state: State) -> web::View {
  return web::element("main", [], [], [
    web::element("h1", [], [], [web::text(title())]),
    web::element("p", [web::attr("role", "status")], [], [web::text(str(state.count))]),
    web::button("Increment", "increment")
  ]);
}
```

`initial()` returns any non-unit state type. `update(State, std::web::Event) -> State`, `view(State) -> std::web::View`, and `title() -> str` must have exactly these signatures, empty declared effects, and a `shared` or `client` realm. They need not be public. Test functions cannot be application entries. The compiler checks the standard web types' layouts before generating the adapter; a mismatched overridden library is rejected. State/view generation and updates are synchronous and pure. The adapter owns browser event handling, rendering and the optional request commands described below.

The larger `examples/web/main.nex` exercises local text input, forms, immutable updates/deletion and routing. It remains a memory-only example. `examples/fullstack/client.nex` and `server.nex` use a shared `model.nex` for persistent authenticated tasks.

## Request commands and responses

Import `std/net.nex` and optionally define this fifth pure client/shared entry:

```nex
client fn commands(before: State, after: State, event: web::Event) -> list<net::Command> {
  if event.name == "refresh" {
    return [net::request("unique-request-id", "GET", "/api/tasks", "", after.token, "response", 5000)];
  }
  return [];
}
```

The state type must match `initial`. Programs without `commands` retain their existing behavior. The adapter processes events serially: `update` computes the next state, `commands` computes its outgoing batch, and the host validates/executes the batch. React rendering does not replay commands. The initial `route` event may describe startup work. Language evaluation/tests only construct these values; they never perform network I/O. The compiler validates the exact library layouts:

```nex
pub struct Command {
  kind: str; id: str; method: str; path: str; body: str;
  token: str; action: str; timeout_ms: i64;
}
pub struct Response { id: str; status: i64; body: result<str>; }
```

Use `net::request(id, method, path, body, token, action, timeout_ms)`, `net::cancel(id)` or `net::cancel_all()`. IDs must be nonempty, at most 128 UTF-8 bytes and unique among outstanding/queued work. Use a monotonically increasing state counter and ignore responses whose ID is no longer current. A command batch has at most 64 entries and at most 32 requests may be pending. The entire batch is checked before any external action; invalid descriptors raise `E_REQUEST`. Canceling an absent ID does nothing.

Requests permit GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS, same-origin `/api/` paths up to 2048 bytes, 1..60000 millisecond timeouts and a 1 MiB body limit. GET/HEAD bodies must be empty. The adapter forbids redirects, uses no cookie credentials or response cache, and sends an optional bearer token from runtime state. It decodes response streams with strict UTF-8 and a 1 MiB byte limit. It never converts wire i64 values through JavaScript Number. The response event envelope must also fit the strict JSON wire limits; escaping can make that limit smaller than the raw response limit.

Completion dispatches `Event(action, encoded_response, current_path)`. `net::response(event)` returns `result<net::Response>` using the standard strict codec. Check the envelope, request ID, `body` result and HTTP `status`; then decode the body as the shared application model with `decode_json<T>`. HTTP 4xx/5xx are ordinary responses with their status/body. Transport failures produce body errors: `E_NETWORK`, `E_TIMEOUT`, `E_CANCELED`, `E_UTF8` or `E_LIMIT`. Their messages omit URLs, tokens and native error details. A response is delivered at most once. Unmount aborts work and suppresses late events; sign-out should clear state and issue `cancel_all`.

Cancellation/timeouts are cooperative at the server and do not prove a mutation was rolled back: it may have committed before the connection ended. Refresh to determine the durable result. The adapter does not automatically retry mutations. Out-of-order response handling belongs in the pure update function; the example checks IDs across cancellation/logout/re-entry. Tokens are entered at runtime and retained only in page memory in the example; reload requires sign-in again. Never put credentials in NEX client source or static assets. Account registration, cookie sessions and cross-origin APIs are outside this adapter's current contract.

Build both sides and serve them from the native host:

```sh
./build/nex test examples/fullstack/client.nex --target web
./build/nex build examples/fullstack/client.nex --target web --profile release --json
./build/nex build examples/fullstack/server.nex --target server --profile release --json
./build/nex token --user alice --auth /private/tmp/nex-auth.json --json
SERVER --auth /private/tmp/nex-auth.json --database /private/tmp/nex-data.sqlite --static DIST --port 8080
```

Use the reported server executable and browser `dist` paths. Open its local address and enter the issued token. TLS is configured with `--cert/--key`. The example supports creation, replacement text, completion, deletion, URL filtering, cancel/refresh, sign-out and re-entry with distinct users. Both entry files import the same public models; the server independently decodes/checks all requests and uses its injected principal partition. `examples/api` additionally generates the server dispatcher and typed client helpers from endpoint declarations. Its typed commands validate successful payloads against generated wire schemas before delivering application events; see `docs/api.md` for setup, pure helpers and schema limits.

## Views, attributes and events

`std/web.nex` exports ordinary NEX structures:

```nex
pub struct Attribute { name: str; value: str; }
pub struct Binding { event: str; action: str; }
pub struct Event { name: str; value: str; path: str; }
pub struct View {
  tag: str;
  text: str;
  attributes: list<Attribute>;
  events: list<Binding>;
  children: list<View>;
}
```

Helpers are `attr(name, value)`, `on(event, action)`, `text(value)`, `element(tag, attributes, events, children)`, `button(label, action)`, `link(label, path)`, and `input(id, value, action)`. Their signatures are also available through source/graph context.

Text nodes use `tag == "text"`; elements carry text as child text nodes. HTML text is escaped by React. The adapter accepts a defined set of semantic HTML tags, form controls and table elements. It rejects script/style/iframe/object elements, arbitrary handler attributes and inline styles. Attributes include common identifiers, form values, accessibility (`aria-*`) and `data-*` attributes; `class`/`for` map to React's `className`/`htmlFor`. Boolean attributes use `"true"` or `"false"`; integer attributes require safe integer text. URLs use HTTP(S), with `mailto:`/`tel:` additionally permitted for links. See `web/renderer.tsx` for the complete current allowlist. Unsupported tags, attributes, duplicate attributes/handlers and malformed descriptors produce `E_UI`. Rendering is limited to 10,000 nodes and depth 256 with `E_UI_LIMIT`.

Bindings support `click`, `input`, `change`, `submit` and `navigate`. The adapter sends `Event(action, value, path)` to `update`. Text controls send their current value; checkbox/radio controls send `"true"`/`"false"`. Submit prevents the browser's default form navigation. Controlled inputs update synchronously through the state function. A value without a change handler is read-only.

`link` binds `navigate` to the `route` action. Same-origin navigation updates history and dispatches the new pathname/query/hash without reloading; modifier keys, alternate targets and external origins retain normal browser behavior. Initial route, back/forward and hash changes dispatch a `route` event. An application's `update` decides how to interpret that path.

## Semantics, isolation and diagnostics

NEX `i64` becomes TypeScript `bigint` with explicit range checks on arithmetic. BigInt is never converted to a JavaScript number for arithmetic. Division/remainder, left-to-right operand evaluation, short-circuiting, lexical scope, Unicode scalar indexing/slicing, nominal equality and immutable aggregate behavior follow the reference interpreter. Conversion to JavaScript array indices happens only after bounds checking. Browser input rejects unpaired UTF-16 surrogates at the boundary. Managed values use frozen arrays/records and the JavaScript garbage collector; native reference-counted handles are a backend detail.

The emitter traverses only the functions reachable from selected client/shared entries. Server functions cannot be emitted as entries; the checker also rejects direct cross-realm calls. Unreachable definitions and their literals do not enter generated TypeScript or its source maps. Full archived sources remain local development artifacts and are not copied into browser assets. This is code separation; it does not implement server authorization or secret management.

Arithmetic, assertions and collection failures throw `NexError` with a code and original NEX file/line/column. The application boundary displays render/update failures. Vite's source maps expose generated TypeScript. `nex-map.json` maps generated function/statement lines to NEX source coordinates and function content hashes; debugger-consumable chained maps directly to NEX and graph-attributed browser profiles are pending.

For a standalone checked module:

```sh
./build/nex emit examples/data.nex --kind typescript --entry main --directory build/ts-module
```

The result contains `program.ts`, its `nex-runtime.ts` and mapping metadata. The selected function is exported as `entry`, with other emitted names qualified through the compiler's native-symbol encoding. This does not install React or require an application contract.

## Tests

`nex test --target web` runs reachable-project shared/client tests in the interpreter and in generated TypeScript using Node, comparing successful exit/output. Server tests are explicitly reported as skipped. This checks language semantics and is distinct from browser UI tests. Native tests remain `nex test` without the web target; a client test is not a native entry.

Language 0.4's result<T> and typed JSON also compile to the browser backend. Wire i64 values use canonical decimal strings; decode_json<T> reconstructs BigInt/nominal immutable values and returns recoverable errors. Strict duplicate-key, Unicode, field-shape and resource checks match the native/interpreter codec. The request adapter uses this boundary; codecs themselves remain pure.

Every generated application includes a Playwright smoke test. After installing matching browsers with `npx playwright install`, `npm test` checks mounting on Chromium, Firefox and WebKit. The repository also provides opt-in real-build and application interaction checks:

```sh
python3 tests/web_build.py ./build/nex --npm-cache /path/to/npm-cache
python3 tests/web_browser.py RETURNED_BUILD_DIRECTORY --browsers-path /path/to/playwright-browsers
python3 tests/fullstack_browser.py ./build/nex FULLSTACK_BUILD_DIRECTORY --browsers-path /path/to/playwright-browsers
```

The second command targets the built `examples/web` project. It checks production assets in all three browser engines, then exercises renderer rejection cases against the development module. The third targets built `examples/fullstack/client.nex` output, compiles its matching native server and verifies actual multi-user CRUD/reload/re-entry plus injected network/schema/Unicode/size/timeout/cancellation failures and persistence after server restart. A test-only forwarding proxy supplies a real same-origin redirect because WebKit's interception cannot synthesize a 302; normal API/static requests are forwarded to the compiled server. Headless engine checks do not establish support for every released browser, device or assistive technology.

On macOS WebKit the keyboard scenario uses Option+Tab for full link traversal under the default focus preference, followed by Enter activation and keyboard form submission. This follows [WebKit's documented link-focus preference](https://developer.apple.com/documentation/webkit/wkpreferences/tabfocuseslinks); the application does not override the user's browser navigation settings.

Toolchain 0.15 adds deterministic operation sites to the TypeScript map and as an optional fourth item of runtime error locations. Only emitted reachable client/shared functions receive operation-site tables. This metadata is not a browser debugger source-map implementation; native/browser execution semantics, package lock and third-party dependencies are unchanged. See [operations.md](operations.md).

Language 0.6 permits enums as application state and data. `examples/enums/web.nex` uses typed cases and exhaustive match statements for update/view. The TypeScript emitter narrows a private symbol discriminator; wire case/fields wrappers are validated at typed request boundaries. Existing web Event/View/Command library layouts remain the adapter contract.

Language 0.9 emits concrete generic specializations rather than JavaScript generic dispatch. `examples/generics/web.nex` uses bounded State<T: add>, a parametric transition helper an integer-constrained counter helper and a record-pattern update match; the standard application signatures and browser dependency lock remain unchanged. Build it with --target web, then run `python3 tests/generics_browser.py BUILD_DIRECTORY --browsers-path PATH` for the opt-in three-engine interaction check.
