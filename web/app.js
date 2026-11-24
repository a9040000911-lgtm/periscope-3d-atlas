// Periscope Production 3D/2D Botanical Engine (Waves 0–4 Hardened)
// - Zero external CDN / zero importmap dependency (152-FZ self-hosted vendor bundle)
// - Data-First boot + 4-level graceful fallback (WebGPU -> WebGL2 -> 2D WebP Atlas -> SSR/Print Poster)
// - Multi-instance PeriscopeStageController with 100% idempotent destroy() VRAM/DOM cleanup
// - Render-on-Demand + IntersectionObserver (0% GPU load when static or off-screen)
// - Mobile scroll-trap freedom (pan-y + desktop embedded wheel guard) & compact >=3 threat badges

const SVG_NS = "http://www.w3.org/2000/svg";
const FLANK_ARC_LEN = 245 * ((64 * Math.PI) / 180);
const FOV_DEG = 36;
const TAN_HALF_FOV = Math.tan((FOV_DEG * Math.PI) / 360);

const DEFAULT_CAMERA_PRESETS = {
  root_crop: {
    overview: { pos: [0.44, 0.14, 3.28], target: [0.0, -0.18, 0.0] },
    root: { pos: [0.24, -0.32, 1.95], target: [0.0, -0.36, 0.0] },
    canopy: { pos: [0.55, 1.05, 1.85], target: [0.0, 0.24, 0.0] },
  },
  legume_pulse: {
    overview: { pos: [0.42, 0.20, 3.05], target: [0.0, 0.04, 0.0] },
    root: { pos: [0.28, -0.26, 1.65], target: [0.0, -0.32, 0.0] },
    canopy: { pos: [0.50, 0.70, 1.78], target: [0.0, 0.42, 0.0] },
  },
};

const SEVERITY_LABELS = {
  critical: "Критично",
  high: "Высокий риск",
  medium: "Средний риск",
};

const THREAT_ICON_SHAPES = {
  beetle: [
    { tag: "ellipse", attrs: { cx: "12", cy: "13", rx: "5", ry: "6" } },
    { tag: "path", attrs: { d: "M12 7V19M8 10L4 8M16 10L20 8M7 14L3 15M17 14L21 15M10 6L8 3M14 6L16 3" } },
  ],
  worm: [
    { tag: "path", attrs: { d: "M4 16c2-5 5-5 7-1s5 3 9-4" } },
    { tag: "circle", attrs: { cx: "19.5", cy: "10.5", r: "1.2" } },
  ],
  aphid: [
    { tag: "ellipse", attrs: { cx: "12", cy: "13", rx: "4", ry: "5" } },
    { tag: "circle", attrs: { cx: "12", cy: "7", r: "2" } },
    { tag: "path", attrs: { d: "M9 10L5 7M15 10L19 7M8 14L4 15M16 14L20 15M10 18L7 21M14 18L17 21" } },
  ],
  moth: [
    { tag: "path", attrs: { d: "M12 6v12" } },
    { tag: "path", attrs: { d: "M12 9C8 5 3 6 4 11c1 3 4 3 8 1M12 9c4-4 9-3 8 2-1 3-4 3-8 1" } },
    { tag: "path", attrs: { d: "M12 13c-3 1-5 4-3 6 1.5 1 3-1 3-3M12 13c3 1 5 4 3 6-1.5 1-3-1-3-3" } },
  ],
  fungus: [
    { tag: "circle", attrs: { cx: "12", cy: "12", r: "7" } },
    { tag: "circle", attrs: { cx: "9.5", cy: "10.5", r: "1.3" } },
    { tag: "circle", attrs: { cx: "14.5", cy: "12.5", r: "1.5" } },
    { tag: "circle", attrs: { cx: "11.5", cy: "15.5", r: "1.1" } },
  ],
  weed: [
    { tag: "path", attrs: { d: "M12 20V8M12 14C9 12 7 9 8 6c3 1 4 4 4 8M12 15c3-2 6-4 6-8-3 0-5 3-6 8" } },
  ],
};

const SYMPTOM_MODE_MAP = {
  none: 0,
  rhizoctonia_rot: 1,
  cercospora_spots: 2,
  powdery_mildew: 3,
  phoma_rings: 4,
  pest_damage: 5,
};

const SYMPTOM_TARGET_MAP = {
  both: 0,
  root: 1,
  leaf: 2,
};

let cachedThreeRuntimePromise = null;

function loadThreeRuntime() {
  if (!cachedThreeRuntimePromise) {
    cachedThreeRuntimePromise = Promise.all([
      import("./vendor/three/build/three.webgpu.js"),
      import("./vendor/three/build/three.tsl.js"),
      import("./vendor/three/examples/jsm/controls/OrbitControls.js"),
      import("./vendor/three/examples/jsm/loaders/GLTFLoader.js"),
      import("./vendor/three/examples/jsm/loaders/HDRLoader.js"),
    ]).then(([THREE, TSL, orbitMod, gltfMod, hdrMod]) => ({
      THREE,
      TSL,
      OrbitControls: orbitMod.OrbitControls,
      GLTFLoader: gltfMod.GLTFLoader,
      HDRLoader: hdrMod.HDRLoader,
    }));
  }
  return cachedThreeRuntimePromise;
}

function buildThreatIconSvg(iconType) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  const shapes = THREAT_ICON_SHAPES[iconType] || THREAT_ICON_SHAPES.fungus;
  for (const spec of shapes) {
    const node = document.createElementNS(SVG_NS, spec.tag);
    for (const [k, v] of Object.entries(spec.attrs)) {
      node.setAttribute(k, v);
    }
    svg.appendChild(node);
  }
  return svg;
}

function defaultProjectRootUrl() {
  try {
    return new URL("../", import.meta.url).href;
  } catch {
    return "../";
  }
}

export function resolvePeriscopeUrl(relOrAbs, baseRootUrl) {
  if (!relOrAbs) return "";
  if (/^(https?:|data:|blob:)/i.test(relOrAbs)) return relOrAbs;
  const cleanRel = String(relOrAbs).replace(/^(\.\.\/|\.\/)+/, "");
  const root = baseRootUrl || defaultProjectRootUrl();
  const normalizedRoot = root.endsWith("/") ? root : `${root}/`;
  try {
    return new URL(cleanRel, normalizedRoot).href;
  } catch {
    return `${normalizedRoot}${cleanRel}`;
  }
}

export async function fetchWithRetry(url, { retries = 3, baseDelayMs = 450, timeoutMs = 12000, signal = null } = {}) {
  let lastErr = null;
  for (let attempt = 0; attempt < retries; attempt++) {
    if (signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    const timeoutCtrl = new AbortController();
    const timer = setTimeout(() => timeoutCtrl.abort(), timeoutMs);
    const onOuterAbort = () => timeoutCtrl.abort();
    if (signal) signal.addEventListener("abort", onOuterAbort, { once: true });
    try {
      const res = await fetch(url, { signal: timeoutCtrl.signal });
      if (!res.ok && res.status >= 500 && attempt + 1 < retries) {
        throw new Error(`HTTP ${res.status}`);
      }
      return res;
    } catch (err) {
      lastErr = err;
      if (signal?.aborted) throw err;
      if (attempt + 1 < retries) {
        await new Promise((r) => setTimeout(r, baseDelayMs * 2 ** attempt));
      }
    } finally {
      clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", onOuterAbort);
    }
  }
  throw lastErr || new Error(`Network error fetching ${url}`);
}

/**
 * Pure-JS exact PerspectiveCamera(fov=36, aspect=w/h) world-to-screen projection.
 * Allows 100% accurate 3D threat hotspot pins and dynamic ring sizing in Level-3 2D mode
 * without loading Three.js or touching WebGPU/WebGL!
 */
export function projectWorldPointPureJS(point3, camPos3, camTarget3, stageW, stageH) {
  let fx = camTarget3[0] - camPos3[0];
  let fy = camTarget3[1] - camPos3[1];
  let fz = camTarget3[2] - camPos3[2];
  const fLen = Math.hypot(fx, fy, fz) || 1;
  fx /= fLen;
  fy /= fLen;
  fz /= fLen;

  // R = normalize(F x Up(0,1,0)) = normalize((-fz, 0, fx))
  let rx = -fz;
  let ry = 0;
  let rz = fx;
  const rLen = Math.hypot(rx, ry, rz) || 1;
  rx /= rLen;
  rz /= rLen;

  // V = R x F
  const vx = ry * fz - rz * fy;
  const vy = rz * fx - rx * fz;
  const vz = rx * fy - ry * fx;

  const dx = point3[0] - camPos3[0];
  const dy = point3[1] - camPos3[1];
  const dz = point3[2] - camPos3[2];

  const depth = dx * fx + dy * fy + dz * fz;
  if (depth <= 0.05 || depth >= 40.0) {
    return { visible: false, x: 0, y: 0, ndcX: 0, ndcY: 0, rightVec: [rx, ry, rz] };
  }
  const viewX = dx * rx + dy * ry + dz * rz;
  const viewY = dx * vx + dy * vy + dz * vz;
  const denomY = depth * TAN_HALF_FOV;
  const ndcY = viewY / denomY;
  const aspect = Math.max(0.1, stageW / Math.max(1, stageH));
  const ndcX = viewX / (denomY * aspect);

  return {
    visible: true,
    ndcX,
    ndcY,
    x: (ndcX * 0.5 + 0.5) * stageW,
    y: (-ndcY * 0.5 + 0.5) * stageH,
    rightVec: [rx, ry, rz],
  };
}

export async function probeGpuCapabilities({ blockSoftwareGpu = false } = {}) {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return { supported: false, reason: "ssr_no_window", isSoftware: false, hasWebGPU: false, hasWebGL2: false };
  }
  let hasWebGPU = false;
  let hasWebGL2 = false;
  let isSoftware = false;
  let rendererName = "";

  try {
    const probeCanvas = document.createElement("canvas");
    const gl = probeCanvas.getContext("webgl2", { failIfMajorPerformanceCaveat: false });
    if (gl) {
      hasWebGL2 = true;
      const dbg = gl.getExtension("WEBGL_debug_renderer_info");
      if (dbg) {
        rendererName = String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) || "");
      } else {
        rendererName = String(gl.getParameter(gl.RENDERER) || "");
      }
      if (/SwiftShader|llvmpipe|Software|Basic Render Driver|Warp/i.test(rendererName)) {
        isSoftware = true;
      }
      const loseExt = gl.getExtension("WEBGL_lose_context");
      if (loseExt) loseExt.loseContext();
    }
  } catch {
    hasWebGL2 = false;
  }

  if (typeof navigator !== "undefined" && navigator.gpu && typeof navigator.gpu.requestAdapter === "function") {
    try {
      const adapter = await Promise.race([
        navigator.gpu.requestAdapter(),
        new Promise((resolve) => setTimeout(() => resolve(null), 1500)),
      ]);
      if (adapter) {
        hasWebGPU = true;
        if (adapter.isFallbackAdapter) {
          isSoftware = true;
        }
      }
    } catch {
      hasWebGPU = false;
    }
  }

  if (!hasWebGPU && !hasWebGL2) {
    return { supported: false, reason: "no_webgpu_or_webgl2", isSoftware, hasWebGPU, hasWebGL2, rendererName };
  }
  if (isSoftware && blockSoftwareGpu) {
    return { supported: false, reason: "software_gpu_blocked", isSoftware, hasWebGPU, hasWebGL2, rendererName };
  }
  return { supported: true, reason: "ok", isSoftware, hasWebGPU, hasWebGL2, rendererName };
}

export function createPeriscopeTemplateDOM() {
  const wrapper = document.createElement("div");
  wrapper.className = "periscope-app";
  wrapper.tabIndex = 0;
  wrapper.innerHTML = `
    <div class="field-backdrop" data-role="field-backdrop" aria-hidden="true">
      <div class="sky-layer" data-role="sky-layer"></div>
      <div class="subsoil-layer" data-role="subsoil-layer"></div>
      <div class="horizon-seam" data-role="horizon-band"></div>
    </div>
    <header class="topbar" data-role="topbar">
      <div class="brand-group">
        <div class="brand-mark" aria-hidden="true">П</div>
        <div>
          <h2 class="brand-title">ПЕРИСКОП</h2>
          <p class="brand-subtitle">Интерактивный 3D-гид фаз развития и защиты культур</p>
        </div>
      </div>
      <div class="crop-badge">
        <span class="crop-dot" aria-hidden="true"></span>
        <select class="crop-select" data-role="crop-select" aria-label="Выбор сельскохозяйственной культуры" hidden></select>
        <span class="crop-name" data-role="crop-name">Сахарная свекла</span>
        <span class="crop-latin" data-role="crop-latin">Beta vulgaris subsp. vulgaris</span>
      </div>
      <div class="telemetry-pill" data-role="telemetry-pill" aria-live="polite">
        <span class="debug-only" data-role="stat-size" hidden>Загрузка…</span>
        <span class="sep debug-only" hidden>·</span>
        <span class="debug-only" data-role="stat-tris" hidden>—</span>
        <span class="sep debug-only" hidden>·</span>
        <span class="debug-only" data-role="stat-fps" hidden>— FPS</span>
        <span class="sep debug-only" hidden>·</span>
        <span class="bbch-live" data-role="stat-bbch">BBCH 00–05</span>
      </div>
    </header>
    <main class="workspace">
      <section class="stage-column" aria-label="Интерактивная модель культуры">
        <div class="stage-card" data-role="stage-container">
          <svg class="periscope-reticle" data-role="periscope-reticle" viewBox="0 0 800 800" aria-hidden="true">
            <circle cx="400" cy="400" r="145" />
            <circle cx="400" cy="400" r="245" />
            <path class="reticle-flank-track" d="M 192.2 529.8 A 245 245 0 0 1 192.2 270.2" />
            <path class="reticle-flank-track" d="M 607.8 270.2 A 245 245 0 0 1 607.8 529.8" />
            <path class="reticle-progress-arc" data-role="reticle-progress-left" d="M 192.2 529.8 A 245 245 0 0 1 192.2 270.2" />
            <path class="reticle-progress-arc" data-role="reticle-progress-right" d="M 607.8 270.2 A 245 245 0 0 1 607.8 529.8" />
            <circle cx="400" cy="400" r="345" stroke-dasharray="4 6" />
            <circle class="orb-dot dim" cx="298" cy="70" r="3.5" />
            <circle class="orb-dot dim" cx="725" cy="390" r="3.5" />
            <circle class="orb-dot dim" cx="120" cy="430" r="3.5" />
          </svg>
          <img class="stage-fallback-img" data-role="stage-fallback-img" alt="Фаза развития культуры" decoding="async" />
          <canvas class="viewport-canvas" data-role="viewport-canvas"></canvas>
          <div class="stage-controls-top">
            <div class="preset-bar" role="group" aria-label="Ракурсы камеры">
              <button type="button" class="pill-btn is-active" data-preset="overview">Общий вид</button>
              <button type="button" class="pill-btn" data-preset="root">Корнеплод</button>
              <button type="button" class="pill-btn" data-preset="canopy">Листья</button>
            </div>
            <div class="toggle-group">
              <button type="button" class="pill-btn toggle-btn is-active" data-role="toggle-symptoms" aria-pressed="true">Симптомы 3D: Вкл</button>
              <button type="button" class="pill-btn toggle-btn is-active" data-role="toggle-hotspots" aria-pressed="true">Радар угроз: Вкл</button>
              <button type="button" class="pill-btn toggle-btn" data-role="toggle-ssao" aria-pressed="false">Объёмные тени: Выкл</button>
            </div>
          </div>
          <svg class="hotspot-leaders" data-role="hotspot-leaders" aria-hidden="true"></svg>
          <div class="reticle-phase-ring" data-role="reticle-phase-ring" role="tablist" aria-label="Фазы развития по кругу"></div>
          <div class="hotspots-layer" data-role="hotspots-layer" aria-label="Метки угроз на растении"></div>
          <div class="stage-bottom-hud" aria-label="Статус и авто-рост">
            <button type="button" class="autoplay-circle-btn" data-role="btn-autoplay" aria-label="Запустить авто-рост" title="Авто-рост по фазам">▶</button>
            <div class="stage-mini-readout">
              <span class="phase-tag-inline" data-role="readout-bbch">BBCH 00–05</span>
              <span data-role="readout-phase">Фаза 1 из 6</span>
              <span class="sep mini-frame-sep debug-only" hidden>·</span>
              <span class="debug-only readout-frame" data-role="readout-frame" hidden>Кадр 0 / 150</span>
              <span class="sep mini-hint-sep">·</span>
              <span class="mini-hint" data-role="mini-hint">360° мышью · колёсико — масштаб</span>
            </div>
          </div>
          <div class="loading-bar" data-role="loading-overlay" aria-hidden="true">
            <div class="loading-bar-fill" data-role="loading-bar-fill"></div>
          </div>
          <div class="error-banner" data-role="error-banner" hidden role="alert"></div>
        </div>
      </section>
      <aside class="info-column" data-role="info-panel" aria-label="Фазы развития и угрозы">
        <div class="bbch-rail" data-role="phase-buttons" role="tablist" aria-label="Шкала фаз развития BBCH"></div>
        <div class="phase-details-pane">
          <div class="phase-header-card">
            <div class="phase-meta-row">
              <span class="bbch-badge" data-role="phase-bbch">BBCH 00–05</span>
              <span class="maturity-pill" data-role="maturity-label">Набухание и старт корешка</span>
            </div>
            <h3 class="phase-title" data-role="phase-title">Семя и прорастание</h3>
            <p class="phase-summary" data-role="phase-summary"></p>
            <div class="metrics-grid" aria-label="Динамика созревания">
              <div class="metric-box">
                <span class="metric-label" data-role="metric-label-0">Сахаристость</span>
                <span class="metric-val" data-role="metric-brix">0.0%</span>
              </div>
              <div class="metric-box">
                <span class="metric-label" data-role="metric-label-1">Диаметр корня</span>
                <span class="metric-val" data-role="metric-diam">4 мм</span>
              </div>
              <div class="metric-box">
                <span class="metric-label" data-role="metric-label-2">Листьев</span>
                <span class="metric-val" data-role="metric-leaves">0 шт</span>
              </div>
            </div>
          </div>
          <div class="threats-section">
            <div class="threats-header">
              <h3>Вредители и болезни в фазе</h3>
              <span class="threat-count" data-role="threat-count">0</span>
            </div>
            <div class="threats-list" data-role="threats-list"></div>
          </div>
        </div>
      </aside>
    </main>
  `;
  return wrapper;
}

