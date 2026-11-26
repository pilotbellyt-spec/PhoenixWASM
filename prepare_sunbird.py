"""Package the upstream desktop loader, plugins and Linux HTTP dependencies."""

import io, json, lzma, os, subprocess, tarfile, zipfile
from pathlib import Path
from elftools.elf.elffile import ELFFile
from prepare import CACHE, LIB, data_tar, fetch_package

SRC = CACHE / "sunbird-src"
OUT = CACHE / "sunbird-linux-target/x86_64-unknown-linux-gnu/dev-fast/libphoenix.so"


def package():
    if not OUT.is_file():
        raise RuntimeError("Build phoenix-loader for Linux first")
    entries = {}
    bundle = {}
    esbuild = (["node", "node_modules/esbuild/bin/esbuild"] if os.name == "nt"
               else [str(Path("node_modules/esbuild/bin/esbuild").resolve())])
    for entry in sorted((SRC / "plugins").glob("*/src/index.ts")):
        name = entry.parents[1].name
        if name == "example":
            continue
        dest = CACHE / "sunbird-plugins" / (name + ".js")
        dest.parent.mkdir(exist_ok=True)
        subprocess.run(
            [
                *esbuild,
                str(entry),
                "--bundle",
                "--format=iife",
                "--target=es2023",
                "--log-level=warning",
                "--banner:js="
                + chr(10).join(
                    line
                    for line in entry.read_text(encoding="utf8").splitlines()
                    if line.startswith("// @")
                ),
                "--outfile=" + str(dest),
            ],
            check=True,
        )
        bundle[name] = dest.read_text(encoding="utf8")
    packages = {}
    for para in (
        lzma.open(CACHE / "Packages.xz", "rt", encoding="utf8").read().split("\n\n")
    ):
        fields = dict(
            line.split(": ", 1)
            for line in para.splitlines()
            if not line.startswith(" ") and ": " in line
        )
        if "Filename" in fields:
            packages[fields["Package"]] = fields
    # curl's dynamic dependencies are read from the ELF, as for Phoenix.
    import gzip

    owners = {}
    with gzip.open(CACHE / "Contents-amd64.gz", "rt", encoding="utf8") as lines:
        for line in lines:
            if line.startswith(LIB):
                path, pkgs = line.rsplit(maxsplit=1)
                if "/" not in path[len(LIB) :]:
                    owners[Path(path).name] = (pkgs.split(",")[0].split("/")[-1], path)
    pending = ["libcurl.so.4"]
    while pending:
        name = pending.pop()
        if name in entries or (CACHE / "libs" / name).exists():
            continue
        pkg, path = owners[name]
        with data_tar(fetch_package(packages[pkg])) as archive:
            info = archive.getmember("./" + path)
            while info.issym():
                info = archive.getmember("./" + LIB + Path(info.linkname).name)
            data = archive.extractfile(info).read()
        entries[name] = data
        elf = ELFFile(io.BytesIO(data))
        dyn = elf.get_section_by_name(".dynamic")
        if dyn:
            pending.extend(t.needed for t in dyn.iter_tags("DT_NEEDED"))
    with tarfile.open(CACHE / "sunbird.tar", "w") as archive:
        archive.add(OUT, arcname="lib/libphoenix.so")
        for path, data in [
            ("lib/libplm.plugins.so", json.dumps(bundle).encode()),
            *[("lib/x86_64-linux-gnu/" + n, b) for n, b in entries.items()],
        ]:
            info = tarfile.TarInfo(path)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    print("Packaged Sunbird and", len(entries), "HTTP libraries")


if __name__ == "__main__":
    package()
