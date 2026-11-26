FROM node:22-bookworm-slim AS javascript
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM rust:bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv 7zip curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/build-python
ENV PATH="/opt/build-python/bin:/usr/local/cargo/bin:${PATH}"
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
COPY --from=javascript /app/node_modules ./node_modules
COPY . .
RUN mkdir -p .build \
    && git init .build/gex \
    && git -C .build/gex remote add origin https://github.com/HeyPuter/gex \
    && git -C .build/gex fetch --depth 1 origin c690edca39a092a2ed2222d040567093545a6858 \
    && git -C .build/gex checkout --detach FETCH_HEAD \
    && git init .build/sunbird-src \
    && git -C .build/sunbird-src remote add origin https://github.com/sunbird-tools/sunbird \
    && git -C .build/sunbird-src fetch --depth 1 origin 10f30b3390d52d12e23e28ead49dcca8e2df32ef \
    && git -C .build/sunbird-src checkout --detach FETCH_HEAD
ARG APPIMAGE_URL
ARG APPIMAGE_SHA256
RUN test -n "$APPIMAGE_URL" && test -n "$APPIMAGE_SHA256" \
    && curl --fail --location --retry 3 "$APPIMAGE_URL" -o .build/input.AppImage \
    && printf '%s  .build/input.AppImage\n' "$APPIMAGE_SHA256" | sha256sum --check \
    && python prepare.py .build/input.AppImage
RUN cargo build --locked --manifest-path .build/sunbird-src/Cargo.toml -p phoenix-loader \
    --target x86_64-unknown-linux-gnu --profile dev-fast --target-dir .build/sunbird-linux-target \
    && python prepare_sunbird.py
RUN rustup component add rust-src && python sunbird/build_memory64.py
RUN mkdir -p /output/usr/bin \
    && cp .build/usr/bin/discord-phoenix /output/usr/bin/ \
    && cp .build/linux.tar .build/sunbird.tar .build/gex-memory64.wasm /output/

FROM python:3.13-slim-bookworm AS runtime
WORKDIR /app
RUN pip install --no-cache-dir 'aiohttp>=3.12,<4' certifi
COPY --from=javascript /app/node_modules ./node_modules
COPY --from=build /output ./.build
COPY app.js index.html windows.js serve.py ./
ENV HOST=0.0.0.0 PORT=10000 PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["python", "serve.py"]
