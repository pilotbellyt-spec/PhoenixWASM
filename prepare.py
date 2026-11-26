"""Prepare the Phoenix executable and its Linux dynamic-link dependencies."""
import argparse
import gzip
import hashlib
import io
import lzma
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from elftools.elf.elffile import ELFFile

CACHE = Path(".build")
LIB = "usr/lib/x86_64-linux-gnu/"
MIRROR = "https://deb.debian.org/debian/"


def download(rel, dest):
    if not dest.exists():
        tmp = dest.with_suffix(".part")
        subprocess.run(["curl", "-fsSL", "--retry", "3", MIRROR + rel, "-o", tmp], check=True)
        tmp.replace(dest)


def data_tar(deb):
    with deb.open("rb") as f:
        if f.read(8) != b"!<arch>\n":
            raise ValueError(deb)
        while header := f.read(60):
            size = int(header[48:58])
            if header.startswith(b"data.tar"):
                return tarfile.open(fileobj=io.BytesIO(f.read(size)))
            f.seek(size + size % 2, 1)
    raise ValueError(f"No data archive in {deb}")


def fetch_package(info):
    deb = CACHE / Path(info["Filename"]).name
    download(info["Filename"], deb)
    if hashlib.sha256(deb.read_bytes()).hexdigest() != info["SHA256"]:
        raise ValueError(f"Unexpected digest for {deb}")
    return deb


def build(app):
    CACHE.mkdir(exist_ok=True)
    exe = CACHE / "usr/bin/discord-phoenix"
    seven = shutil.which("7zz") or shutil.which("7z") or r"C:\Program Files\7-Zip\7z.exe"
    driver = Path("usr/lib/discord-phoenix/modules/discord_cef-0/discord_cef")
    icd = driver / "vk_swiftshader_icd.json"
    swiftshader = driver / "libvk_swiftshader.so"
    subprocess.run([seven, "x", "-y", "-o.build", app.resolve(), "usr/bin/discord-phoenix", str(icd), str(swiftshader)], check=True)
    index = CACHE / "Packages.xz"
    contents = CACHE / "Contents-amd64.gz"
    download("dists/trixie/main/binary-amd64/Packages.xz", index)
    download("dists/trixie/main/Contents-amd64.gz", contents)
    packages = {}
    for para in lzma.open(index, "rt", encoding="utf-8").read().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in para.splitlines() if not line.startswith(" ") and ": " in line)
        if "Filename" in fields:
            packages[fields["Package"]] = fields
    owners = {}
    with gzip.open(contents, "rt", encoding="utf-8") as entries:
        for line in entries:
            if line.startswith(LIB):
                path, pkgs = line.rsplit(maxsplit=1)
                if "/" not in path[len(LIB):] or "/pulseaudio/" in path:
                    owners[Path(path).name] = (pkgs.split(",")[0].split("/")[-1], path)

    libdir = CACHE / "libs"
    libdir.mkdir(exist_ok=True)
    pending = [exe, CACHE / swiftshader]
    libraries = {}
    while pending:
        binary = pending.pop()
        with binary.open("rb") as f:
            dyn = ELFFile(f).get_section_by_name(".dynamic")
            needed = [tag.needed for tag in dyn.iter_tags("DT_NEEDED")]
        if binary == exe:
            needed.extend(["libwayland-client.so.0", "libwayland-cursor.so.0", "libwayland-egl.so.1", "libEGL.so.1", "libvulkan.so.1"])
        for soname in needed:
            if soname in libraries:
                continue
            owner, source = owners[soname]
            info = packages[owner]
            deb = fetch_package(info)
            target = libdir / soname
            with data_tar(deb) as archive:
                entry = archive.getmember("./" + source)
                while entry.issym():
                    entry = archive.getmember("./" + LIB + Path(entry.linkname).name)
                with target.open("wb") as out:
                    shutil.copyfileobj(archive.extractfile(entry), out)
            libraries[soname] = target
            pending.append(target)

    shim = CACHE / "wayland-keymap.so"
    subprocess.run([sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-linux-gnu",
                    "-shared", "-fPIC", "-O2", "wayland-keymap.c", "-o", shim, "-ldl"], check=True)
    with tarfile.open(CACHE / "linux.tar", "w") as archive:
        archive.add(shim, arcname="lib/wayland-keymap.so")
        archive.add(CACHE / icd, arcname="usr/share/vulkan/icd.d/" + icd.name)
        archive.add(CACHE / swiftshader, arcname="usr/share/vulkan/icd.d/" + swiftshader.name)
        for pkg, prefix in [("xkb-data", "./usr/share/X11/xkb/"), ("fonts-dejavu-core", "./usr/share/fonts/")]:
            with data_tar(fetch_package(packages[pkg])) as data:
                for entry in data:
                    if entry.isfile() and entry.name.startswith(prefix):
                        stream = data.extractfile(entry)
                        entry.name = entry.name.removeprefix("./")
                        archive.addfile(entry, stream)
        for name, path in libraries.items():
            archive.add(path, arcname="lib/x86_64-linux-gnu/" + name)
        link = tarfile.TarInfo("lib64/ld-linux-x86-64.so.2")
        link.type = tarfile.SYMTYPE
        link.linkname = "/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
        archive.addfile(link)
    print(f"Prepared {exe.stat().st_size} bytes of Phoenix and {len(libraries)} shared libraries.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("appimage", type=Path)
    build(parser.parse_args().appimage)
