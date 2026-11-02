# Optional live-debugger overlay. The compiler/toolchain image is unchanged.
ARG TOOLCHAIN_IMAGE=nex-linux-toolchain:arm64
FROM ${TOOLCHAIN_IMAGE} AS debugger-build
ARG LLDB_APT_VERSION=1:23.1.5~++20261028083854+a738f2737189-1~exp1~20261028203912.92
ARG LLDB_SOURCE_COMMIT=a738f2737189bcc1de75c25e8cd1d4b466c9526e
ARG LLDB_SOURCE_SHA256=5407c03d902d188a67638aa10ceec05d94950e83d0dfaab4ad3769dd1b0ad048
RUN apt-get update && apt-get install -y --no-install-recommends \
    llvm-23-dev="${LLDB_APT_VERSION}" clang-23="${LLDB_APT_VERSION}" \
    libclang-23-dev="${LLDB_APT_VERSION}" libclang-cpp23-dev="${LLDB_APT_VERSION}" \
    ninja-build python3-dev swig libedit-dev libxml2-dev libncurses-dev \
    libcurl4-openssl-dev patch \
    && rm -rf /var/lib/apt/lists/*
COPY tools/linux/lldb23-indexed-pages.patch /tmp/lldb23-indexed-pages.patch
RUN curl -fsSL "https://github.com/llvm/llvm-project/archive/${LLDB_SOURCE_COMMIT}.tar.gz" -o /tmp/lldb.tar.gz \
    && echo "${LLDB_SOURCE_SHA256}  /tmp/lldb.tar.gz" | sha256sum -c - \
    && echo '447806a73c12274b26a6bb8306a12e7d1a57a0759052f5ae0c66f582e74e6653  /tmp/lldb23-indexed-pages.patch' | sha256sum -c - \
    && mkdir /opt/lldb-src \
    && tar -xzf /tmp/lldb.tar.gz -C /opt/lldb-src --strip-components=1 \
       "llvm-project-${LLDB_SOURCE_COMMIT}/lldb" "llvm-project-${LLDB_SOURCE_COMMIT}/cmake" \
       "llvm-project-${LLDB_SOURCE_COMMIT}/clang/cmake" \
    && cd /opt/lldb-src \
    && echo '22d2c4fd44ef498df98364972ef704efc252c45dc5d45ba581230d56c4a46421  lldb/tools/lldb-dap/Variables.cpp' | sha256sum -c - \
    && patch -p1 < /tmp/lldb23-indexed-pages.patch \
    && echo '960a03ea8b6a64b09ef5bdefd2a9af5d50da38022f548de8ca05ec648a9ee562  lldb/tools/lldb-dap/Variables.cpp' | sha256sum -c - \
    && rm /tmp/lldb.tar.gz /tmp/lldb23-indexed-pages.patch
# LLVM's exported LLVMHTTP target requires CURL::libcurl in standalone users.
RUN echo 'find_package(CURL REQUIRED)' > /opt/lldb-src/find-curl.cmake
RUN cmake -S /opt/lldb-src/lldb -B /opt/lldb-build -G Ninja \
    -DCMAKE_PROJECT_lldb_INCLUDE=/opt/lldb-src/find-curl.cmake \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-23 -DCMAKE_CXX_COMPILER=clang++-23 \
    -DLLVM_DIR=/usr/lib/llvm-23/lib/cmake/llvm -DClang_DIR=/usr/lib/llvm-23/lib/cmake/clang \
    -DLLVM_LINK_LLVM_DYLIB=ON -DLLDB_INCLUDE_TESTS=OFF -DLLDB_ENABLE_LIBCXX_TESTS=OFF \
    -DLLDB_ENABLE_PYTHON=ON -DLLDB_ENABLE_LUA=OFF -DLLDB_ENABLE_CURSES=OFF \
    -DLLDB_ENABLE_LIBEDIT=ON -DLLDB_ENABLE_LZMA=OFF -DLLVM_INCLUDE_TESTS=OFF \
    -DLLDB_BUILD_INTEL_PT=OFF -DLLDB_ENABLE_LIBXML2=ON \
    -DCMAKE_INSTALL_PREFIX=/opt/nex-debugger-patched
RUN cmake --build /opt/lldb-build --target lldb-dap -j 4
RUN cmake --build /opt/lldb-build --target install-liblldb install-lldb \
    install-lldb-dap install-lldb-server install-lldb-argdumper -j 4 \
    && cp -a /usr/lib/llvm-23/lib/clang /opt/nex-debugger-patched/lib/clang


# Preserve the pinned base debugger build cache, then repair the independently
# reproduced ARM64 optional-register inventory crash before deployment.
COPY tools/linux/lldb23-za-registers.patch /tmp/lldb23-za-registers.patch
COPY tools/linux/lldb23-za-registers-test.cpp tools/linux/check_lldb_registers.py /tmp/nex-lldb-registers/
RUN cd /opt/lldb-src \
    && echo '6a3bdf7cab9e7dc64d37081871851f705c22ed03067c02ff62eaa4057dc938eb  /tmp/lldb23-za-registers.patch' | sha256sum -c - \
    && echo 'c0c6d57ccd69fc4f0b37ddac64bbf2fa4e039077c505ae6915c01376f5888a16  lldb/source/Plugins/Process/Utility/RegisterInfoPOSIX_arm64.cpp' | sha256sum -c - \
    && patch -p1 < /tmp/lldb23-za-registers.patch \
    && echo 'c672b3ec6a24a1d5f621279426eb662a571c46e0dc83d55c0097b2c97b5ee4ee  lldb/source/Plugins/Process/Utility/RegisterInfoPOSIX_arm64.cpp' | sha256sum -c - \
    && cmake --build /opt/lldb-build --target lldb lldb-dap lldb-server -j 4 \
    && python3 -B /tmp/nex-lldb-registers/check_lldb_registers.py \
       --build /opt/lldb-build --test-source /tmp/nex-lldb-registers/lldb23-za-registers-test.cpp \
       --output /tmp/nex-lldb-register-evidence \
    && cmake --build /opt/lldb-build --target install-liblldb install-lldb \
       install-lldb-dap install-lldb-server install-lldb-argdumper -j 4

FROM ${TOOLCHAIN_IMAGE}
# Deploy the matching debugger cohort and its resources. Replacing only DAP
# against the APT liblldb failed the unchanged pre-launch breakpoint check.
# Source trees, object files and LLVM23 compilers remain in the build stage.
COPY --from=debugger-build /opt/nex-debugger-patched /opt/nex-debugger-patched
ENV PATH="/opt/nex-debugger-patched/bin:${PATH}"
ENV NEX_LLDB=/opt/nex-debugger-patched/bin/lldb NEX_LLDB_DAP=/opt/nex-debugger-patched/bin/lldb-dap
RUN /opt/nex-debugger-patched/bin/lldb-dap --version \
    && /opt/nex-debugger-patched/bin/lldb --no-lldbinit --batch \
       -o 'script import lldb; assert lldb.__file__.startswith("/opt/nex-debugger-patched/")' \
    && clang --version | head -n 1
