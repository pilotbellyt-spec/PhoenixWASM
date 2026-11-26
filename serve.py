"""Serve the Phoenix guest and carry its Discord TLS connections over loopback."""
import asyncio
import os
import re
import tarfile
from pathlib import Path

import certifi
from aiohttp import WSMsgType, web

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "node_modules/@gexemu/runtime"
PORT = int(os.environ.get("PHOENIX_PORT", "8789"))
LOCAL_HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
DISCORD_DOMAINS = (
    "discord.com", "discord.gg", "discordapp.com", "discordapp.net", "discord.media", "discordcdn.com",
    "assets.sunbird.tools", "badges.equicord.org", "sponsor.ajay.app", "dearrow-thumb.ajay.app",
    "translate-pa.googleapis.com", "translate.kagi.com", "manti.vendicated.dev",
)
CHUNK = 256 * 1024


async def isolation_headers(request, response):
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"


async def tcp(request):
    if request.host not in LOCAL_HOSTS or request.headers.get("Origin") != "http://" + request.host:
        raise web.HTTPForbidden()
    host = request.query.get("host", "").lower()
    allowed = host == "ciscobinary.openh264.org" or any(
        host == domain or host.endswith("." + domain) for domain in DISCORD_DOMAINS
    )
    if (request.query.get("port") != "443" or
            not re.fullmatch(r"(?:[a-z0-9-]{1,63}\.)+[a-z0-9-]{1,63}", host) or
            not allowed):
        raise web.HTTPForbidden()
    ws = web.WebSocketResponse(compress=False)
    if not ws.can_prepare(request).ok:
        raise web.HTTPBadRequest()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, 443), timeout=12)
    except (OSError, TimeoutError):
        raise web.HTTPBadGateway(text="Discord connection failed")

    async def upstream():
        async for message in ws:
            if message.type != WSMsgType.BINARY:
                if message.type == WSMsgType.TEXT:
                    raise ValueError("Expected a binary frame")
                break
            writer.write(message.data)
            await writer.drain()

    async def downstream():
        while data := await reader.read(64 * 1024):
            await ws.send_bytes(data)

    tasks = []
    try:
        await ws.prepare(request)
        tasks = [asyncio.create_task(upstream()), asyncio.create_task(downstream())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (OSError, ValueError):
        await ws.close(code=1011)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        writer.close()
        await ws.close()
    return ws


async def phoenix_tar(request):
    elf = ROOT / ".build/usr/bin/discord-phoenix"
    if not elf.is_file():
        raise web.HTTPNotFound(text="Run prepare.py first")
    stat = elf.stat()
    entry = tarfile.TarInfo("usr/bin/discord-phoenix")
    entry.mode, entry.size, entry.mtime = 0o755, stat.st_size, int(stat.st_mtime)
    header = entry.tobuf(format=tarfile.USTAR_FORMAT)
    padding = bytes((-entry.size % 512) + 1024)
    response = web.StreamResponse()
    response.content_type = "application/x-tar"
    response.content_length = len(header) + entry.size + len(padding)
    await response.prepare(request)
    if request.method == "GET":
        await response.write(header)
        with elf.open("rb") as stream:
            while data := stream.read(CHUNK):
                await response.write(data)
        await response.write(padding)
    return response


async def asset(request):
    name = request.path
    assets = {"/": ROOT / "index.html", "/app.js": ROOT / "app.js", "/runtime/windows-fit.mjs": ROOT / "windows.js", "/linux.tar": ROOT / ".build/linux.tar",
              "/phoenix": ROOT / ".build/usr/bin/discord-phoenix", "/ca.pem": Path(certifi.where()),
              "/sunbird.tar": ROOT / ".build/sunbird.tar"}
    path = assets.get(name)
    if re.fullmatch(r"/runtime/gex_browser\.x86\.m64\.shared-[\w-]+\.wasm", name):
        expanded = ROOT / ".build/gex-memory64.wasm"
        if expanded.is_file():
            return web.FileResponse(expanded, headers={"Content-Type": "application/wasm"})
    if name == "/gex/gex_kernel.x86.m64.wasm":
        path = next(RUNTIME.glob("gex_kernel.x86-*.wasm"), None)
    elif re.fullmatch(r"/units/(?:providers/glibc_(?:math|mem)-[a-f0-9]{16}\.wasm|[a-f0-9]{64}/c\.(?:wasm|entries))", name):
        path = ROOT / name[1:]
    elif name == "/aot/manifest.json" or re.fullmatch(r"/aot/[a-f0-9]{64}\.bin", name):
        path = ROOT / ".build/aot" / Path(name).name
    elif path is None and re.fullmatch(r"/runtime/[\w.-]+\.(?:js|mjs|wasm|xkm)", name):
        path = RUNTIME / Path(name).name
    if path is None or not path.is_file():
        raise web.HTTPNotFound()
    types = {".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm"}
    headers = {"Content-Type": types[path.suffix]} if path.suffix in types else {}
    return web.FileResponse(path, headers=headers)


if __name__ == "__main__":
    app = web.Application()
    app.on_response_prepare.append(isolation_headers)
    app.router.add_get("/tcp", tcp, allow_head=False)
    app.router.add_get("/phoenix.tar", phoenix_tar)
    app.router.add_get("/{path:.*}", asset)
    web.run_app(app, host="127.0.0.1", port=PORT, access_log=None)
