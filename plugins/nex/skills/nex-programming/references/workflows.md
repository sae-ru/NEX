# Focused NEX documentation routing

Use this table after reading the selected compiler's capability index. Query
only advertised fields and retrieve their indicated guide. These names route
discovery; they do not assert that every feature is available in an older SDK.

| Task | Descriptor fields | Typical guide kinds |
|---|---|---|
| Values, generic functions and errors | `types`, `generic_features`, `trait_features`, `result_propagation`, `source_exceptions` | `language`, `grammar`, `trait`, `result`, `exception` |
| Collections and output construction | `standard_library`, `list_construction`, `text_construction`, `bytes_construction` | `stdlib`, `list-build`, `text-construction`, `bytes-construction` |
| Cells and shared identity | `managed_references`, `project_languages` | `references` |
| Contracts or a language upgrade | `source_contracts`, `project_languages` | `source-contract`, `source-contract-migration` |
| Graph changes and recovery | `graph_features`, `patch_features`, `history_features`, `snapshot_features` | `graph`, `history`, `snapshot` |
| Static/shared libraries and application builds | `project_build`, `native_target_policy`, `native_entry_abi`, `application_package_platforms` | `project`, `build`, `native-entry-abi` |
| HTTP, APIs and browser applications | `api_features`, `browser_workers`, `structured_tasks_runtime` | `web`, `api`, `server`, `browser-worker` |
| Tasks and CPU parallelism | `task_features`, `source_concurrency`, `structured_tasks_runtime` | `task`, `concurrency` |
| GPU/NPU or platform packaging | `compute`, `device`, `gpu_codegen`, `opencl_codegen`, `application_package_platforms` | Follow the returned provider/platform guide |
| Debugging and profiling | `debug_features`, `profile_features`, `task_debugging`, `task_profiling` | `debug`, `profile` |

For a web application, preserve client/server/shared boundaries and check the
generated browser behavior. A native binary, an emitted TypeScript file and an
executed browser UI are separate acceptance results. Use the advertised browser
adapter and the project's authored CSS/assets/components rather than replacing
the requested NEX application with an unrelated stack.

For device work, distinguish source support, a matching provider/SDK and actual
hardware execution. Select a fallback only if it preserves the user's required
behavior and disclose it. Pending platform support is not established by LLVM
supporting the CPU architecture.

For language migrations, read the guide referenced by the selected descriptor
and preserve namespace, history, revisions and physical source until the guarded
operation succeeds. Do not treat changing `nex.json` as a migration.

The maintained [model-independent language pack](https://github.com/sae-ru/NEX/tree/main/llm)
and [language specification](https://github.com/sae-ru/NEX/blob/main/docs/language.md)
are source references. Prefer the corresponding installed compiler's guides
when their versions differ from GitHub main.
