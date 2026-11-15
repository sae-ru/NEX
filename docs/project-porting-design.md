# Java / Python / C++ project conversion — planned

This is a proposed development tool, not an implemented command or a claim that
arbitrary projects can be translated. NEX currently has no project converter.
Finish and validate the language/development chain before implementing it.

User priority, 2026-11-15: **Java first, Python second**, then the retained C++
scope. No Java/Python converter command is implemented. Preparation of language
requirements does not establish project-conversion support.

The intended output is a separate NEX project: modules, typed declarations,
explicit effects/realms, architecture/build metadata, tests, preserved original
inputs and a structured conversion report. Never overwrite the original project.
Record original paths/spans, input digests, parser version/build flags, mappings,
unsupported features, reviewed bridge dependencies and validation results.

## Pipeline

1. Inventory source, dependencies, build settings, tests and observable contracts.
   Parse source without importing Python modules or running application/build
   scripts. A separate operator-supplied build-context capture can record actual
   Maven/Gradle/JDK classpaths, generated sources and compiler settings. Querying
   a Gradle build model executes build configuration; it is not passive source
   parsing and must not be hidden inside a read-only inventory command.
   C++ parsing uses reviewed compilation settings, including macros,
   includes, target and language standard; declarations may differ by target.
2. Translate a documented subset deterministically through typed intermediate
   models. Java uses a binding-resolving frontend such as
   [Eclipse JDT](https://help.eclipse.org/latest/topic/org.eclipse.jdt.doc.isv/reference/api/org/eclipse/jdt/core/dom/ASTParser.html),
   the project's target JDK and captured dependencies. Missing/recovered bindings
   remain unresolved work, not a successful semantic conversion. The
   [Gradle Tooling API](https://docs.gradle.org/current/userguide/tooling_api.html)
   can supply build models in the explicit build-context step.
   Use the matching version's [Python AST](https://docs.python.org/3/library/ast.html)
   for Python and [Clang LibTooling](https://clang.llvm.org/docs/LibTooling.html)
   for C++. Syntax trees alone do not establish semantic equivalence.
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

## Java requirements

Inventory the complete project/module/dependency graph, generated sources,
resources and original tests. Use one real Java project to grow a documented
feature matrix from libraries/business logic toward its complete application.
NEX modules, checked effects, build components and source/debug mappings are
required outputs, not only a collection of translated functions.

Preserve reference identity and mutable aliasing, nullable values, constructors
and class initialization, virtual/interface dispatch, exceptions/finally,
thread synchronization and the actual library contracts. A compatibility heap
also needs an explicit policy for object cycles, garbage collection and host
references; ordinary immutable NEX structs are not a drop-in Java object model.
An analysis can lower a proven non-escaping, identity-insensitive value object to
an immutable struct. Apply that optimization only where aliasing, mutation and
identity behavior are preserved; report the remaining reference-based objects.
Java integer overflow,
floating-point special values and UTF-16 string operations cannot silently use
NEX checked i64, finite f64 and Unicode-scalar indexing. Introduce explicit typed
compatibility operations/runtime support where needed; do not weaken ordinary
NEX semantics. [Java numeric rules](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.2.2)
remain the source contract for those operations.

Classify every JDK/framework dependency as converted, replaced by a validated
NEX implementation, temporarily bridged, or unsupported. Reflection, dynamic
class loading, annotation processing, JNI, dependency injection and ORM require
specific support. Replacing a Spring/Hibernate project with generated endpoint
stubs is not a project conversion. JVM-assisted modules remain explicitly hybrid
until their application behavior and required libraries have been transferred.

Build the converter around a versioned semantic project IR with source spans,
resolved symbols/types, dependency edges and source-language operations. Share
the report, NEX emitter, validation and project packaging between frontends;
retain separate Java/Python semantic passes. Cache unchanged modules by their
source, dependency and frontend identities. Repeated migration should rebuild
only affected modules and must not overwrite hand-edited output silently.

The first milestone should import and assess a real Maven/Gradle library, emit
one runnable module, preserve a source-to-output map and execute the original
and converted tests. Expand the documented subset using that project before
attempting a framework application. Track converted application behavior and
remaining dependency/runtime obligations separately from translated line counts.

## Retained Python and C++ requirements

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
