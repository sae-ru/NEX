ARG TOOLCHAIN_IMAGE=nex-linux-toolchain:arm64
FROM ${TOOLCHAIN_IMAGE}
ARG PATCHELF_VERSION=0.18.0-1.1build1
RUN apt-get update && apt-get install -y --no-install-recommends patchelf="${PATCHELF_VERSION}" \
    && rm -rf /var/lib/apt/lists/*
# This is a separate packaging image; the verified compiler image is unchanged.
WORKDIR /work
