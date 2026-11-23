# Blender 5.2 LTS Pitfalls, Botanical Geometry Rules & QA Invariants

Battle-tested rules distilled from production builds of the Periscope 3D crop pipeline on **Windows + Blender 5.2.2 LTS**.

---

## 1. Blender 5.2 LTS API Breaking Changes (Mandatory Patterns)

1. **EEVEE Engine Identifier:**
   - Use `scene.render.engine = "BLENDER_EEVEE"` (do **NOT** use `"BLENDER_EEVEE_NEXT"` — removed/renamed in 5.2).
2. **Slotted Actions / F-Curves Smoothing (`Action.fcurves` removed in Blender 5.2):**
   - Never access `action.fcurves` directly. Use the Blender 5.2 channelbag API:
     ```python
     def smooth_datablock_fcurves(datablock: bpy.types.ID) -> None:
         ad = getattr(datablock, "animation_data", None)
         if not ad or not ad.action:
             return
         act = ad.action
         slot = ad.action_slot
         if not hasattr(act, "layers") or not act.layers or slot is None:
             return
         for layer in act.layers:
             for strip in layer.strips:
                 cb = strip.channelbag(slot)
                 if cb is None:
                     continue
                 for fc in cb.fcurves:
                     for kp in fc.keyframe_points:
                         kp.interpolation = "BEZIER"
                         kp.handle_left_type = "AUTO_CLAMPED"
                         kp.handle_right_type = "AUTO_CLAMPED"
     ```
3. **`ShaderNodeMix` (`data_type = "RGBA"`) Duplicate Socket Names:**
   - `ShaderNodeMix` exposes multiple `"A"`, `"B"`, and `"Result"` sockets across Float/Vector/RGBA. Indexing by name picks the wrong socket!
   - Always select by socket type:
     ```python
     rgba_in = [s for s in tint_mix.inputs if s.type == "RGBA"]
     rgba_out = [s for s in tint_mix.outputs if s.type == "RGBA"][0]
     ```
4. **CLI Exit Code & Windows UTF-8 Safety:**
   - Always invoke Blender with `--background --python-exit-code 1` so tracebacks fail automation cleanly.
   - Always pass `encoding="utf-8"` in `Path.read_text()` / `Path.write_text()` (prevents Windows `cp1251` crashes on Cyrillic metadata).
   - Resolve paths via `Path(__file__).resolve().parent`, never CWD assumptions.

---

## 2. Botanical Geometry & Attachment Engineering (Anti-Floating / Anti-Clip)

### A. Analytical Parent Tracking (Never Hardcode Floating World Z)
- Extract parent keyframe tables (`TAPROOT_KEYFRAMES`, `STALK_KEYFRAMES`) to module constants and provide an evaluator `evaluate_parent_transform(frame)` using smoothstep/cubic interpolation.
- Compute every child organ's socket coordinates dynamically from the parent's current surface at every milestone frame (`0, f_start, f_mid, f_full, 45, 58, 75, 90, 120, 150`).
- During seedling-to-vegetative transitions (e.g., hypocotyl shrinking into a swelling root crown, or coleoptile transitioning to tillering node), smoothly migrate early true-leaf buds from the narrow central shoot apex (`r ~ 0.004-0.006`) outward onto the expanding collar/node.

### B. Watertight Caps & Basal Organ Plugs
- **Stems / Hypocotyls / Culms:** Always close top and bottom cylinder rings with domed triangle fans (`top_cap`, `bot_cap`) so camera orbits never reveal a hollow tube.
- **Petioles / Leaf Sheaths / Branches:** Start parametric length `t` slightly negative (`t = -0.055`, `-0.025`, then `0.0..1.0`) tapering into a closed basal plug embedded `6-14 mm` inside the parent crown/node. Macro close-ups will show seamless biological emergence with `0 mm` air gap.
- **Crowns & Collars:** Use smooth spheroidal dome profiles (`rings >= 72` clustered toward the top via `s = (r_i / rings) ** 1.28`) instead of sharp linear cones.

