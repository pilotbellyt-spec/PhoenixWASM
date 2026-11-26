$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = (Get-Command python).Source
@"
import subprocess, sys
args = [arg for arg in sys.argv[1:] if not arg.startswith("--target=")]
raise SystemExit(subprocess.call([sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-linux-gnu.2.28", *args]))
"@ | Set-Content .build/linux-cc.py -Encoding ascii
("@"+[char]34+$python+[char]34+" "+[char]34+'%~dp0linux-cc.py'+[char]34+" %*") | Set-Content .build/linux-cc.cmd -Encoding ascii
("@"+[char]34+$python+[char]34+" -m ziglang ar %*") | Set-Content .build/linux-ar.cmd -Encoding ascii
$env:CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER = (Resolve-Path .build/linux-cc.cmd).Path
$env:CC_x86_64_unknown_linux_gnu = $env:CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER
$env:AR_x86_64_unknown_linux_gnu = (Resolve-Path .build/linux-ar.cmd).Path
$env:CARGO_TARGET_DIR = Join-Path $root '.build/sunbird-linux-target'
& "$env:USERPROFILE/.cargo/bin/cargo.exe" +stable-x86_64-pc-windows-gnu build --manifest-path .build/sunbird-src/Cargo.toml -p phoenix-loader --target x86_64-unknown-linux-gnu --profile dev-fast --locked
if ($LASTEXITCODE -ne 0) { throw 'Sunbird build failed' }
python prepare_sunbird.py
if ($LASTEXITCODE -ne 0) { throw 'Sunbird packaging failed' }
