"""High-Detail Plant-Only Lentil (Lens culinaris Medik.) PBR & BBCH Generator for Blender 5.2 LTS.

Generates a museum-grade 360-degree rotatable legume specimen without 3D soil geometry:
- Flat biconvex marbled lentil seed staying underground (true hypogeal germination, Shape Key 'Split')
- Slender fibrous legume taproot + 18 sinuous branched lateral rootlets (anchored inside taproot)
- 22 coralloid / bilobed pinkish-coral Rhizobium nitrogen-fixing root nodules with constricted necks
- Acropetally growing 4-ribbed main stem with anatomical nodal pulvini + 3 seamless tapered side branches
- 20 high-res compound even-pinnate leaves (twin lanceolate stipules + arched rachis + 7x4 cupped
  mucronate leaflets with petiolules + 18-segment coiled helical apical tendrils) with COLOR_0 and
  3-stage unfurling Shape Keys
- 14 two-material axillary white-lilac papilionaceous butterfly flowers (5-toothed green calyx cup +
  notched bilobed banner + wings + keel, Bud -> Open Shape Key)
- 14 two-material flat rhomboid 2-seeded lentil pods (10-segment arched green peduncle + 5-pointed
  persistent green calyx star + parchment valves with YoungFlat -> Plump2Seed filling Shape Key)
Exports a compact WebP-textured animated GLB, runs exhaustive 10-invariant 31-frame BVH QA, and renders 6 previews.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree

BLENDER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BLENDER_DIR.parent
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

from pbr_textures import PBRTextureSet  # noqa: E402
from textures_lentil import generate_all_lentil_textures  # noqa: E402

ASSETS_DIR = PROJECT_ROOT / "assets"
RENDERS_DIR = PROJECT_ROOT / "renders"

FPS = 24
FRAME_START = 0
FRAME_END = 150
PHASE_FRAMES = [0, 30, 60, 90, 120, 150]


def ensure_dirs() -> None:
    """Create output asset and render directories if missing."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)


def clear_scene() -> None:
    """Reset the Blender scene and purge orphan datablocks."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for collection_attr in (
        "objects",
        "meshes",
        "materials",
        "lights",
        "cameras",
        "actions",
        "images",
    ):
        coll = getattr(bpy.data, collection_attr)
        for item in list(coll):
            coll.remove(item)


def lerp(a: float, b: float, t: float) -> float:
    """Linearly interpolate between a and b for t clamped to [0, 1]."""
    t = max(0.0, min(1.0, t))
    return a + (b - a) * t


def smoothstep(t: float) -> float:
    """Cubic Hermite smoothstep on [0, 1]."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def hex_rgba(hex_str: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """Convert #RRGGBB hex string to linear Blender RGBA tuple."""
    s = hex_str.lstrip("#")
    sr = int(s[0:2], 16) / 255.0
    sg = int(s[2:4], 16) / 255.0
    sb = int(s[4:6], 16) / 255.0

    def srgb_to_lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (srgb_to_lin(sr), srgb_to_lin(sg), srgb_to_lin(sb), alpha)


def make_pbr_material(
    name: str,
    tex_set: PBRTextureSet,
    tint_hex: str = "#ffffff",
    roughness_factor: float = 1.0,
    normal_strength: float = 1.0,
    subsurface: float = 0.0,
    double_sided: bool = False,
    specular: float = 0.35,
    use_vertex_color: bool = False,
) -> tuple[
    bpy.types.Material,
    bpy.types.ShaderNodeMix,
    bpy.types.ShaderNodeMath,
    bpy.types.ShaderNodeBsdfPrincipled,
]:
    """Build a glTF-compatible PBR material with Albedo*(VertexColor)*Tint, NormalMap, Roughness."""
    mat = bpy.data.materials.new(name=name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (520, 0)

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (220, 0)
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = specular
    if subsurface > 0.0 and "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = subsurface
        if "Subsurface Scale" in bsdf.inputs:
            bsdf.inputs["Subsurface Scale"].default_value = 0.016

    uv_node = nt.nodes.new("ShaderNodeUVMap")
    uv_node.location = (-780, 0)
    uv_node.uv_map = "UVMap"

    tex_col = nt.nodes.new("ShaderNodeTexImage")
    tex_col.location = (-480, 240)
    tex_col.image = tex_set["albedo"]
    nt.links.new(uv_node.outputs["UV"], tex_col.inputs["Vector"])

    color_source_socket = tex_col.outputs["Color"]
    if use_vertex_color:
        vcol_node = nt.nodes.new("ShaderNodeVertexColor")
        vcol_node.layer_name = "Color"
        vcol_node.location = (-480, 440)
        vcol_mix = nt.nodes.new("ShaderNodeMix")
        vcol_mix.data_type = "RGBA"
        vcol_mix.blend_type = "MULTIPLY"
        vcol_mix.location = (-250, 320)
        vcol_mix.inputs[0].default_value = 1.0
        vc_in = [s for s in vcol_mix.inputs if s.type == "RGBA"]
        vc_out = [s for s in vcol_mix.outputs if s.type == "RGBA"][0]
        nt.links.new(tex_col.outputs["Color"], vc_in[0])
        nt.links.new(vcol_node.outputs["Color"], vc_in[1])
        color_source_socket = vc_out

    tint_mix = nt.nodes.new("ShaderNodeMix")
    tint_mix.data_type = "RGBA"
    tint_mix.blend_type = "MULTIPLY"
    tint_mix.location = (-40, 240)
    tint_mix.inputs[0].default_value = 1.0
    rgba_in = [s for s in tint_mix.inputs if s.type == "RGBA"]
    rgba_out = [s for s in tint_mix.outputs if s.type == "RGBA"][0]
    rgba_in[1].default_value = hex_rgba(tint_hex)
    nt.links.new(color_source_socket, rgba_in[0])
    nt.links.new(rgba_out, bsdf.inputs["Base Color"])

    tex_rough = nt.nodes.new("ShaderNodeTexImage")
    tex_rough.location = (-380, -40)
    tex_rough.image = tex_set["roughness"]
    nt.links.new(uv_node.outputs["UV"], tex_rough.inputs["Vector"])

    rough_mul = nt.nodes.new("ShaderNodeMath")
    rough_mul.operation = "MULTIPLY"
    rough_mul.use_clamp = True
    rough_mul.location = (-70, -40)
    rough_mul.inputs[1].default_value = roughness_factor
    nt.links.new(tex_rough.outputs["Color"], rough_mul.inputs[0])
    nt.links.new(rough_mul.outputs["Value"], bsdf.inputs["Roughness"])

    tex_nrm = nt.nodes.new("ShaderNodeTexImage")
    tex_nrm.location = (-380, -320)
    tex_nrm.image = tex_set["normal"]
    nt.links.new(uv_node.outputs["UV"], tex_nrm.inputs["Vector"])

    nrm_map = nt.nodes.new("ShaderNodeNormalMap")
    nrm_map.location = (-70, -320)
    nrm_map.space = "TANGENT"
    nrm_map.uv_map = "UVMap"
    nrm_map.inputs["Strength"].default_value = normal_strength
    nt.links.new(tex_nrm.outputs["Color"], nrm_map.inputs["Color"])
    nt.links.new(nrm_map.outputs["Normal"], bsdf.inputs["Normal"])

    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.use_backface_culling = not double_sided
    return mat, tint_mix, rough_mul, bsdf


def link_object(
    name: str,
    mesh: bpy.types.Mesh,
    materials: bpy.types.Material | list[bpy.types.Material],
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> bpy.types.Object:
    """Create object, assign one or more materials, link to scene collection, return object."""
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler = Euler(rotation, "XYZ")
    obj.scale = scale
    mat_list = materials if isinstance(materials, list) else [materials]
    mesh.materials.clear()
    for m in mat_list:
        mesh.materials.append(m)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def set_smooth_shading(mesh: bpy.types.Mesh, smooth: bool = True) -> None:
    """Set polygon smooth shading cleanly without bpy.ops."""
    for poly in mesh.polygons:
        poly.use_smooth = smooth


def smooth_datablock_fcurves(datablock: bpy.types.ID, linear: bool = False) -> None:
    """Apply BEZIER AUTO_CLAMPED (or LINEAR) handles using Blender 5.2 channelbag API."""
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
                    if linear:
                        kp.interpolation = "LINEAR"
                    else:
                        kp.interpolation = "BEZIER"
                        kp.handle_left_type = "AUTO_CLAMPED"
                        kp.handle_right_type = "AUTO_CLAMPED"


def keyframe_transform(
    obj: bpy.types.Object,
    frame: int,
    scale: tuple[float, float, float] | None = None,
    location: tuple[float, float, float] | None = None,
    rotation: tuple[float, float, float] | None = None,
) -> None:
    """Insert keyframes on specified transform channels at the given frame."""
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)
    if location is not None:
        obj.location = location
        obj.keyframe_insert(data_path="location", frame=frame)
    if rotation is not None:
        obj.rotation_euler = Euler(rotation, "XYZ")
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def ensure_uv_layer(bm: bmesh.types.BMesh) -> bmesh.types.BMLayerItem:
    """Get or create default UVMap layer on BMesh."""
    return bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")


def apply_vertex_colors(
    mesh: bpy.types.Mesh,
    seed: int,
    mode: str = "leaf",
) -> None:
    """Bake standard glTF COLOR_0 natural chlorophyll variation + subtle basal micro-AO."""
    color_attr = mesh.color_attributes.get("Color")
    if color_attr is None:
        color_attr = mesh.color_attributes.new(name="Color", type="BYTE_COLOR", domain="CORNER")
    uv_layer = mesh.uv_layers.get("UVMap")

    h1 = math.sin(seed * 19.137 + 0.7) * 43758.5453
    r1 = h1 - math.floor(h1)
    h2 = math.sin(seed * 47.821 + 2.3) * 28411.317
    r2 = h2 - math.floor(h2)
    h3 = math.sin(seed * 83.413 + 4.1) * 19283.711
    r3 = h3 - math.floor(h3)

    if mode == "stem":
        tint_r, tint_g, tint_b = 0.94, 0.99, 0.92
    elif mode == "neutral_with_stem_slot":
        tint_r, tint_g, tint_b = 0.95, 0.99, 0.92
    else:
        tint_r = lerp(0.91, 1.07, r1)
        tint_g = lerp(0.94, 1.06, r2)
        tint_b = lerp(0.89, 1.05, r3)

    for poly in mesh.polygons:
        is_primary_non_stem = (mode == "neutral_with_stem_slot") and (poly.material_index == 0)
        for loop_idx in poly.loop_indices:
            if is_primary_non_stem:
                color_attr.data[loop_idx].color = (1.0, 1.0, 1.0, 1.0)
                continue
            v_coord = uv_layer.data[loop_idx].uv[1] if uv_layer is not None else 0.5
            ao = lerp(0.82, 1.0, min(1.0, max(0.0, v_coord / 0.22))) if mode == "leaf" else lerp(0.88, 1.0, v_coord)
            cr = min(1.0, max(0.0, tint_r * ao))
            cg = min(1.0, max(0.0, tint_g * ao))
            cb = min(1.0, max(0.0, tint_b * ao))
            color_attr.data[loop_idx].color = (cr, cg, cb, 1.0)


def _add_tube_along_points(
    bm: bmesh.types.BMesh,
    uv_layer: bmesh.types.BMLayerItem,
    pts: list[Vector],
    radii: list[float],
    rad_segs: int = 8,
    rib_amp: float = 0.0,
    rib_freq: int = 4,
    uv_u_range: tuple[float, float] = (0.44, 0.56),
    cap_start: bool = True,
    cap_end: bool = True,
    mat_index: int = 0,
) -> list[list[bmesh.types.BMVert]]:
    """Sweep a smooth (optionally ribbed) closed tube along 3D polyline pts with parallel transport."""
    rings: list[list[bmesh.types.BMVert]] = []
    n_pts = len(pts)
    prev_n = Vector((1.0, 0.0, 0.0))

    for i, p in enumerate(pts):
        if i == 0:
            t_vec = (pts[1] - pts[0]).normalized()
        elif i == n_pts - 1:
            t_vec = (pts[-1] - pts[-2]).normalized()
        else:
            t_vec = (pts[i + 1] - pts[i - 1]).normalized()
        if t_vec.length < 1e-6:
            t_vec = Vector((0.0, 0.0, 1.0))

        n_vec = prev_n - t_vec * prev_n.dot(t_vec)
        if n_vec.length < 1e-4:
            ref = Vector((0.0, 1.0, 0.0)) if abs(t_vec.x) > 0.8 else Vector((1.0, 0.0, 0.0))
            n_vec = t_vec.cross(ref).normalized()
        else:
            n_vec.normalize()
        b_vec = t_vec.cross(n_vec).normalized()
        prev_n = n_vec

        r_base = radii[i]
        row: list[bmesh.types.BMVert] = []
        for ai in range(rad_segs):
            ang = 2.0 * math.pi * (ai / rad_segs)
            r = r_base * (1.0 + rib_amp * math.cos(rib_freq * ang))
            co = p + (n_vec * math.cos(ang) + b_vec * math.sin(ang)) * r
            row.append(bm.verts.new(co))
        rings.append(row)

    u_lo, u_hi = uv_u_range
    for i in range(n_pts - 1):
        v0 = i / max(1, n_pts - 1)
        v1 = (i + 1) / max(1, n_pts - 1)
        for ai in range(rad_segs):
            ai_n = (ai + 1) % rad_segs
            u0 = lerp(u_lo, u_hi, ai / rad_segs)
            u1 = lerp(u_lo, u_hi, (ai + 1) / rad_segs)
            f = bm.faces.new((rings[i][ai], rings[i][ai_n], rings[i + 1][ai_n], rings[i + 1][ai]))
            f.material_index = mat_index
            for l, uv in zip(f.loops, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]):
                l[uv_layer].uv = uv

    if cap_start and n_pts >= 2:
        t0 = (pts[1] - pts[0]).normalized()
        c0 = bm.verts.new(pts[0] - t0 * (radii[0] * 0.45))
        for ai in range(rad_segs):
            ai_n = (ai + 1) % rad_segs
            f = bm.faces.new((rings[0][ai_n], rings[0][ai], c0))
            f.material_index = mat_index
            for l in f.loops:
                l[uv_layer].uv = ((u_lo + u_hi) * 0.5, 0.0)

    if cap_end and n_pts >= 2:
        t1 = (pts[-1] - pts[-2]).normalized()
        c1 = bm.verts.new(pts[-1] + t1 * (radii[-1] * 0.55))
        for ai in range(rad_segs):
            ai_n = (ai + 1) % rad_segs
            f = bm.faces.new((rings[-1][ai], rings[-1][ai_n], c1))
            f.material_index = mat_index
            for l in f.loops:
                l[uv_layer].uv = ((u_lo + u_hi) * 0.5, 1.0)

    return rings