export class PeriscopeStageController {
  constructor(containerEl, options = {}) {
    if (!containerEl) {
      throw new Error("PeriscopeStageController requires a host container element.");
    }
    const urlParams =
      typeof window !== "undefined" ? new URLSearchParams(window.location.search) : new URLSearchParams();

    const allowSwParam = urlParams.get("allowSoftwareGpu") === "1";
    const simSlowParam = Boolean(options.simulateSlowGpu || urlParams.get("simulateSlowGpu") === "1");

    this.options = {
      cropId: options.cropId || urlParams.get("crop") || "sugar_beet",
      assetBaseUrl: options.assetBaseUrl || defaultProjectRootUrl(),
      embedded: Boolean(options.embedded || urlParams.get("embedded") === "1"),
      theme: options.theme || urlParams.get("theme") || "dark",
      hideTopbar: Boolean(options.hideTopbar),
      debug: Boolean(options.debug || urlParams.get("debug") === "1"),
      forceFallback2D: Boolean(options.forceFallback2D || urlParams.get("renderMode") === "2d"),
      blockSoftwareGpu:
        options.blockSoftwareGpu !== undefined
          ? Boolean(options.blockSoftwareGpu)
          : urlParams.get("strictGpu") === "1" ||
            (typeof navigator !== "undefined" && !navigator.webdriver && !allowSwParam),
      simulateSlowGpu: simSlowParam,
      minFpsThreshold: Number(options.minFpsThreshold ?? (allowSwParam && !simSlowParam ? 3 : 16)),
      catalogOverrides: options.catalogOverrides || (typeof window !== "undefined" ? window.PERISCOPE_CMS_CATALOG : null) || {},
      onEvent: typeof options.onEvent === "function" ? options.onEvent : null,
    };

    this.hostEl = containerEl;
    if (containerEl.classList?.contains("periscope-app")) {
      this.appEl = containerEl;
    } else {
      const existing = containerEl.querySelector?.(".periscope-app");
      if (existing) {
        this.appEl = existing;
      } else {
        this.appEl = createPeriscopeTemplateDOM();
        containerEl.appendChild(this.appEl);
        this.createdAppEl = true;
      }
    }

    if (!this.appEl.hasAttribute("tabindex")) {
      this.appEl.tabIndex = 0;
    }
    this.appEl.classList.toggle("is-embedded", this.options.embedded);
    this.setTheme(this.options.theme);

    this.abortCtrl = new AbortController();
    this.destroyed = false;
    this.renderTier = "booting"; // "webgpu" | "webgl2" | "fallback-2d"
    this.isIntersecting = true;
    this.isLoopRunning = false;
    this.rafId = null;
    this.framesRendered = 0;
    this.contextLossCount = 0;
    this.lastResizeW = 0;
    this.lastResizeH = 0;
    this.lastSoilPctX = -1;
    this.lastSoilPctY = -1;

    // Bind scoped DOM handles (works identically with data-role or legacy IDs)
    const q = (role, idFallback) =>
      this.appEl.querySelector(`[data-role="${role}"]`) || (idFallback ? this.appEl.querySelector(`#${idFallback}`) : null);

    this.topbarEl = q("topbar", null) || this.appEl.querySelector(".topbar");
    if (this.topbarEl && this.options.hideTopbar) {
      this.topbarEl.dataset.hideTopbar = "true";
    }

    this.stageContainer = q("stage-container", "stage-container");
    this.canvas = q("viewport-canvas", "viewport-canvas");
    this.fallbackImg = q("stage-fallback-img", "stage-fallback-img");
    if (!this.fallbackImg && this.stageContainer) {
      const img = document.createElement("img");
      img.className = "stage-fallback-img";
      img.dataset.role = "stage-fallback-img";
      img.alt = "Фаза развития культуры";
      img.decoding = "async";
      this.stageContainer.insertBefore(img, this.canvas || this.stageContainer.firstChild);
      this.fallbackImg = img;
    }

    this.stageControlsTop = this.stageContainer?.querySelector(".stage-controls-top") || null;
    this.reticleEl = q("periscope-reticle", "periscope-reticle");
    this.reticleProgressLeft = q("reticle-progress-left", "reticle-progress-left");
    this.reticleProgressRight = q("reticle-progress-right", "reticle-progress-right");
    this.reticlePhaseRing = q("reticle-phase-ring", "reticle-phase-ring");
    this.hotspotLeadersSvg = q("hotspot-leaders", "hotspot-leaders");
    this.hotspotsLayer = q("hotspots-layer", "hotspots-layer");
    this.loadingOverlay = q("loading-overlay", "loading-overlay");
    this.loadingBarFill = q("loading-bar-fill", "loading-bar-fill");
    this.errorBanner = q("error-banner", "error-banner");

    this.statSize = q("stat-size", "stat-size");
    this.statTris = q("stat-tris", "stat-tris");
    this.statFps = q("stat-fps", "stat-fps");
    this.statBbch = q("stat-bbch", "stat-bbch");

    this.phaseButtonsEl = q("phase-buttons", "phase-buttons");
    this.btnAutoplay = q("btn-autoplay", "btn-autoplay");
    this.toggleSymptomsBtn = q("toggle-symptoms", "toggle-symptoms");
    this.toggleHotspotsBtn = q("toggle-hotspots", "toggle-hotspots");
    this.toggleSsaoBtn = q("toggle-ssao", "toggle-ssao");
    this.presetButtons = Array.from(this.appEl.querySelectorAll("[data-preset]"));

    this.readoutBbch = q("readout-bbch", "readout-bbch");
    this.readoutPhase = q("readout-phase", "readout-phase");
    this.readoutFrame = q("readout-frame", "readout-frame");
    this.miniHintEl = q("mini-hint", null) || this.appEl.querySelector(".mini-hint");

    this.phaseBbchEl = q("phase-bbch", "phase-bbch");
    this.maturityLabelEl = q("maturity-label", "maturity-label");
    this.phaseTitleEl = q("phase-title", "phase-title");
    this.phaseSummaryEl = q("phase-summary", "phase-summary");
    this.metricLabelEls = [
      q("metric-label-0", "metric-label-0"),
      q("metric-label-1", "metric-label-1"),
      q("metric-label-2", "metric-label-2"),
    ];
    this.metricValEls = [
      q("metric-brix", "metric-brix"),
      q("metric-diam", "metric-diam"),
      q("metric-leaves", "metric-leaves"),
    ];
    this.cropSelectEl = q("crop-select", "crop-select");
    this.cropNameEl = q("crop-name", "crop-name");
    this.cropLatinEl = q("crop-latin", "crop-latin");
    this.threatCountEl = q("threat-count", "threat-count");
    this.threatsListEl = q("threats-list", "threats-list");

    // Set scoped CSS background URLs resolved via assetBaseUrl
    const skyUrl = resolvePeriscopeUrl("assets/textures/bg_field_sky.webp", this.options.assetBaseUrl);
    const subUrl = resolvePeriscopeUrl("assets/textures/bg_chernozem_subsoil.webp", this.options.assetBaseUrl);
    this.appEl.style.setProperty("--bg-sky-url", `url("${skyUrl}")`);
    this.appEl.style.setProperty("--bg-subsoil-url", `url("${subUrl}")`);

    this.cameraPresets = structuredClone(DEFAULT_CAMERA_PRESETS.root_crop);
    this.state = {
      crop: null,
      activePhaseIndex: 0,
      activeThreatId: null,
      showHotspots: true,
      showSymptoms: true,
      ultraAO: false,
      symptomTargetIntensity: 0.0,
      symptomCurrentIntensity: 0.0,
      autoPlaying: false,
      currentTime: 0,
      targetTime: 0,
      durationSec: 6.25,
      cameraLerpActive: false,
      camPos: [...this.cameraPresets.overview.pos],
      camTarget: [...this.cameraPresets.overview.target],
      camGoalPos: [...this.cameraPresets.overview.pos],
      camGoalTarget: [...this.cameraPresets.overview.target],
      controlsInteracting: false,
      dampingFramesRemaining: 0,
    };

    this.stageGeo = {
      w: 800,
      h: 600,
      cx: 400,
      cy: 300,
      rPhase: 110,
      targetRPhase: 110,
      minRPhase: 84,
      maxRPhase: 196,
      plantScreenHalfW: 36,
      dotR: 15,
      pillMaxW: 182,
      topSafe: 58,
      botSafe: 546,
      isMobile: false,
      dotPositions: [],
    };

    // 3D handles (populated only when Level 1/2 3D initializes)
    this.THREE = null;
    this.TSL = null;
    this.renderer = null;
    this.renderPipeline = null;
    this.scene = null;
    this.camera = null;
    this.controls = null;
    this.mixer = null;
    this.actions = [];
    this.plantRoot = null;
    this.plantExtentProfile = [];
    this.hotspotItems = [];
    this.reticleDotEls = [];
    this.disposableTextures = new Set();
    this.disposableMaterials = new Set();
    this.disposableGeometries = new Set();
    this.matHandles = {
      outer: null,
      mid: null,
      heart: null,
      root: null,
      pod: null,
      flower: null,
      nodule: null,
      stem: null,
    };
    this.tslUniforms = null;
    this.fillLightRef = null;
    this.hemiLightRef = null;
    this.targetMarkerGroup = null;
    this.targetHaloMesh = null;
    this.resizeObserver = null;
    this.intersectionObserver = null;
  }

  emit(eventName, detail) {
    if (this.destroyed) return;
    if (this.options.onEvent) {
      try {
        this.options.onEvent(eventName, detail);
      } catch {
        // ignore host callback error
      }
    }
    try {
      this.hostEl.dispatchEvent(new CustomEvent(`periscope:${eventName}`, { detail, bubbles: true, composed: true }));
    } catch {
      // ignore
    }
  }

  setTheme(theme) {
    const normalized = theme === "light" ? "light" : "dark";
    this.options.theme = normalized;
    this.appEl.dataset.theme = normalized;
  }

  setCatalogOverrides(overridesMap) {
    this.options.catalogOverrides = overridesMap && typeof overridesMap === "object" ? overridesMap : {};
    if (this.state.crop) {
      const phase = this.state.crop.phases?.[this.state.activePhaseIndex];
      if (phase) this.renderThreats(phase.threats);
    }
  }

  getDiagnostics() {
    return {
      destroyed: this.destroyed,
      renderTier: this.renderTier,
      cropId: this.state.crop?.crop_id || null,
      activePhaseIndex: this.state.activePhaseIndex,
      isLoopRunning: this.isLoopRunning,
      isIntersecting: this.isIntersecting,
      framesRendered: this.framesRendered,
      contextLossCount: this.contextLossCount,
      gpuMemory: this.renderer?.info?.memory
        ? {
            geometries: this.renderer.info.memory.geometries,
            textures: this.renderer.info.memory.textures,
          }
        : { geometries: 0, textures: 0 },
    };
  }

  async init() {
    if (this.destroyed) return this;
    this.bindUIAndObservers();
    this.computeStageGeometry(true);

    // STEP 1 (Wave 0 Data-First): Always load JSON passport & render UI + 2D Poster FIRST!
    try {
      await this.loadCropPassport(this.options.cropId);
    } catch (dataErr) {
      this.showBannerError(
        this.options.debug
          ? `Ошибка загрузки данных культуры: ${dataErr?.message || dataErr}`
          : "Не удалось загрузить справочник фаз культуры. Проверьте соединение с сетью."
      );
      return this;
    }

    if (this.destroyed) return this;

    // STEP 2 (Wave 0 GPU Capability & Software-Renderer Gate)
    if (this.options.forceFallback2D) {
      this.activateFallback2D("forced_2d_mode");
      this.emit("ready", this.getDiagnostics());
      return this;
    }

    const gpuProbe = await probeGpuCapabilities({ blockSoftwareGpu: this.options.blockSoftwareGpu });
    if (!gpuProbe.supported) {
      this.activateFallback2D(gpuProbe.reason);
      this.emit("ready", this.getDiagnostics());
      return this;
    }

    // STEP 3: Upgrade seamlessly from 2D Poster to 3D WebGPU / WebGL2
    try {
      await this.init3DStage(gpuProbe);
      if (this.destroyed) return this;
      await this.load3DModelForCurrentCrop();
      if (this.destroyed) return this;
      this.emit("ready", this.getDiagnostics());
    } catch (err3d) {
      if (this.options.debug) {
        console.warn("3D initialization degraded cleanly to Level-3 2D WebP Atlas:", err3d);
      }
      this.dispose3DOnly();
      this.activateFallback2D("init_or_model_error");
      this.emit("ready", this.getDiagnostics());
    }
    return this;
  }

  activateFallback2D(reason = "fallback") {
    this.renderTier = "fallback-2d";
    this.appEl.classList.add("is-mode-2d");
    if (this.canvas) {
      this.canvas.classList.remove("is-ready");
      this.canvas.classList.add("is-fallback-2d");
    }
    if (this.fallbackImg) {
      this.fallbackImg.classList.remove("is-hidden-by-3d");
    }
    if (this.loadingOverlay) {
      this.loadingOverlay.classList.add("is-done");
      this.loadingOverlay.hidden = true;
    }
    if (this.miniHintEl) {
      this.miniHintEl.textContent = "Выберите фазу BBCH или метку угрозы";
    }
    if (this.options.debug && this.statSize) {
      this.statSize.textContent = `2D-атлас (${reason})`;
    }
    this.updateFallbackPosterForPhase(this.state.activePhaseIndex);
    this.updateBackdropSoilHorizon();
    this.updateDynamicRingRadius(0, true);
    this.updateHotspotPositions();
  }

  updateFallbackPosterForPhase(phaseIdx) {
    if (!this.fallbackImg || !this.state.crop) return;
    const phases = this.state.crop.phases || [];
    const clamped = Math.max(0, Math.min(phases.length - 1, phaseIdx));
    const phase = phases[clamped];
    const relPoster =
      phase?.poster_url ||
      this.state.crop.fallback_atlas?.frames?.[clamped] ||
      `assets/fallback/${this.state.crop.crop_id}_phase_${clamped}.webp`;
    const resolved = resolvePeriscopeUrl(relPoster, this.options.assetBaseUrl);
    if (resolved && this.fallbackImg.dataset.currentSrc !== resolved) {
      this.fallbackImg.dataset.currentSrc = resolved;
      this.fallbackImg.src = resolved;
    }
    this.fallbackImg.alt = `${this.state.crop.name} — ${phase?.bbch || ""} ${phase?.title || ""}`.trim();
  }

  showBannerError(text) {
    if (this.loadingOverlay) this.loadingOverlay.hidden = true;
    if (!this.errorBanner) return;
    this.errorBanner.hidden = false;
    this.errorBanner.textContent = "";
    const strong = document.createElement("strong");
    strong.textContent = text;
    this.errorBanner.appendChild(strong);
  }

