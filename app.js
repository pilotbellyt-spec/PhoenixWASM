import { System } from "/runtime/index.mjs";
import { MemoryFilesystem, OPFSFilesystem } from "/runtime/fs.mjs";
import { SingleCanvas } from "/runtime/windows-fit.mjs";

import { MesaGl } from "/runtime/gl.mjs";

const output = document.querySelector("#log");
const status = document.querySelector("#status");
const options = new URLSearchParams(location.search);
const checkOnly = options.has("check");
const useTranslations = !options.has("jit") &&
    ["providers", "keyboard", "recorded", "train"].some(mode => options.has(mode));

async function installTranslations() {
    const response = await fetch("/aot/manifest.json", { cache: "no-store" });
    if (response.status === 404) return;
    if (!response.ok) throw Error("Could not load the translation manifest");
    const { key, file, size } = await response.json();
    if (!/^xc-[a-f0-9]{16}$/.test(key) || !/^[a-f0-9]{64}\.bin$/.test(file) ||
        !Number.isSafeInteger(size) || size <= 0) throw Error("Invalid translation manifest");
    await navigator.locks.request(key, async () => {
        const root = await navigator.storage.getDirectory();
        const handle = await root.getFileHandle(key, { create: true });
        if ((await handle.getFile()).size === size && localStorage.getItem(key) === file) return;
        const data = await fetch("/aot/" + file);
        if (!data.ok || Number(data.headers.get("Content-Length")) !== size)
            throw Error("Incomplete translation download");
        await data.body.pipeTo(await handle.createWritable());
        localStorage.setItem(key, file);
    });
}
status.textContent = checkOnly ? "Startup check stops after Phoenix reports main_init." : "Launch the Linux desktop executable with the browser Wayland compositor.";
let activeSystem;
let desktopWindows;
const expandButton = document.querySelector("#expand");
function setExpanded(expanded) {
    document.body.classList.toggle("expanded", expanded);
    expandButton.textContent = expanded ? "Collapse" : "Expand";
    expandButton.setAttribute("aria-pressed", String(expanded));
    desktopWindows?.expand(expanded);
}
expandButton.onclick = () => setExpanded(!document.body.classList.contains("expanded"));
document.addEventListener("keydown", event => {
    if (event.key === "Escape" && document.body.classList.contains("expanded")) {
        event.preventDefault();
        event.stopPropagation();
        setExpanded(false);
    }
}, true);
document.querySelector("#reload").onclick = async () => {
    const button = document.querySelector("#reload");
    button.disabled = true;
    try {
        status.textContent = "Saving files…";
        await activeSystem?.shutdown();
        location.reload();
    } catch (error) {
        status.textContent = "Could not save files. " + error.message;
        button.disabled = false;
    }
};
function log(text) {
    text = text.replace(/\x1b\[[0-9;]*m/g, "").replace(/\r/g, "");
    output.append(document.createTextNode(text + "\n"));
    output.scrollTop = output.scrollHeight;
    console.info(text);
}
async function start() {
    const startedAt = performance.now();
    document.querySelector("#run").disabled = true;
    document.querySelector("#reload").hidden = false;
    status.textContent = "Starting…";
    if (!useTranslations) log("Translation mode: WASM64 JIT");
    else if (options.has("keyboard")) log("Translation mode: WASM64 with precompiled keyboard, memory and math functions");
    else log("Translation mode: WASM64 with precompiled memory and math functions");
    if (options.has("recorded") && useTranslations) {
        try { await installTranslations(); }
        catch (error) { log("Starting with runtime translation: " + error.message); }
    }
    const sys = new System({
        arch: "x86",
        units: useTranslations ? "/units" : undefined,
        xcache: useTranslations && (options.has("recorded") || options.has("train")) && "phoenix",
        debug: { mem64: 1, elfunits: useTranslations && options.has("keyboard") ? "libxkbcommon.so.0" : "" }
    });
    activeSystem = sys;
    sys.network = {
        async connect(host, port) {
            const url = new URL("/tcp", location.href);
            url.protocol = "ws:";
            url.search = new URLSearchParams({ host, port });
            const socket = new WebSocketStream(url.href);
            // The streams and opened promise already propagate connection failures.
            socket.closed.catch(() => {});
            const { readable, writable } = await socket.opened;
            return {
                readable: readable.pipeThrough(new TransformStream({
                    transform(bytes, controller) { controller.enqueue(new Uint8Array(bytes)); }
                })),
                writable
            };
        }
    };
    const keepFiles = !options.has("volatile") && !checkOnly && !options.has("train");
    const fs = keepFiles
        ? new OPFSFilesystem(sys, { name: "phoenix-home-v1", cache: 128, writeback: 1000 })
        : new MemoryFilesystem(sys);
    if (keepFiles) {
        const protectedStorage = await navigator.storage.persist();
        log("Guest files are saved in this browser." +
            (protectedStorage ? " Persistent storage granted." : " Storage remains subject to browser eviction."));
    }
    document.querySelector("#details").open = checkOnly;
    const windows = new SingleCanvas(sys, { container: document.querySelector("#screen") });
    desktopWindows = windows;
    windows.expand(document.body.classList.contains("expanded"));
    new MesaGl(sys);
    new ResizeObserver(() => windows.resized()).observe(document.querySelector("#screen"));
    let guestOpenedScreen = false;
    const paintCheck = checkOnly ? null : setInterval(async () => {
        if (guestOpenedScreen && (await windows.describe())?.frames > 0) {
            status.textContent = "Phoenix desktop";
            clearInterval(paintCheck);
            log("First compositor paint after " + ((performance.now() - startedAt) / 1000).toFixed(1) + " s");
        }
    }, 2000);
    sys.addEventListener("crash", e => log(e.name + ": " + e.reason));
    fs.addTar("/linux.tar");
    const sunbirdEnabled = options.has("sunbird");
    if (sunbirdEnabled) fs.addTar("/sunbird.tar");
    const caFile = "/etc/ssl/certs/ca-certificates.crt";
    fs.addFiles({ [caFile]: new URL("/ca.pem", location.href) }, { mode: 0o644 });
    const exe = "/usr/bin/discord-phoenix";
    fs.addTar("/phoenix.tar");
    log("Loading the Phoenix ELF and Linux libraries…");
    await sys.boot();
    const restored = sys.state.console.match(/xcache [^\n]*restored \d+ modules/);
    if (restored) log(restored[0]);
    await fs.mkdir("/tmp", { recursive: true });
    await fs.mkdir("/home/phoenix", { recursive: true });
    const proc = sys.spawn([exe], {
        env: { ...windows.env, HOME: "/home/phoenix", PATH: "/usr/bin:/bin", SSL_CERT_FILE: caFile,
               VK_ICD_FILENAMES: "/usr/share/vulkan/icd.d/vk_swiftshader_icd.json",
               LD_LIBRARY_PATH: "/lib/x86_64-linux-gnu", LD_PRELOAD: (sunbirdEnabled ? "/lib/libphoenix.so:" : "") + "/lib/wayland-keymap.so", XKB_CONFIG_ROOT: "/usr/share/X11/xkb" },
        cwd: "/home/phoenix", pty: { cols: 100, rows: 32 }
    });
    const decoder = new TextDecoder();
    proc.pty.addEventListener("data", e => {
        const text = typeof e.data === "string" ? e.data : decoder.decode(e.data, { stream: true });
        log(text);
        if (!checkOnly && text.includes("milestone=main_init"))
            status.textContent = "Phoenix is running. Initializing the desktop…";
        if (!checkOnly && !guestOpenedScreen && /(?:mark|milestone)=first_screen/.test(text)) {
            guestOpenedScreen = true;
            status.textContent = "Phoenix opened its first screen. Waiting for the compositor…";
        }
        if (checkOnly && output.textContent.includes("milestone=main_init") && !status.dataset.passed) {
            status.dataset.passed = "true";
            status.textContent = "Passed. Phoenix reached main_init.";
            proc.kill("SIGKILL");
        }
    });
    log("Guest PID " + await proc.started);
    const { code, signal } = await proc.exited;
    clearInterval(paintCheck);
    if (!status.dataset.passed) status.textContent = "Phoenix exited with status " + code;
    log("Exited " + code + (signal ? " (" + signal + ")" : ""));
}
document.querySelector("#run").onclick = () => start().catch(error => {
    status.textContent = error.code === "EBUSY"
        ? "Storage is in use by another tab. Close that Phoenix tab, then reload."
        : "Could not start Phoenix. " + error.message;
    document.querySelector("#details").open = true;
    log(String(error.stack || error));
});
