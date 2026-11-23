---
name: periscope-crop-3d
description: >-
  End-to-end automated pipeline for building photorealistic, BBCH-animated 3D agricultural crops
  (wheat, corn, rapeseed, sunflower, soy, potato, sugar beet, etc.) in headless Blender 5.2 LTS
  and rendering them in Three.js 0.187.0 WebGPURenderer + TSL + AgX + HDRI for the Periscope web atlas.
  Use whenever adding a new crop species, upgrading botanical geometry/textures/lighting/animation,
  or auditing 3D assets for floating organs, mesh intersections, and WebGPU/WebGL2 readiness without manual Blender editing.
---

# Periscope Crop 3D Factory

Automated, zero-manual-Blender workflow for producing lightweight (`<= 4 MB`), smooth, photorealistic, 6-phase BBCH 3D crop specimens for the **Periscope** interactive web atlas.

## Non-Negotiable Visual & Architectural Invariants

1. **No 3D soil geometry:** Render only the clean 3D plant specimen on a transparent WebGL/WebGPU canvas over the 2D atmospheric sky/field/horizon/dark-subsoil backdrop.
2. **Static settled poses:** Leaves, stems, and roots animate **only during transitions between BBCH phases**. Never add continuous idle wind-sway loops.
3. **Zero floating organs & zero mesh clipping:** Every leaf, sheath, tiller, flower, pod, and lateral rootlet must be analytically socketed into its parent organ across all frames (`0..150`) and verified automatically via `BVHTree`.
4. **Organic variety (no "sticks"):** Every repeating organ uses per-seed multi-frequency 3D S-curves, natural axial twist, asymmetric branching, and proportional tapering.
5. **2026 Photorealistic Web Stack (Wave 2 Standard):** `Three.js 0.187.0` (`WebGPURenderer` with automatic `WebGL 2` fallback), `AgXToneMapping`, real CC0 outdoor farmland HDRI (`Poly Haven farm_field_1k.hdr` via `hdri_meta.json` + offline procedural `daylight_field.hdr` fallback), `PCFSoftShadowMap` (`2048x2048` desktop / `1024x1024` mobile), `THREE.RenderPipeline + SSAONode (depthAwareBlur, builtinAOContext, 4x MSAA, transparent alpha)`, `MeshSSSNodeMaterial` with `select(frontFacing, adaxial, abaxial)`, `COLOR_0` per-leaf variation, and uniform-branched `Fn/If` MaterialX TSL 3D phytopathology symptom overlays.

---

## Step-by-Step Workflow for Any New Crop

### Step 1: Select Botanical Archetype & Create Crop Passport
1. Read [Crop Archetypes Guide](./references/crop-archetypes-guide.md) to pick the right botanical blueprint (`root_crop`, `cereal_grass`, `tall_row_grass`, `broadleaf_oilseed`, `tuber_crop`) and BBCH timeline mapping (`frames 0, 30, 60, 90, 120, 150` at `24 fps` = `6.25 s`).
2. Copy [crop_passport_template.json](./resources/crop_passport_template.json) to `data/<crop_id>.json`, register it in `data/crops_index.json`, and populate:
   - 6 BBCH phases with agronomic `metrics`, optional `metric_defs`, and stage-specific `threats` (including `symptom` `{mode, target, radius, cam_offset}` for live GPU 3D disease/pest rendering and camera fly-to).
   - Well-separated 3D `anchor` points `[x, y, z]` in glTF Y-up space (keep anchors in the same phase at least `0.08` units apart so radar pins never collide).

### Step 2: Build Procedural PBR Textures & Headless Blender 5.2 Generator
1. Read [Blender 5.2 Pitfalls & Geometry QA](./references/blender-52-pitfalls-and-qa.md) **before writing any `bpy` code**.
2. Author or extend `blender/pbr_textures.py` (or `blender/textures_<crop_id>.py`):
   - Cache real CC0 farmland HDRI (`Poly Haven farm_field_1k.hdr` with MD5 check + `hdri_meta.json` sun direction + offline procedural fallback).
   - Generate 2K Voronoi/Worley bullate leaf maps (recessed veins, raised interveinal pillows, waxy cuticle roughness, 1K vascular thickness map) and anisotropic lenticel/groove-soil skin maps; always use C1-continuous `_smoothstep` (never boolean thresholds).
3. Author `blender/generate_<crop_id>.py`:
   - Track parent organ deformation (`bend_x`, `bend_y`, crown dome height, stalk elongation) analytically in every child organ's keyframes.
   - Add closed watertight caps on cylinders/stems, fleshy U-channeled petioles, tapered basal root/petiole plugs (`t < 0`), and standard glTF `COLOR_0` per-leaf chlorophyll + basal-AO vertex colors (`ShaderNodeVertexColor("Color")` + `export_vertex_color="ACTIVE"`, `export_vertex_color_name="Color"`, `export_draco_color_quantization=10`).
   - Embed the mandatory **4-invariant `BVHTree` + attachment audit** with `--full-audit` (31 slices, `0..150` step 5) exporting `assets/export_stats.json` (or `assets/<crop_id>_stats.json`).
   - Export `.glb` with `export_image_format="WEBP"` (`export_image_quality=95`) and `export_draco_mesh_compression_enable=True` (`level=6`) — zero external `toktx` dependency on Windows.

