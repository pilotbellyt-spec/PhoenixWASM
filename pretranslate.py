"""Record reusable WASM64 translations while a fresh Chrome profile starts Phoenix."""
import hashlib
import json
from pathlib import Path
import re
import struct
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent / ".build" / "aot"

def startup_blocks(source, destination, budget=2 * 1024 * 1024):
    """Keep early Phoenix modules from GEXXC v1. Preserve dispatch slots and module IDs."""
    with source.open("rb") as stream:
        def read(fmt):
            codec = struct.Struct("<" + fmt)
            return codec.unpack(stream.read(codec.size))

        def count():
            return read("I")[0]

        if stream.read(8) != b"GEXXC\0\0\1":
            raise ValueError("Unsupported GEX cache format")
        paths = []
        for _ in range(count()):
            paths.append(stream.read(count()).decode())
            read("QQ")
        phoenix_keys = set()
        for _ in range(count()):
            key, index = read("QI")
            if paths[index] == "/usr/bin/discord-phoenix":
                phoenix_keys.add(key)
        stream.seek(count() * 20 + 8, 1)  # Slot assignments and high-water mark.
        prefix_size = stream.tell()
        records = []
        for _ in range(count()):
            start = stream.tell()
            read("Q")
            stream.seek(count() * 12, 1)
            size = count()
            records.append((start, stream.tell(), size))
            stream.seek(size, 1)

        def claims(key_format):
            rows = []
            for _ in range(count()):
                key = read(key_format)
                ids = read(str(count()) + "I")
                if key[-1] in phoenix_keys:
                    rows.append((key, ids))
            return rows

        pages = claims("QQ")
        objects = claims("Q")
        claimed = {i for _, ids in pages + objects for i in ids}
        keep = set()
        for module_id, (_, _, size) in enumerate(records, start=2):
            if module_id in claimed and 0 < size <= budget:
                keep.add(module_id)
                budget -= size
        if not keep:
            raise ValueError("No recorded Phoenix instruction blocks")
        with destination.open("wb") as out:
            def write(fmt, *values):
                out.write(struct.pack("<" + fmt, *values))

            stream.seek(0)
            out.write(stream.read(prefix_size))
            write("I", max(keep) - 1)
            for module_id, (start, body, size) in enumerate(records[:max(keep)-1], start=2):
                if module_id in keep:
                    stream.seek(start)
                    out.write(stream.read(body - start + size))
                else:
                    write("QII", 0, 0, 0)
            for fmt, groups in [("QQ", pages), ("Q", objects)]:
                rows = [(key, [i for i in ids if i in keep]) for key, ids in groups]
                rows = [(key, ids) for key, ids in rows if ids]
                write("I", len(rows))
                for key, ids in rows:
                    write(fmt, *key)
                    write("I", len(ids))
                    write(str(len(ids)) + "I", *ids)
            write("I", 0)  # No whole object is marked fully translated.
    return len(keep)


def publish(source, key):
    if not re.fullmatch(r"xc-[a-f0-9]{16}", key):
        raise ValueError(f"Unexpected GEX cache name: {key}")
    size = source.stat().st_size
    if size == 0:
        raise ValueError("The compiler produced an empty cache")
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    filename = digest + ".bin"
    source.replace(BASE / filename)
    manifest = {"key": key, "size": size, "file": filename}
    temporary = source.parent / "manifest.json"
    temporary.write_text(json.dumps(manifest), encoding="utf-8")
    temporary.replace(BASE / "manifest.json")
    print(f"Published {size / 1048576:.1f} MiB of translations for {key}.")


def build():
    BASE.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=BASE) as tmp, sync_playwright() as pw:
        with pw.chromium.launch(channel="chrome") as browser:
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            page.goto("http://127.0.0.1:8789/?train")
            page.click("#run")
            page.wait_for_function("document.querySelector('#status').textContent === 'Phoenix desktop'", timeout=360000)
            # Workers save the shared translation cache as child processes exit.
            page.wait_for_function("""async () => {
                for await (const [name, handle] of (await navigator.storage.getDirectory()).entries()) {
                    if (name.startsWith('xc-') && (await handle.getFile()).size) return true;
                }
                return false;
            }""", timeout=60000)
            with page.expect_download() as recording:
                page.evaluate("""async () => {
                    const dir = await navigator.storage.getDirectory();
                    const keys = [];
                    for await (const key of dir.keys()) if (key.startsWith('xc-')) keys.push(key);
                    if (keys.length !== 1) throw Error('Expected one translation cache');
                    const file = await (await dir.getFileHandle(keys[0])).getFile();
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(file);
                    link.download = keys[0] + ".bin";
                    link.click();
                }""")
            file = Path(tmp) / "recording"
            recording.value.save_as(file)
            subset = Path(tmp) / "startup"
            modules = startup_blocks(file, subset)
            print(f"Selected {modules} modules from the Phoenix executable.")
            publish(subset, recording.value.suggested_filename.removesuffix(".bin"))


if __name__ == "__main__":
    build()
