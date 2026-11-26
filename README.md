# Phoenix WASM64 proof of concept

Open http://127.0.0.1:8789/ in Chrome and select **Run Phoenix**. Use http://127.0.0.1:8789/?check for a bounded startup check. It stops the guest once Phoenix emits its own main_init milestone. Restart saves the guest filesystem before reloading.

The default launch runs Sunbird with x86-64 to WASM64 JIT translation. Add `?sunbird=0` to launch Phoenix without Sunbird. Precompiled translation modes remain available through their query parameters.

Normal launches keep changed guest files in the browser's origin private filesystem, including Phoenix's cache database and Sunbird settings. Files are flushed within one second, on guest fsync, and on Restart. The runtime also flushes when the page is hidden or left. One running tab can hold this filesystem at a time. Browser storage is separate for each hostname and port, so keep using the same URL. Private browsing and clearing site data remove that browser's files. Add `&volatile` to the Sunbird URL for a temporary session.

Phoenix currently reports that the Linux OS keychain is unavailable. Persistent guest files therefore do not establish persistent account authentication. Login may still be required after restarting.

The browser loads the original Linux ELF from the supplied AppImage. The Phoenix process uses memory64. GEX supplies Linux system calls, a browser Wayland compositor and XWayland. The guest loads its keyboard data, fonts and shared libraries from a local tar archive. The AppImage's SwiftShader Vulkan driver renders the signed-out GPUI window. A preload library enables the system XKB include paths when GPUI reads the compositor's keyboard map.

## Discord network

Open [Phoenix](http://localhost:8789/) in Chrome and select **Run Phoenix**. The same server carries the desktop's outbound TCP connections on port 443. Phoenix negotiates TLS with Discord and validates its certificate using the guest's CA bundle. HTTPS API requests and secure gateway WebSockets share this path. The relay accepts connections from the local launcher to Discord service domains and the Cisco OpenH264 download host. Voice and video UDP are outside the current transport.

To verify the connection without a Discord account, install Go and Playwright and run `python verify_network.py` while the server is running. The test launches an x86-64 Linux guest in Chrome, fetches Discord's public gateway URL over HTTPS, and verifies Discord's WebSocket upgrade response.

## Translation modes

| Chrome URL | What runs |
| --- | --- |
| [Default](http://localhost:8789/) or [JIT](http://localhost:8789/?jit) | Sunbird with runtime x86-64 to WASM64 translation. |
| [Precompiled functions](http://localhost:8789/?providers) | Precompiled WASM64 implementations of glibc memory and math functions, with runtime translation for remaining x86 instructions. |
| [Recorded Phoenix instructions](http://localhost:8789/?recorded) | Installs a small recording of machine-code blocks from the original Phoenix executable before launch. The guest log reports how many modules GEX restores. |
| [AOT keyboard library](http://localhost:8789/?keyboard) | Loads selected keyboard lookup functions statically translated from the Debian x86-64 libxkbcommon ELF at its observed load address. GEX checks the image and compiler fingerprint. |

The large training recording exceeded six minutes without painting in one trial. The recording builder therefore selects early Phoenix modules with a 2 MiB WASM budget and preserves their dispatch slots. GEX can still translate every missing block. The launcher preserves the executable's file timestamp across boots so GEX can validate the recording.

In a sequential cold Chrome comparison on this machine, the first compositor frame took 74.23 s with JIT, 92.28 s with precompiled glibc functions and 116.34 s with the compact recording plus those functions. Each mode ran once in this comparison. Other trials varied with machine load. A separate guest benchmark copied 256 MiB per sample through glibc. Median copy time over three samples fell from 26.73 ms to 9.61 ms with the precompiled provider. Run `python aot/verify_memcpy.py` to repeat that operation-level measurement.

From this directory on Windows, install 7-Zip and ensure Python, Node.js and curl are available. To rebuild and start the server:

```powershell
./setup.ps1
python -m pip install pyelftools ziglang==0.14.1 "aiohttp>=3.12,<4" certifi
python prepare.py "$env:USERPROFILE\Downloads\discord-desktop-0.1.0-dev.20261123093910.gb71ec80-linux-x64.AppImage"
rustup target add x86_64-unknown-linux-gnu --toolchain stable-x86_64-pc-windows-gnu
rustup component add rust-src --toolchain stable-x86_64-pc-windows-gnu
./sunbird/build-linux.ps1
python sunbird/build_memory64.py
python serve.py
```

The package builder fetches Debian trixie metadata and checks each downloaded package against its indexed SHA-256. Local inputs and extracted files stay in the .build directory. To repeat the automated check with Chrome installed:

```powershell
python -m pip install playwright
python verify_startup.py
```

The check requires the expected Phoenix build hash in guest output, a successful memory64 translator fetch and the main_init milestone. It does not exercise sign-in or messaging.

To rebuild the recording, leave the local server running and run `python pretranslate.py`. This starts Phoenix in a fresh Chrome profile, waits for a compositor frame and publishes the small cache under `.build/aot`. To benchmark, run the following with other Phoenix tabs stopped. Each sample opens a fresh Chrome process. Timing starts at the Run button and ends when the launcher observes a compositor frame. It includes loading the guest and its dependencies.

```powershell
python verify_startup.py --benchmark --rounds 2 --modes jit providers recorded keyboard
```

To generate the optional static units, use the GEX revision in `units/NOTICE` with LF line endings in `.build/gex`. From the project root, run `cargo run --manifest-path aot/Cargo.toml` using a host Rust toolchain and a Clang and wasm-ld toolchain with wasm64 support. GEX accepts the tool paths in `GEX_CLANG` and `GEX_WASM_LD`. Re-run `prepare.py` before building units if the guest libraries change.