  async resolveCropUrls(requestedId) {
    const safeId = /^[a-z0-9_]+$/i.test(requestedId) ? requestedId : "sugar_beet";
    let cropId = safeId;
    let passportUrl = resolvePeriscopeUrl(`data/${cropId}.json`, this.options.assetBaseUrl);
    let statsUrl = resolvePeriscopeUrl(
      cropId === "sugar_beet" ? "assets/export_stats.json" : `assets/${cropId}_stats.json`,
      this.options.assetBaseUrl
    );

    try {
      const idxUrl = resolvePeriscopeUrl("data/crops_index.json", this.options.assetBaseUrl);
      const idxRes = await fetchWithRetry(idxUrl, { retries: 2, timeoutMs: 8000, signal: this.abortCtrl.signal });
      if (idxRes.ok) {
        const idxData = await idxRes.json();
        const readyCrops = Array.isArray(idxData.crops) ? idxData.crops.filter((c) => c.ready) : [];
        const chosen =
          readyCrops.find((c) => c.id === cropId) ||
          readyCrops.find((c) => c.id === idxData.default_crop) ||
          readyCrops[0];
        if (chosen) {
          cropId = chosen.id;
          if (chosen.passport_url) {
            passportUrl = resolvePeriscopeUrl(chosen.passport_url, this.options.assetBaseUrl);
          }
          if (chosen.stats_url) {
            statsUrl = resolvePeriscopeUrl(chosen.stats_url, this.options.assetBaseUrl);
          }
        }
        if (this.cropSelectEl && readyCrops.length > 1) {
          this.cropSelectEl.textContent = "";
          for (const c of readyCrops) {
            const opt = document.createElement("option");
            opt.value = c.id;
            opt.textContent = c.name;
            opt.selected = c.id === cropId;
            this.cropSelectEl.appendChild(opt);
          }
          this.cropSelectEl.hidden = false;
          if (this.cropNameEl) this.cropNameEl.hidden = true;
        }
      }
    } catch {
      // Direct fallback to data/<crop>.json
    }
    return { cropId, passportUrl, statsUrl };
  }

  async loadCropPassport(requestedCropId) {
    const { cropId, passportUrl, statsUrl } = await this.resolveCropUrls(requestedCropId);
    this.options.cropId = cropId;
    this.currentStatsUrl = statsUrl;

    const cropRes = await fetchWithRetry(passportUrl, { retries: 3, timeoutMs: 10000, signal: this.abortCtrl.signal });
    if (!cropRes.ok) {
      throw new Error(`HTTP ${cropRes.status}`);
    }
    const crop = await cropRes.json();
    if (this.destroyed) return;

    this.state.crop = crop;
    this.state.durationSec = Number(crop.duration_sec || 6.25);
    this.plantExtentProfile = Array.isArray(crop.extent_profile) ? crop.extent_profile : [];

    const archPresets =
      crop.archetype === "legume_pulse" ? DEFAULT_CAMERA_PRESETS.legume_pulse : DEFAULT_CAMERA_PRESETS.root_crop;
    this.cameraPresets = structuredClone(archPresets);
    this.state.camPos = [...this.cameraPresets.overview.pos];
    this.state.camTarget = [...this.cameraPresets.overview.target];
    this.state.camGoalPos = [...this.cameraPresets.overview.pos];
    this.state.camGoalTarget = [...this.cameraPresets.overview.target];

    if (crop.camera_preset_labels && typeof crop.camera_preset_labels === "object") {
      for (const btn of this.presetButtons) {
        const label = crop.camera_preset_labels[btn.dataset.preset];
        if (label) btn.textContent = label;
      }
    }

    if (this.cropNameEl) this.cropNameEl.textContent = crop.name || "";
    if (this.cropLatinEl) this.cropLatinEl.textContent = crop.latin || "";
    // Wave 2 D-12: NEVER overwrite host page document.title when embedded!
    if (!this.options.embedded && typeof document !== "undefined") {
      document.title = `Перископ — 3D-атлас фаз роста: ${crop.name}`;
    }

    if (Array.isArray(crop.metric_defs)) {
      crop.metric_defs.slice(0, 3).forEach((def, idx) => {
        if (this.metricLabelEls[idx] && def.label) {
          this.metricLabelEls[idx].textContent = def.label;
        }
      });
    }

    this.renderPhaseButtons();
    this.selectPhase(0, true, true);
    this.updateLiveMetrics(0);
    this.updateBackdropSoilHorizon();
    this.updateDynamicRingRadius(0, true);
    this.updateHotspotPositions();
  }

  async switchCrop(newCropId) {
    if (this.destroyed || !newCropId || newCropId === this.state.crop?.crop_id) return;
    this.stopAutoplay();
    if (this.loadingBarFill) this.loadingBarFill.style.width = "15%";
    if (this.loadingOverlay) {
      this.loadingOverlay.hidden = false;
      this.loadingOverlay.classList.remove("is-done");
    }
    if (this.fallbackImg) this.fallbackImg.classList.remove("is-hidden-by-3d");
    if (this.canvas) this.canvas.classList.remove("is-ready");

    await this.loadCropPassport(newCropId);
    if (this.destroyed) return;

    if (this.renderer && this.scene && this.renderTier !== "fallback-2d") {
      this.clearCurrentPlantMeshes();
      try {
        await this.load3DModelForCurrentCrop();
      } catch {
        this.dispose3DOnly();
        this.activateFallback2D("crop_switch_fallback");
      }
    } else {
      this.activateFallback2D("2d_crop_switch");
    }

    if (!this.options.embedded && typeof window !== "undefined" && window.history?.replaceState) {
      const next = new URL(window.location.href);
      next.searchParams.set("crop", this.options.cropId);
      window.history.replaceState({}, "", next.toString());
    }
  }

