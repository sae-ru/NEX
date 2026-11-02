# Installed NEX0.159 OpenCL source-contract evidence

Source: `13db9b030644f00f14635e5b6e5f71f171ccd63f`, language0.28.
Candidate SDK archive SHA256: `03271d9e5b009d4c385f49fa9a708408beec24754d9ef4db2ae83a87dc1b1604`.

The relocated SDK passed21 native/reference cases and6 native source profiles
on Apple M5 Max, with47 physical kernel events. The generic source clauses were
combined with explicit detached runtime contracts whose predicates were true,
so pre/post failures exercise the inline clauses. Cancellation and deadline
skip the false inline postconditions. All six profiles have balanced visible
managed pools and no incomplete, dropped, invalid or overflowed collector events.
These measurements concern host/source profiling; physical kernel traces are
recorded separately. General GPU compilation, Metal compute, Apple NPU and
current Windows/Linux acceptance remain pending. Complete296-group regression
and the canonical41-phase installed-SDK workflows are separate gates.

Original source/dependency roots and the other SDK were denied by the OS policy;
both SDK prefixes were read-only. Five negative read and two negative write
controls passed before provider preparation. The bundled clang built the provider.
Raw traces, source inputs, projection receipts, gzip-compressed complete profiles
and their SHA256 inventory are included here. `report.json` retains the original
local artifact provenance; `../macos-opencl-0.159.0.json` is the compact receipt.

Reproduce on a compatible Mac with the exact candidate SDK, Python3.10+ and its
Apple platform SDK. Use new output directories. The commands below execute the
checks; reproducing the OS-denied-source property also requires the recorded
SDK isolation policy and its negative controls.

```sh
export NEX_SDK_CANDIDATE=/absolute/path/to/nex-sdk-0.159.0
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
python3 "$NEX_SDK_CANDIDATE/share/nex/tools/owned-opencl/prepare.py" \
  --sdk "$NEX_SDK_CANDIDATE" --output /tmp/nex028-opencl-provider \
  --cxx "$NEX_SDK_CANDIDATE/libexec/nex/llvm/bin/clang++"
python3 "$NEX_SDK_CANDIDATE/share/nex/tools/owned-opencl/verify.py" \
  --sdk "$NEX_SDK_CANDIDATE" --project /tmp/nex028-opencl-provider \
  --output /tmp/nex028-opencl-hardware
python3 docs/evidence/0.159.0-opencl/installed-opencl-contract-driver.py \
  --sdk "$NEX_SDK_CANDIDATE" --provider /tmp/nex028-opencl-provider \
  --output /tmp/nex028-opencl-source-contracts
```

Русский: это аппаратная проверка конкретного SDK0.159 и языка0.28.
Пройдены21 сценарий native/reference и6 профилей на Apple M5 Max; получены47
физических событий ядер. Проверены совместные встроенные и внешние контракты,
ошибки pre/post, переполнение, отмена, тайм-аут и очистка видимых пулов памяти.
Полная приёмка SDK, универсальные GPU-ядра, Metal compute, Apple NPU и текущие
Windows/Linux проверяются отдельно. Для повторения нужны указанный SDK,
совместимый Mac, Python3.10+, Apple SDK и новые выходные каталоги.
