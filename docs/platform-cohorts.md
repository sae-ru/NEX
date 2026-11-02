# Platform preparation and compiler cohorts

Windows CPU/storage acceptance, its TypeScript comparison and CUDA preparation
accept the explicitly supported source languages 0.27 and 0.28. Linux SDK smoke
keeps its retained 0.23–0.27 coverage and also accepts 0.28. The helpers compare
`doctor` and the discovery index before creating source projects. Feature queries
must keep the same toolchain, language, compiler build and descriptor hash.
Unknown versions and mixed query identities fail explicitly.

Typed task consumers also require the advertised ABI7 source-provider family.
This is capability validation; it does not establish native Windows, Linux or
physical accelerator execution. Older acceptance records keep their original
versions and hashes. `tools/windows/summarize_host.py` is a historical 0.152.1
reporting recipe and must not label a new run as that old result.

Windows `--resume` reuses only matching compiler/target identities and pinned
artifacts. Both the acceptance driver and its cohort helper have exact hash pins;
older receipts without them need a new output directory. Existing source and project manifests must still match, and their
bytes are preserved. A changed language or source requires a new output directory;
the helper does not migrate or retag the previous graph.

CUDA source preparation can run without CUDA headers or a Windows toolchain:

```sh
python3 experiments/owned-cuda/prepare.py --compiler /absolute/path/to/nex \
  --source-only --output /new/cuda-source-check
```

It checks the current template and standard library, queries seven actual FFI
signatures and emits their hashes/header. Its distinct
`nex.owned-cuda-source-preparation/1` receipt says that no DLL, context or hardware
execution was accepted. Without `--source-only`, preparation still requires
native Windows, target C++ tools and CUDA headers, and produces the pinned module
for separate execution/sanitizer checks.

The module `tools/compiler_cohort.py` is installed with SDK resources so these
helpers do not import it from an external checkout. Full installed/relocated SDK,
CUDA, Windows GUI/DPI and current Linux/stand acceptance remain separate gates.
