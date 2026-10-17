# NEX language specification 0.5

This document describes the implemented language, independently of any LLM provider. Planned features live in `PLAN.md`. The compiler's `nex describe --json` reports its language version and capabilities.

## Source and program structure

Source is UTF-8; identifiers currently use ASCII letters, digits, and `_`, beginning with a letter or `_`. Keywords are reserved, except contextual `result`/`endpoint` described below. `//` starts a line comment. Whitespace and comments have no semantic meaning. Each file contains one module declaration followed by imports, structures, functions and optional endpoint declarations. Module names may have `::`-separated components. Diagnostic columns count source bytes, and diagnostics include the source file.

```nex
module arithmetic;

fn square(x: i64) -> i64 {
  return x * x;
}

fn main() -> i64 !{io} {
  print(square(12));
  return 0;
}

test fn square_test() -> unit {
  assert(square(12) == 144);
}
```

All function parameters and return types are explicit. Definitions may refer to functions defined later. Recursion is supported. Native application entries take no arguments and return `i64` or `unit`. An `i64` application result is converted to the platform's process exit status; use `print` or `eval --json` to observe full-width results. `unit` entries exit successfully.

## Modules, imports and libraries

```nex
// src/model.nex
module example::model;

pub struct User { name: str; }

fn normalize(name: str) -> str { return name; }

pub fn create(name: str) -> User {
  return User(normalize(name));
}
```

```nex
// src/main.nex
module example::app;
import "./model.nex" as model;
import "std/text.nex" as text;

fn main() -> unit !{io} {
  let user: model::User = model::create("Ada");
  print(text::join([user.name, "NEX"], " + "));
}
```

Definitions are private to their file's module unless prefixed with `pub`. A public function's parameter/result types and a public structure's field types may contain only public structures, including nested list element types. Imported names use exactly `alias::name`; the alias is local to the importing file. A module's fully qualified name is its logical identity, independent of its path. Each reachable file must declare a distinct module name. Multiple aliases may refer to the same file. Imports are not re-exports, and cyclic module imports are rejected; recursion among functions inside a module is supported.

Relative imports begin with `./` or `../` and stay within the current project or library root, including after symlink resolution. Bare paths such as `numbers/math.nex` name a library registered in the project's `nex.json`:

```json
{
  "entry": "src/main.nex",
  "language": "0.5",
  "libraries": { "numbers": "../numbers-library" }
}
```

Library roots can be absolute or relative to the project root. `std/` defaults to the compiler's installed `lib/`; an explicit `libraries.std` overrides that root, allowing a frozen exported project to vendor its exact standard library. `std/math.nex` exports `min`, `max`, `clamp`, `abs`; `std/text.nex` exports `starts_with`, `ends_with`, `join`. These use the same checked arithmetic and Unicode rules as application source. Import depth is limited to 128. Native module object reuse is available in toolchain 0.9; call contracts and referenced layouts participate in invalidation. Remote package retrieval and finer-grained frontend/function caching remain pending. See [the build guide](incremental.md).

`nex lock` records content hashes of the reachable library and standard-library sources in `nex.lock.json`. Source-based checks/builds enforce existing pins. After reviewing a dependency change, run `nex lock` explicitly to update its pins. Local application sources are not pinned. Unused pins remain available for other entry points in the project. See the protocol for snapshots and portable export.

## Types and values

| Type | Values |
|---|---|
| `i64` | Signed integers from -9223372036854775808 through 9223372036854775807 |
| `bool` | `true`, `false` |
| `unit` | No result; only as a function result or expression result |
| `str` | Immutable valid UTF-8 text |
| `list<T>` | Immutable homogeneous sequence of non-unit values |
| `result<T>` | Immutable success containing T, or an error with code/message |
| Named structure | Immutable value with declared, typed fields |

There are no implicit numeric/boolean conversions. Parameters, locals and collection elements cannot have type `unit`. There are no source-level pointers, reference identity, null values or manual memory operations. General user-defined generics, mutable collections and custom destructors remain unimplemented.