### C. Organic Variation & Hollywood Growth Feel (No "Sticks")
- **Individual per-organ variation (`seed`):** Vary length, width, elevation pitch, radial offset, axial roll/twist, lateral sweep (`S`-bend in local `Y`), asymmetric blade margin waves, and gentle gravity arch per organ.
- **Curve Unfurling (`Folded` Shape Key):** Roll/cup young leaves inward along their midrib (`fold_amt = 1.0`) while emerging near-vertically (`pitch_closed`), then unfurl smoothly (`fold_amt -> 0.0`) as `age` progresses.
- **Maturation Morph (`MatureCurl` Shape Key + Material Shift):** Age outer/older leaves gently (subtle edge curl, slight roughness rise, warm ochre/yellowing tint) without letting them droop into the root/stem body.
- **No Idle Wind Sway:** Never animate oscillating rotation loops once a phase is reached.

### D. Root System & Fibrous Rootlet Rules
- **Include Parent Bend:** If the main taproot/rhizome bends by `(bend_x(s), bend_y(s))`, **every lateral rootlet** anchored at `s_pos` MUST add `(bend_x(s_pos), bend_y(s_pos))` to its `(ax, ay)` origin!
- **Recess Behind Surface Grooves:** If surface grooves indent radius to `0.825 * base_r`, anchor rootlets at `r_anchor <= 0.68 * base_r` so roots never detach even on tight curves.
- **Proportional Tail Tapering:** Scale both `r_start` and `length` down toward the tail tip (`s_pos -> 1.0`):
  - Example (*Beta vulgaris*): `r_start` tapers `0.0038 -> 0.0016` (`r_end = 0.0005`), `length` tapers `0.07-0.12 m` mid-root down to `0.025-0.055 m` at tail tip, with unique multi-frequency 3D organic curves and `2-3` fine asymmetric capillary sub-forks.

---

## 3. PBR Textures, Baking & Export Pitfalls

1. **No Boolean Cliffs in Normal/Height Maps:**
   - Never multiply height fields by boolean arrays like `(n_micro > 0.45)`. Hard `0/1` steps turn into ugly faceted craters in tangent-space normal maps. Always use `_smoothstep(np.clip((val - low) / span, 0.0, 1.0))`.
2. **Normal Strength Calibration:**
   - Smooth root/stem/fruit skins: `normal_strength = 0.55..0.65` and gentle height derivative (`strength = 1.5..1.8`).
   - Veined foliage: `normal_strength = 0.90..1.15` with distinct midrib + arcuate lateral veins + fine reticulate venation.
3. **Avoid Static Global `Cycles AO` on Shared-UV Animated Foliage:**
   - When multiple leaves share `[0..1]` `UVMap` and grow from frame `0` to `150`, baking global scene AO at frame `150` overwrites UV islands AND leaves fake dark shadows from nonexistent leaves on early seedling frames!
   - Bake only **local cavity micro-AO** (vein troughs, sugar grooves) and **Thickness maps** (for SSS), letting dynamic `PCFSoftShadowMap` + `GTAONode` handle inter-leaf occlusion at every BBCH frame.
4. **Zero-Dependency Compact Export:**
   - Export GLB with `export_image_format="WEBP"`, `export_image_quality=94..95` (`EXT_texture_webp`), `export_draco_mesh_compression_enable=True`, `export_draco_mesh_compression_level=6`, `export_morph=True`, `export_morph_normal=True`, `export_morph_animation=True`.
   - Keep `glb_bytes <= 4.2 MB` even with 2K textures. (`KTX2` via `toktx` is optional when `KhronosGroup.KTX-Software` is installed.)

---

## 4. Mandatory 4-Invariant Automated QA Gate (`export_stats.json`)

Every crop generator script MUST compute and serialize these 4 lists before exiting:

| Key in `export_stats.json` | Frames Audited | Exact Pass Condition |
| :--- | :--- | :--- |
| `leaf_overlap_pairs` | `60, 90, 120, 150` | `[]` — zero `BVHTree` intersections between external leaf meshes (`local_x >= 0.015`) |
| `leaf_blade_root_clipping` | `60, 90, 120, 150` | `[]` — zero `BVHTree` intersections between leaf blades/outer petioles (`local_x >= 0.060`) and parent root/stem |
| `floating_leaf_bases` | `40, 60, 77, 90, 120, 150` | `[]` — every active leaf basal plug (`vert 0`) stays within `<= collar_z + 0.004` |
| `floating_rootlet_bases` | `60, 90, 120, 150` | `[]` — every active lateral rootlet base stays inside `<= base_r(s) * 0.80` measured from parent `(bend_x, bend_y)` |

Also record `phase_bounds` (`gltf_min`, `gltf_max` converted from Blender Z-up to glTF Y-up: `[x, z, -y]`) to validate threat anchor coordinates in `data/<crop_id>.json`.
