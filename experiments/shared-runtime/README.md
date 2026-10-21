# One shared native runtime: mechanism experiment

This developer experiment relinks real checked NEX LLVM outputs into two native
libraries plus one runtime. It is not an implemented `shared_library` project
kind, a binary-only package API or a supported replacement for `nex project`.

From a source checkout with its matching SDK dependencies:

```sh
python3 experiments/shared-runtime/probe.py --nex build/nex --output build/new-shared-runtime-proof
```

The output directory must be new. The probe checks reference/native/TypeScript
source behavior, builds the normal checked archive project, then manually
compiles PIC runtime/IR and links platform libraries. Both providers resolve
the same runtime release function.64 rounds transfer records, strings, bytes,
finite numeric lists and snapshot callbacks; one module opens a file and the
other writes it. A checked division failure exercises cleanup and executable
identity binding. The complete runtime folder moves and executes again.

Exact macOS ARM64 and Linux ARM64 observations are in `evidence/`. Linux runs
in a separate network-disabled container with only the SDK, probe and output
mounted. Neither test establishes kernel-enforced source read denial. The
static build receipts are inputs to this research; they do not describe the
manually relinked images. The original script/checksums and private logs remain
with the full local evidence.

Production integration still needs checked dynamic project edges, one captured
runtime, exact final-image provenance, incremental PIC objects, bound provider
debug/core images, profiling host identity, notices/packaging, project execution
flows and target-platform validation. Existing compiler capability descriptors
remain authoritative. No new third-party source is vendored here.
