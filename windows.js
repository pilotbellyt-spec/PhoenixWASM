// Adapted from GEX SingleCanvas, AGPL-3.0-only. See units/LICENSE.
// `SingleCanvas`: the guest's windows drawn straight into one element of the
// page, laid out there with no frames (page/src/bare-desktop.js): for a page
// that is one program -- a game, a Win32 program whose windows draw their own
// frames -- rather than a desktop.

import { t as INTERNAL, a as internals } from '/runtime/internal-BemElA8-.mjs';
import { t as xOnDemand } from '/runtime/x11-QnYTdhQp.mjs';
import { t as mirrored } from '/runtime/mirrored-akNWWQws.mjs';

export class SingleCanvas extends EventTarget {
  #d = null;
  #container;
  #expanded = false;
  #saved = new Map();

  /**
   * `container`: a positioned element; its size is the output's, what a
   * program asking for the screen's size sees. The windows' canvases go in
   * it, the first at its corner, popups over their parents, a window its
   * client places (Wine's) where it says.
   */
  constructor(sys, { container } = {}) {
    super();
    if (!container || container.nodeType !== 1) throw new TypeError('SingleCanvas: a container element');
    const i = internals(sys, 'SingleCanvas');
    this.#container = container;
    i.attach('windows', this, { beforeBoot: true });
    // What a preset asks (page/src/run-program.js): the X server's kind, and
    // `onDesktop(desktop, bare)` when the desktop is made.
    const x = {};
    i.devices(async (dev) => {
      const { bareDesktop } = await import('/runtime/bare-desktop-H6zxJ1Ue.mjs');
      const onDesktop = (d) => {
        this.#d = bareDesktop(d, container);
        x.onDesktop?.(d, this.#d);
        d.onwindowgone = () => this.dispatchEvent(new Event('change'));
        const onwindow = d.onwindow;
        d.onwindow = (w) => {
          onwindow(w);
          this.#fit();
          this.dispatchEvent(new Event('change'));
        };
      };
      if (dev.single) {
        mirrored(dev, container, { width: container.clientWidth, height: container.clientHeight, scale: 1 }, onDesktop);
        return;
      }
      Object.assign(dev, await dev.rt.openWayland({ wl: container, onDesktop, say: (t) => dev.say(`${t}\n`) }));
    });
    xOnDemand(i, x);
    this[INTERNAL] = {
      x,
      of: () => [],
      shutdown: () => this.#d?.stop(),
    };
  }

  /** What a program needs to reach this compositor and the X display. */
  get env() {
    return { XDG_RUNTIME_DIR: '/tmp', WAYLAND_DISPLAY: 'wayland-0', DISPLAY: ':0' };
  }

  /** The container's new size, as the output's: after the page resized it. */
  resized() {
    this.#d?.resizeOutput(this.#container.clientWidth, this.#container.clientHeight);
    if (this.#expanded) this.#fit();
  }

  expand(enabled) {
    this.#expanded = enabled;
    this.resized();
    this.#fit();
  }

  #fit() {
    const primary = this.#d?.windows().find(w => w.role === 1);
    if (!primary) return;
    if (this.#expanded) {
      if (!this.#saved.has(primary.key)) {
        this.#saved.set(primary.key, {
          width: primary.width, height: primary.height,
          x: parseInt(primary.canvas.style.left) || 0,
          y: parseInt(primary.canvas.style.top) || 0,
        });
      }
      primary.resize(this.#container.clientWidth, this.#container.clientHeight);
      primary.place(0, 0);
      primary.canvas.style.left = "0px";
      primary.canvas.style.top = "0px";
    } else {
      const saved = this.#saved.get(primary.key);
      if (!saved) return;
      primary.resize(saved.width, saved.height);
      primary.place(saved.x, saved.y);
      primary.canvas.style.left = saved.x + "px";
      primary.canvas.style.top = saved.y + "px";
      this.#saved.delete(primary.key);
    }
  }

  /** The windows' titles, surfaces and a hash of what is shown, as a test
   *  harness reads it (`change` events say when it changes). */
  describe() {
    return this.#d?.describe?.() ?? null;
  }
}
