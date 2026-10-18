FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ENV DEBIAN_FRONTEND=noninteractive
# GNU runtime only. Python drives acceptance; the native apps do not invoke it.
# No headers, GCC/Clang, LLVM, NEX, Node, OpenSSL/SQLite development packages.
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libgcc-s1 python3 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /deployment
