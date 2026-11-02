# Native library entry ABI

Source development toolchain 0.160 adds `native_entry_abi` to the JSON result and
retained `build.json` of `nex build --library --entry NAME --json`. Discover its
availability with `nex describe --field native_entry_abi --json`; read this guide
with `nex guide --kind native-entry-abi --json`. Language 0.28
and its graph format are unchanged. Installed SDK/platform acceptance is separate.

The object describes the selected root and explicit project-library exports,
using the actual verified LLVM definitions/declarations. It records physical
parameter order/types/attributes, return type/attributes, calling convention,
target/layout and the LLVM SHA256. Source names/types identify each ordinary
parameter; a source-error output and a closure environment have distinct roles.
It does not dump every reachable helper into a model's context.

```sh
nex build --library --entry step --profile debug --json
```

For example, a synchronous `fn step(x:i64)->i64 !{throw}` currently lowers to
`i64 (i64, ptr)`. The final pointer is an output slot for a managed source-error
packet. It is absent from the source signature. Calling the native symbol with
only `x` can corrupt memory even when the particular invocation never throws.
Read the actual result rather than assuming this example covers another entry.

Use the exact matching runtime headers, target and `library_abi` cohort. In a
trusted matching C++ host this particular entry needs a prototype equivalent to:

```cpp
extern "C" int64_t ACTUAL_NATIVE_SYMBOL(int64_t, nexrt::Handle **);
```

Every synchronous call must be enclosed by `nexrt::RequestScope`. Initialize the
error slot to `nullptr`; after the call, inspect it before using the return value.
For a non-null slot, `nex_source_error_unhandled` raises the matching runtime's
`nexrt::NativeSourceException`. A fatal runtime trap instead unwinds directly.
Catch these at the host boundary. The private typed exception's `code` identifies
the concrete source type; `E_SOURCE_EXCEPTION` is the outer CLI/transport
diagnostic, not that type name. Keep packet/heap handles within their valid
runtime scopes; do not reinterpret them as strings or release them twice.
`nex_runtime_finish()` checks cleanup after the host has closed its scopes and
released its owned snapshots. Returned heap handles belong to the enclosing
runtime scope. Host arguments must be valid matching-runtime values.

`direct_host_call: false` forbids treating a task continuation, closure requiring
an environment, or externally supplied declaration as an ordinary direct entry.
Task entries retain their executor/provider interface; their physical LLVM
arguments are marked `task_executor_argument`, not source arguments. Discovery
does not create an executor or confer resource authority.

The JSON is also available on warm and archived-revision builds. Completion
checks bind the LLVM and metadata; a warm library hit recomputes the selected
entry description from LLVM and checks the retained object. A changed ordinary
executable does not acquire a library ABI object.

This is a **compiler-private, matching-runtime interface**, not a stable public
C, Swift or JNI ABI, generated header, exception boundary for untrusted foreign
code, or permission to mix SDK/runtime versions. LLVM types alone are not a
complete portable C prototype. The host must honor attributes, calling
convention, target and lifetime requirements. Automatic public bindings remain
planned work. See [project linking](project-build.md), [iOS archives](ios.md) and
the [machine-readable schema](../llm/native-entry-abi.schema.json).

По-русски: поле `native_entry_abi` описывает реальную сигнатуру выбранной функции
в нативной библиотеке. Оно явно показывает скрытый параметр ошибки, порядок
аргументов и совместимый runtime. Одного имени из `nex context` для вызова
недостаточно. Для C++ нужны соответствующие заголовки, `RequestScope`, обработка
ошибок и очистка; задачи вызываются через исполнитель. Стабильный публичный
интерфейс C/Swift/JNI ещё не реализован.
