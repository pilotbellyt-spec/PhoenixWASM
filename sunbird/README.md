# Sunbird UI codec for WASM64

The full Linux desktop loader is also available at http://localhost:8790/?sunbird in the test server. It runs inside Phoenix's WASM64 process with upstream QuickJS, SQLite, native hooks and all 17 bundled plugins. The separate mobile UI codec below remains available.

Run `sunbird/build-linux.ps1` to rebuild the Linux loader and package its plugins and libcurl dependencies. Run `python sunbird/build_memory64.py` to rebuild GEX's memory64 shim. These commands use the local Sunbird and GEX checkouts under `.build`.

The GEX shim now permits its low translator arena to grow to 4 GiB. The memory64 guest retains its 16 GiB address space, with its high region beginning at 4 GiB. This resolves the observed 2 GiB allocator abort during Sunbird initialization.

Full Linux feature parity remains unverified. Account-dependent plugins require sign-in. Normal launches persist guest files in OPFS. Phoenix's OS keychain and Sunbird's Linux tray helper require desktop services the browser guest currently lacks.

This module compiles the Rust UI batch encoder and decoder from Sunbird's `phoenix-ui-mobile` crate and its `phoenix-wire` dependency. It handles the mobile UI format. Phoenix's desktop GPUI uses a separate backend. This module runs independently of the signed-in client.

`encode_template(index)` writes a batch for one of the ten upstream layouts. Nodes receive fresh IDs in preorder. `reserve_input(length)` allocates a buffer for an encoded batch. `describe_batch()` replaces the input with upstream's JSON description, returning its byte length on success or the negative length of a UTF-8 error message. `buffer_ptr()` gives the address until the next buffer operation. Chrome exposes the pointer and lengths as BigInt.

The source revision is [Sunbird 10f30b3](https://github.com/sunbird-tools/sunbird/tree/10f30b3390d52d12e23e28ead49dcca8e2df32ef). To rebuild from the PhoenixWASM project root with a Rust nightly toolchain:

```powershell
git clone https://github.com/sunbird-tools/sunbird .build/sunbird-src
git -C .build/sunbird-src checkout --detach 10f30b3390d52d12e23e28ead49dcca8e2df32ef
rustup component add rust-src --toolchain nightly
cargo +nightly build --manifest-path sunbird/Cargo.toml --target-dir .build/sunbird-target --locked --release --target wasm64-unknown-unknown '-Zbuild-std=std,panic_abort'
Copy-Item .build/sunbird-target/wasm64-unknown-unknown/release/sunbird_ui.wasm sunbird/sunbird_ui.wasm
python sunbird/verify.py
```