### Step 3: Wire & Verify the WebGPU + TSL Web Viewer (Multi-Crop Contract)
1. Read [WebGPU & Three.js 2026 Stack](./references/webgpu-threejs-2026-stack.md) for the exact `importmap`, `async initScene()`, `HDRLoader`, `AgXToneMapping`, `PCFSoftShadowMap`, `THREE.RenderPipeline + SSAONode (builtinAOContext, 4x MSAA)`, `select(frontFacing, ...)`, MaterialX `Fn/If` symptom shaders, bidirectional `AnimationMixer` scrubbing clamp, and `serve.py` MIME map.
2. Verify `web/index.html` maps BOTH `"three"` and `"three/webgpu"` to `three.webgpu.js` (prevents the Dual-Package Hazard) and ensure `assets/textures/farm_field_1k.hdr` (or `daylight_field.hdr`) is present on disk.
3. **Multi-Crop Viewer Integration Contract (`web/app.js` & `web/index.html`):**
   - Route crop selection dynamically via `data/crops_index.json` and `?crop=<crop_id>` (`URLSearchParams`), showing `#crop-select` automatically when 2+ `ready: true` crops exist.
   - Name exported Blender materials using standard Periscope PBR slot names (`Outer_Leaf_PBR`, `Mid_Leaf_PBR`, `Heart_Leaf_PBR`, `Taproot_PBR` — or extend `upgradeToPhotorealNodeMaterial` tier matching for `Blade_PBR` / `Stalk_PBR` / `Ear_PBR`) so **TSL translucency, `frontFacing` duality, edge senescence, and 3D symptom overlays** never silently fall back to `"other"`.
   - Support `metric_defs` in `data/<crop_id>.json` so non-root crops (wheat, corn, rapeseed) dynamically relabel the 3 maturation cards (`Белок` / `Кущение` / `Длина колоса`) instead of showing hardcoded `Сахаристость` / `Диаметр корня`.
4. Ensure `serve.py` serves `.glb`, `.wasm`, `.hdr`, `.webp`, and `.ktx2` with exact MIME types and `Cache-Control: no-store`.

### Step 4: Headless Build & Automated Pipeline Audit
Run Blender headless with strict exit-code propagation and 31-frame `--full-audit`, then execute the bundled audit gate:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python-exit-code 1 --python "e:\Videos\перископ\blender\generate_<crop_id>.py" -- --full-audit
python ".agents\skills\periscope-crop-3d\scripts\audit_crop_pipeline.py" --self-test
python ".agents\skills\periscope-crop-3d\scripts\audit_crop_pipeline.py" --crop <crop_id>
```

All checks in [audit_crop_pipeline.py](./scripts/audit_crop_pipeline.py) must exit `0`:
- `stats["crop_id"] == "<crop_id>"` and `model_url` `.glb` exists on disk
- `leaf_overlap_pairs == []`
- `leaf_blade_root_clipping == []`
- `floating_leaf_bases == []`
- `floating_rootlet_bases == []`
- `glb_bytes <= 4.2 MB` and 3D threat `anchor` points sit within `phase_bounds`

### Step 5: Closed-Loop Visual Verification ("Hollywood Dailies Loop")
1. Inspect EEVEE preview renders (`renders/phase_0.png` .. `phase_5.png`).
2. Open `http://127.0.0.1:8080/web/` in a real browser (or browser subagent) and verify:
   - `0` console/network errors, active `WebGPURenderer` (or clean `WebGL 2` fallback), smooth 60 FPS.
   - Transition frames (`40`, `58`, `77`) + full maturity (`150`) + macro close-ups of stem collar, leaf junctions, and lower rootlets.
   - Bidirectional scrubbing (backward from final frame to frame `0`) without locked clips or detached pins.
   - Visual look-dev check against real macro photography of the species (soft shadows, natural `AgX` greens, backlit translucency, organic silhouette variation).
3. Iterate parameters in Blender/TSL until all visual defects disappear.

---

## Quick Error-Prevention Reference

| Symptom | Root Cause | Prevented By |
| :--- | :--- | :--- |
| Leaves/roots float in mid-air on intermediate frames | Hardcoded world `Z` or missing parent `bend_x/bend_y` | Analytical collar/bend helper + milestone keyframes |
| Hollow open stem tube during seedling transition | Open-ended BMesh cylinder | Domed top/bottom triangle-fan caps |
| Leaves look like stiff identical sticks | Linear `x = t*L`, uniform arch, zero twist | Per-seed 3D S-curve, lateral sweep, twist & `Curve Unfurling` |
| Giant identical rootlets at tail tip | Constant `r_start` and `length` along root | Taper `r_start` & `length` proportionally with `base_r` |
| Blocky cliff islands on skin normal map | Boolean mask (`n > 0.45`) + aggressive normal strength | `_smoothstep` masks + `normal_strength <= 0.65` + `WebP q=95` |
| Dark mature shadows on young seedlings | Global static `Cycles AO` baked at frame 150 on shared UVs | Local cavity micro-AO only + dynamic `PCFSoftShadowMap` / `GTAONode` |
| `GLTFLoader` / `OrbitControls` crash on Three.js `0.187` | Dual `THREE` instances (`three.module.js` + `three.webgpu.js`) | Map both `"three"` and `"three/webgpu"` to `three.webgpu.js` |
| Backward timeline scrub freezes animations | `LoopOnce` clamps and stops when reaching clip end | Keep `action.enabled = true`, clamp `time <= clipDur - 1e-5` |
| Blender script fails silently with exit code `0` | Default Blender CLI ignores Python exceptions | Always pass `--python-exit-code 1` |
| `KTX2` CLI build fails on Windows | `toktx`/`ktx` C++ binaries absent on host | Default to Blender native `EXT_texture_webp (q=95)` + `Draco` |
