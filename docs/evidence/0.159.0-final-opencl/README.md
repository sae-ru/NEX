# Installed NEX 0.159.0 Mac OpenCL evidence

Exact SDK source: `3165aaf56866b0c3f341b63571e808cfb061aa3a`.
Archive SHA256: `fe8dde075971f422b2311c27e131ca00b4c3cac24094cc6bd6857eab8b537374`.
Apple M5 Max OpenCL U8 Add/Affine: 21 native/reference cases, six complete
source profiles and 47 physical kernel events. The original report, fixture
sources, provider inputs, trace files and gzip profiles are preserved byte for
byte; `manifest.json` records their SHA256 values. Absolute local paths record
provenance and are not installation instructions.

The earlier candidate remains in `../0.159.0-opencl/` with its own source/archive.
Full SDK acceptance is recorded separately in `../../releases/0.159.0.json`.
General kernels, Metal compute, Apple NPU and current Windows/Linux acceptance
are not established by these OpenCL checks.
