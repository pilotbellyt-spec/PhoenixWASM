"""Run an x86-64 HTTPS and WebSocket probe inside the browser guest."""
import io
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright


def guest_tar():
    buf = io.BytesIO()
    with TemporaryDirectory() as tmp:
        exe = Path(tmp) / "network-check"
        env = {**os.environ, "GOOS": "linux", "GOARCH": "amd64", "CGO_ENABLED": "0"}
        subprocess.run(["go", "build", "-buildmode=pie", "-ldflags", "-s -w", "-o", exe,
                        Path(__file__).parent / "tests/network/main.go"], env=env, check=True)
        with tarfile.open(fileobj=buf, mode="w") as archive:
            entry = archive.gettarinfo(str(exe), arcname="usr/bin/discord-phoenix")
            entry.mode = 0o755
            with exe.open("rb") as source:
                archive.addfile(entry, source)
    return buf.getvalue()


if __name__ == "__main__":
    payload = guest_tar()
    with sync_playwright() as pw, pw.chromium.launch(channel="chrome") as browser:
        page = browser.new_page()
        page.route("**/phoenix.tar", lambda route: route.fulfill(body=payload, content_type="application/x-tar"))
        page.goto("http://localhost:8789/?volatile&sunbird=0")
        page.click("#run")
        page.wait_for_function("""() => {
            const log = document.querySelector('#log').textContent;
            return log.includes('Discord TLS WebSocket upgrade passed') || log.includes('Exited ');
        }""", timeout=120_000)
        log = page.locator("#log").text_content()
        assert "Discord HTTPS gateway discovery passed" in log and "Discord TLS WebSocket upgrade passed" in log, log
        print("Discord gateway discovery returned HTTP 200 and the guest verified the TLS WebSocket upgrade.")
