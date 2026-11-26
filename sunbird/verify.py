"""Exercise the WASM64 UI codec in Chrome against Sunbird's checked-in templates."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / ".build/sunbird-src/crates/ui-mobile/src/templates.json"
NAMES = ["section", "header", "group", "switchRow", "divider", "buttonRow", "valueRow", "input", "page", "sheet"]


def expected(node):
    return [node["type"], [expected(child) for child in node.get("kids", [])]]


def decoded_tree(ops):
    nodes = {op["id"]: op["kind"] for op in ops if op["op"] == "create"}
    children = {op["id"]: op["ids"] for op in ops if op["op"] == "children"}

    def visit(node_id):
        return [nodes[node_id], [visit(i) for i in children.get(node_id, [])]]

    return visit(next(op["id"] for op in ops if op["op"] == "root"))


if __name__ == "__main__":
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    with sync_playwright() as pw, pw.chromium.launch(channel="chrome") as browser:
        page = browser.new_page()
        page.route("http://codec.test/", lambda route: route.fulfill(body="<title>Codec test</title>", content_type="text/html"))
        page.route("http://codec.test/ui.wasm", lambda route: route.fulfill(path=HERE / "sunbird_ui.wasm", content_type="application/wasm"))
        page.goto("http://codec.test/")
        result = page.evaluate("""async count => {
            const {instance} = await WebAssembly.instantiateStreaming(fetch('/ui.wasm'));
            const api = instance.exports;
            if (typeof api.buffer_ptr() !== 'bigint') throw Error('Expected a 64-bit pointer');
            function read(size) {
                return new Uint8Array(api.memory.buffer, Number(api.buffer_ptr()), Number(size));
            }
            function decode(bytes) {
                const ptr = api.reserve_input(BigInt(bytes.length));
                new Uint8Array(api.memory.buffer, Number(ptr), bytes.length).set(bytes);
                const n = api.describe_batch();
                const text = new TextDecoder().decode(read(n < 0n ? -n : n));
                if (n < 0n) throw Error(text);
                return JSON.parse(text);
            }
            try {
                decode(Uint8Array.of(255));
                throw Error('Malformed batch accepted');
            } catch (e) {
                if (!/version/i.test(e.message)) throw e;
            }
            const root = decode(Uint8Array.of(1, 5, 42, 0, 0, 0));
            const templates = Array.from({length: count}, (_, i) => {
                const bytes = read(api.encode_template(i)).slice();
                return decode(bytes);
            });
            return {root, templates};
        }""", len(NAMES))
    assert result["root"] == [{"op": "root", "id": 42}]
    for name, ops in zip(NAMES, result["templates"], strict=True):
        assert decoded_tree(ops) == expected(fixtures[name]), name
    print(f"Chrome passed {len(NAMES)} template trees, the known root frame, and the malformed input check.")
