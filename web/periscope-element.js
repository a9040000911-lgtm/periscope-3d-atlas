// Periscope Custom Element (<periscope-crop-stage>) + Hardened iframe postMessage RPC Bridge
// Encapsulates all styles inside Shadow DOM, auto-disposes VRAM on SPA unmount (Nuxt 3 <ClientOnly>),
// and supports strict origin-validated postMessage commands for sandboxed iframe pilots.

import { PeriscopeStageController, resolvePeriscopeUrl } from "./app.js";

let sharedCssTextPromise = null;

function loadScopedCssText(cssUrl) {
  if (!sharedCssTextPromise) {
    sharedCssTextPromise = fetch(cssUrl).then((r) => {
      if (!r.ok) throw new Error(`CSS load failed: ${r.status}`);
      return r.text();
    });
  }
  return sharedCssTextPromise;
}

export class PeriscopeCropStageElement extends HTMLElement {
  static get observedAttributes() {
    return ["crop", "theme", "asset-base", "render-mode", "hide-topbar"];
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.controller = null;
    this._mounting = false;
    this._pendingCatalogOverrides = null;
  }

  connectedCallback() {
    this.mountInternal();
  }

  disconnectedCallback() {
    if (this.controller) {
      this.controller.destroy();
      this.controller = null;
    }
  }

  attributeChangedCallback(name, oldVal, newVal) {
    if (oldVal === newVal || !this.controller) return;
    if (name === "crop" && newVal) {
      this.controller.switchCrop(newVal);
    } else if (name === "theme") {
      this.controller.setTheme(newVal || "dark");
    } else if (name === "hide-topbar") {
      if (this.controller.topbarEl) {
        this.controller.topbarEl.dataset.hideTopbar = newVal === "true" || newVal === "" ? "true" : "false";
      }
    }
  }

  setCatalogOverrides(map) {
    this._pendingCatalogOverrides = map;
    if (this.controller) {
      this.controller.setCatalogOverrides(map);
    }
  }

  selectPhase(index) {
    this.controller?.selectPhase(Number(index) || 0, true);
  }

  getDiagnostics() {
    return this.controller ? this.controller.getDiagnostics() : null;
  }

  async mountInternal() {
    if (this._mounting || this.controller) return;
    this._mounting = true;
    try {
      const assetBaseUrl = this.getAttribute("asset-base") || new URL("../", import.meta.url).href;
      const cssUrl = new URL("./style.css", import.meta.url).href;

      this.shadowRoot.textContent = "";
      try {
        const cssText = await loadScopedCssText(cssUrl);
        if (typeof CSSStyleSheet === "function" && "adoptedStyleSheets" in this.shadowRoot) {
          const sheet = new CSSStyleSheet();
          sheet.replaceSync(cssText);
          this.shadowRoot.adoptedStyleSheets = [sheet];
        } else {
          const styleEl = document.createElement("style");
          styleEl.textContent = cssText;
          this.shadowRoot.appendChild(styleEl);
        }
      } catch {
        const linkEl = document.createElement("link");
        linkEl.rel = "stylesheet";
        linkEl.href = resolvePeriscopeUrl("web/style.css", assetBaseUrl);
        this.shadowRoot.appendChild(linkEl);
      }

      if (!this.isConnected) return;

      const mountRoot = document.createElement("div");
      this.shadowRoot.appendChild(mountRoot);

      const hideTopbarAttr = this.getAttribute("hide-topbar");
      const renderMode = this.getAttribute("render-mode");

      this.controller = new PeriscopeStageController(mountRoot, {
        cropId: this.getAttribute("crop") || "sugar_beet",
        theme: this.getAttribute("theme") || "dark",
        assetBaseUrl,
        embedded: true,
        hideTopbar: hideTopbarAttr === "true" || hideTopbarAttr === "",
        forceFallback2D: renderMode === "2d",
        catalogOverrides: this._pendingCatalogOverrides || undefined,
        onEvent: (eventName, detail) => {
          this.dispatchEvent(new CustomEvent(`periscope:${eventName}`, { detail, bubbles: true, composed: true }));
        },
      });
      await this.controller.init();
    } finally {
      this._mounting = false;
    }
  }
}

if (typeof customElements !== "undefined" && !customElements.get("periscope-crop-stage")) {
  customElements.define("periscope-crop-stage", PeriscopeCropStageElement);
}

/**
 * Hardened postMessage RPC adapter for sandboxed iframe deployments.
 * Rejects messages from untrusted origins and validates strict JSON payload schemas.
 */
export function attachHardenedIframeBridge(controller, { allowedOrigins = [] } = {}) {
  if (typeof window === "undefined" || !controller) return () => {};
  const abortCtrl = new AbortController();

  const normalizedOrigins = new Set(
    allowedOrigins.length > 0 ? allowedOrigins : [window.location.origin]
  );

  const postToParent = (type, payload) => {
    if (window.parent && window.parent !== window) {
      for (const targetOrigin of normalizedOrigins) {
        try {
          window.parent.postMessage({ namespace: "periscope.v1", type, payload }, targetOrigin);
        } catch {
          // ignore mismatched origin target
        }
      }
    }
  };

  const prevOnEvent = controller.options.onEvent;
  controller.options.onEvent = (eventName, detail) => {
    if (prevOnEvent) prevOnEvent(eventName, detail);
    postToParent(eventName, detail);
  };

  window.addEventListener(
    "message",
    (ev) => {
      if (!normalizedOrigins.has(ev.origin)) return;
      const msg = ev.data;
      if (!msg || typeof msg !== "object" || msg.namespace !== "periscope.v1") return;

      if (msg.command === "selectPhase" && Number.isInteger(msg.phaseIndex)) {
        controller.selectPhase(Math.max(0, Math.min(20, msg.phaseIndex)), true);
      } else if (msg.command === "switchCrop" && typeof msg.cropId === "string" && /^[a-z0-9_]{2,32}$/.test(msg.cropId)) {
        controller.switchCrop(msg.cropId);
      } else if (msg.command === "setTheme" && (msg.theme === "light" || msg.theme === "dark")) {
        controller.setTheme(msg.theme);
      } else if (msg.command === "setCatalogOverrides" && msg.overrides && typeof msg.overrides === "object") {
        controller.setCatalogOverrides(msg.overrides);
      } else if (msg.command === "ping") {
        postToParent("pong", controller.getDiagnostics());
      }
    },
    { signal: abortCtrl.signal }
  );

  return () => abortCtrl.abort();
}
