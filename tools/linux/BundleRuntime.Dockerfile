ARG TOOLCHAIN_IMAGE=nex-linux-toolchain:arm64
FROM ${TOOLCHAIN_IMAGE} AS host_tools
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ENV DEBIAN_FRONTEND=noninteractive
# The platform's C/C++ development SDK remains a declared prerequisite. No
# LLVM, MLIR, Z3 or NEX libraries are installed in this validation environment.
RUN apt-get update && apt-get install -y --no-install-recommends g++ python3 openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Node/npm are external browser-build prerequisites, separate from the SDK.
COPY --from=host_tools /usr/local/bin/node /usr/local/bin/node
COPY --from=host_tools /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
COPY --from=host_tools /opt/nex-npm-cache /opt/nex-npm-cache
ENV NEX_NPM_CACHE=/opt/nex-npm-cache
ENV npm_config_offline=true
WORKDIR /work
