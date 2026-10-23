# Следующий этап: общий compute API

Acceptance update: optimized bytes fixture PASSED30 calls/6400 values,993161 reference steps, ordinary Debug/Release tests, profile/replay/standalone. Supplemental138 receipt files locally verified. Same bytes ABI/worker min/max and int8 extrema PASSED6 NEX calls/16448 values; current pack checks all256 values on native/TypeScript/reference. This supersedes the earlier in-progress wording below. Generic compute API remains next.
Полная цель остаётся прежней; файл задаёт следующий этап после текущего0.120 physical acceptance. Проект не завершён, перечисленное ниже не является реализованными возможностями.

Фактическая основа: typed value C FFI, explicit library/export grants и manifest/signature pins; immutable bytes/aggregate snapshots; source realm/effect checks. На RK3588 доказан GPU-only bounded affine вызов из0.120 через отдельный pinned child worker:30GPU/30720bytes, Debug/Release/reference/test/profile/replay/standalone. Parent JSON остаётся строгим, vendor stdout сохраняется отдельно. Прямой in-process вариант имел корректные значения, но нарушал machine stdout. NPU matmul на RK3588 исправлен в собственном адаптере: нельзя CPU-инициализировать cached C DMA mapping. Оригинальные3 матрицы, NEX reference/nativeDebugRelease/tests/profile/replay/standalone дали30RKNN/6400 значений; начальный list-per-scalar путь наmaxshape упёрся в4096refs, bulkbytes ABI это устраняет без повышения FFIквот. Эталонные min/max/fullint86calls16448values прошли с явным16M boundedreference(2.51M actual); текущая оптимизированная NEX обёртка завершает свою matchingприёмку. Это bounded matmul fixture, не общий compute API. CIX fixed OpenCL/Zhouyi proof имеет свою область30GPU20NPU.

## Реализация

1. Версионированные typed Request/Response/Capability/Device/DType/Fallback; Context с server fn(Request)->result<Response> !{ffi}. Context не является wire-значением; через IPC/FFI проходят только проверенные данные. Явная CPU fallback policy и фактический backend в результате. Ошибки версии/формы/range/precision/device не маскируются.
2. Проверенные immutable tensor snapshots, shape/byte size/limit validation без overflow. Начальные общие операции — elementwise и matmul для явно описанного dtype; это начало API, а не произвольная GPU-компиляция. Никакого неявного изменения NEX i64/f64 semantics; precision и narrowing задаются отдельно.
3. CPU oracle/backend и настоящие OpenCL backend на CIX/RK3588/Mac по фактической доступности; NPU providers с отдельными проверенными runtime/model/kernel constraints. Версии SDK, библиотеки, устройства и fallback связываются с provenance. Непроверенный RKNN путь остаётся unavailable до точного numerical/device proof.
4. Сохранить process boundary для vendor runtimes: bounded binary IPC, private logs, pinned executable, controlled publication, cancellation с физическим drain. Не перенаправлять stdio всего NEX host и не ослаблять machine protocol. Для производительности — ограниченный сохраняемый worker/cache; его физические leases/очереди/limits проверяются до публичного включения.
5. Дальнейшие обязательные части: owned device buffers/external resources и async/task bridge, generic kernels/models, wgpu/SDL3/graphics и остальные platforms. Перед изменением source types/effects — согласованные checker/reference/native/TypeScript/spec/grammar/discovery/language-pack, explicit history-preserving migration и backend equivalence.
6. Поставить реально вызываемый NEX example/API и model-independent usage; показать выбор CPU/GPU/NPU и запрет fallback. Доказать обычные/граничные/rejected программы, реальные device placement, cleanup, cancellation/error exits, native/reference agreement и отсутствие privileged client code.
7. Для compiler/runtime изменения — сборка и соответствующие целевые тесты, затем matching full regression/installed SDK/platform gates, source manifests и recovery backup. Не объявлять всё готовым по узкому probe или одной платформе.


Context boundary clarification (verified with actual0.121 checker): the current
ordinary-source Context is non-wire, not a new opaque resource type. Existing
opaque callable forwarding through trusted C FFI and resource-free passive CPU
map captures remain legal. It grants no host permissions and cannot be invoked
from a pure/client callback. Future owned device contexts/buffers still require
the planned ownership/non-transfer/device-settlement guards; do not infer these
from the current source record.