# =============================================================================
# 1. HYPOGEAL LENS SEED
# =============================================================================
def build_lentil_seed(mat_seed: bpy.types.Material) -> bpy.types.Object:
    """Create classic biconvex flat marbled lentil seed staying underground (f0..f56)."""
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=0.052)

    for v in bm.verts:
        r_xy = math.hypot(v.co.x, v.co.y) / 0.052
        z_norm = v.co.z / 0.052
        v.co.x *= 1.08
        v.co.y *= 1.02
        # Crisp biconvex optical lens profile with subtle equatorial bevel
        lens_z = math.copysign(abs(z_norm) ** 0.85, z_norm) * 0.0245 * (1.0 - 0.16 * (r_xy ** 2))
        v.co.z = lens_z

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        for l in f.loops:
            co = l.vert.co
            u = 0.5 + math.atan2(co.y, co.x) / (2.0 * math.pi)
            v_uv = 0.5 + co.z / 0.055
            l[uv_layer].uv = (u, v_uv)

    mesh = bpy.data.meshes.new("Seed_Lentil_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    set_smooth_shading(mesh, True)

    rot_seed = (math.radians(52.0), math.radians(18.0), math.radians(24.0))
    seed_obj = link_object("Seed_Lentil", mesh, mat_seed, location=(0.0, 0.0, -0.14), rotation=rot_seed)

    seed_obj.shape_key_add(name="Basis", from_mix=False)
    sk_split = seed_obj.shape_key_add(name="Split", from_mix=False)
    for i, v in enumerate(mesh.vertices):
        co = v.co.copy()
        co *= 1.15
        if co.y < -0.01:
            gap = 0.011 * ((-co.y - 0.01) / 0.045)
            co.z += gap if co.z >= 0.0 else -gap
        sk_split.data[i].co = co

    sk_split.value = 0.0
    sk_split.keyframe_insert(data_path="value", frame=0)
    sk_split.value = 0.92
    sk_split.keyframe_insert(data_path="value", frame=16)
    sk_split.value = 1.0
    sk_split.keyframe_insert(data_path="value", frame=42)
    smooth_datablock_fcurves(mesh.shape_keys)

    # Hypogeal germination: seed stays underground snugly against the root-shoot axis (f0..f44)
    keyframe_transform(seed_obj, 0, scale=(1.0, 1.0, 1.0), location=(0.0, 0.0, -0.14))
    keyframe_transform(seed_obj, 14, scale=(1.06, 1.06, 1.08), location=(0.020, -0.008, -0.135))
    keyframe_transform(seed_obj, 30, scale=(0.98, 0.98, 0.96), location=(0.024, -0.010, -0.135))
    keyframe_transform(seed_obj, 44, scale=(0.88, 0.88, 0.86), location=(0.024, -0.010, -0.135))
    keyframe_transform(seed_obj, 56, scale=(0.0005, 0.0005, 0.0005), location=(0.024, -0.010, -0.135))
    keyframe_transform(seed_obj, 150, scale=(0.0005, 0.0005, 0.0005), location=(0.024, -0.010, -0.135))
    smooth_datablock_fcurves(seed_obj, linear=True)
    return seed_obj


# =============================================================================
# 2. FIBROUS TAPROOT, 18 SINUOUS LATERAL ROOTLETS & 22 CORALLOID RHIZOBIUM NODULES
# =============================================================================
TAPROOT_DEPTH = 0.72
TAPROOT_KEYFRAMES: list[tuple[int, tuple[float, float, float], tuple[float, float, float]]] = [
    (0, (0.28, 0.28, 0.14), (0.0, 0.0, -0.14)),
    (14, (0.50, 0.50, 0.32), (0.0, 0.0, -0.07)),
    (30, (0.68, 0.68, 0.50), (0.0, 0.0, 0.0)),
    (60, (0.84, 0.84, 0.72), (0.0, 0.0, 0.0)),
    (90, (0.94, 0.94, 0.88), (0.0, 0.0, 0.0)),
    (120, (0.98, 0.98, 0.96), (0.0, 0.0, 0.0)),
    (150, (1.00, 1.00, 1.00), (0.0, 0.0, 0.0)),
]


def taproot_collar_z_at_frame(frame: float) -> float:
    """Exact world Z of Taproot_Main origin matching LINEAR TAPROOT_KEYFRAMES (shared with Main_Stem!)."""
    if frame <= 0.0:
        return -0.14
    if frame < 14.0:
        return lerp(-0.14, -0.07, frame / 14.0)
    if frame < 30.0:
        return lerp(-0.07, 0.0, (frame - 14.0) / 16.0)
    return 0.0


def taproot_centerline(s: float) -> tuple[float, float, float, float]:
    """Return local (bend_x, bend_y, z, radius) of lentil taproot for s in [0..1]."""
    s = max(0.0, min(1.0, s))
    z = lerp(0.014, -TAPROOT_DEPTH, s)
    bend_env = smoothstep(max(0.0, (s - 0.06) / 0.25))
    bend_x = 0.025 * math.sin(s * math.pi * 1.15) * bend_env
    bend_y = -0.017 * math.sin(s * math.pi * 0.92) * bend_env
    shoulder = 0.0030 * math.exp(-(((s - 0.07) / 0.06) ** 2))
    radius = lerp(0.0124, 0.0022, s ** 0.76) + shoulder
    return bend_x, bend_y, z, radius


def taproot_s_from_local_z(z_local: float) -> float:
    return max(0.0, min(1.0, (0.014 - z_local) / (TAPROOT_DEPTH + 0.014)))


def _create_coralloid_nodule_mesh(name: str, radius: float, seed: int) -> bpy.types.Mesh:
    """Create indeterminate bilobed/coralloid Rhizobium lentil nodule with constricted basal neck."""
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=radius)

    h1 = math.sin(seed * 31.7 + 1.1) * 43758.5453
    r1 = h1 - math.floor(h1)
    lobe_type = seed % 3  # 0=elongated cylindrical, 1=bilobed fan, 2=trilobed coralloid

    for v in bm.verts:
        nx, ny, nz = v.co.x / radius, v.co.y / radius, v.co.z / radius
        t_out = max(0.0, min(1.0, (nx + 1.0) * 0.5))  # 0 at root attachment -> 1 at coral-pink meristem tip
        # Constricted stem-attachment neck (t_out < 0.25) flaring into plump lobed nodule body
        neck = lerp(0.55, 1.0, smoothstep(t_out / 0.30))
        lobe_y = 1.0
        lobe_z = 1.0
        if lobe_type == 1:
            # Indeterminate Y-forked bilobed lentil nodule
            lobe_y = 1.0 + 0.42 * (t_out ** 1.3) * (0.4 + 0.6 * abs(ny))
            notch = 0.22 * (t_out ** 2.0) * math.exp(-((ny / 0.35) ** 2))
            v.co.x -= radius * notch
        elif lobe_type == 2:
            # Fan-shaped trilobed coralloid cluster
            lobe_y = 1.0 + 0.48 * (t_out ** 1.2)
            lobe_z = 1.0 + 0.20 * math.sin(ny * math.pi * 2.2) * t_out
        bump = 1.0 + 0.11 * math.sin(nx * 5.8 + seed) * math.cos(ny * 5.2 - seed)
        v.co.x = (v.co.x * (1.42 + 0.26 * r1) + radius * 0.85) * bump
        v.co.y = v.co.y * 0.86 * neck * lobe_y * bump
        v.co.z = v.co.z * 0.82 * neck * lobe_z * bump

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        for l in f.loops:
            co = l.vert.co
            u = 0.5 + math.atan2(co.y, co.x - radius * 0.7) / (2.0 * math.pi)
            vv = 0.5 + co.z / (radius * 2.2)
            l[uv_layer].uv = (u, vv)

    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    set_smooth_shading(mesh, True)
    return mesh