Decimal integer literals have no separators or suffixes. Negative values use unary `-`; the minimum i64 literal is accepted explicitly. Positive literals outside the range are rejected.

### Strings and Unicode

String literals use double quotes and JSON escape rules: `\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`, `\t`, and `\uXXXX`. A surrogate pair encodes a supplementary scalar; an unpaired surrogate is invalid. Raw control characters and malformed UTF-8 are rejected. Embedded U+0000 is supported through an escape.

`len(text)`, `text[index]` and `slice(text, start, count)` operate on Unicode scalar values, not bytes or user-perceived grapheme clusters. Indexing returns a one-scalar `str`. Slices use a start and count; an empty slice at the end is valid. Negative or out-of-range indices and slices terminate with `E_BOUNDS`. Strings are not normalized automatically. Concatenation uses `+`; equality compares exact content.

### Lists and structures

```nex
struct User {
  id: i64;
  name: str;
  tags: list<str>;
}

fn example() -> User {
  let tags: list<str> = ["nex", "web"];
  return User(7, "Ada", tags);
}
```

A structure's qualified module/name is its nominal type and its positional constructor. Equal-looking structures in different modules have different types. Constructor arguments follow field declaration order. Field selection uses `value.name`. Fields must have distinct names and non-unit types. Structures can refer to other structures, including recursively through lists; values are constructed from already initialized values.

Lists use `[a, b]`; nested lists are supported. An empty list needs an element type from a variable declaration, return signature, parameter, constructor field, or another contextual type. `push([], value)` can infer its element type from the value. An unconstrained `[]` is rejected with `E_INFER`. Indexing is checked; lists concatenate using `+`.

`push(list, value)` returns a list with an appended item. `set(list, index, value)` returns a list with one replaced item and checks the index. Earlier values and aliases remain unchanged. `==`/`!=` compare list contents recursively; structure equality requires the same nominal type and compares its fields recursively. Ordering comparisons are currently integer-only.

Heap-backed values have automatic reference-counted ownership. Parameters borrow values during a call; returned values remain valid independently of the caller's temporaries. Assignment releases the previous owned value; block exit and return release local values. Immutable aggregates can share their children, and source programs cannot form mutable reference cycles. Native application/test wrappers verify that normal execution released all managed values. This is the implemented ownership model; a future mutable/resource/concurrent model needs additional rules.

### Recoverable results

```nex
fn parse(text: str) -> result<i64> { return decode_json<i64>(text); }

fn example() -> i64 {
  let value: result<i64> = parse("\"42\"");
  if is_ok(value) { return unwrap(value); }
  return 0;
}
```

`ok(value)` creates a success. `err(code, message)` needs an expected `result<T>` type from context; `err<T>(code, message)` states it explicitly. Payloads cannot have type unit. `is_ok(result)` returns bool. `unwrap(result)` returns T and traps with `E_RESULT` on an error. `error_code` and `error_message` return the error's strings, or empty strings on success. Results may contain other results, lists and structures; they follow immutable ownership and structural equality with statically matching payload types. Display formatting is `{"ok":VALUE}` or `{"error":{"code":"CODE","message":"MESSAGE"}}`. The word `result` is contextual in a type followed by `<`; existing local names such as `var result: str` remain valid.

Recoverable errors are data and require no io effect. Arithmetic, bounds and assertion failures retain their trapping behavior. A result is not an exception handler; general exceptions, user-defined variants and pattern matching remain unimplemented.

### Typed JSON boundary

`encode_json(value) -> str` serializes a non-unit value using `nex.wire/1` rules. Every i64 is a canonical decimal **JSON string**, preserving all 64 bits across browsers. Booleans/text remain JSON booleans/strings, lists become arrays, and structures become objects with declared field names. Nominal type names are restored from the checked destination type rather than transmitted as user-controlled tags. Results use the tagged display shape above, with their payloads encoded recursively. Ordinary print/str formatting still prints integer numbers without wire quoting.