  bindUIAndObservers() {
    const sig = this.abortCtrl.signal;

    if (this.options.debug) {
      for (const el of this.appEl.querySelectorAll(".debug-only")) {
        el.hidden = false;
      }
    }

    if (this.cropSelectEl) {
      this.cropSelectEl.addEventListener(
        "change",
        () => {
          this.switchCrop(this.cropSelectEl.value);
        },
        { signal: sig }
      );
    }

    if (this.btnAutoplay) {
      this.btnAutoplay.addEventListener("click", () => this.toggleAutoplay(), { signal: sig });
    }

    // Wave 2 D-13: Scoped keydown on this.appEl ONLY (never hijacks Swiper / host page arrow keys!)
    this.appEl.addEventListener(
      "keydown",
      (ev) => {
        if (!this.state.crop || (ev.target && /^(INPUT|SELECT|TEXTAREA)$/.test(ev.target.tagName))) {
          return;
        }
        if (ev.key === "ArrowLeft") {
          ev.preventDefault();
          this.stopAutoplay();
          this.selectPhase(this.state.activePhaseIndex - 1, true);
        } else if (ev.key === "ArrowRight") {
          ev.preventDefault();
          this.stopAutoplay();
          this.selectPhase(this.state.activePhaseIndex + 1, true);
        }
      },
      { signal: sig }
    );

    if (this.toggleSymptomsBtn) {
      this.toggleSymptomsBtn.addEventListener(
        "click",
        () => {
          this.state.showSymptoms = !this.state.showSymptoms;
          this.toggleSymptomsBtn.classList.toggle("is-active", this.state.showSymptoms);
          this.toggleSymptomsBtn.setAttribute("aria-pressed", this.state.showSymptoms ? "true" : "false");
          this.toggleSymptomsBtn.textContent = `Симптомы 3D: ${this.state.showSymptoms ? "Вкл" : "Выкл"}`;
          this.applyThreatSymptom(this.getActiveThreatData());
          this.requestRender();
        },
        { signal: sig }
      );
    }

    if (this.toggleSsaoBtn) {
      this.toggleSsaoBtn.addEventListener(
        "click",
        async () => {
          if (!this.state.ultraAO) {
            this.toggleSsaoBtn.textContent = "Объёмные тени: …";
            const ok = await this.ensureUltraAOPipeline();
            this.state.ultraAO = ok;
          } else {
            this.state.ultraAO = false;
          }
          this.syncUltraAOState();
          this.requestRender();
        },
        { signal: sig }
      );
    }

    if (this.toggleHotspotsBtn) {
      this.toggleHotspotsBtn.addEventListener(
        "click",
        () => {
          this.state.showHotspots = !this.state.showHotspots;
          this.toggleHotspotsBtn.classList.toggle("is-active", this.state.showHotspots);
          this.toggleHotspotsBtn.setAttribute("aria-pressed", this.state.showHotspots ? "true" : "false");
          this.toggleHotspotsBtn.textContent = `Радар угроз: ${this.state.showHotspots ? "Вкл" : "Выкл"}`;
          this.updateHotspotPositions();
          this.updateTarget3DMarker();
          this.requestRender();
        },
        { signal: sig }
      );
    }

    for (const btn of this.presetButtons) {
      btn.addEventListener("click", () => this.applyCameraPreset(btn.dataset.preset), { signal: sig });
    }

    if (typeof window !== "undefined") {
      window.addEventListener("resize", () => this.handleResize(false), { signal: sig, passive: true });
      document.addEventListener(
        "visibilitychange",
        () => {
          if (document.hidden) {
            this.stopRenderLoop();
          } else {
            this.requestRender();
          }
        },
        { signal: sig }
      );
    }

    if (typeof ResizeObserver === "function" && this.stageContainer) {
      this.resizeObserver = new ResizeObserver(() => this.handleResize(false));
      this.resizeObserver.observe(this.stageContainer);
      if (this.stageControlsTop) this.resizeObserver.observe(this.stageControlsTop);
    }

    // Wave 1 D-09: IntersectionObserver pauses GPU 100% when widget scrolls out of viewport
    if (typeof IntersectionObserver === "function") {
      this.intersectionObserver = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            this.isIntersecting = entry.isIntersecting && entry.intersectionRatio > 0.02;
            if (this.isIntersecting) {
              this.requestRender();
            } else {
              this.stopRenderLoop();
            }
          }
        },
        { threshold: [0, 0.03, 0.2] }
      );
      this.intersectionObserver.observe(this.appEl);
    }
  }

  handleResize(force = false) {
    if (this.destroyed || !this.stageContainer) return;
    const w = Math.max(200, this.stageContainer.clientWidth || 800);
    const h = Math.max(220, this.stageContainer.clientHeight || 520);

    // Wave 3 D-18: Ignore small vertical mobile address-bar jitter (<80px) in Telegram/WhatsApp/Safari WebView
    const isNarrowMobile = w < 768;
    const widthSame = Math.abs(w - this.lastResizeW) < 2;
    const smallHeightJitter = Math.abs(h - this.lastResizeH) > 0 && Math.abs(h - this.lastResizeH) < 80;
    if (!force && this.lastResizeW > 0 && isNarrowMobile && widthSame && smallHeightJitter) {
      return;
    }

    this.lastResizeW = w;
    this.lastResizeH = h;
    this.computeStageGeometry(false);

    if (this.renderer && this.camera) {
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(w, h, false);
      this.requestRender();
    } else {
      this.updateBackdropSoilHorizon();
      this.updateHotspotPositions();
    }
  }

  computeStageGeometry() {
    if (!this.stageContainer) return;
    const w = Math.max(220, this.stageContainer.clientWidth || 800);
    const h = Math.max(240, this.stageContainer.clientHeight || 520);
    const controlsH = this.stageControlsTop
      ? this.stageControlsTop.offsetTop + this.stageControlsTop.offsetHeight
      : w < 620
        ? 84
        : 46;
    const topSafe = Math.max(54, controlsH + 10);
    const isMobile = w < 560;
    const botSafe = h - (isMobile ? 50 : 52);
    const availH = Math.max(150, botSafe - topSafe);
    const cx = w * 0.5;
    const cy = topSafe + availH * 0.5;

    let dotR;
    let pillMaxW;
    let minRPhase;
    let maxRPhase;
    if (isMobile) {
      dotR = 13;
      pillMaxW = Math.max(112, Math.floor((w - 24) / 2));
      minRPhase = 56;
      const maxRFromH = Math.max(62, (availH - 84) * 0.5 - dotR - 4);
      maxRPhase = Math.max(62, Math.min(w * 0.5 - dotR - 10, maxRFromH, 142));
    } else {
      dotR = w >= 700 ? 15 : 14;
      pillMaxW = Math.min(186, Math.max(132, Math.floor(w * 0.245)));
      minRPhase = Math.max(76, Math.min(104, w * 0.14));
      maxRPhase = Math.max(minRPhase + 18, Math.min(w * 0.5 - dotR - 22, availH * 0.5 - dotR - 14, 215));
    }

    Object.assign(this.stageGeo, {
      w,
      h,
      cx,
      cy,
      minRPhase,
      maxRPhase,
      dotR,
      pillMaxW,
      topSafe,
      botSafe,
      isMobile,
      rPhase: Math.max(minRPhase, Math.min(maxRPhase, this.stageGeo.rPhase)),
    });

    const reticleSize = this.stageGeo.rPhase / (245 / 800);
    this.stageContainer.style.setProperty("--reticle-cx", `${cx.toFixed(1)}px`);
    this.stageContainer.style.setProperty("--reticle-cy", `${cy.toFixed(1)}px`);
    this.stageContainer.style.setProperty("--reticle-size", `${reticleSize.toFixed(1)}px`);
    this.stageContainer.style.setProperty("--dot-size", `${(dotR * 2).toFixed(0)}px`);
    this.stageContainer.style.setProperty("--pill-max-w", `${pillMaxW}px`);

    if (this.hotspotLeadersSvg) {
      this.hotspotLeadersSvg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    }
    this.updateDynamicRingRadius(0, true);
    this.layoutReticlePhaseDots();
  }

  getActiveCameraArrays() {
    if (this.camera && this.controls) {
      return {
        pos: [this.camera.position.x, this.camera.position.y, this.camera.position.z],
        target: [this.controls.target.x, this.controls.target.y, this.controls.target.z],
      };
    }
    return {
      pos: this.state.camPos,
      target: this.state.camTarget,
    };
  }

  getInterpolatedPlantExtent(timeSec) {
    const prof = this.plantExtentProfile;
    if (!prof || prof.length === 0) {
      return { halfW: 0.14, midY: 0 };
    }
    if (timeSec <= prof[0].t) return prof[0];
    const last = prof[prof.length - 1];
    if (timeSec >= last.t) return last;

    for (let i = 0; i < prof.length - 1; i++) {
      const a = prof[i];
      const b = prof[i + 1];
      if (timeSec >= a.t && timeSec <= b.t) {
        const span = Math.max(1e-5, b.t - a.t);
        const alpha = (timeSec - a.t) / span;
        return {
          halfW: a.halfW + (b.halfW - a.halfW) * alpha,
          midY: a.midY + (b.midY - a.midY) * alpha,
        };
      }
    }
    return last;
  }

  updateDynamicRingRadius(dt, snap = false) {
    const { w, h, minRPhase, maxRPhase, dotR } = this.stageGeo;
    const { pos, target } = this.getActiveCameraArrays();
    const { halfW, midY } = this.getInterpolatedPlantExtent(this.state.currentTime);

    const centerProj = projectWorldPointPureJS([0, midY, 0], pos, target, w, h);
    let screenHalf = this.stageGeo.plantScreenHalfW;
    if (centerProj.visible) {
      const [rx, ry, rz] = centerProj.rightVec;
      const sideProj = projectWorldPointPureJS([rx * halfW, midY + ry * halfW, rz * halfW], pos, target, w, h);
      if (sideProj.visible) {
        screenHalf = Math.max(18, Math.abs(sideProj.x - centerProj.x));
      }
    }
    this.stageGeo.plantScreenHalfW = screenHalf;

    const cosFlank = Math.cos((32 * Math.PI) / 180);
    const rNeeded = (screenHalf + dotR + 16) / cosFlank;
    const targetR = Math.max(minRPhase, Math.min(maxRPhase, rNeeded));
    this.stageGeo.targetRPhase = targetR;

    const prevR = this.stageGeo.rPhase;
    const nextR = snap
      ? targetR
      : prevR + (targetR - prevR) * Math.min(1, Math.max(0.01, dt || 0.016) * 8.0);
    this.stageGeo.rPhase = Math.max(minRPhase, Math.min(maxRPhase, nextR));

    if (snap || Math.abs(this.stageGeo.rPhase - prevR) > 0.2) {
      if (this.stageContainer) {
        const reticleSize = this.stageGeo.rPhase / (245 / 800);
        this.stageContainer.style.setProperty("--reticle-size", `${reticleSize.toFixed(1)}px`);
      }
      this.layoutReticlePhaseDots();
    }
  }

  renderPhaseButtons() {
    if (!this.phaseButtonsEl || !this.state.crop) return;
    this.phaseButtonsEl.textContent = "";
    const phases = this.state.crop.phases || [];

    phases.forEach((phase, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "phase-row-btn";
      btn.setAttribute("role", "tab");
      btn.dataset.index = String(idx);

      const dot = document.createElement("span");
      dot.className = "phase-dot";
      dot.setAttribute("aria-hidden", "true");

      const wrap = document.createElement("span");
      wrap.className = "phase-row-text";

      const bbchSpan = document.createElement("span");
      bbchSpan.className = "phase-row-bbch";
      bbchSpan.textContent = phase.bbch || "";

      const lblSpan = document.createElement("span");
      lblSpan.className = "phase-row-label";
      lblSpan.textContent = phase.short_label || phase.title || "";

      wrap.appendChild(bbchSpan);
      wrap.appendChild(lblSpan);
      btn.appendChild(dot);
      btn.appendChild(wrap);

      btn.addEventListener("click", (ev) => {
        if (ev.detail > 0) btn.blur();
        this.stopAutoplay();
        this.selectPhase(idx, true);
      });
      this.phaseButtonsEl.appendChild(btn);
    });

    this.renderReticlePhaseRing();
  }

  renderReticlePhaseRing() {
    if (!this.reticlePhaseRing || !this.state.crop) return;
    this.reticlePhaseRing.textContent = "";
    const phases = this.state.crop.phases || [];

    this.reticleDotEls = phases.map((phase, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "reticle-phase-dot";
      btn.setAttribute("role", "tab");
      btn.dataset.index = String(idx);
      btn.setAttribute("aria-label", `Фаза ${idx + 1}: ${phase.bbch} — ${phase.title}`);

      const numSpan = document.createElement("span");
      numSpan.textContent = String(idx + 1);

      const tipSpan = document.createElement("span");
      tipSpan.className = "reticle-phase-tooltip";
      tipSpan.textContent = `${phase.bbch} · ${phase.short_label}`;

      btn.appendChild(numSpan);
      btn.appendChild(tipSpan);

      btn.addEventListener("click", (ev) => {
        if (ev.detail > 0) btn.blur();
        this.stopAutoplay();
        this.selectPhase(idx, true);
      });
      this.reticlePhaseRing.appendChild(btn);
      return btn;
    });

    this.layoutReticlePhaseDots();
    this.updateReticlePhaseRing(this.state.activePhaseIndex);
  }

  layoutReticlePhaseDots() {
    const n = this.reticleDotEls.length;
    this.stageGeo.dotPositions = [];
    if (!n) return;
    const leftCount = Math.ceil(n / 2);
    const rightCount = n - leftCount;
    const { w, cx, cy, rPhase, dotR } = this.stageGeo;

    for (let idx = 0; idx < n; idx++) {
      const btn = this.reticleDotEls[idx];
      const isLeft = idx < leftCount;
      let deg;
      if (isLeft) {
        deg = leftCount === 1 ? 180 : 148 + (idx / (leftCount - 1)) * 64;
      } else {
        const j = idx - leftCount;
        deg = rightCount === 1 ? 0 : 328 + (j / (rightCount - 1)) * 64;
      }
      const ang = (deg * Math.PI) / 180;
      const px = cx + Math.cos(ang) * rPhase;
      const py = cy + Math.sin(ang) * rPhase;
      btn.style.left = `${px.toFixed(1)}px`;
      btn.style.top = `${py.toFixed(1)}px`;
      const side = isLeft ? "left" : "right";
      btn.dataset.quadrant = side;
      // Wave 3 D-17: If outward margin is < 150px, lift tooltip upward so it neither hits edge nor overlaps stem
      const outwardRoom = isLeft ? px - dotR : w - (px + dotR);
      btn.classList.toggle("is-edge-tight", outwardRoom < 148);
      this.stageGeo.dotPositions[idx] = { x: px, y: py, side };
    }
  }

  updateReticleArcProgress(progress01) {
    if (!this.state.crop) return;
    const n = Math.max(2, (this.state.crop.phases || []).length);
    const leftCount = Math.ceil(n / 2);
    const clamped = Math.max(0, Math.min(1, progress01));

    const leftEnd = (leftCount - 1) / Math.max(1, n - 1);
    const rightStart = leftCount / Math.max(1, n - 1);
    const leftFrac = leftEnd > 0 ? Math.max(0, Math.min(1, clamped / leftEnd)) : 1;
    const rightFrac = 1 - rightStart > 0 ? Math.max(0, Math.min(1, (clamped - rightStart) / (1 - rightStart))) : 0;

    if (this.reticleProgressLeft) {
      const len = leftFrac * FLANK_ARC_LEN;
      this.reticleProgressLeft.style.strokeDasharray = `${len.toFixed(1)} ${(FLANK_ARC_LEN + 8).toFixed(1)}`;
    }
    if (this.reticleProgressRight) {
      const len = rightFrac * FLANK_ARC_LEN;
      this.reticleProgressRight.style.strokeDasharray = `${len.toFixed(1)} ${(FLANK_ARC_LEN + 8).toFixed(1)}`;
    }
  }

  updateReticlePhaseRing(activeIdx) {
    for (let idx = 0; idx < this.reticleDotEls.length; idx++) {
      const btn = this.reticleDotEls[idx];
      const isSel = idx === activeIdx;
      btn.classList.toggle("is-active", isSel);
      btn.classList.toggle("is-passed", idx < activeIdx);
      btn.setAttribute("aria-selected", isSel ? "true" : "false");
    }
    const phases = this.state.crop?.phases || [];
    if (phases.length > 1) {
      this.updateReticleArcProgress(activeIdx / (phases.length - 1));
    }
  }

  selectPhase(index, updateTargetTime = true, forceRenderCards = false) {
    const phases = this.state.crop?.phases || [];
    if (!phases.length) return;
    const clamped = Math.max(0, Math.min(phases.length - 1, index));
    const changed = forceRenderCards || clamped !== this.state.activePhaseIndex || !this.threatsListEl?.childElementCount;
    this.state.activePhaseIndex = clamped;
    const phase = phases[clamped];

    if (updateTargetTime) {
      this.state.targetTime = Number(phase.time_sec || 0);
      if (this.renderTier === "fallback-2d" || !this.mixer) {
        this.state.currentTime = this.state.targetTime;
        this.updateLiveMetrics(this.state.currentTime);
      }
    }

    this.updateFallbackPosterForPhase(clamped);

    if (this.phaseButtonsEl) {
      for (const btn of this.phaseButtonsEl.querySelectorAll(".phase-row-btn")) {
        const isSel = Number(btn.dataset.index) === clamped;
        btn.classList.toggle("is-active", isSel);
        btn.setAttribute("aria-selected", isSel ? "true" : "false");
      }
    }
    this.updateReticlePhaseRing(clamped);

    if (this.readoutBbch) this.readoutBbch.textContent = phase.bbch;
    if (this.readoutPhase) this.readoutPhase.textContent = `Фаза ${clamped + 1} из ${phases.length}`;
    if (this.statBbch) this.statBbch.textContent = phase.bbch;

    if (changed) {
      this.state.activeThreatId = phase.threats?.[0]?.id || null;
      if (this.phaseBbchEl) this.phaseBbchEl.textContent = phase.bbch || "";
      if (this.maturityLabelEl) this.maturityLabelEl.textContent = phase.metrics?.maturity_label || "";
      if (this.phaseTitleEl) this.phaseTitleEl.textContent = phase.title || "";
      if (this.phaseSummaryEl) this.phaseSummaryEl.textContent = phase.summary || "";
      this.renderThreats(phase.threats || []);
      this.renderHotspots(phase.threats || []);
      this.updateTarget3DMarker();
      this.applyThreatSymptom(phase.threats?.[0] || null);
      this.updateDynamicRingRadius(0, this.renderTier === "fallback-2d");
      this.updateHotspotPositions();
      this.emit("phasechange", {
        cropId: this.state.crop.crop_id,
        phaseIndex: clamped,
        bbch: phase.bbch,
        title: phase.title,
      });
    }
    this.requestRender();
  }

  updateLiveMetrics(timeSec) {
    const phases = this.state.crop?.phases;
    if (!phases || phases.length < 2) return;
    let i0 = 0;
    for (let i = 0; i < phases.length - 1; i++) {
      if (timeSec >= phases[i].time_sec) i0 = i;
    }
    const i1 = Math.min(phases.length - 1, i0 + 1);
    const p0 = phases[i0];
    const p1 = phases[i1];
    const span = Math.max(1e-4, p1.time_sec - p0.time_sec);
    const alpha = i0 === i1 ? 0 : Math.max(0, Math.min(1, (timeSec - p0.time_sec) / span));

    const m0 = p0.metrics || { brix_pct: 0, root_diam_mm: 4, leaves_count: 0 };
    const m1 = p1.metrics || m0;
    const defs =
      Array.isArray(this.state.crop.metric_defs) && this.state.crop.metric_defs.length >= 3
        ? this.state.crop.metric_defs
        : [
            { key: "brix_pct", label: "Сахаристость", unit: "%", decimals: 1 },
            { key: "root_diam_mm", label: "Диаметр корня", unit: " мм", decimals: 0 },
            { key: "leaves_count", label: "Листьев", unit: " шт", decimals: 0 },
          ];

    for (let k = 0; k < 3; k++) {
      const def = defs[k];
      const v0 = Number(m0[def.key] ?? 0);
      const v1 = Number(m1[def.key] ?? v0);
      const val = v0 + (v1 - v0) * alpha;
      const dec = Number(def.decimals ?? 0);
      const formatted = dec > 0 ? val.toFixed(dec) : String(Math.round(val));
      if (this.metricValEls[k]) this.metricValEls[k].textContent = `${formatted}${def.unit || ""}`;
    }
  }

  // Wave 0 D-05 + Wave 2 D-14: Safe DOM node creation (zero dynamic innerHTML XSS) + live CMS catalog overrides
  renderThreats(threats) {
    if (!this.threatsListEl) return;
    if (this.threatCountEl) this.threatCountEl.textContent = String(threats.length);
    this.threatsListEl.textContent = "";

    threats.forEach((threat) => {
      const cmsOverride = this.options.catalogOverrides?.[threat.id] || null;
      const card = document.createElement("article");
      card.className = "threat-card";
      card.tabIndex = 0;
      card.dataset.threatId = threat.id;
      card.dataset.severity = threat.severity;
      if (threat.id === this.state.activeThreatId) {
        card.classList.add("is-active");
      }

      const topRow = document.createElement("div");
      topRow.className = "threat-top";

      const titleWrap = document.createElement("div");
      titleWrap.className = "threat-title-wrap";

      const iconWrap = document.createElement("span");
      iconWrap.className = "threat-card-icon";
      iconWrap.setAttribute("aria-hidden", "true");
      iconWrap.appendChild(buildThreatIconSvg(threat.icon_type));

      const h4 = document.createElement("h4");
      h4.className = "threat-name";
      h4.textContent = cmsOverride?.name || threat.name || "";

      titleWrap.appendChild(iconWrap);
      titleWrap.appendChild(h4);

      const sevBadge = document.createElement("span");
      sevBadge.className = `severity-badge ${threat.severity}`;
      sevBadge.textContent = SEVERITY_LABELS[threat.severity] || threat.severity || "";

      topRow.appendChild(titleWrap);
      topRow.appendChild(sevBadge);

      const latinEl = document.createElement("div");
      latinEl.className = "threat-latin";
      latinEl.textContent = threat.latin || "";

      const zoneEl = document.createElement("div");
      zoneEl.className = "threat-zone";
      zoneEl.textContent = `Зона: ${threat.target_zone || ""}`;

      const descEl = document.createElement("p");
      descEl.className = "threat-desc";
      descEl.textContent = cmsOverride?.description || threat.description || "";

      const tipEl = document.createElement("p");
      tipEl.className = "threat-tip";
      const strong = document.createElement("strong");
      strong.textContent = "Защита: ";
      tipEl.appendChild(strong);
      tipEl.appendChild(document.createTextNode(cmsOverride?.protection_tip || threat.protection_tip || ""));

      card.appendChild(topRow);
      card.appendChild(latinEl);
      card.appendChild(zoneEl);
      card.appendChild(descEl);
      card.appendChild(tipEl);

      if (cmsOverride?.product_url && /^https?:\/\/|^\//i.test(cmsOverride.product_url)) {
        const link = document.createElement("a");
        link.className = "threat-product-link";
        link.href = cmsOverride.product_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = cmsOverride.product_label || "Перейти к препарату в каталоге →";
        link.addEventListener("click", (ev) => ev.stopPropagation());
        card.appendChild(link);
      }

      const activate = () => this.setActiveThreat(threat.id, false, true);
      card.addEventListener("click", activate);
      card.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          activate();
        }
      });
      this.threatsListEl.appendChild(card);
    });
  }

  renderHotspots(threats) {
    if (!this.hotspotsLayer) return;
    this.hotspotsLayer.textContent = "";
    if (this.hotspotLeadersSvg) this.hotspotLeadersSvg.textContent = "";

    this.hotspotItems = threats.map((threat, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "hotspot-pin";
      btn.dataset.threatId = threat.id;
      btn.dataset.severity = threat.severity;
      btn.setAttribute("aria-label", `${threat.name} (${SEVERITY_LABELS[threat.severity] || threat.severity})`);
      if (threat.id === this.state.activeThreatId) {
        btn.classList.add("is-active");
      }

      const iconSpan = document.createElement("span");
      iconSpan.className = "hotspot-icon";
      iconSpan.setAttribute("aria-hidden", "true");
      iconSpan.appendChild(buildThreatIconSvg(threat.icon_type));

      const badgeNum = document.createElement("span");
      badgeNum.className = "hotspot-badge-num";
      badgeNum.textContent = String(idx + 1);

      const labelSpan = document.createElement("span");
      labelSpan.className = "hotspot-label";
      labelSpan.textContent = threat.name || "";

      btn.appendChild(iconSpan);
      btn.appendChild(badgeNum);
      btn.appendChild(labelSpan);
      btn.addEventListener("click", () => this.setActiveThreat(threat.id, true, true));
      this.hotspotsLayer.appendChild(btn);

      let lineEl = null;
      let anchorDotEl = null;
      if (this.hotspotLeadersSvg) {
        lineEl = document.createElementNS(SVG_NS, "polyline");
        lineEl.setAttribute("class", "hotspot-leader-line");
        anchorDotEl = document.createElementNS(SVG_NS, "circle");
        anchorDotEl.setAttribute("class", "hotspot-anchor-dot");
        anchorDotEl.dataset.severity = threat.severity;
        anchorDotEl.setAttribute("r", "3.5");
        this.hotspotLeadersSvg.appendChild(lineEl);
        this.hotspotLeadersSvg.appendChild(anchorDotEl);
      }

      return {
        id: threat.id,
        index: idx,
        severity: threat.severity,
        anchorArr: Array.isArray(threat.anchor) ? [...threat.anchor] : [0, 0, 0],
        symptom: threat.symptom || null,
        el: btn,
        lineEl,
        anchorDotEl,
      };
    });
  }

  getActiveThreatData() {
    const phase = this.state.crop?.phases?.[this.state.activePhaseIndex];
    if (!phase || !Array.isArray(phase.threats)) return null;
    return phase.threats.find((t) => t.id === this.state.activeThreatId) || null;
  }

  setActiveThreat(threatId, scrollToCard, focusCamera = false) {
    this.state.activeThreatId = threatId;
    if (this.threatsListEl) {
      for (const card of this.threatsListEl.querySelectorAll(".threat-card")) {
        const match = card.dataset.threatId === threatId;
        card.classList.toggle("is-active", match);
        if (match && scrollToCard) {
          card.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
    }
    for (const item of this.hotspotItems) {
      item.el.classList.toggle("is-active", item.id === threatId);
    }
    this.updateTarget3DMarker();

    const threat = this.getActiveThreatData();
    this.applyThreatSymptom(threat);
    this.emit("threatselect", {
      cropId: this.state.crop?.crop_id,
      phaseIndex: this.state.activePhaseIndex,
      threatId,
      threatName: threat?.name || "",
    });

    if (
      focusCamera &&
      this.renderTier !== "fallback-2d" &&
      threat &&
      Array.isArray(threat.anchor) &&
      threat.symptom?.cam_offset
    ) {
      const [ax, ay, az] = threat.anchor;
      const [ox, oy, oz] = threat.symptom.cam_offset;
      this.state.camGoalTarget = [ax, ay, az];
      this.state.camGoalPos = [ax + ox, ay + oy, az + oz];
      this.state.cameraLerpActive = true;
      for (const btn of this.presetButtons) {
        btn.classList.remove("is-active");
      }
    }
    this.updateHotspotPositions();
    this.requestRender();
  }

  applyCameraPreset(presetName) {
    const preset = this.cameraPresets[presetName];
    if (!preset) return;
    this.state.camGoalPos = [...preset.pos];
    this.state.camGoalTarget = [...preset.target];
    this.state.cameraLerpActive = true;
    for (const btn of this.presetButtons) {
      btn.classList.toggle("is-active", btn.dataset.preset === presetName);
    }
    this.requestRender();
  }

  applyThreatSymptom(threat) {
    const sym = threat?.symptom;
    const modeNum = sym ? (SYMPTOM_MODE_MAP[sym.mode] ?? 0) : 0;
    if (!this.state.showSymptoms || !threat || modeNum === 0) {
      this.state.symptomTargetIntensity = 0.0;
      return;
    }
    if (this.tslUniforms) {
      const anchor = Array.isArray(threat.anchor) ? threat.anchor : [0, 0, 0];
      this.tslUniforms.uSymptomCenter.value.set(anchor[0], anchor[1], anchor[2]);
      this.tslUniforms.uSymptomRadius.value = typeof sym.radius === "number" ? sym.radius : 0.2;
      this.tslUniforms.uSymptomMode.value = modeNum;
      this.tslUniforms.uSymptomTarget.value = SYMPTOM_TARGET_MAP[sym.target] ?? 0;
    }
    this.state.symptomTargetIntensity = 1.0;
  }

  updateTarget3DMarker() {
    if (!this.targetMarkerGroup) return;
    const active = this.hotspotItems.find((item) => item.id === this.state.activeThreatId);
    if (!active || !this.state.showHotspots) {
      this.targetMarkerGroup.visible = false;
      return;
    }
    this.targetMarkerGroup.visible = true;
    this.targetMarkerGroup.position.set(active.anchorArr[0], active.anchorArr[1], active.anchorArr[2]);
  }

  updateBackdropSoilHorizon() {
    if (!this.stageContainer) return;
    const { w, h } = this.stageGeo;
    const { pos, target } = this.getActiveCameraArrays();
    const originProj = projectWorldPointPureJS([0, 0, 0], pos, target, w, h);
    if (!originProj.visible) return;

    const appRect = this.appEl.getBoundingClientRect();
    const stageRect = this.stageContainer.getBoundingClientRect();
    const relX = stageRect.left - appRect.left + originProj.x;
    const relY = stageRect.top - appRect.top + originProj.y;
    const pctX = Math.max(12, Math.min(88, (relX / Math.max(1, appRect.width || w)) * 100));
    const pctY = Math.max(24, Math.min(78, (relY / Math.max(1, appRect.height || h)) * 100));

    // Wave 2 D-12: Write CSS variables ONLY onto scoped this.appEl (never document.documentElement!)
    // and only when delta > 0.15% to avoid redundant style invalidations
    if (Math.abs(pctX - this.lastSoilPctX) > 0.15 || Math.abs(pctY - this.lastSoilPctY) > 0.15) {
      this.lastSoilPctX = pctX;
      this.lastSoilPctY = pctY;
      this.appEl.style.setProperty("--plant-center-x", `${pctX.toFixed(1)}%`);
      this.appEl.style.setProperty("--soil-line-y", `${pctY.toFixed(1)}%`);
    }
  }

  hideHotspotItem(item) {
    item.el.style.display = "none";
    if (item.lineEl) item.lineEl.style.display = "none";
    if (item.anchorDotEl) item.anchorDotEl.style.display = "none";
  }

  updateHotspotPositions() {
    if (!this.hotspotsLayer) return;
    if (!this.state.showHotspots) {
      this.hotspotsLayer.hidden = true;
      if (this.hotspotLeadersSvg) this.hotspotLeadersSvg.hidden = true;
      return;
    }
    this.hotspotsLayer.hidden = false;
    if (this.hotspotLeadersSvg) this.hotspotLeadersSvg.hidden = false;

    const { w, h, cx, cy, rPhase, dotR, pillMaxW, topSafe, botSafe, isMobile } = this.stageGeo;
    const { pos, target } = this.getActiveCameraArrays();
    const visible = [];

    for (const item of this.hotspotItems) {
      const proj = projectWorldPointPureJS(item.anchorArr, pos, target, w, h);
      if (!proj.visible || proj.x < -20 || proj.x > w + 20 || proj.y < -20 || proj.y > h + 20) {
        this.hideHotspotItem(item);
        continue;
      }
      item.el.style.display = "inline-flex";
      visible.push({
        item,
        ax: proj.x,
        ay: proj.y,
        pw: pillMaxW,
        ph: 30,
        x1: 0,
        y1: 0,
        x2: 0,
        y2: 0,
        side: "right",
      });
    }

    if (visible.length === 0) return;

    if (isMobile) {
      const byY = [...visible].sort((a, b) => a.ay - b.ay);
      let topShelf;
      let botShelf;
      if (byY.length === 1) {
        topShelf = byY[0].ay <= cy ? [byY[0]] : [];
        botShelf = byY[0].ay <= cy ? [] : [byY[0]];
      } else {
        const topCount = Math.ceil(byY.length / 2);
        topShelf = byY.slice(0, topCount);
        botShelf = byY.slice(topCount);
      }

      // Wave 3 D-16: Guaranteed non-overflow shelf layout for ANY number of threats (1..10+)
      const placeShelf = (shelf, isTop) => {
        if (!shelf.length) return;
        shelf.sort((a, b) => a.ax - b.ax);

        // First measure full-label widths; if >=3 items or total width > w - 16, engage compact badge mode!
        for (const entry of shelf) {
          entry.item.el.classList.remove("is-compact-badge");
        }
        let useCompact = shelf.length >= 3;
        if (!useCompact) {
          let totalW = (shelf.length - 1) * 6;
          for (const entry of shelf) {
            const measuredW = Math.min(pillMaxW, Math.max(84, entry.item.el.offsetWidth || pillMaxW));
            totalW += measuredW;
          }
          if (totalW > w - 16) useCompact = true;
        }

        for (const entry of shelf) {
          entry.item.el.classList.toggle("is-compact-badge", useCompact);
          const rawW = entry.item.el.offsetWidth || (useCompact ? 46 : pillMaxW);
          const maxEach = Math.max(38, Math.floor((w - 16 - (shelf.length - 1) * 6) / shelf.length));
          entry.pw = Math.min(maxEach, useCompact ? Math.max(40, rawW) : Math.min(pillMaxW, Math.max(82, rawW)));
          entry.ph = Math.max(26, entry.item.el.offsetHeight || 28);
        }

        const gap = 6;
        const totalRowW = shelf.reduce((acc, e) => acc + e.pw, 0) + gap * (shelf.length - 1);
        let cursorX =
          shelf.length === 1
            ? Math.max(8, Math.min(w - shelf[0].pw - 8, shelf[0].ax - shelf[0].pw * 0.5))
            : shelf.length === 2 && !useCompact
              ? 8
              : Math.max(8, (w - totalRowW) * 0.5);

        shelf.forEach((entry, idx) => {
          const y1 = isTop ? topSafe + 4 : botSafe - entry.ph - 4;
          let x1;
          if (shelf.length === 2 && !useCompact && idx === 1) {
            x1 = Math.max(cursorX, w - entry.pw - 8);
          } else {
            x1 = Math.max(8, Math.min(w - entry.pw - 8, cursorX));
          }
          cursorX = x1 + entry.pw + gap;
          entry.side = isTop ? "top" : "bottom";
          entry.x1 = x1;
          entry.y1 = y1;
          entry.x2 = x1 + entry.pw;
          entry.y2 = y1 + entry.ph;
        });
      };

      placeShelf(topShelf, true);
      placeShelf(botShelf, false);
    } else {
      for (const entry of visible) {
        entry.item.el.classList.remove("is-compact-badge");
        entry.pw = Math.min(pillMaxW, Math.max(88, entry.item.el.offsetWidth || pillMaxW));
        entry.ph = Math.max(28, entry.item.el.offsetHeight || 34);
      }

      const byX = [...visible].sort((a, b) => a.ax - b.ax);
      let leftGroup = [];
      let rightGroup = [];
      for (const entry of byX) {
        if (entry.ax < cx - 8) leftGroup.push(entry);
        else if (entry.ax > cx + 8) rightGroup.push(entry);
        else if (leftGroup.length <= rightGroup.length) leftGroup.push(entry);
        else rightGroup.push(entry);
      }
      if (byX.length >= 2 && (leftGroup.length === 0 || rightGroup.length === 0)) {
        const mid = Math.floor(byX.length / 2);
        leftGroup = byX.slice(0, mid);
        rightGroup = byX.slice(mid);
      }

      const minGap = 10;
      const plantClear = Math.max(this.stageGeo.plantScreenHalfW + 16, rPhase * 0.56);

      for (const [side, grp] of [
        ["left", leftGroup],
        ["right", rightGroup],
      ]) {
        if (!grp.length) continue;
        grp.sort((a, b) => a.ay - b.ay);
        const sideDots = this.stageGeo.dotPositions.filter((d) => d.side === side);
        const minDotY = sideDots.length ? Math.min(...sideDots.map((d) => d.y)) : cy;
        const maxDotY = sideDots.length ? Math.max(...sideDots.map((d) => d.y)) : cy;
        const ys = grp.map((e) => Math.max(topSafe + e.ph * 0.5, Math.min(botSafe - e.ph * 0.5, e.ay)));

        const computeNeededXClear = (py, ph) => {
          let xClear = plantClear;
          for (const dot of sideDots) {
            if (Math.abs(py - dot.y) < ph * 0.5 + dotR + 10) {
              xClear = Math.max(xClear, Math.abs(dot.x - cx) + dotR + 12);
            }
          }
          return xClear;
        };

        const nudgeAboveOrBelowDots = (entry, py) => {
          const xClear = computeNeededXClear(py, entry.ph);
          const availLane = side === "left" ? cx - xClear - 10 : w - 10 - (cx + xClear);
          if (availLane >= entry.pw || sideDots.length === 0) return py;

          const aboveY = Math.max(topSafe + entry.ph * 0.5, minDotY - dotR - entry.ph * 0.5 - 10);
          const belowY = Math.min(botSafe - entry.ph * 0.5, maxDotY + dotR + entry.ph * 0.5 + 10);
          const aboveFree = aboveY <= minDotY - dotR - entry.ph * 0.5 - 8;
          const belowFree = belowY >= maxDotY + dotR + entry.ph * 0.5 + 8;
          if (aboveFree && belowFree) {
            return Math.abs(aboveY - entry.ay) <= Math.abs(belowY - entry.ay) ? aboveY : belowY;
          }
          if (aboveFree) return aboveY;
          if (belowFree) return belowY;
          return py;
        };

        const relaxSideY = () => {
          for (let passIdx = 0; passIdx < 4; passIdx++) {
            for (let j = 1; j < grp.length; j++) {
              const minY = ys[j - 1] + grp[j - 1].ph * 0.5 + grp[j].ph * 0.5 + minGap;
              if (ys[j] < minY) ys[j] = minY;
            }
            for (let j = grp.length - 1; j >= 0; j--) {
              const maxY = botSafe - grp[j].ph * 0.5;
              if (ys[j] > maxY) ys[j] = maxY;
              if (j > 0) {
                const maxPrev = ys[j] - grp[j].ph * 0.5 - grp[j - 1].ph * 0.5 - minGap;
                if (ys[j - 1] > maxPrev) ys[j - 1] = maxPrev;
              }
            }
            for (let j = 0; j < grp.length; j++) {
              ys[j] = Math.max(topSafe + grp[j].ph * 0.5, Math.min(botSafe - grp[j].ph * 0.5, ys[j]));
            }
          }
        };

        relaxSideY();
        let nudged = false;
        for (let j = 0; j < grp.length; j++) {
          const ny = nudgeAboveOrBelowDots(grp[j], ys[j]);
          if (Math.abs(ny - ys[j]) > 1) {
            ys[j] = ny;
            nudged = true;
          }
        }
        if (nudged) relaxSideY();

        grp.forEach((entry, j) => {
          const py = ys[j];
          const xClear = computeNeededXClear(py, entry.ph);
          let x1;
          let x2;
          if (side === "left") {
            x2 = cx - xClear;
            x1 = Math.max(10, x2 - entry.pw);
            x2 = x1 + entry.pw;
          } else {
            x1 = cx + xClear;
            x2 = Math.min(w - 10, x1 + entry.pw);
            x1 = x2 - entry.pw;
          }
          entry.side = side;
          entry.x1 = x1;
          entry.x2 = x2;
          entry.y1 = py - entry.ph * 0.5;
          entry.y2 = py + entry.ph * 0.5;
        });
      }
    }

    for (const entry of visible) {
      const { item, ax, ay, x1, y1, x2, y2, side } = entry;
      const isActive = item.id === this.state.activeThreatId;
      item.el.dataset.align = side;
      item.el.style.left = `${x1.toFixed(1)}px`;
      item.el.style.top = `${y1.toFixed(1)}px`;

      if (item.lineEl && item.anchorDotEl) {
        const anchorVisible = ax >= 4 && ax <= w - 4 && ay >= 4 && ay <= h - 4;
        item.lineEl.style.display = anchorVisible ? "" : "none";
        item.anchorDotEl.style.display = anchorVisible ? "" : "none";
        if (anchorVisible) {
          let pts;
          if (side === "left" || side === "right") {
            const edgeX = side === "left" ? x2 : x1;
            const edgeY = (y1 + y2) * 0.5;
            const elbowX =
              side === "left"
                ? Math.min(Math.max(ax, edgeX), edgeX + 16)
                : Math.max(Math.min(ax, edgeX), edgeX - 16);
            pts = `${ax.toFixed(1)},${ay.toFixed(1)} ${elbowX.toFixed(1)},${edgeY.toFixed(1)} ${edgeX.toFixed(1)},${edgeY.toFixed(1)}`;
          } else {
            const edgeX = (x1 + x2) * 0.5;
            const edgeY = side === "top" ? y2 : y1;
            const stubY = side === "top" ? edgeY + 10 : edgeY - 10;
            pts = `${ax.toFixed(1)},${ay.toFixed(1)} ${edgeX.toFixed(1)},${stubY.toFixed(1)} ${edgeX.toFixed(1)},${edgeY.toFixed(1)}`;
          }
          item.lineEl.setAttribute("points", pts);
          item.lineEl.classList.toggle("is-active", isActive);
          item.anchorDotEl.setAttribute("cx", ax.toFixed(1));
          item.anchorDotEl.setAttribute("cy", ay.toFixed(1));
          item.anchorDotEl.setAttribute("r", isActive ? "5.2" : "3.5");
          item.anchorDotEl.classList.toggle("is-active", isActive);
        }
      }
    }
  }

  stopAutoplay() {
    this.state.autoPlaying = false;
    if (this.btnAutoplay) {
      this.btnAutoplay.textContent = "▶";
      this.btnAutoplay.classList.remove("is-playing");
      this.btnAutoplay.setAttribute("aria-label", "Запустить авто-рост");
    }
  }

  toggleAutoplay() {
    this.state.autoPlaying = !this.state.autoPlaying;
    if (this.state.autoPlaying) {
      if (this.renderTier === "fallback-2d") {
        // In 2D mode, step smoothly across discrete phases every 1.1s
        if (this.state.activePhaseIndex >= (this.state.crop?.phases?.length || 1) - 1) {
          this.selectPhase(0, true);
        }
        this.start2DAutoplayTimer();
      } else if (this.state.targetTime >= this.state.durationSec - 0.05) {
        this.state.targetTime = 0;
        this.state.currentTime = 0;
      }
      if (this.btnAutoplay) {
        this.btnAutoplay.textContent = "⏸";
        this.btnAutoplay.classList.add("is-playing");
        this.btnAutoplay.setAttribute("aria-label", "Приостановить авто-рост");
      }
      this.requestRender();
    } else {
      this.stop2DAutoplayTimer();
      this.stopAutoplay();
    }
  }

  start2DAutoplayTimer() {
    this.stop2DAutoplayTimer();
    this.autoplay2DTimer = setInterval(() => {
      if (this.destroyed || !this.state.autoPlaying || this.renderTier !== "fallback-2d") {
        this.stop2DAutoplayTimer();
        return;
      }
      const next = this.state.activePhaseIndex + 1;
      const total = this.state.crop?.phases?.length || 1;
      if (next >= total) {
        this.stop2DAutoplayTimer();
        this.stopAutoplay();
      } else {
        this.selectPhase(next, true);
      }
    }, 1050);
  }

  stop2DAutoplayTimer() {
    if (this.autoplay2DTimer) {
      clearInterval(this.autoplay2DTimer);
      this.autoplay2DTimer = null;
    }
  }

  // ==================== 3D ENGINE INITIALIZATION & SHADERS ====================

  async init3DStage(gpuProbe) {
    const runtime = await loadThreeRuntime();
    if (this.destroyed) return;
    this.THREE = runtime.THREE;
    this.TSL = runtime.TSL;
    this.OrbitControls = runtime.OrbitControls;
    this.GLTFLoader = runtime.GLTFLoader;
    this.HDRLoader = runtime.HDRLoader;

    const { THREE, TSL } = this;
    const isMobile = (typeof window !== "undefined" ? window.innerWidth : 1024) < 768;

    this.tslUniforms = {
      uOuterSenescence: TSL.uniform(0.0),
      uPodPhase: TSL.uniform(0.0),
      uSymptomCenter: TSL.uniform(new THREE.Vector3(0, 0, 0)),
      uSymptomRadius: TSL.uniform(0.18),
      uSymptomIntensity: TSL.uniform(0.0),
      uSymptomMode: TSL.uniform(0.0),
      uSymptomTarget: TSL.uniform(0.0),
    };
    this.applyThreatSymptom(this.getActiveThreatData());

    this.renderer = new THREE.WebGPURenderer({ canvas: this.canvas, antialias: true, alpha: true });
    let initTimer = null;
    try {
      await Promise.race([
        this.renderer.init(),
        new Promise((_, reject) => {
          initTimer = setTimeout(() => reject(new Error("GPU adapter init timeout")), 8000);
        }),
      ]);
    } finally {
      if (initTimer) clearTimeout(initTimer);
    }
    if (this.destroyed) {
      this.renderer.dispose();
      return;
    }

    const isWebGPUBackend = Boolean(this.renderer.backend?.isWebGPUBackend);
    this.renderTier = isWebGPUBackend ? "webgpu" : "webgl2";

    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 2));
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.AgXToneMapping;
    this.renderer.toneMappingExposure = 1.06;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;

    // Wave 0 D-03: Context-loss & WebGPU device.lost protection
    const sig = this.abortCtrl.signal;
    this.canvas.addEventListener(
      "webglcontextlost",
      (ev) => {
        ev.preventDefault();
        this.handleContextLost();
      },
      { signal: sig }
    );
    this.canvas.addEventListener(
      "webglcontextrestored",
      () => {
        this.handleContextRestored();
      },
      { signal: sig }
    );
    if (this.renderer.backend?.device?.lost) {
      this.renderer.backend.device.lost.then((info) => {
        if (!this.destroyed && info?.reason !== "destroyed") {
          this.handleContextLost();
        }
      });
    }

    this.scene = new THREE.Scene();
    const w = Math.max(200, this.stageContainer.clientWidth || 800);
    const h = Math.max(220, this.stageContainer.clientHeight || 520);
    this.camera = new THREE.PerspectiveCamera(FOV_DEG, w / h, 0.05, 40);
    this.camera.position.set(...this.state.camPos);

    this.controls = new this.OrbitControls(this.camera, this.canvas);
    this.controls.target.set(...this.state.camTarget);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 0.85;
    this.controls.maxDistance = 6.0;
    this.controls.maxPolarAngle = Math.PI * 0.88;

    // Wave 3 D-15: Override OrbitControls inline touchAction='none' on coarse pointers so vertical page scroll never traps!
    const isCoarseTouch =
      typeof window !== "undefined" && Boolean(window.matchMedia?.("(pointer: coarse)")?.matches);
    if (isCoarseTouch) {
      this.canvas.style.touchAction = "pan-y pinch-zoom";
      this.canvas.addEventListener(
        "pointerdown",
        (ev) => {
          if (ev.pointerType === "touch") {
            const polar = this.controls.getPolarAngle();
            this.controls.minPolarAngle = polar;
            this.controls.maxPolarAngle = polar;
          }
        },
        { signal: sig, passive: true }
      );
      const unlockPolar = () => {
        if (this.controls) {
          this.controls.minPolarAngle = 0;
          this.controls.maxPolarAngle = Math.PI * 0.88;
        }
      };
      this.canvas.addEventListener("pointerup", unlockPolar, { signal: sig, passive: true });
      this.canvas.addEventListener("pointercancel", unlockPolar, { signal: sig, passive: true });
    }

    // Embedded Desktop Scroll Guard: require Ctrl/Meta or active stage click before wheel zooms 3D
    if (this.options.embedded && !isCoarseTouch) {
      this.controls.enableZoom = false;
      this.canvas.addEventListener(
        "pointerdown",
        () => {
          if (this.controls) this.controls.enableZoom = true;
        },
        { signal: sig, passive: true }
      );
      this.appEl.addEventListener(
        "mouseleave",
        () => {
          if (this.controls) this.controls.enableZoom = false;
        },
        { signal: sig, passive: true }
      );
      this.canvas.addEventListener(
        "wheel",
        (ev) => {
          if ((ev.ctrlKey || ev.metaKey) && this.controls) {
            this.controls.enableZoom = true;
          }
        },
        { signal: sig, passive: true }
      );
    }

    this.controls.addEventListener("start", () => {
      this.state.cameraLerpActive = false;
      this.state.controlsInteracting = true;
      this.requestRender();
    });
    this.controls.addEventListener("change", () => {
      // Only extend damping tail while user is actively interacting (never re-arm from internal damping step!)
      if (this.state.controlsInteracting) {
        this.state.dampingFramesRemaining = 18;
        this.requestRender();
      }
    });
    this.controls.addEventListener("end", () => {
      this.state.controlsInteracting = false;
      this.state.dampingFramesRemaining = 18;
      this.requestRender();
    });
    this.canvas.addEventListener(
      "wheel",
      () => {
        if (this.controls?.enableZoom) {
          this.state.dampingFramesRemaining = 18;
          this.requestRender();
        }
      },
      { signal: sig, passive: true }
    );

    const hemi = new THREE.HemisphereLight(0xe4f3ff, 0x3b2c1e, 0.48);
    this.hemiLightRef = hemi;
    this.scene.add(hemi);

    const shadowRes = isMobile || !isWebGPUBackend ? 1024 : 2048;
    const keyLight = new THREE.DirectionalLight(0xfff6e8, 2.3);
    keyLight.position.set(2.2, 3.6, 2.6);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(shadowRes, shadowRes);
    keyLight.shadow.camera.near = 0.4;
    keyLight.shadow.camera.far = 9.0;
    const d = 1.25;
    keyLight.shadow.camera.left = -d;
    keyLight.shadow.camera.right = d;
    keyLight.shadow.camera.top = d;
    keyLight.shadow.camera.bottom = -d;
    keyLight.shadow.bias = -0.0003;
    keyLight.shadow.normalBias = 0.018;
    keyLight.shadow.radius = 2.5;
    this.scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xd2e6ff, 0.62);
    fillLight.position.set(-2.4, 1.3, 2.2);
    this.fillLightRef = fillLight;
    this.scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xf3fee4, 1.1);
    rimLight.position.set(0.3, 1.8, -2.8);
    this.scene.add(rimLight);

    // Load compact 512x256 HDRI environment asynchronously (non-blocking)
    this.loadEnvironmentHdriAsync(keyLight);

    this.targetMarkerGroup = new THREE.Group();
    const coreGeo = new THREE.SphereGeometry(0.018, 16, 16);
    const coreMat = new THREE.MeshBasicMaterial({ color: 0xff5a5f });
    const haloGeo = new THREE.RingGeometry(0.028, 0.042, 24);
    const haloMat = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.78,
    });
    this.disposableGeometries.add(coreGeo);
    this.disposableGeometries.add(haloGeo);
    this.disposableMaterials.add(coreMat);
    this.disposableMaterials.add(haloMat);
    const coreMesh = new THREE.Mesh(coreGeo, coreMat);
    this.targetHaloMesh = new THREE.Mesh(haloGeo, haloMat);
    this.targetMarkerGroup.add(coreMesh);
    this.targetMarkerGroup.add(this.targetHaloMesh);
    this.targetMarkerGroup.visible = false;
    this.scene.add(this.targetMarkerGroup);
    this.updateTarget3DMarker();

    this.handleResize(true);
  }

  async loadEnvironmentHdriAsync(keyLight) {
    const { THREE } = this;
    try {
      let hdrRel = "assets/textures/farm_field_512.hdr";
      let fallbackRel = "assets/textures/farm_field_1k.hdr";
      try {
        const metaUrl = resolvePeriscopeUrl("assets/textures/hdri_meta.json", this.options.assetBaseUrl);
        const metaRes = await fetchWithRetry(metaUrl, { retries: 2, timeoutMs: 6000, signal: this.abortCtrl.signal });
        if (metaRes.ok) {
          const meta = await metaRes.json();
          if (meta.file) hdrRel = `assets/textures/${meta.file}`;
          if (meta.fallback_hdri) fallbackRel = `assets/textures/${meta.fallback_hdri}`;
          if (Array.isArray(meta.sun_dir_gltf) && meta.sun_dir_gltf.length === 3 && keyLight) {
            keyLight.position.set(meta.sun_dir_gltf[0], meta.sun_dir_gltf[1], meta.sun_dir_gltf[2]);
          }
        }
      } catch {
        // use default compact HDRI
      }
      if (this.destroyed || !this.scene) return;
      const hdrLoader = new this.HDRLoader();
      let hdrTex = null;
      try {
        hdrTex = await hdrLoader.loadAsync(resolvePeriscopeUrl(hdrRel, this.options.assetBaseUrl));
      } catch {
        hdrTex = await hdrLoader.loadAsync(resolvePeriscopeUrl(fallbackRel, this.options.assetBaseUrl));
      }
      if (this.destroyed || !this.scene) {
        hdrTex?.dispose?.();
        return;
      }
      this.disposableTextures.add(hdrTex);
      hdrTex.mapping = THREE.EquirectangularReflectionMapping;
      this.scene.environment = hdrTex;
      this.scene.environmentIntensity = 0.9;
      this.requestRender();
    } catch {
      // Direct lights already provide full outdoor illumination
    }
  }

  handleContextLost() {
    if (this.destroyed) return;
    this.contextLossCount += 1;
    this.stopRenderLoop();
    // Immediately reveal 2D WebP phase poster so user never sees a blank hole!
    if (this.fallbackImg) this.fallbackImg.classList.remove("is-hidden-by-3d");
    if (this.canvas) this.canvas.classList.remove("is-ready");
    if (this.contextLossCount >= 2) {
      this.dispose3DOnly();
      this.activateFallback2D("repeated_context_loss");
    }
    this.emit("contextlost", { count: this.contextLossCount, renderTier: this.renderTier });
  }

  async handleContextRestored() {
    if (this.destroyed || this.renderTier === "fallback-2d") return;
    this.requestRender();
    if (this.canvas) this.canvas.classList.add("is-ready");
    if (this.fallbackImg) this.fallbackImg.classList.add("is-hidden-by-3d");
  }

  upgradeToPhotorealNodeMaterial(srcMat, tier, leafThickTex, rootThickTex, podThickTex, hasVertexColor) {
    const { THREE, TSL } = this;
    const {
      abs,
      clamp,
      cos,
      distance,
      dot,
      float,
      Fn,
      fract,
      frontFacing,
      If,
      length,
      mix,
      normalView,
      positionWorld,
      select,
      sin,
      smoothstep,
      texture,
      uniform,
      uv,
      vec3,
      vec4,
      vertexColor,
    } = TSL;
    const {
      uOuterSenescence,
      uPodPhase,
      uSymptomCenter,
      uSymptomRadius,
      uSymptomIntensity,
      uSymptomMode,
      uSymptomTarget,
    } = this.tslUniforms;

    const isAboveGround =
      tier === "outer" ||
      tier === "mid" ||
      tier === "heart" ||
      tier === "stem" ||
      tier === "pod" ||
      tier === "flower";
    const isUnderground = tier === "root" || tier === "nodule";
    if (!isAboveGround && !isUnderground) {
      return srcMat;
    }

    const fastNoise3D = (p) => {
      const a = sin(dot(p, vec3(1.17, 2.31, 1.73))).mul(cos(dot(p.yzx, vec3(1.93, 1.37, 2.11))));
      const p2 = p.mul(float(2.13)).add(vec3(a.mul(float(1.4)), a.mul(float(-1.1)), a.mul(float(0.9))));
      const b = sin(dot(p2, vec3(1.61, 1.29, 2.47))).mul(cos(dot(p2.zxy, vec3(2.07, 1.71, 1.19))));
      return a.mul(float(0.62)).add(b.mul(float(0.38)));
    };

    const fastSpots3D = (p) => {
      const warp = vec3(
        sin(p.y.mul(float(1.73)).add(p.z.mul(float(1.19)))),
        cos(p.z.mul(float(1.61)).sub(p.x.mul(float(1.37)))),
        sin(p.x.mul(float(1.49)).add(p.y.mul(float(1.83))))
      ).mul(float(0.28));
      const cell = fract(p.add(warp)).sub(float(0.5));
      return length(cell);
    };

    const isLeaf = tier === "outer" || tier === "mid" || tier === "heart";
    const isRoot = tier === "root";
    const isPod = tier === "pod";
    const nodeMat = new THREE.MeshSSSNodeMaterial();
    this.disposableMaterials.add(nodeMat);

    nodeMat.name = srcMat.name;
    nodeMat.map = srcMat.map || null;
    nodeMat.normalMap = srcMat.normalMap || null;
    nodeMat.normalScale = srcMat.normalScale ? srcMat.normalScale.clone() : new THREE.Vector2(1, 1);
    nodeMat.roughnessMap = srcMat.roughnessMap || null;
    nodeMat.roughness = typeof srcMat.roughness === "number" ? srcMat.roughness : 0.85;
    nodeMat.metalness = 0.0;
    nodeMat.color = srcMat.color ? srcMat.color.clone() : new THREE.Color(0xffffff);
    nodeMat.side = srcMat.side;

    const uMatTint = uniform(nodeMat.color.clone());
    const uRoughMul = uniform(nodeMat.roughness);
    const uSenWeight = uniform(tier === "outer" ? 1.0 : 0.0);
    const uPodWeight = uniform(isPod ? 1.0 : 0.0);
    const uBackfaceBlend = uniform(isLeaf ? 1.0 : 0.0);
    const sssHex = isRoot
      ? 0xd9c296
      : tier === "nodule"
        ? 0xf27668
        : tier === "flower"
          ? 0xf0eaff
          : isPod
            ? 0x90c63a
            : tier === "stem"
              ? 0x5ca322
              : tier === "heart"
                ? 0x6eb81e
                : tier === "mid"
                  ? 0x3b9a14
                  : 0x4b8f12;
    const uSssTint = uniform(new THREE.Color(sssHex));
    const uSssAtten = uniform(
      tier === "flower" ? 0.16 : isLeaf ? 0.09 : isPod ? 0.095 : tier === "nodule" ? 0.08 : 0.04
    );
    const uVelvetTint = uniform(
      new THREE.Color(
        tier === "flower"
          ? 0xf5f0ff
          : isPod
            ? 0xe8dd99
            : tier === "nodule"
              ? 0xffb3a1
              : isRoot
                ? 0xdccaa8
                : 0xc8e898
      )
    );
    const uVelvetStrength = uniform(
      tier === "flower" ? 0.22 : isPod ? 0.14 : isLeaf ? 0.15 : tier === "nodule" ? 0.16 : tier === "stem" ? 0.1 : 0.05
    );
    nodeMat.userData.uMatTint = uMatTint;
    nodeMat.userData.uRoughMul = uRoughMul;

    const texRgb = srcMat.map ? texture(srcMat.map, uv()).rgb : vec3(1.0, 1.0, 1.0);
    const vColRgb = hasVertexColor ? vertexColor().rgb : vec3(1.0, 1.0, 1.0);
    let baseCol = texRgb.mul(vColRgb).mul(uMatTint);
    let baseRough = srcMat.roughnessMap ? texture(srcMat.roughnessMap, uv()).g.mul(uRoughMul) : uRoughMul;
    let clearcoatVal = float(isLeaf ? 0.18 : isPod ? 0.14 : 0.06);

    const rimOneMinus = clamp(float(1.0).sub(abs(normalView.z)), float(0.0), float(1.0));
    const velvetRim = rimOneMinus.mul(rimOneMinus).mul(rimOneMinus).mul(uVelvetStrength);

    if (isAboveGround) {
      nodeMat.clearcoat = isLeaf ? 0.22 : isPod ? 0.14 : 0.06;
      nodeMat.clearcoatRoughness = 0.36;
      nodeMat.sheen = tier === "flower" ? 0.18 : isPod ? 0.12 : 0.1;
      nodeMat.sheenRoughness = 0.5;
      nodeMat.sheenColor = new THREE.Color(tier === "flower" ? 0xd9d2ff : isPod ? 0xd8c87a : 0x9bd258);

      const adaxialCol = baseCol.mul(vec3(0.95, 0.99, 0.94));
      const abaxialCol = mix(baseCol.mul(float(1.14)), vec3(0.42, 0.56, 0.24), float(0.24));
      const leafCol = select(frontFacing, adaxialCol, abaxialCol);
      baseCol = mix(baseCol, leafCol, uBackfaceBlend);
      const leafRough = select(frontFacing, baseRough.mul(float(0.86)), baseRough.mul(float(1.24)));
      baseRough = mix(baseRough, leafRough, uBackfaceBlend);
      const leafCoat = select(frontFacing, float(0.22), float(0.05));
      clearcoatVal = mix(clearcoatVal, leafCoat, uBackfaceBlend);

      const edgeDist = abs(uv().x.sub(float(0.5))).mul(float(2.0));
      const tipDist = clamp(uv().y.sub(float(0.26)).div(float(0.74)), float(0.0), float(1.0));
      const orgRipenNoise = fastNoise3D(positionWorld.mul(float(16.0))).mul(float(0.2));
      const edgeCoord = edgeDist.mul(float(0.68)).add(tipDist.mul(float(0.5))).add(orgRipenNoise);
      const senActive = uOuterSenescence.mul(uSenWeight);
      const chlorosisMask = smoothstep(float(0.72), float(1.18), edgeCoord).mul(senActive);
      const crispBrownMask = smoothstep(float(0.96), float(1.28), edgeCoord)
        .mul(clamp(uOuterSenescence.sub(float(0.45)).div(float(0.55)), float(0.0), float(1.0)))
        .mul(uSenWeight);
      baseCol = mix(baseCol, vec3(0.78, 0.67, 0.16), chlorosisMask.mul(float(0.8)));
      baseCol = mix(baseCol, vec3(0.36, 0.24, 0.09), crispBrownMask.mul(float(0.85)));
      baseRough = mix(baseRough, float(0.86), crispBrownMask.mul(float(0.85)));
      clearcoatVal = clearcoatVal.mul(float(1.0).sub(chlorosisMask.mul(float(0.75))));

      const podSutureMask = smoothstep(
        float(0.58),
        float(1.15),
        edgeDist.mul(float(0.85)).add(tipDist.mul(float(0.45))).add(orgRipenNoise)
      )
        .mul(uPodPhase)
        .mul(uPodWeight);
      baseCol = mix(baseCol, vec3(0.72, 0.56, 0.24), podSutureMask.mul(float(0.48)));
      baseRough = mix(baseRough, float(0.78), podSutureMask.mul(float(0.55)));
      baseCol = baseCol.add(uVelvetTint.mul(velvetRim));

      const activeThickTex = isPod ? podThickTex : isLeaf ? leafThickTex : null;
      const thickSample = activeThickTex ? texture(activeThickTex, uv()).r : float(tier === "flower" ? 0.94 : 0.45);
      const podDryAtten = float(1.0).sub(uPodPhase.mul(uPodWeight).mul(float(0.62)));
      const sssSideBoost = select(frontFacing, float(1.0), float(1.18));
      nodeMat.thicknessColorNode = uSssTint
        .mul(thickSample)
        .mul(sssSideBoost)
        .mul(podDryAtten)
        .mul(float(1.0).sub(crispBrownMask.mul(float(0.82))));
      nodeMat.thicknessDistortionNode = float(0.36);
      nodeMat.thicknessAmbientNode = float(0.0);
      nodeMat.thicknessAttenuationNode = uSssAtten;
      nodeMat.thicknessPowerNode = float(3.1);
      nodeMat.thicknessScaleNode = float(2.3);

      const radialDist = positionWorld.xz.length();
      const heightAboveCrown = clamp(positionWorld.y.add(float(0.02)).div(float(0.3)), float(0.0), float(1.0));
      const radialOpen = clamp(radialDist.div(float(0.2)), float(0.0), float(1.0));
      nodeMat.aoNode = mix(
        float(0.62),
        float(1.0),
        clamp(heightAboveCrown.mul(float(0.6)).add(radialOpen.mul(float(0.56))), float(0.0), float(1.0))
      );
    } else if (isUnderground) {
      nodeMat.clearcoat = tier === "nodule" ? 0.1 : 0.06;
      nodeMat.clearcoatRoughness = tier === "nodule" ? 0.48 : 0.58;
      nodeMat.sheen = tier === "nodule" ? 0.12 : 0.05;
      nodeMat.sheenRoughness = 0.62;
      nodeMat.sheenColor = new THREE.Color(tier === "nodule" ? 0xf6b8a8 : 0xeaddc4);
      baseCol = baseCol.add(uVelvetTint.mul(velvetRim));

      const rThick = isRoot && rootThickTex ? texture(rootThickTex, uv()).r : float(0.62);
      nodeMat.thicknessColorNode = uSssTint.mul(rThick);
      nodeMat.thicknessDistortionNode = float(0.26);
      nodeMat.thicknessAmbientNode = float(0.0);
      nodeMat.thicknessAttenuationNode = uSssAtten;
      nodeMat.thicknessPowerNode = float(3.4);
      nodeMat.thicknessScaleNode = float(tier === "nodule" ? 1.65 : 1.15);
    }

    // Wave 4 D-22: AgX chroma-calibrated diagnostic disease symptom overlays
    const targetMatch = isUnderground
      ? select(uSymptomTarget.lessThan(float(1.5)), float(1.0), float(0.0))
      : select(uSymptomTarget.equal(float(0.0)).or(uSymptomTarget.greaterThan(float(1.5))), float(1.0), float(0.0));

    const evalSymptomColorRough = Fn(() => {
      const outCol = baseCol.toVar();
      const outRough = baseRough.toVar();

      If(
        uSymptomIntensity.greaterThan(float(0.005)).and(targetMatch.greaterThan(float(0.5))),
        () => {
          const distToFocus = distance(positionWorld, uSymptomCenter);
          const orgNoise = fastNoise3D(positionWorld.mul(float(28.0)));
          const warpedDist = distToFocus.add(orgNoise.mul(uSymptomRadius).mul(float(0.28)));
          const focusMask = float(1.0)
            .sub(smoothstep(uSymptomRadius.mul(float(0.24)), uSymptomRadius, warpedDist))
            .mul(uSymptomIntensity);

          If(uSymptomMode.lessThan(float(1.5)), () => {
            const crackN = fastNoise3D(positionWorld.mul(float(68.0)));
            const m1 = focusMask.mul(smoothstep(float(-0.42), float(0.38), crackN.add(float(0.32))));
            outCol.assign(mix(outCol, vec3(0.062, 0.033, 0.019), m1.mul(float(0.93))));
            outRough.assign(mix(outRough, float(0.95), m1));
          })
            .ElseIf(uSymptomMode.lessThan(float(2.5)), () => {
              const spotD = fastSpots3D(positionWorld.mul(float(22.0)));
              const spotCore = float(1.0).sub(smoothstep(float(0.1), float(0.16), spotD));
              const spotHalo = smoothstep(float(0.11), float(0.16), spotD).mul(
                float(1.0).sub(smoothstep(float(0.2), float(0.27), spotD))
              );
              const m2Core = focusMask.mul(spotCore);
              const m2Halo = focusMask.mul(spotHalo);
              outCol.assign(mix(outCol, vec3(0.44, 0.055, 0.095), m2Halo.mul(float(0.94))));
              outCol.assign(mix(outCol, vec3(0.57, 0.52, 0.45), m2Core.mul(float(0.9))));
              outRough.assign(mix(outRough, float(0.92), clamp(m2Core.add(m2Halo), float(0.0), float(1.0))));
            })
            .ElseIf(uSymptomMode.lessThan(float(3.5)), () => {
              const mPatch = smoothstep(float(-0.22), float(0.34), fastNoise3D(positionWorld.mul(float(42.0))));
              const upperBias = select(frontFacing, float(1.0), float(0.2));
              const m3 = focusMask.mul(mPatch).mul(upperBias);
              outCol.assign(mix(outCol, vec3(0.88, 0.89, 0.85), m3.mul(float(0.84))));
              outRough.assign(mix(outRough, float(0.96), m3));
            })
            .ElseIf(uSymptomMode.lessThan(float(4.5)), () => {
              const ringW = sin(distToFocus.mul(float(105.0)).add(orgNoise.mul(float(4.5))))
                .mul(float(0.5))
                .add(float(0.5));
              const phCol = mix(vec3(0.095, 0.06, 0.036), vec3(0.44, 0.3, 0.16), ringW);
              outCol.assign(mix(outCol, phCol, focusMask.mul(float(0.92))));
              outRough.assign(mix(outRough, float(0.92), focusMask));
            })
            .Else(() => {
              const pestD = fastSpots3D(positionWorld.mul(float(17.0)));
              const pCen = float(1.0).sub(smoothstep(float(0.11), float(0.18), pestD));
              const pRim = smoothstep(float(0.14), float(0.19), pestD).mul(
                float(1.0).sub(smoothstep(float(0.22), float(0.29), pestD))
              );
              const m5C = focusMask.mul(pCen);
              const m5R = focusMask.mul(pRim);
              outCol.assign(mix(outCol, vec3(0.74, 0.71, 0.28), focusMask.mul(float(0.4))));
              outCol.assign(mix(outCol, vec3(0.34, 0.18, 0.07), m5R.mul(float(0.86))));
              outCol.assign(mix(outCol, vec3(0.8, 0.75, 0.44), m5C.mul(float(0.84))));
              outRough.assign(mix(outRough, float(0.86), clamp(m5C.add(m5R), float(0.0), float(1.0))));
            });
        }
      );

      return vec4(outCol.x, outCol.y, outCol.z, clamp(outRough, float(0.16), float(0.98)));
    })();

    const symRes = evalSymptomColorRough.toVar();
    const lesionMatteFactor = smoothstep(float(0.78), float(0.93), symRes.w).mul(uSymptomIntensity);

    if (nodeMat.thicknessColorNode) {
      nodeMat.thicknessColorNode = nodeMat.thicknessColorNode.mul(
        float(1.0).sub(lesionMatteFactor.mul(float(0.85)))
      );
    }

    nodeMat.colorNode = symRes.rgb;
    nodeMat.roughnessNode = symRes.w;
    nodeMat.clearcoatNode = clamp(clearcoatVal.mul(float(1.0).sub(lesionMatteFactor)), float(0.0), float(0.35));
    return nodeMat;
  }

  async load3DModelForCurrentCrop() {
    const { THREE } = this;
    const crop = this.state.crop;
    if (!crop || !this.renderer || !this.scene) return;

    const cropId = crop.crop_id;
    const texLoader = new THREE.TextureLoader();
    const loadLinearMap = async (relPath, fallbackRel = null) => {
      try {
        const tex = await texLoader.loadAsync(resolvePeriscopeUrl(relPath, this.options.assetBaseUrl));
        tex.flipY = false;
        tex.colorSpace = THREE.NoColorSpace;
        this.disposableTextures.add(tex);
        return tex;
      } catch {
        if (fallbackRel) return loadLinearMap(fallbackRel, null);
        return null;
      }
    };

    const leafThickRel =
      cropId === "sugar_beet" ? "assets/textures/leaf_thickness.png" : `assets/textures/${cropId}_leaf_thickness.png`;
    const rootThickRel =
      cropId === "sugar_beet" ? "assets/textures/root_thickness.png" : `assets/textures/${cropId}_root_thickness.png`;
    const podThickRel = cropId === "sugar_beet" ? null : `assets/textures/${cropId}_pod_thickness.png`;

    if (this.loadingBarFill) this.loadingBarFill.style.width = "22%";

    let expectedGlbBytes = 0;
    if (this.currentStatsUrl) {
      fetchWithRetry(this.currentStatsUrl, { retries: 2, timeoutMs: 6000, signal: this.abortCtrl.signal })
        .then((r) => (r.ok ? r.json() : null))
        .then((stats) => {
          if (stats && !this.destroyed) {
            expectedGlbBytes = Number(stats.glb_bytes || 0);
            if (this.options.debug && this.statSize && this.statTris) {
              this.statSize.textContent = `GLB ${(expectedGlbBytes / 1024).toFixed(0)} КБ`;
              this.statTris.textContent = `${Number(stats.triangle_count || 0).toLocaleString("ru-RU")} треуг.`;
            }
          }
        })
        .catch(() => {});
    }

    const modelUrl = resolvePeriscopeUrl(crop.model_url, this.options.assetBaseUrl);
    const loadGlbWithRetry = async () => {
      let lastErr = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        if (this.destroyed) throw new Error("Destroyed");
        try {
          const loader = new this.GLTFLoader();
          return await loader.loadAsync(modelUrl, (xhr) => {
            const total = xhr.total || expectedGlbBytes;
            if (total > 0 && xhr.loaded > 0 && this.loadingBarFill) {
              const pct = 22 + Math.min(68, Math.round((xhr.loaded / total) * 68));
              this.loadingBarFill.style.width = `${pct}%`;
            }
          });
        } catch (err) {
          lastErr = err;
          if (attempt + 1 < 3) {
            await new Promise((r) => setTimeout(r, 500 * 2 ** attempt));
          }
        }
      }
      throw lastErr;
    };

    const [[leafThickTex, rootThickTex, podThickTex], gltf] = await Promise.all([
      Promise.all([
        loadLinearMap(leafThickRel, "assets/textures/leaf_thickness.png"),
        loadLinearMap(rootThickRel, "assets/textures/root_thickness.png"),
        podThickRel ? loadLinearMap(podThickRel, null) : Promise.resolve(null),
      ]),
      loadGlbWithRetry(),
    ]);

    if (this.destroyed) return;

    this.activePalette = {
      outerFresh: new THREE.Color(crop.maturation_palette?.outer_fresh || "#edf5df"),
      outerMature: new THREE.Color(crop.maturation_palette?.outer_mature || "#d8be56"),
      midFresh: new THREE.Color(crop.maturation_palette?.mid_fresh || "#f5faef"),
      midMature: new THREE.Color(crop.maturation_palette?.mid_mature || "#dce8a8"),
      heartFresh: new THREE.Color(crop.maturation_palette?.heart_fresh || "#e2ffad"),
      heartMature: new THREE.Color(crop.maturation_palette?.heart_mature || "#cce87a"),
      podFresh: new THREE.Color(crop.maturation_palette?.pod_fresh || "#74b632"),
      podMature: new THREE.Color(crop.maturation_palette?.pod_mature || "#d6b562"),
      stemFresh: new THREE.Color("#e9f5d8"),
      stemMature: new THREE.Color("#cfc274"),
      rootEarly: new THREE.Color(crop.maturation_palette?.root_early || "#ffffff"),
      rootMature: new THREE.Color(crop.maturation_palette?.root_mature || "#f4ecd8"),
    };
    this.tmpColor = new THREE.Color();

    const upgradedMaterials = new Map();
    gltf.scene.traverse((obj) => {
      if (obj.isMesh) {
        if (obj.geometry) this.disposableGeometries.add(obj.geometry);
        if (obj.material) {
          const srcMat = obj.material;
          this.disposableMaterials.add(srcMat);
          for (const texKey of ["map", "normalMap", "roughnessMap", "emissiveMap", "aoMap"]) {
            if (srcMat[texKey]) this.disposableTextures.add(srcMat[texKey]);
          }
          obj.castShadow = true;
          obj.receiveShadow = true;
          let tier = "other";
          if (srcMat.name === "Outer_Leaf_PBR") tier = "outer";
          else if (srcMat.name === "Mid_Leaf_PBR") tier = "mid";
          else if (srcMat.name === "Heart_Leaf_PBR") tier = "heart";
          else if (srcMat.name === "Stem_PBR") tier = "stem";
          else if (srcMat.name === "Pod_PBR") tier = "pod";
          else if (srcMat.name === "Flower_PBR") tier = "flower";
          else if (srcMat.name === "Taproot_PBR") tier = "root";
          else if (srcMat.name === "Nodule_PBR") tier = "nodule";

          let nodeMat = upgradedMaterials.get(srcMat);
          if (!nodeMat) {
            const hasVCol = Boolean(obj.geometry?.attributes?.color);
            nodeMat = this.upgradeToPhotorealNodeMaterial(
              srcMat,
              tier,
              leafThickTex,
              rootThickTex,
              podThickTex,
              hasVCol
            );
            upgradedMaterials.set(srcMat, nodeMat);
            if (tier !== "other") {
              this.matHandles[tier] = nodeMat;
            }
          }
          obj.material = nodeMat;
        }
      }
    });

    this.plantRoot = gltf.scene;
    this.scene.add(gltf.scene);

    if (this.camera && this.controls) {
      this.camera.position.set(...this.cameraPresets.overview.pos);
      this.controls.target.set(...this.cameraPresets.overview.target);
      this.controls.update();
    }

    this.mixer = new THREE.AnimationMixer(gltf.scene);
    this.actions = gltf.animations.map((clip) => {
      const action = this.mixer.clipAction(clip);
      action.setLoop(THREE.LoopOnce);
      action.clampWhenFinished = true;
      action.enabled = true;
      action.play();
      action.paused = true;
      action.time = this.state.targetTime;
      return action;
    });
    this.state.currentTime = this.state.targetTime;
    this.mixer.update(0);

    // Wave 1 D-10: Only run fallback Box3 sampling if passport JSON lacked precomputed extent_profile!
    if (!this.plantExtentProfile || this.plantExtentProfile.length === 0) {
      this.samplePlantExtentsFallback();
    }

    this.updateMaturationMaterials(Math.max(0, Math.min(1, this.state.currentTime / this.state.durationSec)));
    this.updateDynamicRingRadius(0, true);

    if (this.loadingBarFill) this.loadingBarFill.style.width = "95%";
    if (typeof this.renderer.compileAsync === "function") {
      try {
        await this.renderer.compileAsync(this.scene, this.camera);
      } catch {
        // fallback to synchronous first render
      }
    }
    if (this.destroyed) return;

    this.renderer.render(this.scene, this.camera);
    this.framesRendered += 1;

    if (this.loadingBarFill) this.loadingBarFill.style.width = "100%";
    if (this.canvas) {
      this.canvas.classList.remove("is-fallback-2d");
      this.canvas.classList.add("is-ready");
    }
    // Seamless 180ms crossfade from pixel-aligned 2D poster to live 3D WebGPU/WebGL2!
    if (this.fallbackImg) {
      this.fallbackImg.classList.add("is-hidden-by-3d");
    }
    this.appEl.classList.remove("is-mode-2d");
    if (this.loadingOverlay) {
      this.loadingOverlay.classList.add("is-done");
      this.loadingOverlay.hidden = true;
    }
    this.requestRender();
  }

  samplePlantExtentsFallback() {
    if (!this.plantRoot || !this.mixer || !this.actions.length || !this.THREE) return;
    const dur = Math.max(0.1, this.state.durationSec || 6.25);
    const prevTime = this.state.currentTime;
    const box = new this.THREE.Box3();
    const profile = [];
    for (let i = 0; i < 11; i++) {
      const t = (i / 10) * dur;
      for (const action of this.actions) {
        const clipDur = action.getClip().duration || dur;
        action.time = Math.max(0, Math.min(t, Math.max(0, clipDur - 1e-5)));
      }
      this.mixer.update(0);
      this.plantRoot.updateMatrixWorld(true);
      box.setFromObject(this.plantRoot);
      if (!box.isEmpty()) {
        profile.push({
          t,
          halfW: Math.max(0.04, Math.abs(box.min.x), Math.abs(box.max.x), Math.abs(box.min.z), Math.abs(box.max.z)),
          midY: (box.min.y + box.max.y) * 0.5,
        });
      }
    }
    for (const action of this.actions) {
      const clipDur = action.getClip().duration || dur;
      action.time = Math.max(0, Math.min(prevTime, Math.max(0, clipDur - 1e-5)));
    }
    this.mixer.update(0);
    this.plantExtentProfile = profile;
  }

  updateMaturationMaterials(progress) {
    if (!this.tslUniforms || !this.activePalette || !this.tmpColor) return;
    const matPhase = Math.max(0, Math.min(1, (progress - 0.52) / 0.48));
    const podPhase = Math.max(0, Math.min(1, (progress - 0.68) / 0.32));
    this.tslUniforms.uOuterSenescence.value = matPhase;
    this.tslUniforms.uPodPhase.value = podPhase;

    const applyTint = (handle, c0, c1, t, roughBase = null, roughAdd = 0) => {
      if (!handle) return;
      this.tmpColor.copy(c0).lerp(c1, t);
      handle.color.copy(this.tmpColor);
      if (handle.userData.uMatTint) handle.userData.uMatTint.value.copy(this.tmpColor);
      if (roughBase !== null && handle.userData.uRoughMul) {
        handle.userData.uRoughMul.value = roughBase + roughAdd;
      }
    };

    applyTint(this.matHandles.outer, this.activePalette.outerFresh, this.activePalette.outerMature, matPhase * 0.65, 0.95, 0.35 * matPhase);
    applyTint(this.matHandles.mid, this.activePalette.midFresh, this.activePalette.midMature, matPhase * 0.58, 0.88, 0.25 * matPhase);
    applyTint(this.matHandles.heart, this.activePalette.heartFresh, this.activePalette.heartMature, matPhase * 0.42);
    applyTint(this.matHandles.stem, this.activePalette.stemFresh, this.activePalette.stemMature, podPhase * 0.55);
    applyTint(this.matHandles.pod, this.activePalette.podFresh, this.activePalette.podMature, podPhase, 0.85, 0.4 * podPhase);
    applyTint(this.matHandles.root, this.activePalette.rootEarly, this.activePalette.rootMature, progress * 0.65);
  }

  async ensureUltraAOPipeline() {
    if (this.renderPipeline) return true;
    const { THREE, TSL } = this;
    if (!this.renderer || !this.scene || !this.camera || typeof THREE?.RenderPipeline !== "function") return false;
    try {
      const { ssao } = await import("./vendor/three/examples/jsm/tsl/display/SSAONode.js");
      const isMobile = (typeof window !== "undefined" ? window.innerWidth : 1024) < 768;
      const { builtinAOContext, clamp, float, mix, mrt, normalView, packNormalToRGB, pass, sample, screenUV, smoothstep, unpackRGBToNormal, vec4 } = TSL;

      const prePass = pass(this.scene, this.camera);
      prePass.transparent = false;
      prePass.setMRT(mrt({ output: packNormalToRGB(normalView) }));
      const normalTex = prePass.getTexture("output");
      normalTex.type = THREE.UnsignedByteType;
      const prePassNormal = sample((u) => unpackRGBToNormal(prePass.getTextureNode().sample(u)));
      const prePassDepth = prePass.getTextureNode("depth");

      const aoPass = ssao(prePassDepth, prePassNormal, this.camera);
      aoPass.resolutionScale = isMobile ? 0.5 : 0.75;
      aoPass.samples.value = isMobile ? 12 : 16;
      aoPass.radius.value = 0.085;
      aoPass.intensity.value = 2.4;
      if (aoPass.bias) aoPass.bias.value = 0.015;
      aoPass.blurEnabled = true;
      if (aoPass.blurSharpness) aoPass.blurSharpness.value = 12.0;

      const aoSample = clamp(aoPass.getTextureNode().sample(screenUV).r, float(0.0), float(1.0));
      const scenePass = pass(this.scene, this.camera);
      scenePass.options.samples = isMobile ? 2 : 4;
      scenePass.contextNode = builtinAOContext(aoSample);

      const sceneColor = scenePass.getTextureNode("output");
      const creviceFactor = mix(float(0.42), float(1.0), smoothstep(float(0.08), float(0.96), aoSample));
      const finalOutput = vec4(sceneColor.rgb.mul(creviceFactor), sceneColor.a);

      this.renderPipeline = new THREE.RenderPipeline(this.renderer, finalOutput);
      this.renderPipeline.outputColorTransform = true;
      return true;
    } catch {
      this.renderPipeline = null;
      return false;
    }
  }

  syncUltraAOState() {
    if (this.fillLightRef) this.fillLightRef.intensity = this.state.ultraAO ? 0.44 : 0.62;
    if (this.hemiLightRef) this.hemiLightRef.intensity = this.state.ultraAO ? 0.54 : 0.48;
    if (this.toggleSsaoBtn) {
      this.toggleSsaoBtn.classList.toggle("is-active", this.state.ultraAO);
      this.toggleSsaoBtn.setAttribute("aria-pressed", this.state.ultraAO ? "true" : "false");
      this.toggleSsaoBtn.textContent = `Объёмные тени: ${this.state.ultraAO ? "Вкл" : "Выкл"}`;
    }
  }

  // ==================== WAVE 1 RENDER-ON-DEMAND + WAVE 0 FPS WATCHDOG ====================

  needsNextFrame() {
    if (this.destroyed || !this.isIntersecting || !this.renderer || this.renderTier === "fallback-2d") {
      return false;
    }
    if (this.state.autoPlaying || this.state.cameraLerpActive || this.state.controlsInteracting) {
      return true;
    }
    if (this.state.dampingFramesRemaining > 0) return true;
    if (Math.abs(this.state.targetTime - this.state.currentTime) > 0.0006) return true;
    if (Math.abs(this.state.symptomTargetIntensity - this.state.symptomCurrentIntensity) > 0.002) return true;
    if (Math.abs(this.stageGeo.targetRPhase - this.stageGeo.rPhase) > 0.35) return true;
    return false;
  }

  requestRender() {
    if (this.destroyed || this.renderTier === "fallback-2d" || !this.renderer || !this.isIntersecting) {
      return;
    }
    if (this.isLoopRunning) return;
    this.isLoopRunning = true;
    this.prevFrameTs = performance.now();
    if (typeof this.watchdogFrames !== "number") {
      this.watchdogFrames = 0;
      this.watchdogElapsedSec = 0;
    }

    const step = (now) => {
      if (this.destroyed || !this.isLoopRunning || !this.renderer) {
        this.isLoopRunning = false;
        this.rafId = null;
        return;
      }

      if (this.options.simulateSlowGpu) {
        const burnUntil = performance.now() + 85;
        while (performance.now() < burnUntil) {
          // Synthetic GPU stall for automated Wave 0/5 FPS Watchdog verification
        }
      }

      const rawDt = Math.max(0.001, (now - this.prevFrameTs) / 1000);
      const dt = Math.min(0.05, rawDt);
      this.prevFrameTs = now;

      // FPS Watchdog over cumulative active animation frames (ignores tab switches > 350ms)
      if (rawDt > 0.004 && rawDt < 0.35) {
        this.watchdogFrames += 1;
        this.watchdogElapsedSec += rawDt;
        if (this.watchdogFrames >= 14) {
          const measuredFps = this.watchdogFrames / Math.max(0.001, this.watchdogElapsedSec);
          if (this.options.debug && this.statFps) {
            this.statFps.textContent = `${Math.round(measuredFps)} FPS`;
          }
          if (measuredFps < this.options.minFpsThreshold) {
            this.stopRenderLoop();
            this.dispose3DOnly();
            this.activateFallback2D("fps_watchdog_downgrade");
            this.emit("downgrade2d", { measuredFps: Math.round(measuredFps) });
            return;
          }
          this.watchdogFrames = 0;
          this.watchdogElapsedSec = 0;
        }
      }

      this.renderSingleFrame(dt, now / 1000);

      if (this.needsNextFrame()) {
        this.rafId = requestAnimationFrame(step);
      } else {
        // Render-on-Demand sleep: 0% GPU & 0% battery drain when idle!
        this.isLoopRunning = false;
        this.rafId = null;
        if (this.options.debug && this.statFps) {
          this.statFps.textContent = "0 FPS (сон)";
        }
      }
    };

    this.rafId = requestAnimationFrame(step);
  }

  stopRenderLoop() {
    this.isLoopRunning = false;
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }

  findClosestPhaseIndex(timeSec) {
    const phases = this.state.crop?.phases || [];
    let bestIdx = 0;
    let bestDist = Infinity;
    phases.forEach((p, idx) => {
      const d = Math.abs(p.time_sec - timeSec);
      if (d < bestDist) {
        bestDist = d;
        bestIdx = idx;
      }
    });
    return bestIdx;
  }

  renderSingleFrame(dt, elapsedSec) {
    if (!this.renderer || !this.scene || !this.camera) return;

    if (this.state.autoPlaying && this.state.crop) {
      this.state.targetTime += dt * 0.95;
      if (this.state.targetTime >= this.state.durationSec) {
        this.state.targetTime = this.state.durationSec;
        this.stopAutoplay();
      }
      const nearest = this.findClosestPhaseIndex(this.state.targetTime);
      if (nearest !== this.state.activePhaseIndex) {
        this.selectPhase(nearest, false);
      }
    }

    if (this.mixer && this.actions.length > 0) {
      const diff = this.state.targetTime - this.state.currentTime;
      if (Math.abs(diff) > 0.0005) {
        this.state.currentTime += diff * Math.min(1, dt * 8.5);
      } else {
        this.state.currentTime = this.state.targetTime;
      }

      for (const action of this.actions) {
        const clipDur = action.getClip().duration || this.state.durationSec;
        action.enabled = true;
        action.paused = true;
        action.time = Math.max(0, Math.min(this.state.currentTime, Math.max(0, clipDur - 1e-5)));
      }
      this.mixer.update(0);

      const progress = Math.max(0, Math.min(1, this.state.currentTime / this.state.durationSec));
      this.updateMaturationMaterials(progress);
      this.updateLiveMetrics(this.state.currentTime);
      this.updateReticleArcProgress(progress);

      if (this.options.debug && this.state.crop && this.readoutFrame) {
        const currentFrame = Math.round(this.state.currentTime * (this.state.crop.fps || 24));
        this.readoutFrame.textContent = `Кадр ${currentFrame} / ${this.state.crop.total_frames}`;
      }
    }

    const symDiff = this.state.symptomTargetIntensity - this.state.symptomCurrentIntensity;
    if (Math.abs(symDiff) > 0.002) {
      this.state.symptomCurrentIntensity += symDiff * Math.min(1, dt * 7.5);
    } else {
      this.state.symptomCurrentIntensity = this.state.symptomTargetIntensity;
    }
    if (this.tslUniforms) {
      this.tslUniforms.uSymptomIntensity.value = this.state.symptomCurrentIntensity;
    }

    if (this.targetMarkerGroup?.visible) {
      this.targetMarkerGroup.lookAt(this.camera.position);
      const pulse = 1.0 + 0.18 * Math.sin(elapsedSec * 4.2);
      if (this.targetHaloMesh) this.targetHaloMesh.scale.set(pulse, pulse, 1);
    }

    if (this.state.cameraLerpActive && this.controls) {
      const k = Math.min(1, dt * 6.0);
      const [gx, gy, gz] = this.state.camGoalPos;
      const [tx, ty, tz] = this.state.camGoalTarget;
      this.camera.position.x += (gx - this.camera.position.x) * k;
      this.camera.position.y += (gy - this.camera.position.y) * k;
      this.camera.position.z += (gz - this.camera.position.z) * k;
      this.controls.target.x += (tx - this.controls.target.x) * k;
      this.controls.target.y += (ty - this.controls.target.y) * k;
      this.controls.target.z += (tz - this.controls.target.z) * k;
      if (
        Math.hypot(gx - this.camera.position.x, gy - this.camera.position.y, gz - this.camera.position.z) < 0.01 &&
        Math.hypot(tx - this.controls.target.x, ty - this.controls.target.y, tz - this.controls.target.z) < 0.01
      ) {
        this.state.cameraLerpActive = false;
      }
    }

    if (this.controls) {
      this.controls.update();
      if (this.state.dampingFramesRemaining > 0 && !this.state.controlsInteracting) {
        this.state.dampingFramesRemaining -= 1;
      }
      this.state.camPos = [this.camera.position.x, this.camera.position.y, this.camera.position.z];
      this.state.camTarget = [this.controls.target.x, this.controls.target.y, this.controls.target.z];
    }

    this.updateBackdropSoilHorizon();
    if (this.state.ultraAO && this.renderPipeline) {
      try {
        this.renderPipeline.render();
      } catch {
        this.state.ultraAO = false;
        this.renderPipeline = null;
        this.syncUltraAOState();
        this.renderer.render(this.scene, this.camera);
      }
    } else {
      this.renderer.render(this.scene, this.camera);
    }
    this.framesRendered += 1;
    this.updateDynamicRingRadius(dt, false);
    this.updateHotspotPositions();
  }

  // ==================== WAVE 1 VRAM & SPA LIFECYCLE CLEANUP ====================

  clearCurrentPlantMeshes() {
    if (this.mixer && this.plantRoot) {
      this.mixer.stopAllAction();
      this.mixer.uncacheRoot(this.plantRoot);
    }
    this.mixer = null;
    this.actions = [];
    if (this.plantRoot && this.scene) {
      this.scene.remove(this.plantRoot);
    }
    this.plantRoot = null;
    for (const k of Object.keys(this.matHandles)) {
      this.matHandles[k] = null;
    }
  }

  dispose3DOnly() {
    this.stopRenderLoop();
    this.clearCurrentPlantMeshes();

    if (this.controls) {
      try {
        this.controls.dispose();
      } catch {
        // ignore
      }
      this.controls = null;
    }

    if (this.renderPipeline) {
      try {
        this.renderPipeline.dispose?.();
      } catch {
        // ignore
      }
      this.renderPipeline = null;
    }

    for (const geo of this.disposableGeometries) {
      try {
        geo.dispose();
      } catch {
        // ignore
      }
    }
    this.disposableGeometries.clear();

    for (const mat of this.disposableMaterials) {
      try {
        mat.dispose();
      } catch {
        // ignore
      }
    }
    this.disposableMaterials.clear();

    for (const tex of this.disposableTextures) {
      try {
        tex.dispose();
      } catch {
        // ignore
      }
    }
    this.disposableTextures.clear();

    if (this.scene) {
      this.scene.environment = null;
      this.scene.clear();
      this.scene = null;
    }

    if (this.renderer) {
      try {
        this.renderer.setAnimationLoop(null);
        this.renderer.dispose();
      } catch {
        // ignore
      }
      this.renderer = null;
    }
    this.camera = null;
    this.targetMarkerGroup = null;
    this.targetHaloMesh = null;
  }

  destroy() {
    if (this.destroyed) return;
    this.destroyed = true;
    this.stop2DAutoplayTimer();
    this.abortCtrl.abort();
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.intersectionObserver?.disconnect();
    this.intersectionObserver = null;

    this.dispose3DOnly();

    if (this.reticlePhaseRing) this.reticlePhaseRing.textContent = "";
    if (this.hotspotsLayer) this.hotspotsLayer.textContent = "";
    if (this.hotspotLeadersSvg) this.hotspotLeadersSvg.textContent = "";
    if (this.phaseButtonsEl) this.phaseButtonsEl.textContent = "";
    if (this.threatsListEl) this.threatsListEl.textContent = "";

    if (this.createdAppEl && this.appEl?.parentNode) {
      this.appEl.parentNode.removeChild(this.appEl);
    }
  }
}

export async function mountPeriscopeStage(containerEl, options = {}) {
  const ctrl = new PeriscopeStageController(containerEl, options);
  await ctrl.init();
  return ctrl;
}

// Auto-bootstrap ONLY when running standalone web/index.html (never hijacks host SPA pages importing PeriscopeStageController)
if (typeof document !== "undefined") {
  const standaloneApp = document.querySelector("body.periscope-standalone-page > .periscope-app");
  if (standaloneApp && !window.__PERISCOPE_SKIP_AUTOBOOT__) {
    const qParams = new URLSearchParams(window.location.search);
    const isIframe = qParams.get("iframe") === "1";
    mountPeriscopeStage(standaloneApp, { embedded: isIframe || qParams.get("embedded") === "1" }).then(async (ctrl) => {
      window.__PERISCOPE_CTRL__ = ctrl;
      if (isIframe) {
        const { attachHardenedIframeBridge } = await import("./periscope-element.js");
        const allowedOrigin = qParams.get("parentOrigin");
        attachHardenedIframeBridge(ctrl, {
          allowedOrigins: allowedOrigin ? [allowedOrigin] : [window.location.origin],
        });
      }
    });
  }
}