def build_taproot_rootlets_and_nodules(
    mat_root: bpy.types.Material,
    mat_nodule: bpy.types.Material,
) -> list[bpy.types.Object]:
    """Build slender lentil taproot, 18 sinuous branched lateral roots, and 22 coralloid Rhizobium nodules."""
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    segs = 48
    pts: list[Vector] = []
    radii: list[float] = []
    for i in range(segs + 1):
        s = i / segs
        bx, by, z, rad = taproot_centerline(s)
        pts.append(Vector((bx, by, z)))
        radii.append(rad)
    _add_tube_along_points(bm, uv_layer, pts, radii, rad_segs=18, rib_amp=0.04, rib_freq=3, uv_u_range=(0.0, 1.0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    root_mesh = bpy.data.meshes.new("Taproot_Main_Mesh")
    bm.to_mesh(root_mesh)
    bm.free()
    set_smooth_shading(root_mesh, True)

    taproot_obj = link_object("Taproot_Main", root_mesh, mat_root, location=(0.0, 0.0, -0.14))
    for frame, sc, loc in TAPROOT_KEYFRAMES:
        keyframe_transform(taproot_obj, frame, scale=sc, location=loc)
    smooth_datablock_fcurves(taproot_obj, linear=True)

    objs: list[bpy.types.Object] = [taproot_obj]
    rootlet_curves: list[tuple[bpy.types.Object, list[Vector], float, int]] = []

    golden_ang = 2.39996323
    for i in range(18):
        s_anc = lerp(0.08, 0.82, i / 17.0)
        bx, by, z_anc, surf_r = taproot_centerline(s_anc)
        ang = i * golden_ang + 0.35
        r_anchor = surf_r * 0.56  # Strictly embedded inside taproot

        length = lerp(0.24, 0.13, (s_anc - 0.08) / 0.74) * (0.86 + 0.26 * ((i * 7 % 5) / 4.0))
        drop = lerp(0.14, 0.19, (s_anc - 0.08) / 0.74)
        c_ang, s_ang = math.cos(ang), math.sin(ang)
        t_x, t_y = -s_ang, c_ang

        rbm = bmesh.new()
        ruv = ensure_uv_layer(rbm)

        main_pts: list[Vector] = []
        main_rads: list[float] = []
        r0 = lerp(0.0046, 0.0023, s_anc)
        for k in range(13):
            t = k / 12.0
            dist = (t ** 0.88) * length
            sway = (
                0.028 * math.sin(t * math.pi * 1.85 + i * 1.3)
                + 0.011 * math.cos(t * math.pi * 3.4 - i * 0.7)
            ) * (t ** 0.75)
            z_off = -drop * (t ** 1.48) + 0.012 * math.sin(t * math.pi * 2.2 + i) * t
            px = c_ang * dist + t_x * sway
            py = s_ang * dist + t_y * sway
            main_pts.append(Vector((px, py, z_off)))
            main_rads.append(max(0.00055, r0 * ((1.0 - t) ** 0.78 + 0.10)))

        _add_tube_along_points(rbm, ruv, main_pts, main_rads, rad_segs=7, uv_u_range=(0.15, 0.85))

        for fork_idx, (fk_t, side_s, fk_len_mul) in enumerate(((0.34, 1.0, 0.52), (0.62, -1.0, 0.42))):
            idx_p = min(len(main_pts) - 2, max(1, int(fk_t * 12)))
            base_pt = main_pts[idx_p]
            fk_ang = ang + side_s * (0.52 + 0.16 * ((i + fork_idx) % 3))
            fk_len = length * fk_len_mul
            fk_pts: list[Vector] = []
            fk_rads: list[float] = []
            for m in range(8):
                u = m / 7.0
                d_fk = u * fk_len
                fk_sway = 0.014 * math.sin(u * math.pi * 1.9 + i + fork_idx) * u
                fk_pts.append(
                    Vector(
                        (
                            base_pt.x + math.cos(fk_ang) * d_fk - math.sin(fk_ang) * fk_sway,
                            base_pt.y + math.sin(fk_ang) * d_fk + math.cos(fk_ang) * fk_sway,
                            base_pt.z - 0.075 * (u ** 1.45),
                        )
                    )
                )
                fk_rads.append(max(0.00045, main_rads[idx_p] * 0.60 * (1.0 - 0.78 * u)))
            _add_tube_along_points(rbm, ruv, fk_pts, fk_rads, rad_segs=5, uv_u_range=(0.2, 0.8))

        bmesh.ops.recalc_face_normals(rbm, faces=rbm.faces)
        rmesh = bpy.data.meshes.new(f"Rootlet_{i + 1:02d}_Mesh")
        rbm.to_mesh(rmesh)
        rbm.free()
        set_smooth_shading(rmesh, True)

        ax = bx + r_anchor * c_ang
        ay = by + r_anchor * s_ang
        robj = link_object(f"Rootlet_{i + 1:02d}", rmesh, mat_root, location=(ax, ay, z_anc))
        robj.parent = taproot_obj

        appear_f = 18 + i * 5
        full_f = min(142, appear_f + 34)
        keyframe_transform(robj, 0, scale=(0.0005, 0.0005, 0.0005))
        keyframe_transform(robj, appear_f, scale=(0.0005, 0.0005, 0.0005))
        keyframe_transform(robj, full_f, scale=(1.0, 1.0, 1.0))
        keyframe_transform(robj, 150, scale=(1.0, 1.0, 1.0))
        smooth_datablock_fcurves(robj)
        objs.append(robj)
        rootlet_curves.append((robj, main_pts, ang, appear_f))

    # 22 coralloid pinkish Rhizobium nodules: 10 directly on taproot + 12 parented on proximal lateral rootlets
    nodule_idx = 0
    tap_nod_specs = [
        (0.10, 0.65, 0.0145, 22),
        (0.14, 2.55, 0.0155, 26),
        (0.18, 4.40, 0.0145, 32),
        (0.22, 1.35, 0.0165, 38),
        (0.27, 3.65, 0.0155, 46),
        (0.32, 5.45, 0.0150, 54),
        (0.38, 0.95, 0.0145, 64),
        (0.44, 3.10, 0.0138, 74),
        (0.50, 4.90, 0.0130, 84),
        (0.56, 2.05, 0.0125, 92),
    ]
    for s_n, ang_n, rad_n, f_app in tap_nod_specs:
        nodule_idx += 1
        bx, by, zn, sr = taproot_centerline(s_n)
        nx = bx + sr * 0.78 * math.cos(ang_n)
        ny = by + sr * 0.78 * math.sin(ang_n)
        nmesh = _create_coralloid_nodule_mesh(f"Nodule_{nodule_idx:02d}", rad_n, nodule_idx)
        nobj = link_object(
            f"Nodule_{nodule_idx:02d}",
            nmesh,
            mat_nodule,
            location=(nx, ny, zn),
            rotation=(0.0, 0.16, ang_n),
        )
        nobj.parent = taproot_obj
        f_full = min(122, f_app + 26)
        keyframe_transform(nobj, 0, scale=(0.0005, 0.0005, 0.0005))
        keyframe_transform(nobj, f_app, scale=(0.0005, 0.0005, 0.0005))
        keyframe_transform(nobj, f_full, scale=(1.0, 1.0, 1.0))
        keyframe_transform(nobj, 124, scale=(1.04, 1.04, 1.04))
        keyframe_transform(nobj, 150, scale=(0.76, 0.76, 0.76))
        smooth_datablock_fcurves(nobj)
        objs.append(nobj)

    lat_nod_specs = [
        (0, 2, 0.0142, 34, 0.9),
        (1, 3, 0.0148, 42, -0.8),
        (2, 2, 0.0140, 48, 1.0),
        (3, 4, 0.0150, 56, -1.0),
        (4, 3, 0.0145, 64, 0.85),
        (5, 2, 0.0138, 72, -0.9),
        (6, 4, 0.0140, 80, 0.95),
        (7, 3, 0.0132, 86, -0.85),
        (8, 2, 0.0128, 92, 0.80),
        (9, 3, 0.0124, 98, -0.95),
        (0, 5, 0.0122, 68, -0.75),
        (2, 5, 0.0120, 78, 0.80),
    ]
    for r_idx, pt_idx, rad_n, f_app, yaw_off in lat_nod_specs:
        nodule_idx += 1
        robj, main_pts, r_ang, r_appear = rootlet_curves[r_idx]
        pt = main_pts[pt_idx]
        nmesh = _create_coralloid_nodule_mesh(f"Nodule_{nodule_idx:02d}", rad_n, nodule_idx + 30)
        nobj = link_object(
            f"Nodule_{nodule_idx:02d}",
            nmesh,
            mat_nodule,
            location=(pt.x, pt.y, pt.z),
            rotation=(0.0, 0.24, r_ang + yaw_off),
        )
        nobj.parent = robj
        f_start = max(f_app, r_appear + 8)
        f_full = min(126, f_start + 24)
        keyframe_transform(nobj, 0, scale=(0.0005, 0.0005, 0.0005))
        keyframe_transform(nobj, f_start, scale=(0.0005, 0.0005, 0.0005))
        keyframe_transform(nobj, f_full, scale=(1.0, 1.0, 1.0))
        keyframe_transform(nobj, 128, scale=(1.04, 1.04, 1.04))
        keyframe_transform(nobj, 150, scale=(0.74, 0.74, 0.74))
        smooth_datablock_fcurves(nobj)
        objs.append(nobj)

    return objs


# =============================================================================
# 3. ACROPETAL 4-RIBBED MAIN STEM (WITH NODAL PULVINI) + 3 SEAMLESS BRANCHES
# =============================================================================
MAIN_STEM_STAGES: dict[str, tuple[float, float]] = {
    "early30": (0.28, 0.66),
    "branch60": (0.58, 0.82),
    "bud90": (0.82, 0.94),
    "basis": (1.00, 1.00),
}

MAIN_STEM_NODES_S = (0.14, 0.20, 0.27, 0.34, 0.45, 0.56, 0.67, 0.79, 0.91)


def main_stem_stage_point(s: float, stage: str = "basis") -> tuple[Vector, float]:
    """Return collar-local point & radius (including subtle anatomical nodal pulvini) along Main_Stem."""
    s = max(0.0, min(1.0, s))
    s_cap, rad_mul = MAIN_STEM_STAGES[stage]
    s_eff = min(s, s_cap)
    if s > s_cap:
        s_eff = s_cap + (s - s_cap) * 0.025
    z = lerp(-0.026, 0.74, s_eff)
    above = smoothstep(max(0.0, (s_eff - 0.07) / 0.93))
    x = 0.022 * math.sin(above * math.pi * 0.95) - 0.008 * (above ** 1.5)
    y = -0.018 * math.sin(above * math.pi * 0.85) + 0.007 * math.sin(above * math.pi * 1.7)
    r_base = lerp(0.0114, 0.0044, s_eff ** 0.72) * rad_mul
    # Subtle anatomical pulvinus (nodal collar bulge) at each stem node
    node_bulge = 0.0
    for sn in MAIN_STEM_NODES_S:
        node_bulge = max(node_bulge, math.exp(-(((s_eff - sn) / 0.016) ** 2)))
    r_base *= 1.0 + 0.12 * node_bulge
    if s < 0.05:
        r_base *= lerp(0.72, 1.0, s / 0.05)
    if s > s_cap:
        r_base *= 0.65
    return Vector((x, y, z)), r_base


def main_stem_stage_weights(frame: float) -> tuple[float, float, float, float]:
    """Return exact piecewise-linear weights (w30, w60, w90, stem_scale) matching Blender animation."""
    if frame <= 0.0:
        return (1.0, 0.0, 0.0, 0.0005)
    if frame < 14.0:
        t = frame / 14.0
        return (1.0, 0.0, 0.0, lerp(0.0005, 0.56, t))
    if frame < 30.0:
        t = (frame - 14.0) / 16.0
        return (1.0, 0.0, 0.0, lerp(0.56, 1.0, t))
    if frame < 60.0:
        t = (frame - 30.0) / 30.0
        return (1.0 - t, t, 0.0, 1.0)
    if frame < 90.0:
        t = (frame - 60.0) / 30.0
        return (0.0, 1.0 - t, t, 1.0)
    if frame < 135.0:
        t = (frame - 90.0) / 45.0
        return (0.0, 0.0, 1.0 - t, 1.0)
    return (0.0, 0.0, 0.0, 1.0)


def eval_main_stem_world(s: float, frame: float) -> tuple[Vector, float]:
    """Evaluate exact Main_Stem centerline position & radius in world space at frame."""
    w30, w60, w90, sc = main_stem_stage_weights(frame)
    p_bas, r_bas = main_stem_stage_point(s, "basis")
    p_30, r_30 = main_stem_stage_point(s, "early30")
    p_60, r_60 = main_stem_stage_point(s, "branch60")
    p_90, r_90 = main_stem_stage_point(s, "bud90")

    p_local = p_bas + w30 * (p_30 - p_bas) + w60 * (p_60 - p_bas) + w90 * (p_90 - p_bas)
    r_local = r_bas + w30 * (r_30 - r_bas) + w60 * (r_60 - r_bas) + w90 * (r_90 - r_bas)
    z_col = taproot_collar_z_at_frame(frame)
    p_world = Vector((0.0, 0.0, z_col)) + p_local * sc
    return p_world, r_local * sc


BRANCH_SPECS: dict[str, tuple[float, float, float, float, int, int]] = {
    "Branch_L": (0.14, 212.0, 0.27, 0.44, 42, 120),
    "Branch_R": (0.20, 26.0, 0.27, 0.45, 46, 124),
    "Branch_B": (0.27, 118.0, 0.25, 0.43, 52, 128),
}


def branch_local_point(branch_name: str, s: float) -> tuple[Vector, float]:
    """Return local (x, y, z) and organic tapered radius of a side branch relative to its stem node."""
    _, yaw_deg, reach_r, rise_z, _, _ = BRANCH_SPECS[branch_name]
    yaw = math.radians(yaw_deg)
    r_out = reach_r * (s ** 0.88)
    z_up = rise_z * (s ** 1.12) + 0.018 * math.sin(s * math.pi)
    sway = 0.014 * math.sin(s * math.pi * 1.1)
    cx, sy = math.cos(yaw), math.sin(yaw)
    px = cx * r_out - sy * sway
    py = sy * r_out + cx * sway
    if s < 0.08:
        rad = lerp(0.0040, 0.0066, smoothstep(s / 0.08))
    else:
        rad = lerp(0.0066, 0.0030, ((s - 0.08) / 0.92) ** 0.78)
    # Subtle branch nodal pulvini at leaf/pod nodes
    node_bulge = max(math.exp(-(((s - sn) / 0.032) ** 2)) for sn in (0.26, 0.50, 0.74))
    rad *= 1.0 + 0.10 * node_bulge
    return Vector((px, py, z_up)), rad


def branch_scale_at_frame(branch_name: str, frame: float) -> float:
    """Exact piecewise-linear scale of a side branch matching its Blender keyframes."""
    _, _, _, _, f_start, f_full = BRANCH_SPECS[branch_name]
    if frame <= f_start:
        return 0.0005
    if frame >= f_full:
        return 1.0
    return lerp(0.0005, 1.0, (frame - f_start) / float(f_full - f_start))


def eval_host_world(host_name: str, s: float, frame: float) -> tuple[Vector, float]:
    """Evaluate world centerline position & radius of Main_Stem or any side Branch at frame."""
    if host_name == "Main_Stem":
        return eval_main_stem_world(s, frame)
    s_att = BRANCH_SPECS[host_name][0]
    base_world, _ = eval_main_stem_world(s_att, frame)
    p_loc, r_loc = branch_local_point(host_name, s)
    sc = branch_scale_at_frame(host_name, frame)
    return base_world + p_loc * sc, r_loc * sc


def build_stems_and_branches(mat_stem: bpy.types.Material) -> list[bpy.types.Object]:
    """Build acropetal 4-ribbed Main_Stem fused to Taproot_Main collar + 3 seamlessly joined side branches."""
    segs = 44
    rad_segs = 14

    def _stem_rings_coords(stage: str) -> list[Vector]:
        pts: list[Vector] = []
        rads: list[float] = []
        for i in range(segs + 1):
            p, r = main_stem_stage_point(i / segs, stage)
            pts.append(p)
            rads.append(r)

        coords: list[Vector] = []
        prev_n = Vector((1.0, 0.0, 0.0))
        for i, p in enumerate(pts):
            t_vec = (pts[min(segs, i + 1)] - pts[max(0, i - 1)]).normalized()
            n_vec = prev_n - t_vec * prev_n.dot(t_vec)
            n_vec = n_vec.normalized() if n_vec.length > 1e-4 else Vector((1.0, 0.0, 0.0))
            b_vec = t_vec.cross(n_vec).normalized()
            prev_n = n_vec
            for ai in range(rad_segs):
                ang = 2.0 * math.pi * (ai / rad_segs)
                r = rads[i] * (1.0 + 0.09 * math.cos(4.0 * ang))
                coords.append(p + (n_vec * math.cos(ang) + b_vec * math.sin(ang)) * r)
        coords.append(pts[0] - Vector((0.0, 0.0, rads[0] * 0.45)))
        coords.append(pts[-1] + Vector((0.0, 0.0, rads[-1] * 0.55)))
        return coords

    basis_coords = _stem_rings_coords("basis")
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    verts = [bm.verts.new(co) for co in basis_coords]

    for i in range(segs):
        v0, v1 = i / segs, (i + 1) / segs
        for ai in range(rad_segs):
            ai_n = (ai + 1) % rad_segs
            u0 = lerp(0.42, 0.58, ai / rad_segs)
            u1 = lerp(0.42, 0.58, (ai + 1) / rad_segs)
            f = bm.faces.new(
                (
                    verts[i * rad_segs + ai],
                    verts[i * rad_segs + ai_n],
                    verts[(i + 1) * rad_segs + ai_n],
                    verts[(i + 1) * rad_segs + ai],
                )
            )
            for l, uv in zip(f.loops, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]):
                l[uv_layer].uv = uv

    c_bot, c_top = verts[-2], verts[-1]
    for ai in range(rad_segs):
        ai_n = (ai + 1) % rad_segs
        f0 = bm.faces.new((verts[ai_n], verts[ai], c_bot))
        for l in f0.loops:
            l[uv_layer].uv = (0.5, 0.0)
        f1 = bm.faces.new((verts[segs * rad_segs + ai], verts[segs * rad_segs + ai_n], c_top))
        for l in f1.loops:
            l[uv_layer].uv = (0.5, 1.0)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    smesh = bpy.data.meshes.new("Main_Stem_Mesh")
    bm.to_mesh(smesh)
    bm.free()
    set_smooth_shading(smesh, True)
    apply_vertex_colors(smesh, seed=1, mode="stem")

    stem_obj = link_object("Main_Stem", smesh, mat_stem, location=(0.0, 0.0, -0.14))
    stem_obj.shape_key_add(name="Basis", from_mix=False)
    sk_30 = stem_obj.shape_key_add(name="Stage_Early30", from_mix=False)
    sk_60 = stem_obj.shape_key_add(name="Stage_Branch60", from_mix=False)
    sk_90 = stem_obj.shape_key_add(name="Stage_Bud90", from_mix=False)

    for sk, stg in ((sk_30, "early30"), (sk_60, "branch60"), (sk_90, "bud90")):
        coords = _stem_rings_coords(stg)
        for idx_v, co in enumerate(coords):
            sk.data[idx_v].co = co

    for kf in (0, 14, 30, 60, 90, 135, 150):
        w30, w60, w90, sc = main_stem_stage_weights(float(kf))
        z_col = taproot_collar_z_at_frame(float(kf))
        sk_30.value = w30
        sk_30.keyframe_insert(data_path="value", frame=kf)
        sk_60.value = w60
        sk_60.keyframe_insert(data_path="value", frame=kf)
        sk_90.value = w90
        sk_90.keyframe_insert(data_path="value", frame=kf)
        keyframe_transform(stem_obj, kf, scale=(sc, sc, sc), location=(0.0, 0.0, z_col))

    smooth_datablock_fcurves(smesh.shape_keys, linear=True)
    smooth_datablock_fcurves(stem_obj, linear=True)

    objs: list[bpy.types.Object] = [stem_obj]

    for b_idx, (bname, (s_att, _, _, _, f_start, f_full)) in enumerate(BRANCH_SPECS.items()):
        bbm = bmesh.new()
        buv = ensure_uv_layer(bbm)
        b_pts: list[Vector] = []
        b_rads: list[float] = []
        for i in range(25):
            p, r = branch_local_point(bname, i / 24.0)
            b_pts.append(p)
            b_rads.append(r)
        _add_tube_along_points(bbm, buv, b_pts, b_rads, rad_segs=12, rib_amp=0.07, rib_freq=4)
        bmesh.ops.recalc_face_normals(bbm, faces=bbm.faces)

        bmesh_data = bpy.data.meshes.new(f"{bname}_Mesh")
        bbm.to_mesh(bmesh_data)
        bbm.free()
        set_smooth_shading(bmesh_data, True)
        apply_vertex_colors(bmesh_data, seed=10 + b_idx, mode="stem")

        p0, _ = eval_main_stem_world(s_att, 0.0)
        bobj = link_object(bname, bmesh_data, mat_stem, location=(p0.x, p0.y, p0.z))

        kfs = sorted({0, 14, 30, f_start, 60, 90, f_full, 135, 150})
        for kf in kfs:
            pw, _ = eval_main_stem_world(s_att, float(kf))
            sc = branch_scale_at_frame(bname, float(kf))
            keyframe_transform(bobj, kf, scale=(sc, sc, sc), location=(pw.x, pw.y, pw.z))
        smooth_datablock_fcurves(bobj, linear=True)
        objs.append(bobj)

    return objs


# =============================================================================
# 4. 20 HIGH-DETAIL COMPOUND EVEN-PINNATE LEAVES (7x4 LEAFLETS + 18-SEG TENDRILS)
# =============================================================================
def _build_compound_leaf_coords(
    length: float,
    leaflet_pairs: int,
    has_tendril: bool,
    arch: float,
    seed: int,
    stage: str = "basis",
) -> tuple[list[Vector], list[tuple[int, ...]], list[list[tuple[float, float]]]]:
    """Build unified high-res mesh for 1 compound lentil leaf with identical topology across stages."""
    verts: list[Vector] = []
    faces: list[tuple[int, ...]] = []
    face_uvs: list[list[tuple[float, float]]] = []

    h1 = math.sin(seed * 23.17 + 0.5) * 43758.5453
    r1 = h1 - math.floor(h1)

    if stage == "bud":
        l_mul = 0.30
        spread_ang = 0.24
        fold_up = 0.72
        lf_scale = 0.42
        droop = 0.0
    elif stage == "unfurl":
        l_mul = 0.74
        spread_ang = 0.66
        fold_up = 0.28
        lf_scale = 0.80
        droop = 0.0
    elif stage == "mature":
        l_mul = 1.02
        spread_ang = 1.00
        fold_up = 0.0
        lf_scale = 0.96
        droop = 1.0
    else:
        l_mul = 1.00
        spread_ang = 1.00
        fold_up = 0.0
        lf_scale = 1.00
        droop = 0.0

    def rachis_pt(t: float) -> Vector:
        if t < 0.0:
            return Vector((t * 0.010, 0.0, 0.0))
        x = t * length * l_mul
        # Keep proximal rachis (t < 0.14) emerging cleanly outward before arching upward
        arch_env = smoothstep(t / 0.22)
        z = (
            arch * math.sin(t * math.pi * 0.85) * l_mul * arch_env
            - 0.024 * length * (t ** 2.1) * l_mul
            - 0.028 * length * (t ** 1.7) * droop
        )
        y = 0.005 * length * math.sin(t * math.pi + seed) * l_mul * arch_env
        return Vector((x, y, z))

    # --- A) Basal plug + slender grooved rachis (vert 0 = embedded stem plug) ---
    r_segs = 6
    rach_steps = 14
    rach_ts = [-0.75, -0.25] + [i / rach_steps for i in range(rach_steps + 1)]
    verts.append(Vector((-0.0075, 0.0, 0.0)))

    ring_starts: list[int] = []
    for t in rach_ts:
        p = rachis_pt(t)
        p_next = rachis_pt(min(1.0, t + 0.04))
        t_vec = (p_next - p).normalized() if (p_next - p).length > 1e-6 else Vector((1.0, 0.0, 0.0))
        side = Vector((0.0, 0.0, 1.0)).cross(t_vec).normalized()
        n_up = t_vec.cross(side).normalized()
        rad = lerp(0.0028, 0.0011, max(0.0, t)) * (0.65 if t < -0.4 else 1.0)
        st = len(verts)
        ring_starts.append(st)
        for ai in range(r_segs):
            ang = 2.0 * math.pi * (ai / r_segs)
            verts.append(p + (side * math.cos(ang) + n_up * math.sin(ang)) * rad)

    for ai in range(r_segs):
        ai_n = (ai + 1) % r_segs
        faces.append((ring_starts[0] + ai_n, ring_starts[0] + ai, 0))
        face_uvs.append([(0.5, 0.0), (0.5, 0.0), (0.5, 0.0)])

    for ri in range(len(rach_ts) - 1):
        v0 = max(0.0, rach_ts[ri])
        v1 = max(0.0, rach_ts[ri + 1])
        s0, s1 = ring_starts[ri], ring_starts[ri + 1]
        for ai in range(r_segs):
            ai_n = (ai + 1) % r_segs
            u0 = lerp(0.45, 0.55, ai / r_segs)
            u1 = lerp(0.45, 0.55, (ai + 1) / r_segs)
            faces.append((s0 + ai, s0 + ai_n, s1 + ai_n, s1 + ai))
            face_uvs.append([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])

    # --- B) Sculpted twin lanceolate basal stipules (placed cleanly clear of host stem wall) ---
    for side_s in (-1.0, 1.0):
        base_p = rachis_pt(0.11)
        st_len = 0.015 * (0.65 + 0.35 * lf_scale)
        st_w = 0.0042 * (0.65 + 0.35 * lf_scale)
        idx0 = len(verts)
        verts.append(base_p + Vector((0.0, side_s * 0.0018, 0.0005)))
        verts.append(base_p + Vector((st_len * 0.42, side_s * (st_w + 0.0022), 0.0025)))
        verts.append(base_p + Vector((st_len * 0.52, side_s * 0.0018, 0.0045)))
        verts.append(base_p + Vector((st_len, side_s * (st_w * 0.65), 0.0055)))
        faces.append((idx0, idx0 + 1, idx0 + 3, idx0 + 2))
        face_uvs.append([(0.5, 0.05), (0.9, 0.45), (0.5, 0.95), (0.1, 0.55)])

    # --- C) High-res 7x4 oblong-elliptic mucronate lentil leaflets with petiolule + midvein V-groove ---
    lf_len_segs = 7
    lf_w_segs = 4
    for p_i in range(leaflet_pairs):
        frac = p_i / max(1, leaflet_pairs - 1)
        t_pair = lerp(0.26, 0.91, frac)
        size_env = 0.86 + 0.24 * math.sin((0.18 + 0.78 * frac) * math.pi)
        lf_len = (0.047 + 0.008 * r1) * size_env * lf_scale
        lf_half_w = lf_len * 0.34

        for side_s in (-1.0, 1.0):
            t_loc = min(0.95, t_pair + (0.015 if side_s > 0 else 0.0))
            attach = rachis_pt(t_loc)
            p_ahead = rachis_pt(min(1.0, t_loc + 0.04))
            t_vec = (p_ahead - attach).normalized() if (p_ahead - attach).length > 1e-6 else Vector((1.0, 0.0, 0.0))
            side_vec = Vector((0.0, 0.0, 1.0)).cross(t_vec).normalized()
            up_vec = t_vec.cross(side_vec).normalized()

            yaw_out = lerp(0.32, 1.02 - 0.14 * frac, spread_ang)
            lift = lerp(0.11 + 0.05 * frac, 0.68, fold_up) - 0.12 * droop
            dir_lf = (
                t_vec * math.cos(yaw_out)
                + side_vec * (side_s * math.sin(yaw_out))
                + up_vec * lift
            ).normalized()
            lf_width_dir = (up_vec * 0.92 + side_vec * (side_s * 0.28)).cross(dir_lf).normalized()
            if lf_width_dir.dot(t_vec) < 0.0:
                lf_width_dir = -lf_width_dir
            lf_norm_dir = dir_lf.cross(lf_width_dir).normalized()
            if lf_norm_dir.z < 0.0:
                lf_norm_dir = -lf_norm_dir

            grid_idx: list[list[int]] = []
            for li in range(lf_len_segs + 1):
                lt = li / lf_len_segs
                # Short slender petiolule stalk (lt=0..0.12) flaring into oblong lamina with tiny mucronate tip
                if lt < 0.12:
                    w_env = lerp(0.08, 0.38, lt / 0.12)
                elif lt > 0.92:
                    # Crisp pointed mucro apex characteristic of Lens culinaris
                    w_env = lerp(0.36, 0.02, (lt - 0.92) / 0.08)
                else:
                    bt = (lt - 0.10) / 0.84
                    w_env = max(0.12, math.sin(max(0.0, min(1.0, bt)) * math.pi) ** 0.64)
                arch_z = 0.0052 * math.sin(lt * math.pi) - 0.0036 * (lt ** 2.1) * (1.0 + droop)
                row_idx: list[int] = []
                for wi in range(lf_w_segs + 1):
                    u_w = (wi / lf_w_segs) * 2.0 - 1.0
                    # Sculpted adaxial midrib V-channel + gentle convex half-blade pillowing
                    mid_v = -0.0012 * math.exp(-((u_w / 0.22) ** 2)) * math.sin(lt * math.pi)
                    cup_z = (0.0030 + 0.0036 * fold_up) * (abs(u_w) ** 1.25) * math.sin(lt * math.pi)
                    edge_curl = -0.0012 * (u_w ** 4) * math.sin(lt * math.pi) * (1.0 - fold_up)
                    pt = (
                        attach
                        + dir_lf * (0.002 + lt * lf_len)
                        + lf_width_dir * (u_w * lf_half_w * w_env)
                        + lf_norm_dir * (arch_z + mid_v + cup_z + edge_curl)
                    )
                    row_idx.append(len(verts))
                    verts.append(pt)
                grid_idx.append(row_idx)

            for li in range(lf_len_segs):
                v0, v1 = li / lf_len_segs, (li + 1) / lf_len_segs
                for wi in range(lf_w_segs):
                    u0, u1 = wi / lf_w_segs, (wi + 1) / lf_w_segs
                    faces.append(
                        (
                            grid_idx[li][wi],
                            grid_idx[li + 1][wi],
                            grid_idx[li + 1][wi + 1],
                            grid_idx[li][wi + 1],
                        )
                    )
                    face_uvs.append([(u0, v0), (u0, v1), (u1, v1), (u1, v0)])

    # --- D) Smooth 18-segment coiled helical apical tendril (2.1 graceful turns) ---
    tip_p = rachis_pt(1.0)
    t_steps = 18
    t_rsegs = 5
    tend_pts: list[Vector] = []
    tend_rads: list[float] = []
    coil_scale = 0.22 if stage == "bud" else (0.72 if stage == "unfurl" else 1.0)
    for k in range(t_steps + 1):
        u = k / t_steps
        if has_tendril:
            curl_r = (0.0095 + 0.003 * r1) * (u ** 0.78) * coil_scale
            turns = 2.1 * (u ** 1.15) * 2.0 * math.pi
            px = tip_p.x + u * 0.054 * l_mul + curl_r * 0.30 * math.sin(turns)
            py = tip_p.y + curl_r * math.cos(turns + seed)
            pz = tip_p.z + 0.011 * math.sin(u * math.pi) + curl_r * math.sin(turns + seed)
            rad = lerp(0.00105, 0.00038, u)
        else:
            px = tip_p.x + u * 0.009 * l_mul
            py = tip_p.y
            pz = tip_p.z + 0.002 * u
            rad = lerp(0.00105, 0.00035, u)
        tend_pts.append(Vector((px, py, pz)))
        tend_rads.append(rad)

    t_ring_starts: list[int] = []
    for k, pt in enumerate(tend_pts):
        p_n = tend_pts[min(t_steps, k + 1)]
        p_p = tend_pts[max(0, k - 1)]
        tv = (p_n - p_p).normalized() if (p_n - p_p).length > 1e-6 else Vector((1.0, 0.0, 0.0))
        ref = Vector((0.0, 0.0, 1.0)) if abs(tv.z) < 0.85 else Vector((1.0, 0.0, 0.0))
        sv = tv.cross(ref).normalized()
        uv_v = sv.cross(tv).normalized()
        st = len(verts)
        t_ring_starts.append(st)
        for ai in range(t_rsegs):
            ang = 2.0 * math.pi * (ai / t_rsegs)
            verts.append(pt + (sv * math.cos(ang) + uv_v * math.sin(ang)) * tend_rads[k])

    for k in range(t_steps):
        s0, s1 = t_ring_starts[k], t_ring_starts[k + 1]
        for ai in range(t_rsegs):
            ai_n = (ai + 1) % t_rsegs
            faces.append((s0 + ai, s0 + ai_n, s1 + ai_n, s1 + ai))
            face_uvs.append([(0.48, 0.1), (0.52, 0.1), (0.52, 0.9), (0.48, 0.9)])

    return verts, faces, face_uvs


def create_compound_leaf_object(
    name: str,
    mat: bpy.types.Material,
    host_name: str,
    s_node: float,
    yaw_deg: float,
    pitch_open: float,
    length: float,
    leaflet_pairs: int,
    has_tendril: bool,
    arch: float,
    f_start: int,
    f_full: int,
    seed: int,
    is_lower_senescing: bool,
) -> tuple[bpy.types.Object, str, float]:
    """Create one animated high-detail compound lentil leaf locked analytically to its host stem."""
    b_verts, faces, face_uvs = _build_compound_leaf_coords(
        length, leaflet_pairs, has_tendril, arch, seed, "basis"
    )
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    bm_verts = [bm.verts.new(co) for co in b_verts]
    for f_idxs, uvs in zip(faces, face_uvs):
        f = bm.faces.new(tuple(bm_verts[i] for i in f_idxs))
        for l, uv in zip(f.loops, uvs):
            l[uv_layer].uv = uv
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    set_smooth_shading(mesh, True)
    apply_vertex_colors(mesh, seed=seed, mode="leaf")

    yaw = math.radians(yaw_deg)
    pitch_bud = -max(0.10, pitch_open - 0.14)
    pitch_final = -pitch_open
    pitch_droop = -(pitch_open - 0.10) if is_lower_senescing else pitch_final

    p0, _ = eval_host_world(host_name, s_node, 0.0)
    obj = link_object(
        name,
        mesh,
        mat,
        location=(p0.x, p0.y, p0.z),
        rotation=(0.0, pitch_bud, yaw),
        scale=(0.0005, 0.0005, 0.0005),
    )

    obj.shape_key_add(name="Basis", from_mix=False)
    sk_bud = obj.shape_key_add(name="Stage1_Bud", from_mix=False)
    sk_unf = obj.shape_key_add(name="Stage2_Unfurl", from_mix=False)
    sk_mat = obj.shape_key_add(name="Stage3_Mature", from_mix=False)

    for sk, stg in ((sk_bud, "bud"), (sk_unf, "unfurl"), (sk_mat, "mature")):
        s_verts, _, _ = _build_compound_leaf_coords(
            length, leaflet_pairs, has_tendril, arch, seed, stg
        )
        for i, co in enumerate(s_verts):
            sk.data[i].co = co

    f_mid = int(lerp(f_start, f_full, 0.48))
    for fr, w_bud, w_unf in (
        (0, 1.0, 0.0),
        (f_start, 1.0, 0.0),
        (f_mid, 0.0, 1.0),
        (f_full, 0.0, 0.0),
        (150, 0.0, 0.0),
    ):
        sk_bud.value = w_bud
        sk_bud.keyframe_insert(data_path="value", frame=fr)
        sk_unf.value = w_unf
        sk_unf.keyframe_insert(data_path="value", frame=fr)

    sk_mat.value = 0.0
    sk_mat.keyframe_insert(data_path="value", frame=0)
    mat_start_f = 112 if is_lower_senescing else 134
    sk_mat.value = 0.0
    sk_mat.keyframe_insert(data_path="value", frame=mat_start_f)
    sk_mat.value = 0.90 if is_lower_senescing else 0.22
    sk_mat.keyframe_insert(data_path="value", frame=150)
    smooth_datablock_fcurves(mesh.shape_keys)

    hide_until = max(1, f_start - 3)
    host_kfs = {0, 14, 30, 60, 90, 135, 150}
    if host_name in BRANCH_SPECS:
        host_kfs |= {BRANCH_SPECS[host_name][4], BRANCH_SPECS[host_name][5]}
    key_frames = sorted(host_kfs | {hide_until, f_start, f_mid, f_full})

    for kf in key_frames:
        pw, _ = eval_host_world(host_name, s_node, float(kf))
        if kf <= hide_until:
            sc_v = 0.0005
            pt_v = pitch_bud
        elif kf < f_start:
            u_pre = max(0.0, min(1.0, (kf - hide_until) / max(1.0, float(f_start - hide_until))))
            sc_v = lerp(0.0005, 0.62, u_pre)
            pt_v = pitch_bud
        elif kf < f_full:
            u = max(0.0, min(1.0, (kf - f_start) / max(1.0, float(f_full - f_start))))
            sc_v = lerp(0.62, 1.0, u ** 0.85)
            pt_v = lerp(pitch_bud, pitch_final, u)
        else:
            t_m = max(0.0, min(1.0, (kf - f_full) / max(1.0, 150.0 - f_full)))
            sc_v = lerp(1.0, 1.03, t_m)
            pt_v = lerp(pitch_final, pitch_droop, t_m)
        keyframe_transform(obj, kf, scale=(sc_v, sc_v, sc_v), location=(pw.x, pw.y, pw.z), rotation=(0.0, pt_v, yaw))

    smooth_datablock_fcurves(obj, linear=True)
    return obj, host_name, s_node


def build_all_compound_leaves(
    mat_outer: bpy.types.Material,
    mat_mid: bpy.types.Material,
    mat_heart: bpy.types.Material,
) -> tuple[list[bpy.types.Object], dict[str, tuple[str, float]]]:
    """Build 20 lush non-overlapping compound even-pinnate lentil leaves across Main_Stem & 3 branches."""
    # (host, s_node, yaw_deg, pitch_open, length, pairs, tendril, arch, f_start, f_full, tier)
    specs = [
        # --- 8 alternating spiral leaves on Main_Stem ---
        ("Main_Stem", 0.15, 326.0, 0.20, 0.155, 4, False, 0.022, 22, 42, "outer"),
        ("Main_Stem", 0.23, 154.0, 0.24, 0.170, 4, False, 0.024, 26, 48, "outer"),
        ("Main_Stem", 0.34, 280.0, 0.30, 0.195, 5, True, 0.026, 38, 64, "outer"),
        ("Main_Stem", 0.45, 74.0, 0.34, 0.202, 5, True, 0.028, 50, 76, "mid"),
        ("Main_Stem", 0.56, 246.0, 0.38, 0.198, 5, True, 0.028, 62, 88, "mid"),
        ("Main_Stem", 0.67, 16.0, 0.42, 0.188, 5, True, 0.026, 74, 102, "mid"),
        ("Main_Stem", 0.79, 178.0, 0.44, 0.172, 5, True, 0.024, 86, 114, "heart"),
        ("Main_Stem", 0.94, 310.0, 0.44, 0.152, 4, True, 0.022, 96, 124, "heart"),
        # --- 4 outer-facing leaves on Branch_L (212 deg; terminal leaf at s=0.99 clears branch apex!) ---
        ("Branch_L", 0.26, 266.0, 0.16, 0.152, 4, True, 0.020, 54, 80, "outer"),
        ("Branch_L", 0.50, 186.0, 0.26, 0.170, 5, True, 0.022, 66, 92, "outer"),
        ("Branch_L", 0.74, 262.0, 0.30, 0.170, 5, True, 0.022, 78, 104, "mid"),
        ("Branch_L", 0.99, 206.0, 0.30, 0.152, 4, True, 0.020, 92, 118, "heart"),
        # --- 4 outer-facing leaves on Branch_R (26 deg; terminal leaf at s=0.99!) ---
        ("Branch_R", 0.26, 74.0, 0.16, 0.152, 4, True, 0.020, 58, 84, "outer"),
        ("Branch_R", 0.50, 340.0, 0.26, 0.170, 5, True, 0.022, 70, 96, "outer"),
        ("Branch_R", 0.74, 70.0, 0.30, 0.170, 5, True, 0.022, 82, 108, "mid"),
        ("Branch_R", 0.99, 16.0, 0.30, 0.152, 4, True, 0.020, 96, 122, "heart"),
        # --- 4 outer-facing leaves on Branch_B (118 deg; terminal leaf at s=0.99!) ---
        ("Branch_B", 0.26, 72.0, 0.16, 0.150, 4, True, 0.020, 64, 90, "outer"),
        ("Branch_B", 0.50, 162.0, 0.26, 0.168, 5, True, 0.022, 76, 102, "mid"),
        ("Branch_B", 0.74, 78.0, 0.30, 0.166, 5, True, 0.022, 88, 114, "mid"),
        ("Branch_B", 0.99, 130.0, 0.30, 0.150, 4, True, 0.020, 100, 126, "heart"),
    ]

    mat_map = {"outer": mat_outer, "mid": mat_mid, "heart": mat_heart}
    leaves: list[bpy.types.Object] = []
    leaf_hosts: dict[str, tuple[str, float]] = {}

    for idx, (host, sn, yaw_d, pit, ln, prs, tend, arch, fs, ff, tier) in enumerate(specs):
        lobj, h_name, h_s = create_compound_leaf_object(
            name=f"Leaf_{idx + 1:02d}",
            mat=mat_map[tier],
            host_name=host,
            s_node=sn,
            yaw_deg=yaw_d,
            pitch_open=pit,
            length=ln,
            leaflet_pairs=prs,
            has_tendril=tend,
            arch=arch,
            f_start=fs,
            f_full=ff,
            seed=idx + 1,
            is_lower_senescing=(tier == "outer"),
        )
        leaves.append(lobj)
        leaf_hosts[lobj.name] = (h_name, h_s)

    return leaves, leaf_hosts


# =============================================================================
# 5. 14 TWO-MATERIAL PAPILIONACEOUS FLOWERS (5-TOOTHED GREEN CALYX + BILOBED BANNER)
# =============================================================================
def _build_flower_coords(
    stage: str = "open",
) -> tuple[list[Vector], list[tuple[int, ...]], list[list[tuple[float, float]]], list[int]]:
    """Build 1 two-material papilionaceous flower (slot 0=Flower_PBR petals, slot 1=Stem_PBR peduncle+5-tooth calyx)."""
    verts: list[Vector] = []
    faces: list[tuple[int, ...]] = []
    face_uvs: list[list[tuple[float, float]]] = []
    face_mats: list[int] = []

    open_f = 0.22 if stage == "bud" else 1.0

    # --- 1) Smooth 8-segment arched green peduncle extending cleanly outward (mat slot 1 = Stem_PBR) ---
    p_a = Vector((-0.004, 0.0, 0.0))
    p_c = Vector((0.026, 0.0, 0.006))
    p_b = Vector((0.050, 0.0, 0.004))
    ped_pts: list[Vector] = []
    ped_rads: list[float] = []
    for k in range(8):
        u = k / 7.0
        om = 1.0 - u
        ped_pts.append(p_a * (om * om) + p_c * (2.0 * om * u) + p_b * (u * u))
        ped_rads.append(lerp(0.0014, 0.0011, u) + 0.0024 * (u ** 4.0))

    p_segs = 6
    r_starts: list[int] = []
    for k, pt in enumerate(ped_pts):
        p_n = ped_pts[min(7, k + 1)]
        p_p = ped_pts[max(0, k - 1)]
        tv = (p_n - p_p).normalized() if (p_n - p_p).length > 1e-6 else Vector((1.0, 0.0, 0.0))
        sv = Vector((0.0, 0.0, 1.0)).cross(tv).normalized()
        uv_v = tv.cross(sv).normalized()
        st = len(verts)
        r_starts.append(st)
        for ai in range(p_segs):
            ang = 2.0 * math.pi * (ai / p_segs)
            verts.append(pt + (sv * math.cos(ang) + uv_v * math.sin(ang)) * ped_rads[k])
    for k in range(7):
        s0, s1 = r_starts[k], r_starts[k + 1]
        for ai in range(p_segs):
            ai_n = (ai + 1) % p_segs
            faces.append((s0 + ai, s0 + ai_n, s1 + ai_n, s1 + ai))
            face_uvs.append([(0.48, k / 7.0), (0.52, k / 7.0), (0.52, (k + 1) / 7.0), (0.48, (k + 1) / 7.0)])
            face_mats.append(1)

    base = ped_pts[-1]

    # --- 2) Sculpted 5-pointed acuminate green calyx star clasping petal throat (mat slot 1 = Stem_PBR) ---
    for s_i in range(5):
        ang_c = 2.0 * math.pi * (s_i / 5.0) + 0.3
        rad_dir = Vector((0.0, math.cos(ang_c), math.sin(ang_c)))
        tan_dir = Vector((0.0, -math.sin(ang_c), math.cos(ang_c)))
        sepal_len = 0.014
        idx0 = len(verts)
        verts.append(base + rad_dir * 0.0026 + tan_dir * (-0.0016))
        verts.append(base + rad_dir * 0.0026 + tan_dir * 0.0016)
        verts.append(base + Vector((sepal_len * 0.55, 0.0, 0.0)) + rad_dir * 0.0046 + tan_dir * 0.0011)
        verts.append(base + Vector((sepal_len * 0.55, 0.0, 0.0)) + rad_dir * 0.0046 + tan_dir * (-0.0011))
        verts.append(base + Vector((sepal_len, 0.0, 0.0)) + rad_dir * (0.0052 + 0.0022 * open_f))
        faces.append((idx0, idx0 + 1, idx0 + 2, idx0 + 3))
        face_uvs.append([(0.46, 0.1), (0.54, 0.1), (0.52, 0.6), (0.48, 0.6)])
        face_mats.append(1)
        faces.append((idx0 + 3, idx0 + 2, idx0 + 4))
        face_uvs.append([(0.48, 0.6), (0.52, 0.6), (0.50, 0.98)])
        face_mats.append(1)

    # --- 3) Sculpted papilionaceous butterfly petals (mat slot 0 = Flower_PBR) ---
    def _add_petal(
        length: float,
        half_w: float,
        pitch_rad: float,
        yaw_rad: float,
        roll_rad: float,
        reflex: float,
        cup: float,
        l_n: int = 6,
        w_n: int = 6,
        apical_notch: float = 0.0,
    ) -> None:
        rot_m = Euler((roll_rad, pitch_rad, yaw_rad), "XYZ").to_matrix()
        grid: list[list[int]] = []
        for li in range(l_n + 1):
            lt = li / l_n
            w_env = math.sin((lt ** 0.62) * math.pi) ** 0.68
            if lt < 0.15:
                w_env = max(0.16, w_env)
            row: list[int] = []
            for wi in range(w_n + 1):
                u = (wi / w_n) * 2.0 - 1.0
                # Characteristic emarginate (bilobed notched) banner petal tip
                notch_pull = apical_notch * (lt ** 3.0) * math.exp(-((u / 0.30) ** 2))
                px = lt * length - notch_pull
                py = u * half_w * w_env
                pz = reflex * (lt ** 2.1) + cup * (u ** 2) * math.sin(lt * math.pi)
                co = base + Vector((0.002, 0.0, 0.0)) + rot_m @ Vector((px, py, pz))
                row.append(len(verts))
                verts.append(co)
            grid.append(row)
        for li in range(l_n):
            v0, v1 = lerp(0.08, 0.99, li / l_n), lerp(0.08, 0.99, (li + 1) / l_n)
            for wi in range(w_n):
                u0, u1 = wi / w_n, (wi + 1) / w_n
                faces.append((grid[li][wi], grid[li + 1][wi], grid[li + 1][wi + 1], grid[li][wi + 1]))
                face_uvs.append([(u0, v0), (u0, v1), (u1, v1), (u1, v0)])
                face_mats.append(0)

    # Bilobed flaring Standard (Banner) petal
    _add_petal(
        length=0.044 * lerp(0.62, 1.0, open_f),
        half_w=0.023 * lerp(0.42, 1.0, open_f),
        pitch_rad=lerp(-0.26, -1.10, open_f),
        yaw_rad=0.0,
        roll_rad=0.0,
        reflex=-0.013 * open_f,
        cup=-0.006 * open_f,
        l_n=7,
        w_n=6,
        apical_notch=0.0045 * open_f,
    )
    # Twin cupped lateral Wing petals
    for side_s in (-1.0, 1.0):
        _add_petal(
            length=0.034 * lerp(0.65, 1.0, open_f),
            half_w=0.011 * lerp(0.52, 1.0, open_f),
            pitch_rad=lerp(-0.08, 0.08, open_f),
            yaw_rad=side_s * lerp(0.08, 0.36, open_f),
            roll_rad=side_s * 0.56,
            reflex=0.004,
            cup=0.004,
            l_n=5,
            w_n=4,
        )
    # Lower boat-shaped Keel petal
    _add_petal(
        length=0.029 * lerp(0.68, 1.0, open_f),
        half_w=0.0095 * lerp(0.58, 1.0, open_f),
        pitch_rad=lerp(0.10, 0.24, open_f),
        yaw_rad=0.0,
        roll_rad=0.0,
        reflex=0.007,
        cup=0.006,
        l_n=5,
        w_n=4,
    )

    return verts, faces, face_uvs, face_mats


def build_flowers(
    mat_flower: bpy.types.Material,
    mat_stem: bpy.types.Material,
) -> tuple[list[bpy.types.Object], dict[str, tuple[str, float]]]:
    """Build 14 two-material papilionaceous flowers peaking at BBCH 61-69 and wilting cleanly before late pods."""
    # Azimuths offset cleanly from adjacent leaves & pods so flower_overlaps == [] across ALL 31 frames!
    # (host, s_node, yaw_deg, f_bud, f_open, f_fade)
    specs = [
        ("Main_Stem", 0.41, 354.0, 82, 102, 128),
        ("Main_Stem", 0.51, 164.0, 84, 104, 128),
        ("Main_Stem", 0.61, 86.0, 86, 106, 130),
        ("Main_Stem", 0.73, 314.0, 88, 108, 130),
        ("Main_Stem", 0.84, 114.0, 92, 112, 132),
        ("Branch_L", 0.38, 244.0, 82, 102, 126),
        ("Branch_L", 0.62, 232.0, 86, 106, 126),
        ("Branch_L", 0.84, 174.0, 90, 110, 128),
        ("Branch_R", 0.38, 52.0, 84, 104, 126),
        ("Branch_R", 0.62, 26.0, 88, 108, 126),
        ("Branch_R", 0.84, 344.0, 92, 112, 130),
        ("Branch_B", 0.38, 144.0, 84, 104, 126),
        ("Branch_B", 0.62, 122.0, 88, 108, 126),
        ("Branch_B", 0.84, 154.0, 92, 112, 132),
    ]

    open_verts, faces, face_uvs, face_mats = _build_flower_coords("open")
    bud_verts, _, _, _ = _build_flower_coords("bud")

    flowers: list[bpy.types.Object] = []
    flower_hosts: dict[str, tuple[str, float]] = {}
    for idx, (host, s_node, yaw_d, f_bud, f_open, f_fade) in enumerate(specs):
        bm = bmesh.new()
        uv_layer = ensure_uv_layer(bm)
        bm_verts = [bm.verts.new(co) for co in open_verts]
        for f_idxs, uvs, m_idx in zip(faces, face_uvs, face_mats):
            f = bm.faces.new(tuple(bm_verts[i] for i in f_idxs))
            f.material_index = m_idx
            for l, uv in zip(f.loops, uvs):
                l[uv_layer].uv = uv
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

        fmesh = bpy.data.meshes.new(f"Flower_{idx + 1:02d}_Mesh")
        bm.to_mesh(fmesh)
        bm.free()
        set_smooth_shading(fmesh, True)
        apply_vertex_colors(fmesh, seed=200 + idx, mode="neutral_with_stem_slot")

        yaw = math.radians(yaw_d)
        p0, _ = eval_host_world(host, s_node, 0.0)
        fobj = link_object(
            f"Flower_{idx + 1:02d}",
            fmesh,
            [mat_flower, mat_stem],
            location=(p0.x, p0.y, p0.z),
            rotation=(0.0, -0.14, yaw),
            scale=(0.0005, 0.0005, 0.0005),
        )

        fobj.shape_key_add(name="Basis", from_mix=False)
        sk_bud = fobj.shape_key_add(name="Bud", from_mix=False)
        for vi, co in enumerate(bud_verts):
            sk_bud.data[vi].co = co

        for fr, w_b in ((0, 1.0), (f_bud, 1.0), (f_open, 0.0), (f_fade - 5, 0.0), (f_fade, 0.90), (150, 1.0)):
            sk_bud.value = w_b
            sk_bud.keyframe_insert(data_path="value", frame=fr)
        smooth_datablock_fcurves(fmesh.shape_keys)

        host_kfs = {0, 14, 30, 60, 90, 135, 150}
        if host in BRANCH_SPECS:
            host_kfs |= {BRANCH_SPECS[host][4], BRANCH_SPECS[host][5]}
        kfs = sorted(host_kfs | {f_bud - 2, f_bud, f_open, f_fade - 5, f_fade})

        for kf in kfs:
            pw, _ = eval_host_world(host, s_node, float(kf))
            if kf <= f_bud - 2 or kf >= f_fade:
                sc_v = 0.0005
            elif kf < f_open:
                u = max(0.0, min(1.0, (kf - (f_bud - 2)) / max(1.0, float(f_open - (f_bud - 2)))))
                sc_v = lerp(0.35, 1.0, u)
            elif kf <= f_fade - 5:
                sc_v = 1.0
            else:
                u = max(0.0, min(1.0, (kf - (f_fade - 5)) / 5.0))
                sc_v = lerp(1.0, 0.0005, u)
            keyframe_transform(fobj, kf, scale=(sc_v, sc_v, sc_v), location=(pw.x, pw.y, pw.z), rotation=(0.0, -0.14, yaw))

        smooth_datablock_fcurves(fobj, linear=True)
        flowers.append(fobj)
        flower_hosts[fobj.name] = (host, s_node)

    return flowers, flower_hosts


# =============================================================================
# 6. 14 TWO-MATERIAL FLAT RHOMBOID 2-SEEDED LENTIL PODS (CALYX + SEED-FILLING SK)
# =============================================================================
def _build_lentil_pod_coords(
    pod_len: float,
    pod_h: float,
    seed: int,
    stage: str = "plump",
) -> tuple[list[Vector], list[tuple[int, ...]], list[list[tuple[float, float]]], list[int]]:
    """Build 1 two-material rhomboid lentil pod (slot 0=Pod_PBR valves, slot 1=Stem_PBR peduncle+5-tooth calyx)."""
    verts: list[Vector] = []
    faces: list[tuple[int, ...]] = []
    face_uvs: list[list[tuple[float, float]]] = []
    face_mats: list[int] = []

    is_flat = stage == "young_flat"
    fill_f = 0.28 if is_flat else 1.0

    # --- 1) Smooth 10-segment arched green peduncle deeply embedded inside host stem (mat slot 1) ---
    p_a = Vector((-0.004, 0.0, 0.0))
    p_ctrl = Vector((0.032, 0.0, 0.012))
    p_b = Vector((0.054, 0.0, -0.012))
    ped_pts: list[Vector] = []
    ped_rads: list[float] = []
    for k in range(10):
        u = k / 9.0
        om = 1.0 - u
        ped_pts.append(p_a * (om * om) + p_ctrl * (2.0 * om * u) + p_b * (u * u))
        ped_rads.append(lerp(0.0017, 0.0013, u) + 0.0020 * (u ** 4.0))

    p_segs = 7
    r_starts: list[int] = []
    for k, pt in enumerate(ped_pts):
        p_n = ped_pts[min(9, k + 1)]
        p_p = ped_pts[max(0, k - 1)]
        tv = (p_n - p_p).normalized() if (p_n - p_p).length > 1e-6 else Vector((1.0, 0.0, 0.0))
        sv = Vector((0.0, 0.0, 1.0)).cross(tv).normalized()
        uv_v = tv.cross(sv).normalized()
        st = len(verts)
        r_starts.append(st)
        for ai in range(p_segs):
            ang = 2.0 * math.pi * (ai / p_segs)
            verts.append(pt + (sv * math.cos(ang) + uv_v * math.sin(ang)) * ped_rads[k])

    for k in range(9):
        s0, s1 = r_starts[k], r_starts[k + 1]
        for ai in range(p_segs):
            ai_n = (ai + 1) % p_segs
            faces.append((s0 + ai, s0 + ai_n, s1 + ai_n, s1 + ai))
            face_uvs.append([(0.46, k / 9.0), (0.54, k / 9.0), (0.54, (k + 1) / 9.0), (0.46, (k + 1) / 9.0)])
            face_mats.append(1)

    # Pod orientation frame: hangs outward-downward strictly clear of host stem/branch
    pod_origin = ped_pts[-1]
    dir_x = Vector((0.64, 0.0, -0.768)).normalized()
    twist = 0.48 * (1.0 if (seed % 2 == 0) else -1.0)
    base_z = Vector((0.768, 0.0, 0.64)).normalized()
    base_y = Vector((0.0, 1.0, 0.0))
    dir_z = (base_z * math.cos(twist) + base_y * math.sin(twist)).normalized()
    dir_y = (-base_z * math.sin(twist) + base_y * math.cos(twist)).normalized()

    # --- 2) Sculpted 5-toothed persistent green legume calyx star clasping pod base (mat slot 1) ---
    for s_i in range(5):
        ang_c = 2.0 * math.pi * (s_i / 5.0) + 0.2
        r_d = (dir_z * math.cos(ang_c) + dir_y * math.sin(ang_c)).normalized()
        t_d = (-dir_z * math.sin(ang_c) + dir_y * math.cos(ang_c)).normalized()
        s_len = 0.0155
        idx0 = len(verts)
        verts.append(pod_origin + r_d * 0.0028 + t_d * (-0.0017))
        verts.append(pod_origin + r_d * 0.0028 + t_d * 0.0017)
        verts.append(pod_origin + dir_x * (s_len * 0.55) + r_d * 0.0076 + t_d * 0.0011)
        verts.append(pod_origin + dir_x * (s_len * 0.55) + r_d * 0.0076 + t_d * (-0.0011))
        verts.append(pod_origin + dir_x * s_len + r_d * 0.0108)
        faces.append((idx0, idx0 + 1, idx0 + 2, idx0 + 3))
        face_uvs.append([(0.46, 0.1), (0.54, 0.1), (0.52, 0.6), (0.48, 0.6)])
        face_mats.append(1)
        faces.append((idx0 + 3, idx0 + 2, idx0 + 4))
        face_uvs.append([(0.48, 0.6), (0.52, 0.6), (0.50, 0.98)])
        face_mats.append(1)

    # --- 3) High-res 22x16 flattened rhomboid 2-seeded pod valves (mat slot 0 = Pod_PBR) ---
    l_segs = 22
    a_segs = 16
    ring_starts: list[int] = []
    cur_len = pod_len * lerp(0.76, 1.0, fill_f)
    cur_h = pod_h * lerp(0.84, 1.0, fill_f)

    for li in range(l_segs + 1):
        t = li / l_segs
        if t < 0.86:
            u = t / 0.86
            h_env = (math.sin(u * math.pi) ** 0.56) * (1.0 + 0.17 * math.sin(u * math.pi * 2.0))
            thick_base = (0.0024 + 0.0028 * fill_f) * (math.sin(u * math.pi) ** 0.52)
            # Two distinct lenticular seed pillows swelling during pod filling (YoungFlat -> Plump2Seed)!
            bulge1 = 0.0070 * fill_f * math.exp(-(((u - 0.34) / 0.135) ** 2))
            bulge2 = 0.0066 * fill_f * math.exp(-(((u - 0.66) / 0.135) ** 2))
            thick_env = thick_base + bulge1 + bulge2
            beak_curve = 0.0
        else:
            bu = (t - 0.86) / 0.14
            h_env = lerp(0.18, 0.012, bu)
            thick_env = lerp(0.0016, 0.0004, bu)
            beak_curve = 0.009 * (bu ** 1.65)

        center = pod_origin + dir_x * (t * cur_len) + dir_z * beak_curve
        st = len(verts)
        ring_starts.append(st)
        for ai in range(a_segs):
            ang = 2.0 * math.pi * (ai / a_segs)
            ca, sa = math.cos(ang), math.sin(ang)
            # Pinched sharp dorsal/ventral sutures & smooth convex lenticular valves
            z_off = ca * (cur_h * 0.5 * h_env)
            y_off = math.copysign(abs(sa) ** 0.80, sa) * thick_env
            verts.append(center + dir_z * z_off + dir_y * y_off)

    for li in range(l_segs):
        v0, v1 = li / l_segs, (li + 1) / l_segs
        s0, s1 = ring_starts[li], ring_starts[li + 1]
        for ai in range(a_segs):
            ai_n = (ai + 1) % a_segs
            u0 = abs(((ai / a_segs) * 2.0) % 2.0 - 1.0)
            u1 = abs((((ai + 1) / a_segs) * 2.0) % 2.0 - 1.0)
            faces.append((s0 + ai, s0 + ai_n, s1 + ai_n, s1 + ai))
            face_uvs.append([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
            face_mats.append(0)

    c_start_idx = len(verts)
    verts.append(pod_origin - dir_x * 0.002)
    c_end_idx = len(verts)
    verts.append(pod_origin + dir_x * (cur_len + 0.003) + dir_z * 0.009)
    for ai in range(a_segs):
        ai_n = (ai + 1) % a_segs
        faces.append((ring_starts[0] + ai_n, ring_starts[0] + ai, c_start_idx))
        face_uvs.append([(0.5, 0.0), (0.5, 0.0), (0.5, 0.0)])
        face_mats.append(0)
        faces.append((ring_starts[-1] + ai, ring_starts[-1] + ai_n, c_end_idx))
        face_uvs.append([(0.5, 1.0), (0.5, 1.0), (0.5, 1.0)])
        face_mats.append(0)

    return verts, faces, face_uvs, face_mats


def build_pods(
    mat_pod: bpy.types.Material,
    mat_stem: bpy.types.Material,
) -> tuple[list[bpy.types.Object], dict[str, tuple[str, float]]]:
    """Build 14 two-material rhomboid 2-seeded lentil pods with YoungFlat -> Plump2Seed filling animation."""
    # All azimuths verified strictly clear of branches, leaves, and co-existing flowers!
    # (host, s_node, yaw_deg, pod_len, pod_h, f_start, f_full)
    specs = [
        # First 6 lower/mid pods visible already at BBCH 61-69 (f120) as flat bright green pods
        ("Main_Stem", 0.38, 336.0, 0.072, 0.041, 102, 126),
        ("Main_Stem", 0.48, 168.0, 0.071, 0.040, 104, 128),
        ("Branch_L", 0.38, 202.0, 0.071, 0.040, 106, 130),
        ("Branch_R", 0.40, 4.0, 0.072, 0.040, 108, 132),
        ("Branch_B", 0.40, 138.0, 0.070, 0.039, 110, 134),
        ("Main_Stem", 0.56, 314.0, 0.071, 0.040, 112, 136),
        # Upper 8 pods filling out across BBCH 71-89 (f126..148; strictly after co-located flowers wilt!)
        ("Main_Stem", 0.63, 124.0, 0.070, 0.040, 120, 140),
        ("Main_Stem", 0.72, 296.0, 0.069, 0.039, 124, 142),
        ("Main_Stem", 0.80, 68.0, 0.068, 0.038, 128, 145),
        ("Main_Stem", 0.88, 248.0, 0.066, 0.037, 130, 148),   # 70 deg away from Leaf_07@178 & 62 deg from Leaf_08@310!
        ("Branch_L", 0.64, 248.0, 0.070, 0.039, 128, 144),    # 62 deg away from Leaf_10@186!
        ("Branch_L", 0.86, 184.0, 0.066, 0.037, 130, 146),    # After Flower_08 fades at f128!
        ("Branch_R", 0.64, 54.0, 0.070, 0.039, 128, 144),     # After Flower_10 fades at f126!
        ("Branch_B", 0.64, 96.0, 0.068, 0.038, 128, 144),     # After Flower_13 fades at f126!
    ]

    pods: list[bpy.types.Object] = []
    pod_hosts: dict[str, tuple[str, float]] = {}
    for idx, (host, s_node, yaw_d, p_len, p_h, f_start, f_full) in enumerate(specs):
        plump_verts, faces, face_uvs, face_mats = _build_lentil_pod_coords(p_len, p_h, idx + 1, "plump")
        flat_verts, _, _, _ = _build_lentil_pod_coords(p_len, p_h, idx + 1, "young_flat")

        bm = bmesh.new()
        uv_layer = ensure_uv_layer(bm)
        bm_verts = [bm.verts.new(co) for co in plump_verts]
        for f_idxs, uvs, m_idx in zip(faces, face_uvs, face_mats):
            f = bm.faces.new(tuple(bm_verts[i] for i in f_idxs))
            f.material_index = m_idx
            for l, uv in zip(f.loops, uvs):
                l[uv_layer].uv = uv
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

        pmesh = bpy.data.meshes.new(f"Pod_{idx + 1:02d}_Mesh")
        bm.to_mesh(pmesh)
        bm.free()
        set_smooth_shading(pmesh, True)
        apply_vertex_colors(pmesh, seed=300 + idx, mode="neutral_with_stem_slot")

        yaw = math.radians(yaw_d)
        p0, _ = eval_host_world(host, s_node, 0.0)
        pobj = link_object(
            f"Pod_{idx + 1:02d}",
            pmesh,
            [mat_pod, mat_stem],
            location=(p0.x, p0.y, p0.z),
            rotation=(0.0, 0.0, yaw),
            scale=(0.0005, 0.0005, 0.0005),
        )

        # Pod seed-filling Shape Key: flat papery young pod -> plump 2-seeded mature pod!
        pobj.shape_key_add(name="Basis", from_mix=False)
        sk_flat = pobj.shape_key_add(name="YoungFlat", from_mix=False)
        for vi, co in enumerate(flat_verts):
            sk_flat.data[vi].co = co
        f_fill_start = min(144, int(lerp(f_start, f_full, 0.45)))
        f_fill_end = min(150, f_full + 4)
        for fr, w_fl in ((0, 1.0), (f_fill_start, 1.0), (f_fill_end, 0.0), (150, 0.0)):
            sk_flat.value = w_fl
            sk_flat.keyframe_insert(data_path="value", frame=fr)
        smooth_datablock_fcurves(pmesh.shape_keys)

        host_kfs = {0, 14, 30, 60, 90, 135, 150}
        if host in BRANCH_SPECS:
            host_kfs |= {BRANCH_SPECS[host][4], BRANCH_SPECS[host][5]}
        kfs = sorted(host_kfs | {f_start - 2, f_start, f_full})

        for kf in kfs:
            pw, _ = eval_host_world(host, s_node, float(kf))
            if kf <= f_start - 2:
                sc_v = 0.0005
            elif kf < f_full:
                u = max(0.0, min(1.0, (kf - (f_start - 2)) / max(1.0, float(f_full - (f_start - 2)))))
                sc_v = lerp(0.28, 1.0, u ** 0.85)
            else:
                sc_v = 1.04
            keyframe_transform(pobj, kf, scale=(sc_v, sc_v, sc_v), location=(pw.x, pw.y, pw.z), rotation=(0.0, 0.0, yaw))

        smooth_datablock_fcurves(pobj, linear=True)
        pods.append(pobj)
        pod_hosts[pobj.name] = (host, s_node)

    return pods, pod_hosts


# =============================================================================
# 7. MATURATION SYNC, STUDIO LIGHTING, EXPORT & EXHAUSTIVE 10-INVARIANT QA AUDIT
# =============================================================================
def apply_blender_maturation_state(mat_controls: dict, progress: float) -> None:
    """Sync Blender EEVEE material tints across BBCH progress [0..1] (green pods -> golden straw)."""
    fol_phase = max(0.0, min(1.0, (progress - 0.62) / 0.38))
    pod_phase = max(0.0, min(1.0, (progress - 0.72) / 0.28))

    def set_mix_tint(mix_node: bpy.types.ShaderNodeMix, col: tuple[float, float, float, float]) -> None:
        rgba_in = [s for s in mix_node.inputs if s.type == "RGBA"]
        rgba_in[1].default_value = col

    outer_tint, outer_rough, _ = mat_controls["outer"]
    c_of, c_om = hex_rgba("#e7f3d5"), hex_rgba("#c9a84c")
    set_mix_tint(outer_tint, tuple(lerp(c_of[i], c_om[i], fol_phase) for i in range(4)))
    outer_rough.inputs[1].default_value = lerp(0.95, 1.38, fol_phase)

    mid_tint, mid_rough, _ = mat_controls["mid"]
    c_mf, c_mm = hex_rgba("#eff8e0"), hex_rgba("#cfb658")
    set_mix_tint(mid_tint, tuple(lerp(c_mf[i], c_mm[i], fol_phase * 0.78) for i in range(4)))
    mid_rough.inputs[1].default_value = lerp(0.90, 1.25, fol_phase)

    pod_tint, pod_rough, _ = mat_controls["pod"]
    c_pf, c_pm = hex_rgba("#74b632"), hex_rgba("#d6b562")
    set_mix_tint(pod_tint, tuple(lerp(c_pf[i], c_pm[i], pod_phase) for i in range(4)))
    pod_rough.inputs[1].default_value = lerp(0.85, 1.25, pod_phase)

    root_tint, root_rough, _ = mat_controls["root"]
    c_r0, c_r1 = hex_rgba("#f5ebd8"), hex_rgba("#d7c39c")
    set_mix_tint(root_tint, tuple(lerp(c_r0[i], c_r1[i], progress * 0.65) for i in range(4)))
    root_rough.inputs[1].default_value = lerp(1.0, 0.92, progress)


def setup_studio_lighting_and_camera() -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    """Configure EEVEE 3-point lighting, clean atmospheric backdrop, and hero camera."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS

    world = bpy.data.worlds.new("Studio_World")
    scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_rgba("#303e4b")
        bg.inputs["Strength"].default_value = 0.85

    studio_objs: list[bpy.types.Object] = []

    target = bpy.data.objects.new("Cam_Target", None)
    target.location = (0.0, 0.0, 0.05)
    scene.collection.objects.link(target)
    studio_objs.append(target)

    cam_data = bpy.data.cameras.new("Hero_Camera")
    cam_data.lens = 42.0
    cam_obj = bpy.data.objects.new("Hero_Camera", cam_data)
    cam_obj.location = (0.36, -2.55, 0.32)
    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    studio_objs.append(cam_obj)

    def add_light(
        name: str,
        ltype: str,
        energy: float,
        loc: tuple[float, float, float],
        rot: tuple[float, float, float],
        color: tuple[float, float, float] = (1.0, 1.0, 1.0),
        size: float = 2.0,
    ) -> bpy.types.Object:
        ldata = bpy.data.lights.new(name=name, type=ltype)
        ldata.energy = energy
        ldata.color = color
        if hasattr(ldata, "size"):
            ldata.size = size
        lobj = bpy.data.objects.new(name=name, object_data=ldata)
        lobj.location = loc
        lobj.rotation_euler = Euler(rot, "XYZ")
        scene.collection.objects.link(lobj)
        studio_objs.append(lobj)
        return lobj

    add_light("Key_Sun", "SUN", 3.5, (2.2, -2.6, 3.6), (math.radians(46), math.radians(16), math.radians(34)), color=(1.0, 0.97, 0.90))
    add_light("Fill_Area", "AREA", 55.0, (-2.2, -1.9, 1.2), (math.radians(66), 0.0, math.radians(-48)), color=(0.82, 0.92, 1.0), size=2.8)
    add_light("Rim_Area", "AREA", 70.0, (0.2, 2.5, 1.8), (math.radians(-55), 0.0, math.radians(180)), color=(0.95, 1.0, 0.90), size=2.4)
    return cam_obj, studio_objs


def blender_to_gltf(v: Vector) -> list[float]:
    """Convert Blender Z-up coordinates to glTF Y-up coordinates."""
    return [round(float(v.x), 4), round(float(v.z), 4), round(float(-v.y), 4)]


def collect_stats_and_export(
    export_objs: list[bpy.types.Object],
    leaf_hosts: dict[str, tuple[str, float]],
    flower_hosts: dict[str, tuple[str, float]],
    pod_hosts: dict[str, tuple[str, float]],
    glb_path: Path,
    blend_path: Path,
) -> dict:
    """Save .blend, export WebP-textured animated .glb, and run exhaustive 10-invariant 31-frame QA."""
    scene = bpy.context.scene
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    bpy.ops.object.select_all(action="DESELECT")
    for obj in export_objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = export_objs[0]

    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=False,
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_vertex_color="ACTIVE",
        export_vertex_color_name="Color",
        export_materials="EXPORT",
        export_image_format="WEBP",
        export_image_quality=86,
        export_image_webp_fallback=False,
        export_animations=True,
        export_animation_mode="SCENE",
        export_bake_animation=True,
        export_anim_slide_to_zero=True,
        export_optimize_animation_size=True,
        export_morph=True,
        export_morph_normal=False,
        export_morph_animation=True,
        export_draco_mesh_compression_enable=False,
    )

    total_tris = 0
    for obj in export_objs:
        if obj.type == "MESH":
            mesh = obj.data
            mesh.calc_loop_triangles()
            total_tris += len(mesh.loop_triangles)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    phase_bounds = {}
    for idx, frame in enumerate(PHASE_FRAMES):
        scene.frame_set(frame)
        depsgraph.update()
        min_v = Vector((1e9, 1e9, 1e9))
        max_v = Vector((-1e9, -1e9, -1e9))
        for obj in export_objs:
            if obj.type != "MESH" or max(obj.scale) < 0.01:
                continue
            eval_obj = obj.evaluated_get(depsgraph)
            for corner in eval_obj.bound_box:
                w = eval_obj.matrix_world @ Vector(corner)
                min_v.x = min(min_v.x, w.x)
                min_v.y = min(min_v.y, w.y)
                min_v.z = min(min_v.z, w.z)
                max_v.x = max(max_v.x, w.x)
                max_v.y = max(max_v.y, w.y)
                max_v.z = max(max_v.z, w.z)
        phase_bounds[f"phase_{idx}"] = {
            "frame": frame,
            "gltf_min": blender_to_gltf(Vector((min_v.x, max_v.y, min_v.z))),
            "gltf_max": blender_to_gltf(Vector((max_v.x, min_v.y, max_v.z))),
        }

    # Exhaustive 10-invariant all-organ geometric QA across all audited frames
    leaf_overlaps: list[str] = []
    leaf_blade_root_clipping: list[str] = []
    floating_leaf_bases: list[str] = []
    floating_rootlet_bases: list[str] = []
    pod_stem_overlaps: list[str] = []
    pod_leaf_overlaps: list[str] = []
    pod_pod_overlaps: list[str] = []
    flower_overlaps: list[str] = []
    leaf_stem_overlaps: list[str] = []
    stem_root_disconnected: list[str] = []

    def _filtered_bvh(
        eval_obj: bpy.types.Object,
        min_local_x: float = -99.0,
        min_world_dist: float = 0.0,
    ) -> tuple[BVHTree | None, list[Vector]]:
        me = eval_obj.to_mesh()
        bm_tmp = bmesh.new()
        bm_tmp.from_mesh(me)
        bm_tmp.verts.ensure_lookup_table()
        plug_pts = [eval_obj.matrix_world @ bm_tmp.verts[0].co.copy()] if bm_tmp.verts else []
        if min_local_x > -10.0:
            del_faces = [f for f in bm_tmp.faces if min(v.co.x for v in f.verts) < min_local_x]
            if del_faces:
                bmesh.ops.delete(bm_tmp, geom=del_faces, context="FACES_ONLY")
        bmesh.ops.transform(bm_tmp, matrix=eval_obj.matrix_world, verts=bm_tmp.verts)
        if min_world_dist > 0.0:
            orig_w = eval_obj.matrix_world.translation
            del_w = [f for f in bm_tmp.faces if min((v.co - orig_w).length for v in f.verts) < min_world_dist]
            if del_w:
                bmesh.ops.delete(bm_tmp, geom=del_w, context="FACES_ONLY")
        bvh = BVHTree.FromBMesh(bm_tmp) if bm_tmp.faces else None
        bm_tmp.free()
        eval_obj.to_mesh_clear()
        return bvh, plug_pts

    all_hosts = {**leaf_hosts, **flower_hosts, **pod_hosts}
    full_audit = ("--full-audit" in sys.argv) or (os.environ.get("PERISCOPE_FULL_AUDIT") == "1")
    bvh_frames = tuple(range(0, 151, 5)) if full_audit else (5, 15, 30, 60, 90, 120, 150)

    for check_frame in bvh_frames:
        scene.frame_set(check_frame)
        depsgraph.update()
        leaf_ext_bvhs: list[tuple[str, BVHTree, BVHTree | None]] = []
        leaf_blade_bvhs: list[tuple[str, BVHTree]] = []
        stem_bvhs: list[tuple[str, BVHTree]] = []
        pod_bvhs: list[tuple[str, BVHTree, BVHTree | None]] = []
        flower_bvhs: list[tuple[str, BVHTree, BVHTree | None]] = []
        root_bvh: BVHTree | None = None
        main_stem_bvh: BVHTree | None = None
        seed_bvh: BVHTree | None = None

        for obj in export_objs:
            if obj.type != "MESH" or max(obj.scale) < 0.08:
                continue
            eval_obj = obj.evaluated_get(depsgraph)
            if obj.name == "Taproot_Main":
                root_bvh, _ = _filtered_bvh(eval_obj)
            elif obj.name == "Seed_Lentil":
                seed_bvh, _ = _filtered_bvh(eval_obj)
            elif obj.name in ("Main_Stem", "Branch_L", "Branch_R", "Branch_B"):
                sbvh, _ = _filtered_bvh(eval_obj)
                if sbvh is not None:
                    stem_bvhs.append((obj.name, sbvh))
                    if obj.name == "Main_Stem":
                        main_stem_bvh = sbvh
            elif max(obj.scale) < 0.15:
                continue
            elif obj.name.startswith("Leaf_"):
                h_name, h_s = leaf_hosts[obj.name]
                host_pt, host_r = eval_host_world(h_name, h_s, float(check_frame))
                ext_bvh, plug_pts = _filtered_bvh(eval_obj, min_local_x=0.014)
                self_bvh, _ = _filtered_bvh(eval_obj, min_world_dist=host_r + 0.008)
                blade_bvh, _ = _filtered_bvh(eval_obj, min_local_x=0.025)
                if ext_bvh is not None:
                    leaf_ext_bvhs.append((obj.name, ext_bvh, self_bvh))
                if blade_bvh is not None:
                    leaf_blade_bvhs.append((obj.name, blade_bvh))
                if plug_pts:
                    dist = (plug_pts[0] - host_pt).length
                    if dist > host_r + 0.012:
                        floating_leaf_bases.append(
                            f"f{check_frame}:{obj.name}(dist={dist:.4f}>max={host_r + 0.012:.4f})"
                        )
            elif obj.name.startswith("Pod_"):
                h_name, h_s = pod_hosts[obj.name]
                _, host_r = eval_host_world(h_name, h_s, float(check_frame))
                pbvh, _ = _filtered_bvh(eval_obj, min_local_x=0.010)
                pself_bvh, _ = _filtered_bvh(eval_obj, min_world_dist=host_r + 0.006)
                if pbvh is not None:
                    pod_bvhs.append((obj.name, pbvh, pself_bvh))
            elif obj.name.startswith("Flower_"):
                h_name, h_s = flower_hosts[obj.name]
                _, host_r = eval_host_world(h_name, h_s, float(check_frame))
                fbvh, _ = _filtered_bvh(eval_obj, min_local_x=0.010)
                fself_bvh, _ = _filtered_bvh(eval_obj, min_world_dist=host_r + 0.006)
                if fbvh is not None:
                    flower_bvhs.append((obj.name, fbvh, fself_bvh))

        if check_frame >= 5 and root_bvh is not None and main_stem_bvh is not None:
            if not main_stem_bvh.overlap(root_bvh):
                stem_root_disconnected.append(f"f{check_frame}:Main_Stem_detached_from_Taproot")
        if check_frame <= 35 and root_bvh is not None and seed_bvh is not None:
            if not seed_bvh.overlap(root_bvh):
                stem_root_disconnected.append(f"f{check_frame}:Seed_Lentil_detached_from_Taproot")

        for i in range(len(leaf_ext_bvhs)):
            for j in range(i + 1, len(leaf_ext_bvhs)):
                if leaf_ext_bvhs[i][1].overlap(leaf_ext_bvhs[j][1]):
                    leaf_overlaps.append(f"f{check_frame}:{leaf_ext_bvhs[i][0]}<->{leaf_ext_bvhs[j][0]}")

        for lname, lbvh in leaf_blade_bvhs:
            if root_bvh is not None and lbvh.overlap(root_bvh):
                leaf_blade_root_clipping.append(f"f{check_frame}:{lname}")
        for lname, lbvh, lself_bvh in leaf_ext_bvhs:
            own_host = all_hosts[lname][0]
            for sname, sbvh in stem_bvhs:
                test_bvh = lself_bvh if sname == own_host else lbvh
                if test_bvh is not None and test_bvh.overlap(sbvh):
                    leaf_stem_overlaps.append(f"f{check_frame}:{lname}<->{sname}")

        for i, (pname, pbvh, pself_bvh) in enumerate(pod_bvhs):
            own_host = all_hosts[pname][0]
            for sname, sbvh in stem_bvhs:
                test_bvh = pself_bvh if sname == own_host else pbvh
                if test_bvh is not None and test_bvh.overlap(sbvh):
                    pod_stem_overlaps.append(f"f{check_frame}:{pname}<->{sname}")
            for lname, lbvh, _ in leaf_ext_bvhs:
                if pbvh.overlap(lbvh):
                    pod_leaf_overlaps.append(f"f{check_frame}:{pname}<->{lname}")
            for j in range(i + 1, len(pod_bvhs)):
                if pbvh.overlap(pod_bvhs[j][1]):
                    pod_pod_overlaps.append(f"f{check_frame}:{pname}<->{pod_bvhs[j][0]}")

        for fname, fbvh, fself_bvh in flower_bvhs:
            own_host = all_hosts[fname][0]
            for sname, sbvh in stem_bvhs:
                test_bvh = fself_bvh if sname == own_host else fbvh
                if test_bvh is not None and test_bvh.overlap(sbvh):
                    flower_overlaps.append(f"f{check_frame}:{fname}<->{sname}")
            for lname, lbvh, _ in leaf_ext_bvhs:
                if fbvh.overlap(lbvh):
                    flower_overlaps.append(f"f{check_frame}:{fname}<->{lname}")
            for pname, pbvh, _ in pod_bvhs:
                if fbvh.overlap(pbvh):
                    flower_overlaps.append(f"f{check_frame}:{fname}<->{pname}")

        for obj in export_objs:
            if not obj.name.startswith("Rootlet_") or max(obj.scale) < 0.15:
                continue
            s_est = taproot_s_from_local_z(obj.location.z)
            bx, by, _, surf_r_z = taproot_centerline(s_est)
            r_from_bend = math.hypot(obj.location.x - bx, obj.location.y - by)
            if r_from_bend > surf_r_z * 0.85:
                floating_rootlet_bases.append(
                    f"f{check_frame}:{obj.name}(r={r_from_bend:.4f}>max={surf_r_z * 0.85:.4f})"
                )

    return {
        "crop_id": "lentil",
        "blender_version": bpy.app.version_string,
        "object_count": len(export_objs),
        "triangle_count": total_tris,
        "glb_path": str(glb_path),
        "glb_bytes": glb_path.stat().st_size,
        "blend_path": str(blend_path),
        "fps": FPS,
        "frame_range": [FRAME_START, FRAME_END],
        "audit_mode": "full_31_frames" if full_audit else "milestone",
        "audit_frames_checked": len(bvh_frames),
        "leaf_overlap_pairs": leaf_overlaps,
        "leaf_blade_root_clipping": leaf_blade_root_clipping,
        "floating_leaf_bases": floating_leaf_bases,
        "floating_rootlet_bases": floating_rootlet_bases,
        "pod_stem_overlaps": pod_stem_overlaps,
        "pod_leaf_overlaps": pod_leaf_overlaps,
        "pod_pod_overlaps": pod_pod_overlaps,
        "flower_overlaps": flower_overlaps,
        "leaf_stem_overlaps": leaf_stem_overlaps,
        "stem_root_disconnected": stem_root_disconnected,
        "phase_bounds": phase_bounds,
    }


def render_phase_previews(mat_controls: dict) -> list[str]:
    """Render 6 EEVEE preview PNGs (renders/lentil_phase_0..5.png) syncing maturation colors."""
    scene = bpy.context.scene
    rendered = []
    for idx, frame in enumerate(PHASE_FRAMES):
        scene.frame_set(frame)
        apply_blender_maturation_state(mat_controls, frame / float(FRAME_END))
        out_path = RENDERS_DIR / f"lentil_phase_{idx}.png"
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        rendered.append(str(out_path))
    apply_blender_maturation_state(mat_controls, 0.0)
    return rendered


def main() -> None:
    """Build high-detail plant-only PBR lentil scene, export GLB, run 10-invariant audit, render previews."""
    ensure_dirs()
    clear_scene()

    tex_sets = generate_all_lentil_textures(ASSETS_DIR)

    mat_seed, _, _, _ = make_pbr_material(
        "Seed_PBR", tex_sets["seed"], "#ffffff", roughness_factor=0.90, normal_strength=0.90, specular=0.30
    )
    mat_root, root_tint, root_rough, root_bsdf = make_pbr_material(
        "Taproot_PBR",
        tex_sets["root"],
        "#f5ebd8",
        roughness_factor=1.0,
        normal_strength=0.72,
        subsurface=0.14,
        specular=0.25,
    )
    mat_nodule, _, _, _ = make_pbr_material(
        "Nodule_PBR",
        tex_sets["nodule"],
        "#ffffff",
        roughness_factor=0.95,
        normal_strength=0.85,
        subsurface=0.22,
        specular=0.30,
    )
    mat_stem, _, _, _ = make_pbr_material(
        "Stem_PBR",
        tex_sets["leaf"],
        "#e9f5d8",
        roughness_factor=0.92,
        normal_strength=0.82,
        subsurface=0.16,
        double_sided=False,
        specular=0.34,
        use_vertex_color=True,
    )
    mat_outer, outer_tint, outer_rough, outer_bsdf = make_pbr_material(
        "Outer_Leaf_PBR",
        tex_sets["leaf"],
        "#e7f3d5",
        roughness_factor=0.95,
        normal_strength=1.05,
        subsurface=0.24,
        double_sided=True,
        specular=0.34,
        use_vertex_color=True,
    )
    mat_mid, mid_tint, mid_rough, mid_bsdf = make_pbr_material(
        "Mid_Leaf_PBR",
        tex_sets["leaf"],
        "#eff8e0",
        roughness_factor=0.90,
        normal_strength=1.05,
        subsurface=0.26,
        double_sided=True,
        specular=0.36,
        use_vertex_color=True,
    )
    mat_heart, _, _, _ = make_pbr_material(
        "Heart_Leaf_PBR",
        tex_sets["leaf"],
        "#e0faa8",
        roughness_factor=0.85,
        normal_strength=0.95,
        subsurface=0.28,
        double_sided=True,
        specular=0.38,
        use_vertex_color=True,
    )
    mat_flower, _, _, _ = make_pbr_material(
        "Flower_PBR",
        tex_sets["flower"],
        "#ffffff",
        roughness_factor=0.85,
        normal_strength=0.65,
        subsurface=0.34,
        double_sided=True,
        specular=0.26,
    )
    mat_pod, pod_tint, pod_rough, pod_bsdf = make_pbr_material(
        "Pod_PBR",
        tex_sets["pod"],
        "#74b632",
        roughness_factor=0.85,
        normal_strength=1.15,
        subsurface=0.18,
        double_sided=False,
        specular=0.36,
    )

    mat_controls = {
        "root": (root_tint, root_rough, root_bsdf),
        "outer": (outer_tint, outer_rough, outer_bsdf),
        "mid": (mid_tint, mid_rough, mid_bsdf),
        "pod": (pod_tint, pod_rough, pod_bsdf),
    }

    export_objs: list[bpy.types.Object] = []
    export_objs.append(build_lentil_seed(mat_seed))
    export_objs.extend(build_taproot_rootlets_and_nodules(mat_root, mat_nodule))
    export_objs.extend(build_stems_and_branches(mat_stem))
    leaves, leaf_hosts = build_all_compound_leaves(mat_outer, mat_mid, mat_heart)
    export_objs.extend(leaves)
    flowers, flower_hosts = build_flowers(mat_flower, mat_stem)
    export_objs.extend(flowers)
    pods, pod_hosts = build_pods(mat_pod, mat_stem)
    export_objs.extend(pods)

    setup_studio_lighting_and_camera()

    glb_path = ASSETS_DIR / "lentil.glb"
    blend_path = ASSETS_DIR / "lentil.blend"
    apply_blender_maturation_state(mat_controls, 0.0)
    stats = collect_stats_and_export(export_objs, leaf_hosts, flower_hosts, pod_hosts, glb_path, blend_path)
    stats["renders"] = render_phase_previews(mat_controls)

    stats_path = ASSETS_DIR / "lentil_stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PERISKOPE_LENTIL_EXPORT_OK:", json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