`decode_json<T>(text) -> result<T>` validates and reconstructs exactly T. It rejects numeric JSON values for i64, noncanonical/range-invalid decimal strings, duplicate keys (including escaped equivalents), malformed UTF-8/surrogates, unknown/missing fields and incorrect value kinds. The current limits are 1 MiB of encoded text, depth 64, 10,000 collection items and 100,000 decoded value nodes. Decoding failures return `E_JSON` error values; encoding beyond limits traps with `E_JSON`. No implicit conversions or silent repairs occur. Only `decode_json<T>` and `err<T>` have explicit call-site type arguments today; general user-defined generic functions are pending.

The wire decoder accepts one optional leading UTF-8 byte-order mark, counted against the byte limit, consistently in all backends. A BOM inside a string value is ordinary text and remains intact. Decimal i64 strings reject every extra character, including trailing line terminators; JSON whitespace outside a value follows normal JSON parsing rules.

## Variables and scope

```nex
let limit: i64 = 10;
var total: i64 = 0;
total = total + limit;
```

`let` and parameters are immutable; `var` is mutable. Every local has an explicit type and initializer. The initializer is evaluated before the new binding is visible. Assignment preserves the declared type. A name can be declared once in a block; nested blocks can shadow outer names. A block's locals disappear when it exits.

## Expressions and evaluation

Precedence from lowest to highest (binary operators associate to the left):

1. `||`
2. `&&`
3. `==`, `!=`
4. `<`, `<=`, `>`, `>=`
5. `+`, `-`
6. `*`, `/`, `%`
7. Unary `-`, `!`
8. Field selection and indexing
9. Literals, local names, function/constructor calls, parenthesized expressions

Operands, list items and call/constructor arguments evaluate left to right. `&&` and `||` evaluate their right operand only when required. Logical operators require `bool`; integer arithmetic and ordering require `i64`. `+` also accepts two strings or lists of the same type. Equality accepts two operands of the same non-unit type.

Integer overflow traps with `E_OVERFLOW` in every build profile. Division truncates toward zero. Remainder has the sign of the dividend. Division/remainder by zero traps with `E_DIV_ZERO`. `MIN_I64 / -1` traps; `MIN_I64 % -1` equals zero. Negating `MIN_I64` traps. Optimizations must preserve these rules.

## Control flow

```nex
var i: i64 = 0;
while i < 10 {
  if i == 5 {
    return i;
  } else {
    i = i + 1;
  }
}
return 10;
```

Conditions must be `bool`. `else if` is supported. `return expression;` ends the function; `return;` returns unit. A unit function may fall through. Every path in a value-returning function must return. A loop alone is not considered proof of a return. Statements after an unconditional return are rejected. There is no `break`, `continue`, exception handling, or pattern matching yet.

## Effects and execution realms

A function declares effects after its return type: `!{io}` or `!{db, io}`. Omitting the declaration means an empty effect set. Current effects are `io` and database access `db`; declaring `db` currently requires a server function. Calling a function requires its effects to be included in the caller's declaration; the compiler checks the call graph through declared signatures. An assertion failure or arithmetic trap is a deterministic terminating error and does not require `io`. Environment and storage builtins require a server realm as well as their effect.

Optional `shared`, `server`, or `client` precedes `fn` (and precedes `test` for a test definition); `pub`, when present, precedes the realm. The default is `shared`. A function may directly call shared functions or functions in its own realm. These checks apply across imports. Direct client/server calls and shared/platform-specific calls are rejected with `E_REALM`. This is a static boundary, not a network-call implementation. Client-entry native builds and server-entry TypeScript emission are rejected. Browser applications use the checked state/update/view contract in `docs/web.md`; the browser emitter includes only reachable client/shared functions.

The browser adapter additionally accepts a pure `commands(before: State, after: State, event: web::Event) -> list<net::Command>` entry with `std/net.nex`. Commands are ordinary immutable values describing same-origin HTTP work or cancellation; constructing one performs no I/O in any language backend. The adapter executes them after a UI/response transition and delivers strict typed response envelopes as events. This adds a library/adapter contract in toolchain 0.6.0 without changing the 0.4 grammar, source semantics or revision format. General source async/await remains pending. Language 0.5 endpoints generate typed request/response helpers; see the web/API guides for contracts and limits.

