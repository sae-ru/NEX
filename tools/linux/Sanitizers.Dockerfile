ARG TOOLCHAIN_IMAGE=nex-sdk-packager:arm64
FROM ${TOOLCHAIN_IMAGE}
ARG LLVM_APT_VERSION=1:22.1.8~++20260714014902+ca7933e47d3a-1~exp1~20260714135019.80
RUN apt-get update && apt-get install -y --no-install-recommends libclang-rt-22-dev="${LLVM_APT_VERSION}" \
    && rm -rf /var/lib/apt/lists/*
# Keep the original verified compiler/packaging image intact. This derived
# development image adds the matching Clang ASAN/UBSAN/TSAN runtime libraries.
WORKDIR /work
