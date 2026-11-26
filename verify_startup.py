"""Check real guest startup or compare click-to-frame latency in fresh Chrome profiles."""
import argparse
import re
import statistics
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8789/"
BUILD = "b71ec8038fe99a85585c1846b05399c174fd7a4d"


def run(chromium, query, desktop):
    with chromium.launch(channel="chrome") as browser:
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        loaded = []
        page.on("response", lambda r: loaded.append(urlsplit(r.url).path) if r.ok else None)
        page.goto(BASE + query)
        start = time.perf_counter()
        page.click("#run")
        condition = ("document.querySelector('#status').textContent === 'Phoenix desktop'" if desktop
                     else "document.querySelector('#status').dataset.passed === 'true'")
        page.wait_for_function(condition, timeout=360000 if desktop else 90000)
        elapsed = time.perf_counter() - start
        log = page.locator("#log").text_content()
        assert BUILD in log, f"Phoenix build missing from guest log: {log[:2000]}"
        assert "milestone=main_init" in log, f"Missing guest startup milestone: {log[:2000]}"
        if desktop:
            assert "first_screen" in log and "screen=login" in log, "Signed-out guest did not reach login"
        assert any("gex_browser.x86.m64.shared" in path for path in loaded)
        if any(mode in query for mode in ["providers", "recorded", "keyboard"]):
            assert any("/units/providers/glibc_mem-" in path for path in loaded)
            assert any("/units/providers/glibc_math-" in path for path in loaded)
        if "recorded" in query:
            assert re.search(r"restored [1-9][0-9]* modules", log), "Phoenix recording was not restored"
        if "keyboard" in query:
            assert any(path.endswith("/c.wasm") for path in loaded)
        print(f"{BASE}{query}  {page.locator('#status').inner_text()}  {elapsed:.2f} s", flush=True)
        return elapsed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--modes", nargs="+", default=["jit", "providers"],
                        choices=["jit", "providers", "recorded", "keyboard"])
    args = parser.parse_args()
    with sync_playwright() as pw:
        if args.benchmark:
            if args.rounds < 1:
                parser.error("--rounds must be positive")
            samples = {mode: [] for mode in args.modes}
            for i in range(args.rounds):
                order = args.modes if i % 2 == 0 else reversed(args.modes)
                for mode in order:
                    samples[mode].append(run(pw.chromium, "?" + mode, True))
            for mode, times in samples.items():
                print(f"{mode} median {statistics.median(times):.2f} s ({len(times)} runs)")
        else:
            run(pw.chromium, "?check", False)
