---
status: current
applies_to: "language 0.30"
owner: repository
---

# NEX 0.30 на Windows x64 в Codex

Язык указывается в `nex.json`. Версию исполняемого SDK показывает `doctor`. Для работы с релизом установите архив Windows x64 и сверьте его SHA256. Описание проверенных платформ и устройств находится в `qualification.json` в Assets выбранного тега. [Установка в PowerShell](getting-started.ru.md) · [Промпт для нового чата Codex](WINDOWS-CODEX-PROMPT.md) · [Релизы](https://github.com/sae-ru/NEX/releases)

## Проверить компилятор и выполнить пример

В PowerShell с настроенным PATH определите абсолютный путь к компилятору. Используйте этот путь для проверки и вызовов из Python.

```powershell
$nex = (Get-Command nex.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$sdk = Split-Path -Parent (Split-Path -Parent $nex)
Get-FileHash -LiteralPath $nex -Algorithm SHA256
& $nex doctor --json
& $nex describe --field project_languages --json
& $nex describe --field gpu_codegen.cuda --json
```

Скопируйте пример из установленного SDK в новый рабочий каталог. Он проверяет вычисление `20.5 × 2 + 1 = 42`. Команда `test` выполняет тест в интерпретаторе и нативной сборке. Команда `emit` записывает исходный код ядра CUDA.

```powershell
$work = Join-Path ([System.IO.Path]::GetTempPath()) ('nex-cuda-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath (Join-Path $sdk 'share/nex/examples/gpu-cuda.nex') -Destination (Join-Path $work 'main.nex') -ErrorAction Stop
[IO.File]::WriteAllText((Join-Path $work 'nex.json'), '{"schema":"nex.project/1","language":"0.30","entry":"main.nex"}', [Text.UTF8Encoding]::new($false))
Push-Location $work
try {
    & $nex context main.nex --kind brief --symbol gpu_cuda::transform --json
    if ($LASTEXITCODE -ne 0) { throw 'context failed' }
    & $nex test main.nex --json
    if ($LASTEXITCODE -ne 0) { throw 'test failed' }
    & $nex emit main.nex --kind cuda --entry transform --input-layout columns -o kernel.cu --json
    if ($LASTEXITCODE -ne 0) { throw 'emit failed' }
    Get-FileHash -LiteralPath kernel.cu -Algorithm SHA256
} finally {
    Pop-Location
}
```

Сверьте SHA256 файла `kernel.cu` с `shader_sha256` в ответе `emit`. Поля `driver_initialized` и `device_executed` указывают, обращалась ли команда к драйверу и запускала ли ядро. На Windows x64 компилятор 0.281.0 прошёл тест примера и записал ядро размером 9251 байт. [Результат прогона и SHA256](evidence/windows-language030-cuda-emission-2026-11-23.json) · [Генерация CUDA](gpu-codegen.md)

## Выполнить операцию на NVIDIA GPU

Для физического запуска нужны Windows x64, драйвер NVIDIA, заголовочные файлы CUDA и нативные инструменты сборки, обнаруженные `doctor`. В SDK 1.0 сценарии подготовки и проверки находятся в каталоге `owned-cuda`. Команды ниже создают новые каталоги рядом с примером и запускают один сценарий на устройстве 0. Параметр `--index` выбирает другую видеокарту.

```powershell
$tools = Join-Path $sdk 'share/nex/tools/owned-cuda'
$project = Join-Path $work 'device-project'
$result = Join-Path $work 'device-result'
python -B (Join-Path $tools 'prepare.py') --compiler $nex --language-version 0.30 --index 0 --output $project
if ($LASTEXITCODE -ne 0) { throw 'CUDA preparation failed' }
python -B (Join-Path $tools 'verify.py') --compiler $nex --project $project --only edge_affine_257 --output $result
if ($LASTEXITCODE -ne 0) { throw 'CUDA verification failed' }
Get-Content -LiteralPath (Join-Path $result 'report.json') -Raw
```

Сценарий проверяет 257 элементов на GPU. В отчёте проверьте устройство, `completed_kernels` в обоих режимах, `physical_completion_verified` и `cpu_fallback`. Ожидаются завершённые ядра с `cpu_fallback=false`. [Провайдер CUDA и сценарии](../experiments/owned-cuda/README.md)

## История проектов и результаты прошлых запусков

При переходе между SDK сохраните каталог снимка с обеими его частями, `graph.db` и `snapshot.json`. В инструкции по совместимости разобран перенос двух ревизий проекта 0.30 с Windows x64 на macOS ARM64. [История и совместимость](compatibility.ru.md) · [Архив результатов Windows 0.165](windows-handoff-0.165.md)
