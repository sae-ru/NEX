# Working on NEX

Read `README.md` for build commands and current status. Read `docs/language.md` and `docs/grammar.ebnf` before changing the language. `PLAN.md` includes future capabilities and is not an implemented feature list.

For NEX programs, use the model-independent workflow in `llm/SYSTEM_PROMPT.md`. Query `nex describe --json` for the actual compiler's capabilities. Query `nex context --symbol NAME` for bounded graph context. Validate patches with the compiler and tests.

For compiler changes, keep the frontend checker, reference interpreter, MLIR and TypeScript backends, language specification, grammar, capability descriptor, language-pack manifest and relevant examples consistent. Test observable semantics, including native/TypeScript/interpreter agreement and rejected programs. Maintain checked arithmetic, left-to-right evaluation, short-circuiting, effect declarations, realm boundaries, strict UTF-8, Unicode scalar string operations, immutable aggregate semantics and owned-value cleanup on all native exits. Language-version changes need an explicit, history-preserving migration path. Read `docs/web.md` before changing the browser adapter; emitted clients must contain only reachable client/shared code. Keep the npm lock and bundled runtime notices consistent when changing browser dependencies.

Use C++20, CMake, LLVM/MLIR 22.1 and SQLite. Batch implementation into complete functional milestones. Use `cmake --build build -j 4` and short checks of changed behavior during development; run `ctest --test-dir build --output-on-failure` and full platform/device suites at milestone or release gates, rather than after each small edit. Preserve earlier results and rerun them only when affected by a new change or unresolved failure. Preserve useful diagnostics and inspect failed intermediate IR rather than disabling verification.

The project is the NEX language and development toolchain. Large image editors and games are outside the requested implementation scope. Keep unsupported platforms and unfinished integrations visible as pending work.
