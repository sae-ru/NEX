---
status: current
applies_to: "toolchain 0.265.0; language 0.30"
owner: repository
---

# Native reference libraries: one enclosing context

Source030 ordinary project components and C++ build APIs accept sequential
reference functions in code-only native archives. They record verified physical signatures in
[`native_entry_abi`](native-entry-abi.md), with an optional
`nex.native-reference-context/1` ownership contract. This is a compiler-private,
matching-runtime development interface. Ordinary static library components use
the consuming application's context. Portable SDK/platform acceptance remains
separate.

## Runtime and context ownership

Set `BuildOptions.libraryEntry`, `codeOnlyLibrary` and `projectLibraryABI` for
the library. Use compatible target/profile/toolchain/PIC settings in producers
and consumers and compare the actual `libraryABI`. An archive includes generated
code, not another runtime. All linked images resolve runtime operations to the
same enclosing host/application runtime. A reference library embedding its own
runtime is rejected with `E_CELL_TARGET`.

For a trusted C++ host, **one `nexrt::RequestScope` spans all related calls and
their live handles**. Do not open a fresh scope around each call while retaining
its raw result for the next call. The first reference operation creates the
context's heap; aliases, aggregates, closure captures and source-error payloads
continue to share that heap across subsequent library calls. A compiled NEX
application instead supplies its existing enclosing application context.

Use the actual emitted LLVM signature, parameter roles, attributes, return
ownership and calling convention. Managed arguments are borrowed valid handles;
managed returns are independently owned handles, even when they alias the same
cell. Release an owned handle exactly once, or let the enclosing scope retire
it. Source-level identity remains distinct from a handle pointer's identity.

This synchronous-entry contract is sequential and thread-affine. The separate
[ABI8 task-provider contract](reference-task-providers.md) handles suspended
calls across checked images. Neither defines a shared mutable memory model or permits an unrelated
request's cells. Source/reference/TypeScript semantics remain unchanged.
`RequestScope` instances cannot nest; a context for a related sequence belongs
to the outer host boundary, rather than each exported function.

## Source errors and fatal exits

Initialize a hidden source-error output to null. Inspect it before using the
ordinary result. Inside the same live context, the owned error packet preserves
the concrete source type and reference-bearing payload; a related call may
observe that payload's cell identity and mutations. A compiled source caller can
catch the same nominal error across a separately compiled archive.

A fatal trap unwinds to the host boundary. Close the enclosing context before
starting further calls; continuing with that context's unfinished generated
ownership frames is unsupported. Catch outside the scope's lifetime:

```cpp
try {
  nexrt::RequestScope context;
  // Related calls and owned handles remain inside this lifetime.
  // Check every emitted source-error output before consuming its result.
} catch (const nexrt::Trap &fatal) {
  // context has already closed; a later operation needs a fresh context.
}
```

## Context and image retirement

Context close retires all its handles and closes the reference heap. A host may
retain an ordinary `Value` snapshot through the matching C++ owner API; its
immutable fields survive, while contained cells become inert. Reconstructing a
handle in another context does not renew the old cell: access fails with
`E_CELL_HEAP`. A raw `Handle*` from an ended scope is invalid and must never be
reused or dereferenced.

Keep every contributing code image loaded until its returned callables,
captures and values requiring image-local cleanup have retired. The contract
qualifies fixed code images, not arbitrary hot unload or mixed runtime versions.
After all scopes and snapshots retire, `nex_runtime_finish()` checks ownership
cleanup. This does not establish a public C/Swift/JNI cell ABI or a wire/browser
representation for live references.

## Qualification

`tests/reference_library.py` builds two code-only PIC archives in Debug and
Release, checks actual LLVM entry metadata and warm reuse, links separate shared
images into one runtime host, and observes related calls, aliases, returned
captures, cycles and typed error packets. It also builds a real source caller
that catches an archive's nominal error and mutates its shared cell. Ended-context
access, fatal-context cleanup and rejection of runtime-embedding reference
libraries are explicit cases. Recorded execution evidence is separate from this
contract and does not qualify untested platforms or a portable SDK.

По-русски: несколько библиотек могут работать с одним объектом, если у них один
совместимый runtime и один живой контекст владельца. Контекст охватывает всю
последовательность связанных вызовов. После его закрытия ссылки недействительны;
код библиотек должен оставаться загруженным, пока живы его замыкания и данные.
