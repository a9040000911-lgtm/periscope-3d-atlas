# WebGPU & Three.js 2026 Photorealistic Web Stack (Verified Nov 2026)

Production web-rendering blueprint for the Periscope 3D atlas using **`Three.js 0.187.0` (`r187`)** with **`WebGPURenderer`** (automatic zero-config fallback to `WebGL 2`) and **`TSL` (Three.js Shading Language)**.

---

## 1. Engine Decision (Why Three.js `0.187.0` WebGPU + TSL)

- **WebGPU is Baseline in 2026** across Chrome, Edge, Safari (macOS/iOS), and Firefox; `WebGPURenderer` falls back transparently to `WebGL 2` on older GPUs.
- **Keep Three.js (upgrade `0.170` -> `0.187.0`):** Smallest bundle, full TSL shader control for botanical translucency, native `AgXToneMapping`, `HDRLoader` / `UltraHDRLoader`, built-in `MeshPhysicalNodeMaterial` / `MeshSSSNodeMaterial`, and `GTAONode`.
- **Avoid for Periscope:** Unity WebGL/WASM (`20-100+ MB` startup), raw 4D Gaussian Splatting (`.SPZ` — hundreds of MB in 4D, lacks clean organ topology for arbitrary BBCH scrubbing and 3D pest anchors).

---

## 2. Exact `importmap` (Prevents Dual-Package Hazard)

Never mix `three.module.js` and `three.webgpu.js` in the same page — doing so instantiates two copies of `THREE` core classes and breaks `GLTFLoader` / `OrbitControls`. Map **both** `"three"` and `"three/webgpu"` to `three.webgpu.js` (which shares `./three.core.js` with `three.tsl.js`):

```html
<script type="importmap">
  {
    "imports": {
      "three": "https://cdn.jsdelivr.net/npm/three@0.187.0/build/three.webgpu.js",
      "three/webgpu": "https://cdn.jsdelivr.net/npm/three@0.187.0/build/three.webgpu.js",
      "three/tsl": "https://cdn.jsdelivr.net/npm/three@0.187.0/build/three.tsl.js",
      "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.187.0/examples/jsm/"
    }
  }
</script>
```

Note on Three.js `0.187.0` loader naming:
- Use `HDRLoader` from `three/addons/loaders/HDRLoader.js` (replaces legacy `RGBELoader`).
- Use `UltraHDRLoader` from `three/addons/loaders/UltraHDRLoader.js` for compact `.jpg` gainmap HDRIs.
- Use `DRACOLoader` decoder path matching the exact version: `https://cdn.jsdelivr.net/npm/three@0.187.0/examples/jsm/libs/draco/gltf/`.

---

## 3. Async Renderer Initialization, Lighting & Soft Shadows

`WebGPURenderer` **must** finish `await renderer.init()` before creating environment maps or rendering frames:

```javascript
async function initScene() {
  renderer = new THREE.WebGPURenderer({ canvas, antialias: true, alpha: true });
  await renderer.init();
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.AgXToneMapping; // Prevents neon-plastic green clipping
  renderer.toneMappingExposure = 1.12;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  scene = new THREE.Scene();

  // Real outdoor sky/field HDRI (NOT synthetic white RoomEnvironment)
  const hdrTex = await new HDRLoader().loadAsync("../assets/textures/daylight_field.hdr");
  hdrTex.mapping = THREE.EquirectangularReflectionMapping;
  scene.environment = hdrTex;
  scene.environmentIntensity = 0.85;

  // Outdoor sunlight with tight shadow frustum around crop bounds
  const hemi = new THREE.HemisphereLight(0xdff0ff, 0x3b2c1e, 0.55);
  const keyLight = new THREE.DirectionalLight(0xfff5e4, 2.35);
  keyLight.position.set(2.2, 3.4, 2.8);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(2048, 2048);
  keyLight.shadow.camera.near = 0.4;
  keyLight.shadow.camera.far = 9.0;
  const d = 1.15;
  Object.assign(keyLight.shadow.camera, { left: -d, right: d, top: d, bottom: -d });
  keyLight.shadow.bias = -0.0003;
  keyLight.shadow.normalBias = 0.018;
  keyLight.shadow.radius = 2.5;
  scene.add(hemi, keyLight);
}
```

- Set `obj.castShadow = true; obj.receiveShadow = true;` on all plant meshes during `gltf.scene.traverse(...)`.
- Optional dynamic screen-space occlusion: `GTAONode` (`three/addons/tsl/display/GTAONode.js`) via `PostProcessing` for real-time crevice shadowing across every BBCH growth frame without static AO baking bugs.

---

## 4. Photorealistic Botanical Materials & TSL Translucency

Blender's `Subsurface Weight` does **not** carry over cleanly to standard glTF materials in the browser. Upgrade loaded glTF materials on load into `THREE.MeshPhysicalNodeMaterial` (or native `THREE.MeshSSSNodeMaterial` in `0.187.0`) while preserving `.map`, `.normalMap`, `.roughnessMap`, `.side`, and Morph Targets:

