FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ARG TARGETARCH
ARG LLVM_APT_VERSION=1:22.1.8~++20260714014902+ca7933e47d3a-1~exp1~20260714135019.80
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg xz-utils unzip \
    && curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key -o /tmp/llvm.asc \
    && gpg --show-keys --with-colons /tmp/llvm.asc | awk -F: '$1 == "fpr" {print $10}' | grep -qx '6084F3CF814B57C1CF12EFD515CF4D18AF4F7421' \
    && gpg --dearmor -o /usr/share/keyrings/llvm.gpg /tmp/llvm.asc \
    && echo 'deb [signed-by=/usr/share/keyrings/llvm.gpg] https://apt.llvm.org/noble/ llvm-toolchain-noble-22 main' > /etc/apt/sources.list.d/llvm.list \
    && apt-get update && apt-get install -y --no-install-recommends \
       clang-22="${LLVM_APT_VERSION}" llvm-22-dev="${LLVM_APT_VERSION}" \
       libmlir-22-dev="${LLVM_APT_VERSION}" mlir-22-tools="${LLVM_APT_VERSION}" \
       lld-22="${LLVM_APT_VERSION}" lldb-22="${LLVM_APT_VERSION}" \
       cmake make g++ python3 libsqlite3-dev libssl-dev openssl zlib1g-dev libzstd-dev \
    && rm -rf /var/lib/apt/lists/* /tmp/llvm.asc
RUN case "$TARGETARCH" in \
      arm64) node_arch=arm64; node_hash=1c4a9933a5e45bc88f54f70b5f91232c127ec49f1a5989d23fb85824c7adf9b7; \
             z3_name=z3-5.3.1-arm64-glibc-2.38; z3_hash=73195cee08f4a1a53a605b65845268e0ac999666cb8f4e604d2260e0c9c60b5a ;; \
      amd64) node_arch=x64; node_hash=2e5d13569282d016861fae7c8f935e741693c269101a5bebcf761a5376d1f99f; \
             z3_name=z3-5.3.1-x64-glibc-2.39; z3_hash=acca9625e8cc8edeb9647b653a1bd696544ddeb5d1c2970a4576734a0c175b40 ;; \
      *) exit 1 ;; esac \
    && curl -fsSL "https://nodejs.org/dist/v22.22.3/node-v22.22.3-linux-${node_arch}.tar.xz" -o /tmp/node.tar.xz \
    && echo "$node_hash  /tmp/node.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && curl -fsSL "https://github.com/Z3Prover/z3/releases/download/z3-5.3.1/${z3_name}.zip" -o /tmp/z3.zip \
    && echo "$z3_hash  /tmp/z3.zip" | sha256sum -c - \
    && unzip -q /tmp/z3.zip -d /opt && mv "/opt/${z3_name}" /opt/z3 \
    && rm /tmp/node.tar.xz /tmp/z3.zip
ENV PATH="/usr/lib/llvm-22/bin:/opt/z3/bin:${PATH}"
ENV NEX_Z3_EXECUTABLE=/opt/z3/bin/z3
COPY web/package.json web/package-lock.json /opt/nex-web-deps/
RUN npm --prefix /opt/nex-web-deps ci --ignore-scripts --no-audit --no-fund --cache /opt/nex-npm-cache \
    && rm -rf /opt/nex-web-deps/node_modules
ENV NEX_NPM_CACHE=/opt/nex-npm-cache
ENV npm_config_offline=true
WORKDIR /work
# Supply source as a read-only mount and keep builds in a separate writable mount.
CMD ["/bin/bash"]