## Endpoint declarations

Language 0.5 adds `endpoint NAME("METHOD", "/api/path"[, SUCCESS_STATUS]) = handler;` at module scope. A handler must be a non-test server function taking authenticated `std::api::Context` and optional typed input, and returning `result<Output>`. GET takes context only. Input/output models must expose public types. The compiler checks fixed routes, methods, body-bearing success statuses, unique operation names/method-path pairs and bounded wire schemas. Declaring an endpoint performs no I/O and does not make a source-level client/server call legal. `endpoint` is contextual here; a function/local named endpoint remains valid.

Endpoints participate in program identity, graph nodes/edges, context, archived source bundles and atomic replacement patches. `nex api` describes contracts or generates checked server/client projects and OpenAPI. Native and TypeScript backends still execute ordinary checked functions; generated client helpers construct pure request descriptors, while the browser host validates successful response data against the generated schema before callback delivery. See `docs/api.md` for complete syntax, limits, HTTP statuses, generated artifacts and the explicit 0.4 migration path.

## Builtins

- `print(value)` accepts any non-unit value and requires `io`. Strings are written as their raw text, including embedded zero bytes. Other values use a JSON-style representation, including recursive lists/structures. It adds a newline and returns `unit`.
- `assert(condition)` requires `bool`, returns `unit`, and traps with `E_ASSERT` when false.
- `len(str | list<T>) -> i64` returns a Unicode scalar count or list item count.
- `str(value) -> str` explicitly formats any non-unit value using the same representation as print, without a newline. A string's content is unchanged.
- `push(list<T>, T) -> list<T>` and `set(list<T>, i64, T) -> list<T>` return updated immutable lists.
- `slice(str, i64, i64) -> str` returns a checked Unicode scalar slice.
- `contains(str, str) -> bool` checks for an exact substring; the empty substring is contained in every string.
- `ok(T) -> result<T>`, `err<T>(str, str) -> result<T>`, `is_ok(result<T>) -> bool`, `unwrap(result<T>) -> T`, `error_code(result<T>) -> str`, `error_message(result<T>) -> str` implement recoverable outcomes.
- `encode_json(T) -> str`, `decode_json<T>(str) -> result<T>` implement the strict wire rules above.
- `read_env(str) -> result<str> !{io}` is server-only. Missing names return `NOT_FOUND`; invalid names return `VALIDATION` and invalid value encoding returns `E_UTF8`.
- `store_get(str) -> result<str>`, `store_put(str, str) -> result<bool>`, `store_remove(str) -> result<bool>`, and `store_keys(str) -> result<list<str>>` are server-only and require `db`. Their resource/transaction boundaries are specified in `docs/server.md`.

Builtin names cannot be redefined. Function and local namespaces are separate.

## Tests

`test fn name() -> unit { ... }` declares a test, with optional declared effects. Test functions take no parameters, return unit, and cannot be called as ordinary functions. `nex test` runs tests in all reachable modules in the interpreter and as separately built native entries, checking successful exit and identical output. Assertions specify expected behavior. `--interpreter-only` omits the native comparison.

`nex test --target web` instead compares the interpreter with generated TypeScript running in Node. It executes shared/client tests and explicitly reports server tests as skipped. Client tests require the web target for compiled execution. Browser interaction tests are a separate Playwright layer described in the web guide. Both backends preserve the arithmetic, Unicode, evaluation-order and immutable-value semantics above; JavaScript uses checked BigInt arithmetic and its garbage collector.

The interpreter has a configurable step budget (default 1,000,000) and a call depth limit of 256. These are evaluation resource limits and are not native program limits. Native programs currently use the host process stack.

## Graph and revision semantics

