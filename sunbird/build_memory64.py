"""Rebuild GEX's memory64 shim with its low arena extended to the 4 GiB boundary."""

import os, subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / ".build/gex/hosts/browser/src/winspace.rs"
old = "ARENA_CEILING: AtomicU64 = AtomicU64::new(gex_abi::MMAP_TOP);"
new = 'ARENA_CEILING: AtomicU64 = AtomicU64::new(if cfg!(target_pointer_width = "64") { gex_abi::IMAGE_ZONE64 } else { gex_abi::MMAP_TOP });'
text = source.read_text()
if old in text:
    source.write_text(text.replace(old, new), newline="\n")
elif text.count(new) != 2:
    raise RuntimeError("Unexpected GEX arena source")
flags = []
for arg in [
    "--import-memory",
    "--initial-memory=117440512",
    "--max-memory=17179869184",
    "--global-base=100663296",
    "-zstack-size=8388608",
    "--export=__stack_pointer",
    "--shared-memory",
]:
    flags.extend(["-C", "link-arg=" + arg])
flags.extend(
    [
        "-C",
        "strip=debuginfo",
        "-C",
        "target-feature=+atomics,+bulk-memory,+mutable-globals",
        "-Zcrate-attr=feature(simd_wasm64)",
    ]
)
env = {**os.environ, "RUSTC_BOOTSTRAP": "1", "RUSTFLAGS": " ".join(flags)}
cargo = Path.home() / ".cargo/bin/cargo.exe"
subprocess.run(
    [
        cargo,
        "+stable-x86_64-pc-windows-gnu",
        "build",
        "--manifest-path",
        root / ".build/gex/Cargo.toml",
        "-p",
        "gex-browser",
        "--target",
        "wasm64-unknown-unknown",
        "--release",
        "-Zbuild-std=std,panic_abort",
        "--features",
        "shared-memory,x86",
        "--target-dir",
        root / ".build/gex-m64-target",
    ],
    env=env,
    check=True,
)


import shutil

shutil.copyfile(
    root / ".build/gex-m64-target/wasm64-unknown-unknown/release/gex_browser.wasm",
    root / ".build/gex-memory64.wasm",
)
