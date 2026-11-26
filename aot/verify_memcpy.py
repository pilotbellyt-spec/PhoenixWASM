"""Time the same dynamically linked x86-64 memcpy loop with and without the provider."""
import io
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tarfile
import tempfile

from playwright.sync_api import sync_playwright


def guest(directory):
    executable = directory / "copybench"
    subprocess.run([sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-linux-gnu",
                    "-fPIE", "-pie", "-O2", "-fno-builtin-memcpy",
                    str(Path(__file__).with_name("memcpy.c")), "-o", str(executable)], check=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as archive:
        info = archive.gettarinfo(str(executable), arcname="usr/bin/discord-phoenix")
        info.mode = 0o755
        with executable.open("rb") as stream:
            archive.addfile(info, stream)
    return buf.getvalue()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        payload = guest(Path(tmp))
    with sync_playwright() as pw:
        for mode in ["jit", "providers"]:
            with pw.chromium.launch(channel="chrome") as browser:
                page = browser.new_page()
                page.route("**/phoenix.tar", lambda route: route.fulfill(body=payload, content_type="application/x-tar"))
                page.goto("http://127.0.0.1:8789/?" + mode + "&sunbird=0")
                page.click("#run")
                page.wait_for_function("document.querySelector('#log').textContent.includes('Copy benchmark complete')")
                rows = re.findall(r"Copy sample ([0-9.]+) s checksum=(\d+)", page.locator("#log").text_content())
                assert [checksum for _, checksum in rows] == ["232", "233", "234"]
                times = [float(seconds) * 1000 for seconds, _ in rows]
                print(f"{mode}: {times} ms, median {statistics.median(times):.2f} ms per 256 MiB")