Each checked function and structure has a canonical structured representation. BLAKE3 hashes identify function content and program revisions. Program identity includes structure layouts, function bodies, resolved module dependencies and endpoint contracts (nex.program/4). Canonical content includes qualified logical names, public visibility, parameter names/types, realm, effects, test status, and statements; comments and source locations are excluded. Reordering independent definitions or renaming an import alias does not change program identity, while changing field order does. Moving files without changing their logical module/dependency identities preserves semantic identity.

SQLite stores revisions, function nodes, and call edges. Local node IDs remain stable for a given logical module/local name as its body changes or another entry module imports it. Explicit identity-preserving rename and portable ID reconciliation are planned. Every current revision archives all reachable source files in a `nex.sources/1` bundle. Building a stored revision does not reload live files, package roots or dependency locks. A revision retains its first source projection; whitespace-only edits can share the semantic revision. Build keys also include the actual source bundle so debug locations are refreshed.

Graph import reparses and checks every archived source and verifies its revision. Imported derived AST data is informational and never trusted as executable compiler input. See `docs/protocol.md` for optimistic graph updates and source materialization.

Revision identity includes the language version. Graph database schema 1 is upgraded transactionally to schema 2, preserving old sources and marking their language as 0.1. Stored 0.1/0.2 single-file sources remain exportable and are wrapped as a one-file bundle for migration; 0.3/0.4 bundles remain complete archived bundles. `nex migrate` explicitly reparses/checks archived sources under language 0.5, creates a current revision and preserves history; `nex migrate GRAPH.json` explicitly adopts checked sources from an older exported graph. Newly reserved builtin function names can require source edits during migration. Migration is not proof that the graph's claimed old hash was valid. Ordinary import requires a current-language `nex.graph/2` bundle and a matching recomputed revision.

## Native debug representation

Toolchain 0.8 preserves NEX parameter/local names, scalar aliases and lexical scopes in DWARF. Heap-backed types remain aliases for actual runtime handle pointers; matching LLDB previews inspect immutable strings, lists, records and results without calling the application. Debug parameter storage borrows the same value and does not create an owned handle. These are tooling changes with no source-language migration or changes to checked execution semantics. See [debugging.md](debugging.md) for LLDB/DAP and the remaining expression/platform limits.

## Stopped-frame expressions

Toolchain 0.13 evaluates pure NEX expressions over exact typed stopped-frame snapshots in a separate reference-interpreter process. It reuses source expression syntax, import visibility, nominal types, effect/realm checks and execution rules; it does not run code or modify values in the inferior. New `inspect`/LLDB/DAP tools and their bounded snapshot protocols do not change language 0.5 or graph revisions. See [expressions.md](expressions.md) for wire values, selected frames, limits and editor adapter configuration.

## Native profiling

Toolchain 0.10 instruments reachable native function calls and managed shallow allocation pools in profile builds, without changing language 0.5 effects or observable execution rules. Reports attribute measured function content to the selected graph revision and node IDs; optional Tracy CPU zones use the same names and frozen source locations. Debug/release output and the reference interpreter/TypeScript semantics are unchanged. See [profiling.md](profiling.md) for wall-time definitions, overhead, bounds and remaining browser/GPU coverage.

## Verification metadata

Toolchain 0.11 adds snapshot-bound scalar contracts as separate `nex.verification-contracts/1` JSON documents. `nex verify` checks the selected pure i64/bool/unit functions with Z3, including checked arithmetic, assertions and explicitly annotated inductive loops/rankings. Source grammar, language 0.5 revisions and execution semantics are unchanged. Proof results do not remove runtime checks or automatically enforce JSON pre/postconditions; see [verification.md](verification.md) for assumptions, statuses and the compiler/runtime trust boundary.

Toolchain 0.12 links external `nex.task/1` acceptance criteria to source candidates, graph definitions and explicit checks. `nex test --symbol NAME` selects a single actual test. Task contracts add no source keywords or runtime pre/postconditions. See [tasks.md](tasks.md) for intent guards, static linkage, evidence and replay limits.
