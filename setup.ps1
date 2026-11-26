$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force .build | Out-Null

$sources = @(
    @{ Name = 'gex'; Url = 'https://github.com/HeyPuter/gex'; Revision = 'c690edca39a092a2ed2222d040567093545a6858' },
    @{ Name = 'sunbird-src'; Url = 'https://github.com/sunbird-tools/sunbird'; Revision = '10f30b3390d52d12e23e28ead49dcca8e2df32ef' }
)
foreach ($source in $sources) {
    $destination = Join-Path '.build' $source.Name
    if (!(Test-Path -LiteralPath $destination)) {
        git -c core.autocrlf=false clone $source.Url $destination
        if ($LASTEXITCODE -ne 0) { throw "Could not clone $($source.Name)" }
        git -C $destination checkout --detach $source.Revision
        if ($LASTEXITCODE -ne 0) { throw "Could not check out $($source.Name)" }
    }
    $head = git -C $destination rev-parse HEAD
    if ($head -ne $source.Revision) { throw "Unexpected revision in $destination" }
}
npm ci
if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
