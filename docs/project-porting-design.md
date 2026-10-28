# C++ / Python project conversion — planned

This is a proposed development tool, not an implemented command or a claim that
arbitrary projects can be translated. NEX currently has no project converter.
Finish and validate the language/development chain before implementing it.

The intended output is a separate NEX project: modules, typed declarations,
explicit effects/realms, architecture/build metadata, tests, preserved original
inputs and a structured conversion report. Never overwrite the original project.
Record original paths/spans, input digests, parser version/build flags, mappings,
unsupported features, reviewed bridge dependencies and validation results.

## Pipeline

1. Inventory source, dependencies, build settings, tests and observable contracts.
   Parse source without importing Python modules or running application/build
   scripts. C++ parsing uses reviewed compilation settings, including macros,
   includes, target and language standard; declarations may differ by target.
2. Translate a documented subset deterministically through typed intermediate
   models. Use [Clang LibTooling](https://clang.llvm.org/docs/LibTooling.html) for
   C++ and the matching version's [Python AST](https://docs.python.org/3/library/ast.html)
   for Python. Syntax trees alone do not establish semantic equivalence.
3. Classify each unit: converted within supported assumptions, proposed repair,
   manual work, or an explicitly reviewed foreign bridge. An LLM can propose
   local repairs using bounded context; compile/test every proposal and retain
   uncertainty. Never silently substitute a stub, default result or weaker test.
4. Emit a current-language NEX project, matching libraries and a reproducible
   conversion report. Discover the actual compiler capabilities first. Do not
   invent missing NEX types, effects, async/exception/concurrency operations.
5. Run original and converted programs on the same defined inputs, checking
   output, errors, state changes and resource behavior. Test native/reference and
   applicable TypeScript behavior. Record coverage and unsupported cases;
   passing examples are evidence, not proof for every possible input.

## First supported scope

Start with small libraries and command-line business logic: typed functions,
records, explicit control flow, arithmetic under reviewed numeric bounds and
strings/collections with known ownership. Prefer a gradual module-by-module
port with runnable tests over a superficially complete generated project.

For C++, templates, macros, inheritance, pointer aliasing, unsigned wraparound,
object layout, destructor timing and exception unwinding need specific rules.
NEX's immutable aggregates and checked arithmetic cannot silently replace those
semantics. For code with undefined behavior, equivalence needs a defined-input
contract. Existing native libraries may be kept behind a reviewed C wrapper and
the existing explicit trusted FFI boundary; general C++ ABI interoperability
and automatically generated wrappers are not already supported.

For Python, annotations assist type inference but do not replace validation.
Unbounded integers, floor division/remainder, truthiness, mutable aliasing,
reflection, monkey-patching, dynamic imports, generators, exceptions and native
packages need explicit support or a reported conversion boundary. Never map an
arbitrary Python int to checked i64 or a mutable aliased list to an immutable
NEX list without proving the required assumptions. General Python interoperability
is also pending; keeping an interpreter behind an adapter is not a full port.

Measure total model/tool/retry tokens, time, success rate and runtime behavior
against reviewed manual/LLM porting baselines. Deterministic conversion should
reduce repeated model work, but no token-saving or completeness percentage is
claimed before those experiments. See [quality criteria](quality.md).