- **Foliage (`outer`, `mid`, `heart`):**
  - Subtle waxy cuticle: `clearcoat = 0.12..0.16`, `clearcoatRoughness = 0.40..0.45`, `sheen = 0.20..0.25`, `sheenColor = 0xc5e86c`.
  - Thin-sheet TSL back-scatter translucency (`emissiveNode`): combine view-to-backlight forward scatter, inverted-normal thin-lamina sun transmission, and soft grazing rim warmth modulated by the leaf's base texture (`baseTex.rgb * chloroTint`) and (when available) a `Thickness` mask so thick midribs/petioles block light while thin blades glow naturally.
- **Root / Tuber / Stalk Skin:**
  - Low clearcoat (`0.05-0.08`, high roughness `0.55-0.68`) + soft matte sheen (`0.08-0.12`) to prevent wet-plastic reflections.
- **Multi-Crop Material Slot Contract:**
  - `web/app.js` currently assigns TSL translucency and maturation color interpolation by material name (`Outer_Leaf_PBR`, `Mid_Leaf_PBR`, `Heart_Leaf_PBR`, `Taproot_PBR`). When adding new crops (wheat, corn, rapeseed, potato), **either reuse these 4 canonical material slot names** for lower/mid/upper foliage & root/culm/tuber, **or** extend `upgradeToPhotorealNodeMaterial()` to match suffix/prefix conventions (`*_Leaf_PBR`, `*_Blade_PBR`, `*_Ear_PBR`, `*_Root_PBR`, `*_Tuber_PBR`) so new crops never fall through to `tier = "other"`.
- **Multi-Crop Routing & Dynamic Metric Labels:**
  - Resolve active crop via `const cropId = new URLSearchParams(window.location.search).get("crop") || "sugar_beet"`, loading `../data/${cropId}.json` and `../assets/${cropId}_stats.json` (falling back to `../assets/export_stats.json` only when `stats.crop_id === cropId`).
  - Render `.metric-label` names dynamically from `crop.metric_defs` when present so cereals/oilseeds show species-accurate agronomic indicators (`Белок`, `Продуктивных стеблей`, `Зёрен в колосе`) while preserving backward compatibility with `sugar_beet.json`.

---

## 5. Bidirectional `AnimationMixer` Scrubbing (Critical Anti-Lock Rule)

Blender exports per-object clips (often 30-50 clips per crop). To guarantee smooth scrubbing **both forward and backward** from the final frame:

```javascript
for (const action of actions) {
  const clipDur = action.getClip().duration || state.durationSec;
  action.enabled = true;
  action.paused = true;
  action.time = Math.max(0, Math.min(state.currentTime, Math.max(0, clipDur - 1e-5)));
}
mixer.update(0);
```

Never let `action.time` hit `clipDur` exactly without `action.enabled = true` — `LoopOnce` + `clampWhenFinished` disables finished actions on backward rewind otherwise.

---

## 6. Local Dev Server (`serve.py`) & UI Standards

- **Mandatory MIME Types in `serve.py`:**
  - `.glb`: `model/gltf-binary`
  - `.gltf`: `model/gltf+json`
  - `.wasm`: `application/wasm` (required for `WebAssembly.instantiateStreaming` on Windows)
  - `.hdr`: `image/vnd.radiance`
  - `.webp`: `image/webp`
  - `.ktx2`: `image/ktx2`
  - Plus `Cache-Control: no-store` so model/HDRI rebuilds show immediately.
- **Slider & Responsive Framing:**
  - Use thumb-only `:focus-visible` ring on `<input type="range">` (avoid boxy outline around the whole dock).
  - Frame `CAMERA_PRESETS.overview` so the lowest root tip stays comfortably above `.timeline-dock` and highest canopy tips stay below `.stage-controls-top`.
  - Sync 2D horizon CSS variable `--soil-line-y` dynamically with projected world `y = 0` (`root collar` line).

---

## 7. Live 2026 Visual Benchmarks for Look-Dev Comparison

Compare browser renders side-by-side against real macro photos of the crop and these live web standards:
- [Khronos glTF Sample Viewer](https://github.khronos.org/glTF-Sample-Viewer-Release/) — reference PBR / HDRI / tone-mapping calibration
- [Lusion](https://www.lusion.co) (`labs.lusion.co`) — studio lighting & Three.js look-dev
- [Igloo Inc.](https://www.igloo.inc) — high-FPS procedural surface realism
- [Bruno Simon](https://bruno-simon.com) — Blender -> Three.js / WebGPU + TSL integration
- [Active Theory](https://www.activetheory.net), [webgpu.com](https://www.webgpu.com), [threejsresources.com](https://threejsresources.com) — modern WebGPU/TSL showcases
