"""Detailed Plant-Only Sugar Beet (Beta vulgaris) PBR & Maturation Generator for Blender 5.2 LTS.

Generates a 360-degree rotatable sugar beet specimen without 3D soil geometry:
- Swelling/cracking seed pellet (Shape Key 'Split')
- Pinkish hypocotyl & twin glossy cotyledons
- Conical taproot with helical sugar grooves, crown collar & 18 branched 360-deg rootlets
- 20 phyllotaxis rosette leaves with 3D grooved petioles, curved lateral veins, and
  Unfold + MatureCurl Shape Keys + 3-tier maturation colors
Exports a compact WebP-textured animated GLB and renders 6 EEVEE phase previews.
"""

from __future__ import annotations

import json
import math
import os
import random
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

from pbr_textures import PBRTextureSet, generate_all_pbr_textures  # noqa: E402

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
            bsdf.inputs["Subsurface Scale"].default_value = 0.018

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
    material: bpy.types.Material,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> bpy.types.Object:
    """Create object, assign material, link to scene collection, return object."""
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler = Euler(rotation, "XYZ")
    obj.scale = scale
    if mesh.materials:
        mesh.materials[0] = material
    else:
        mesh.materials.append(material)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def set_smooth_shading(mesh: bpy.types.Mesh, smooth: bool = True) -> None:
    """Set polygon smooth shading cleanly without bpy.ops."""
    for poly in mesh.polygons:
        poly.use_smooth = smooth


def smooth_datablock_fcurves(datablock: bpy.types.ID) -> None:
    """Apply BEZIER + AUTO_CLAMPED handles using Blender 5.2 channelbag API."""
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


def build_seed_pellet(mat_seed: bpy.types.Material) -> bpy.types.Object:
    """Create smooth coated sugar beet pellet at (0, 0, -0.14) with cracking Shape Key."""
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=0.056)
    for v in bm.verts:
        bump = 1.0 + 0.08 * math.sin(v.co.x * 38.0) * math.cos(v.co.y * 34.0)
        v.co.x *= 1.15 * bump
        v.co.y *= 0.96 * bump
        v.co.z *= 0.84 * bump
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        for l in f.loops:
            co = l.vert.co
            u = 0.5 + math.atan2(co.y, co.x) / (2.0 * math.pi)
            v = 0.5 + co.z / 0.12
            l[uv_layer].uv = (u, v)

    mesh = bpy.data.meshes.new("Seed_Pellet_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    set_smooth_shading(mesh, True)

    seed_obj = link_object("Seed_Pellet", mesh, mat_seed, location=(0.0, 0.0, -0.14))

    seed_obj.shape_key_add(name="Basis", from_mix=False)
    sk_split = seed_obj.shape_key_add(name="Split", from_mix=False)
    for i, v in enumerate(mesh.vertices):
        co = v.co.copy()
        co *= 1.18
        if co.z < 0.0:
            gap = 0.016 * (-co.z / 0.05)
            co.x += gap if co.x >= 0.0 else -gap
        sk_split.data[i].co = co

    sk_split.value = 0.0
    sk_split.keyframe_insert(data_path="value", frame=0)
    sk_split.value = 0.95
    sk_split.keyframe_insert(data_path="value", frame=14)
    sk_split.value = 1.0
    sk_split.keyframe_insert(data_path="value", frame=28)
    smooth_datablock_fcurves(mesh.shape_keys)

    keyframe_transform(seed_obj, 0, scale=(1.0, 1.0, 1.0), location=(0.0, 0.0, -0.14))
    keyframe_transform(seed_obj, 16, scale=(1.12, 1.12, 1.10), location=(0.0, 0.0, -0.14))
    keyframe_transform(seed_obj, 28, scale=(0.0005, 0.0005, 0.0005), location=(0.0, 0.0, -0.14))
    keyframe_transform(seed_obj, 150, scale=(0.0005, 0.0005, 0.0005), location=(0.0, 0.0, -0.14))
    smooth_datablock_fcurves(seed_obj)
    return seed_obj


TAPROOT_KEYFRAMES: list[tuple[int, tuple[float, float, float], tuple[float, float, float]]] = [
    (0, (0.055, 0.055, 0.14), (0.0, 0.0, -0.15)),
    (14, (0.075, 0.075, 0.24), (0.0, 0.0, -0.10)),
    (30, (0.11, 0.11, 0.38), (0.0, 0.0, -0.025)),
    (60, (0.36, 0.36, 0.62), (0.0, 0.0, 0.004)),
    (90, (0.62, 0.62, 0.82), (0.0, 0.0, 0.006)),
    (120, (0.86, 0.86, 0.95), (0.0, 0.0, 0.008)),
    (150, (1.04, 1.04, 1.02), (0.0, 0.0, 0.010)),
]


def taproot_profile(s: float) -> tuple[float, float]:
    """Return (radius, local_z) of anatomical 3-zone Beta vulgaris crown, pear shoulder, & taproot."""
    if s < 0.15:
        t = s / 0.15
        k_ang = math.pi * 0.43
        r = 0.172 * ((math.sin(t * k_ang) / math.sin(k_ang)) ** 0.85)
        z = 0.074 - 0.082 * (t ** 1.35)
        return r, z
    if s < 0.32:
        t = (s - 0.15) / 0.17
        r = lerp(0.172, 0.184, t) + 0.026 * math.sin(t * math.pi)
        z = lerp(-0.008, -0.220, t)
        return r, z
    if s < 0.72:
        t = (s - 0.32) / 0.40
        return lerp(0.184, 0.056, t ** 0.92), lerp(-0.220, -0.575, t)
    t = (s - 0.72) / 0.28
    return lerp(0.056, 0.0035, t ** 0.86), lerp(-0.575, -0.860, t)


def taproot_radius(s: float) -> float:
    """Normalized sugar beet conical profile radius from crown top (s=0) to tail tip (s=1)."""
    return taproot_profile(s)[0]


def taproot_s_from_local_z(lz: float) -> float:
    """Invert local Z to profile parameter s in [0..1] for rootlet anchoring and QA."""
    if lz >= -0.008:
        u = max(0.0, min(1.0, (0.074 - lz) / 0.082))
        return 0.15 * (u ** (1.0 / 1.35))
    if lz >= -0.220:
        return 0.15 + 0.17 * (lz + 0.008) / (-0.220 + 0.008)
    if lz >= -0.575:
        return 0.32 + 0.40 * (lz + 0.220) / (-0.575 + 0.220)
    return max(0.0, min(1.0, 0.72 + 0.28 * (lz + 0.575) / (-0.860 + 0.575)))


def taproot_surface_sample(s: float, theta: float) -> tuple[float, float, float, float]:
    """Return (actual_radius, z, bend_x, bend_y) including grooves, asymmetry, and crown leaf scars."""
    base_r, z = taproot_profile(s)
    bend_x = 0.032 * (max(0.0, s - 0.48) / 0.52) ** 1.55
    bend_y = -0.018 * (max(0.0, s - 0.60) / 0.40) ** 1.50

    groove_theta = theta - 0.24 * s
    groove_strength = math.exp(-((math.sin(groove_theta)) ** 2) / 0.062)
    groove_mask = math.sin(min(1.0, max(0.0, (s - 0.16) / 0.78)) * math.pi)
    groove_cut = 0.185 * groove_strength * groove_mask

    sin_s = math.sin(min(1.0, max(0.0, s)) * math.pi)
    asym_2 = 0.024 * math.cos(2.0 * theta + 0.65 - 0.45 * s) * sin_s
    asym_3 = 0.013 * math.sin(3.0 * theta - 1.15 * s + 0.30) * sin_s
    body_wave = 0.011 * math.sin(s * 30.0 + theta * 2.0) * sin_s

    crown_ring = 0.0020 * math.sin(s * 88.0) * max(0.0, 1.0 - s / 0.16)
    scar_bump = 0.0
    if 0.018 < s < 0.155:
        for k in range(14):
            s_k = lerp(0.028, 0.132, k / 13.0)
            if abs(s - s_k) > 0.032:
                continue
            th_k = k * 2.39996323
            d_th = math.atan2(math.sin(theta - th_k), math.cos(theta - th_k))
            if abs(d_th) > 0.72:
                continue
            s_arc = s_k - 0.009 * ((d_th / 0.44) ** 2)
            scar_bump += 0.0038 * math.exp(
                -((d_th / 0.30) ** 2) - (((s - s_arc) / 0.0078) ** 2)
            )

    r = base_r * (1.0 - groove_cut) * (1.0 + asym_2 + asym_3 + body_wave) + crown_ring + scar_bump
    return max(0.0025, r), z, bend_x, bend_y


def evaluate_taproot_transform(frame: float) -> tuple[float, float, float]:
    """Return (scale_xy, scale_z, location_z) of Taproot_Main interpolated at frame."""
    if frame <= TAPROOT_KEYFRAMES[0][0]:
        _, sc, loc = TAPROOT_KEYFRAMES[0]
        return sc[0], sc[2], loc[2]
    for i in range(len(TAPROOT_KEYFRAMES) - 1):
        f0, sc0, loc0 = TAPROOT_KEYFRAMES[i]
        f1, sc1, loc1 = TAPROOT_KEYFRAMES[i + 1]
        if f0 <= frame <= f1:
            t = (frame - f0) / max(1, f1 - f0)
            t_s = t * t * (3.0 - 2.0 * t)
            return (
                lerp(sc0[0], sc1[0], t_s),
                lerp(sc0[2], sc1[2], t_s),
                lerp(loc0[2], loc1[2], t_s),
            )
    _, sc, loc = TAPROOT_KEYFRAMES[-1]
    return sc[0], sc[2], loc[2]


def taproot_crown_world_z(r_world: float, frame: float) -> float:
    """Compute exact world Z on Taproot_Main conical-domed crown at radial distance r_world."""
    sc_xy, sc_z, loc_z = evaluate_taproot_transform(frame)
    r_local = min(0.170, max(0.0, r_world / max(1e-4, sc_xy)))
    k_ang = math.pi * 0.43
    frac = min(1.0, max(0.0, r_local / 0.172))
    sin_arg = min(1.0, (frac ** (1.0 / 0.85)) * math.sin(k_ang))
    t = math.asin(sin_arg) / k_ang
    z_local = 0.074 - 0.082 * (t ** 1.35)
    return loc_z + sc_z * z_local


def _add_rootlet_tube(
    bm: bmesh.types.BMesh,
    uv_layer: bmesh.types.BMLayerItem,
    pts: list[Vector],
    r_start: float,
    r_end: float,
    rad_segs: int = 5,
) -> None:
    """Sweep a tapered organic tube along 3D points into BMesh with UVs."""
    rings: list[list[bmesh.types.BMVert]] = []
    for i, p in enumerate(pts):
        t = i / max(1, len(pts) - 1)
        tangent = (pts[min(len(pts) - 1, i + 1)] - pts[max(0, i - 1)]).normalized()
        up = Vector((0.0, 0.0, 1.0)) if abs(tangent.z) < 0.9 else Vector((1.0, 0.0, 0.0))
        side_a = tangent.cross(up).normalized()
        side_b = tangent.cross(side_a).normalized()
        rad = lerp(r_start, r_end, t)
        row = []
        for ri in range(rad_segs):
            ang = 2.0 * math.pi * ri / rad_segs
            off = (side_a * math.cos(ang) + side_b * math.sin(ang)) * rad
            row.append(bm.verts.new(p + off))
        rings.append(row)

    tip = bm.verts.new(pts[-1] + (pts[-1] - pts[-2]).normalized() * 0.008)
    for i in range(len(rings) - 1):
        v0 = lerp(0.35, 0.85, i / max(1, len(rings) - 1))
        v1 = lerp(0.35, 0.85, (i + 1) / max(1, len(rings) - 1))
        for ri in range(rad_segs):
            nxt = (ri + 1) % rad_segs
            f = bm.faces.new((rings[i][ri], rings[i + 1][ri], rings[i + 1][nxt], rings[i][nxt]))
            for l, uv in zip(f.loops, [(0.5, v0), (0.5, v1), (0.52, v1), (0.52, v0)]):
                l[uv_layer].uv = uv
    for ri in range(rad_segs):
        nxt = (ri + 1) % rad_segs
        f = bm.faces.new((rings[-1][ri], tip, rings[-1][nxt]))
        for l in f.loops:
            l[uv_layer].uv = (0.5, 0.85)


def build_taproot_and_rootlets(mat_root: bpy.types.Material) -> list[bpy.types.Object]:
    """Build anatomical 3-zone taproot with leaf scars, asymmetry, grooves, & 26 clustered rootlets."""
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    rings = 88
    radial = 72
    z_bot = -0.860

    top_center = bm.verts.new((0.0, 0.0, 0.0745))
    ring_verts: list[list[bmesh.types.BMVert]] = []
    s_vals = [(r_i / rings) ** 1.24 for r_i in range(1, rings + 1)]

    for s in s_vals:
        row = []
        for a_i in range(radial + 1):
            u = a_i / radial
            theta = 2.0 * math.pi * u
            r, z, bend_x, bend_y = taproot_surface_sample(s, theta)
            vx = bend_x + r * math.cos(theta)
            vy = bend_y + r * math.sin(theta)
            row.append(bm.verts.new((vx, vy, z)))
        ring_verts.append(row)

    bot_tip = bm.verts.new((0.032, -0.018, z_bot - 0.020))

    for a_i in range(radial):
        f = bm.faces.new((top_center, ring_verts[0][a_i], ring_verts[0][a_i + 1]))
        u0, u1 = a_i / radial, (a_i + 1) / radial
        s1 = s_vals[0]
        for l, uv in zip(f.loops, [((u0 + u1) * 0.5, 0.0), (u0, s1), (u1, s1)]):
            l[uv_layer].uv = uv

    for r_i in range(len(ring_verts) - 1):
        s0 = s_vals[r_i]
        s1 = s_vals[r_i + 1]
        for a_i in range(radial):
            u0, u1 = a_i / radial, (a_i + 1) / radial
            f = bm.faces.new(
                (
                    ring_verts[r_i][a_i],
                    ring_verts[r_i + 1][a_i],
                    ring_verts[r_i + 1][a_i + 1],
                    ring_verts[r_i][a_i + 1],
                )
            )
            for l, uv in zip(f.loops, [(u0, s0), (u0, s1), (u1, s1), (u1, s0)]):
                l[uv_layer].uv = uv

    last_ring = ring_verts[-1]
    for a_i in range(radial):
        u0, u1 = a_i / radial, (a_i + 1) / radial
        f = bm.faces.new((last_ring[a_i], bot_tip, last_ring[a_i + 1]))
        for l, uv in zip(f.loops, [(u0, 0.98), ((u0 + u1) * 0.5, 1.0), (u1, 0.98)]):
            l[uv_layer].uv = uv

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("Taproot_Main_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    set_smooth_shading(mesh, True)

    taproot_obj = link_object("Taproot_Main", mesh, mat_root, location=(0.0, 0.0, -0.15))

    for f, sc, loc in TAPROOT_KEYFRAMES:
        keyframe_transform(taproot_obj, f, scale=sc, location=loc)
    smooth_datablock_fcurves(taproot_obj)

    objs: list[bpy.types.Object] = [taproot_obj]

    # 10 natural tufted clusters (26 filamentous rootlets) emerging along the two helical sugar grooves
    rng = random.Random(208)
    rootlet_idx = 0
    for tuft_i in range(10):
        side = 1.0 if tuft_i % 2 == 0 else -1.0
        s_tuft = lerp(0.24, 0.87, tuft_i / 9.0)
        u_zone = tuft_i / 9.0
        n_in_tuft = 3 if tuft_i < 6 else 2

        for sub_i in range(n_in_tuft):
            s_pos = max(0.21, min(0.91, s_tuft + rng.uniform(-0.018, 0.018)))
            groove_ang = 0.24 * s_pos + (0.0 if side > 0 else math.pi) + rng.uniform(-0.07, 0.07)
            local_r, z_anchor, bend_x, bend_y = taproot_surface_sample(s_pos, groove_ang)
            r_anchor = local_r * 0.66

            is_primary = sub_i == 0
            scale_sub = 1.0 if is_primary else rng.uniform(0.58, 0.82)
            r_start_main = lerp(0.0038, 0.0015, u_zone ** 0.88) * scale_sub * rng.uniform(0.90, 1.10)
            r_end_main = lerp(0.00052, 0.00030, u_zone)
            len_base = lerp(0.134, 0.036, u_zone ** 1.02) * scale_sub
            length = max(0.026, min(0.140, len_base * rng.uniform(0.86, 1.14)))

            fan_spread = 0.0 if is_primary else (1.0 if sub_i == 1 else -1.0) * rng.uniform(0.30, 0.62)
            fan_angle = groove_ang + fan_spread + rng.uniform(-0.18, 0.18)
            dir_x = math.cos(fan_angle)
            dir_y = math.sin(fan_angle)
            perp_x, perp_y = -dir_y, dir_x

            wf1 = rng.uniform(1.3, 2.4)
            wf2 = rng.uniform(2.7, 4.3)
            wp1 = rng.uniform(0.0, 2.0 * math.pi)
            wp2 = rng.uniform(0.0, 2.0 * math.pi)
            lat_a = length * rng.uniform(0.10, 0.20)
            droop = length * rng.uniform(0.54, 0.82)
            z_osc_freq = 1.2 + 0.4 * (rootlet_idx % 3)

            rbm = bmesh.new()
            ruv = ensure_uv_layer(rbm)
            main_pts: list[Vector] = []
            for si in range(19):
                t = si / 18.0
                rad_reach = (t ** 0.86) * length
                sway = (
                    lat_a * math.sin(t * math.pi * wf1 + wp1) * (t ** 0.85)
                    + 0.36 * lat_a * math.cos(t * math.pi * wf2 + wp2) * t
                )
                px = dir_x * rad_reach + perp_x * sway
                py = dir_y * rad_reach + perp_y * sway
                pz = -droop * (t ** 1.32) + 0.055 * length * math.sin(t * math.pi * z_osc_freq + wp1) * t
                main_pts.append(Vector((px, py, pz)))
            _add_rootlet_tube(rbm, ruv, main_pts, r_start=r_start_main, r_end=r_end_main, rad_segs=7)

            # Delicate asymmetric capillary side-branches (2-3 on primaries, 1 on fine companions)
            side_sign = 1.0 if (rootlet_idx % 2 == 0) else -1.0
            branch_configs: list[tuple[int, float, float, float]] = [
                (rng.choice((5, 7)), side_sign, rng.uniform(0.32, 0.46), 0.48)
            ]
            if is_primary and u_zone < 0.72:
                branch_configs.append(
                    (rng.choice((9, 11)), -side_sign, rng.uniform(0.24, 0.38), 0.36)
                )
            if is_primary and u_zone < 0.40:
                branch_configs.append(
                    (rng.choice((13, 14)), side_sign, rng.uniform(0.18, 0.28), 0.28)
                )
            for fork_idx, fork_sign, len_mul, rad_mul in branch_configs:
                fork_origin = main_pts[fork_idx]
                fork_ang = fan_angle + fork_sign * rng.uniform(0.36, 0.66)
                fdx, fdy = math.cos(fork_ang), math.sin(fork_ang)
                fpx, fpy = -fdy, fdx
                fork_len = length * len_mul
                fork_droop = rng.uniform(0.45, 0.72)
                fork_pts = []
                for fi in range(8):
                    ft = fi / 7.0
                    f_sway = 0.14 * fork_len * math.sin(ft * math.pi * 1.4 + wp2) * ft
                    fork_pts.append(
                        fork_origin
                        + Vector(
                            (
                                fdx * (ft ** 0.92) * fork_len + fpx * f_sway,
                                fdy * (ft ** 0.92) * fork_len + fpy * f_sway,
                                -fork_len * fork_droop * (ft ** 1.28),
                            )
                        )
                    )
                _add_rootlet_tube(
                    rbm,
                    ruv,
                    fork_pts,
                    r_start=max(0.00040, r_start_main * rad_mul),
                    r_end=0.00024,
                    rad_segs=5,
                )

            bmesh.ops.recalc_face_normals(rbm, faces=rbm.faces)
            rmesh = bpy.data.meshes.new(f"Rootlet_{rootlet_idx + 1:02d}_Mesh")
            rbm.to_mesh(rmesh)
            rbm.free()
            set_smooth_shading(rmesh, True)

            ax = bend_x + r_anchor * math.cos(groove_ang)
            ay = bend_y + r_anchor * math.sin(groove_ang)
            robj = link_object(
                f"Rootlet_{rootlet_idx + 1:02d}",
                rmesh,
                mat_root,
                location=(ax, ay, z_anchor),
            )
            robj.parent = taproot_obj

            appear_f = 18 + tuft_i * 9 + sub_i * 4
            full_f = min(146, appear_f + 30)
            keyframe_transform(robj, 0, scale=(0.0005, 0.0005, 0.0005))
            keyframe_transform(robj, appear_f, scale=(0.0005, 0.0005, 0.0005))
            keyframe_transform(robj, full_f, scale=(1.0, 1.0, 1.0))
            keyframe_transform(robj, 150, scale=(1.0, 1.0, 1.0))
            smooth_datablock_fcurves(robj)
            objs.append(robj)
            rootlet_idx += 1

    return objs


def build_hypocotyl_and_cotyledons(
    mat_foliage: bpy.types.Material,
    tex_root: PBRTextureSet,
) -> list[bpy.types.Object]:
    """Build pinkish-crimson hypocotyl and glossy twin cotyledons for BBCH 09..14."""
    mat_hypo, _, _, _ = make_pbr_material(
        "Hypocotyl_PBR",
        tex_root,
        tint_hex="#d66876",
        roughness_factor=0.75,
        normal_strength=0.4,
        subsurface=0.2,
    )

    sbm = bmesh.new()
    suv = ensure_uv_layer(sbm)
    rings = 20
    rad_n = 24
    s_rows = []
    for ri in range(rings + 1):
        t = ri / rings
        z = lerp(-0.08, 0.115, t)
        r = lerp(0.021, 0.013, t)
        bend_x = 0.006 * math.sin(t * math.pi)
        row = []
        for ai in range(rad_n + 1):
            u = ai / rad_n
            ang = 2.0 * math.pi * u
            row.append(sbm.verts.new((bend_x + r * math.cos(ang), r * math.sin(ang), z)))
        s_rows.append(row)
    for ri in range(rings):
        v0, v1 = 0.25 + 0.5 * (ri / rings), 0.25 + 0.5 * ((ri + 1) / rings)
        for ai in range(rad_n):
            u0, u1 = ai / rad_n, (ai + 1) / rad_n
            f = sbm.faces.new(
                (s_rows[ri][ai], s_rows[ri][ai + 1], s_rows[ri + 1][ai + 1], s_rows[ri + 1][ai])
            )
            for l, uv in zip(f.loops, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]):
                l[suv].uv = uv
    bot_cap = sbm.verts.new((0.0, 0.0, -0.082))
    top_cap = sbm.verts.new((0.0, 0.0, 0.118))
    for ai in range(rad_n):
        f_bot = sbm.faces.new((s_rows[0][ai + 1], s_rows[0][ai], bot_cap))
        for l in f_bot.loops:
            l[suv].uv = (0.5, 0.25)
        f_top = sbm.faces.new((s_rows[-1][ai], s_rows[-1][ai + 1], top_cap))
        for l in f_top.loops:
            l[suv].uv = (0.5, 0.75)
    bmesh.ops.recalc_face_normals(sbm, faces=sbm.faces)
    smesh = bpy.data.meshes.new("Hypocotyl_Stem_Mesh")
    sbm.to_mesh(smesh)
    sbm.free()
    set_smooth_shading(smesh, True)
    stem_obj = link_object("Hypocotyl_Stem", smesh, mat_hypo, location=(0.0, 0.0, 0.0))

    keyframe_transform(stem_obj, 0, scale=(0.0005, 0.0005, 0.0005), location=(0.0, 0.0, -0.10))
    keyframe_transform(stem_obj, 16, scale=(0.55, 0.55, 0.42), location=(0.0, 0.0, -0.04))
    keyframe_transform(stem_obj, 30, scale=(1.0, 1.0, 1.0), location=(0.0, 0.0, 0.0))
    keyframe_transform(stem_obj, 45, scale=(1.12, 1.12, 0.65), location=(0.0, 0.0, -0.008))
    keyframe_transform(stem_obj, 58, scale=(1.18, 1.18, 0.28), location=(0.0, 0.0, 0.004))
    keyframe_transform(stem_obj, 66, scale=(0.0005, 0.0005, 0.0005), location=(0.0, 0.0, 0.016))
    keyframe_transform(stem_obj, 150, scale=(0.0005, 0.0005, 0.0005), location=(0.0, 0.0, 0.016))
    smooth_datablock_fcurves(stem_obj)

    cot_objs = [stem_obj]
    for side_name, yaw in (
        ("Cotyledon_L", math.radians(240.0)),
        ("Cotyledon_R", math.radians(60.0)),
    ):
        cbm = bmesh.new()
        cuv = ensure_uv_layer(cbm)
        l_segs = 24
        w_segs = 12
        grid = []
        length = 0.175
        lat_sign = 1.0 if side_name == "Cotyledon_R" else -1.0
        for li in range(l_segs + 1):
            t = li / l_segs
            x = t * length
            half_w = 0.038 * math.sin((t ** 0.72) * math.pi)
            if t < 0.15:
                half_w = max(0.007, half_w)
            z_arch = 0.032 * math.sin(t * math.pi * 0.82) - 0.022 * (t ** 2.2)
            y_sweep = 0.0045 * math.sin(t * math.pi) * lat_sign
            row = []
            for wi in range(w_segs + 1):
                u = (wi / w_segs) * 2.0 - 1.0
                y = y_sweep + u * half_w
                cup = 0.006 * (u ** 2)
                row.append(cbm.verts.new((x, y, z_arch + cup)))
            grid.append(row)
        for li in range(l_segs):
            v0, v1 = li / l_segs, (li + 1) / l_segs
            for wi in range(w_segs):
                u0, u1 = wi / w_segs, (wi + 1) / w_segs
                f = cbm.faces.new(
                    (grid[li][wi], grid[li + 1][wi], grid[li + 1][wi + 1], grid[li][wi + 1])
                )
                for l, uv in zip(f.loops, [(u0, v0), (u0, v1), (u1, v1), (u1, v0)]):
                    l[cuv].uv = uv
        bmesh.ops.recalc_face_normals(cbm, faces=cbm.faces)
        cmesh = bpy.data.meshes.new(f"{side_name}_Mesh")
        cbm.to_mesh(cmesh)
        cbm.free()
        set_smooth_shading(cmesh, True)
        apply_leaf_vertex_colors(cmesh, seed=101 if side_name == "Cotyledon_L" else 102, is_cotyledon=True)
        cobj = link_object(
            side_name,
            cmesh,
            mat_foliage,
            location=(0.0, 0.0, 0.106),
            rotation=(0.0, 0.0, yaw),
        )
        keyframe_transform(
            cobj, 0, scale=(0.0005, 0.0005, 0.0005), location=(0.0, 0.0, -0.04), rotation=(0.0, -1.25, yaw)
        )
        keyframe_transform(
            cobj, 18, scale=(0.38, 0.38, 0.38), location=(0.0, 0.0, 0.008), rotation=(0.0, -1.05, yaw)
        )
        keyframe_transform(
            cobj, 30, scale=(1.0, 1.0, 1.0), location=(0.0, 0.0, 0.106), rotation=(0.0, -0.05, yaw)
        )
        keyframe_transform(
            cobj, 45, scale=(1.02, 1.02, 1.02), location=(0.0, 0.0, 0.062), rotation=(0.0, 0.08, yaw)
        )
        keyframe_transform(
            cobj, 58, scale=(0.95, 0.95, 0.95), location=(0.0, 0.0, 0.030), rotation=(0.0, 0.22, yaw)
        )
        keyframe_transform(
            cobj, 72, scale=(0.0005, 0.0005, 0.0005), location=(0.0, 0.0, 0.025), rotation=(0.0, 0.42, yaw)
        )
        keyframe_transform(
            cobj, 150, scale=(0.0005, 0.0005, 0.0005), location=(0.0, 0.0, 0.025), rotation=(0.0, 0.42, yaw)
        )
        smooth_datablock_fcurves(cobj)
        cot_objs.append(cobj)

    return cot_objs


def leaf_socket_location(
    rad_target: float,
    yaw: float,
    z_tier_offset: float,
    frame: float,
) -> tuple[float, float, float]:
    """Track shoot collar (hypocotyl apex <f58, swelling conical taproot crown dome >=f58)."""
    apical_r = 0.0045
    r58 = rad_target * 0.76
    z58 = taproot_crown_world_z(r58, 58.0) - 0.005 + z_tier_offset
    if frame <= 45.0:
        t30_45 = max(0.0, (frame - 30.0) / 15.0)
        r_cur = apical_r
        z_cur = lerp(0.104, 0.060, t30_45)
    elif frame < 58.0:
        u = (frame - 45.0) / 13.0
        u_s = u * u * (3.0 - 2.0 * u)
        r_cur = lerp(apical_r, r58, u_s)
        z_cur = lerp(0.060, z58, u_s)
    else:
        frac = min(1.0, (frame - 58.0) / 92.0)
        r_cur = rad_target * lerp(0.76, 1.06, frac)
        z_cur = taproot_crown_world_z(r_cur, frame) - 0.005 + z_tier_offset
    return (r_cur * math.cos(yaw), r_cur * math.sin(yaw), z_cur)


def apply_leaf_vertex_colors(
    mesh: bpy.types.Mesh,
    seed: int,
    is_cotyledon: bool = False,
) -> None:
    """Bake standard glTF COLOR_0 per-leaf natural chlorophyll variation + basal socket micro-AO."""
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

    if is_cotyledon:
        tint_r, tint_g, tint_b = 0.96 + 0.04 * r1, 0.98 + 0.02 * r2, 0.94 + 0.04 * r3
    else:
        # Subtle per-leaf chlorophyll variety (rich deep emerald vs sunlit warm green)
        tint_r = lerp(0.89, 1.08, r1)
        tint_g = lerp(0.93, 1.06, r2)
        tint_b = lerp(0.86, 1.05, r3)

    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            v_coord = uv_layer.data[loop_idx].uv[1] if uv_layer is not None else 0.5
            u_coord = uv_layer.data[loop_idx].uv[0] if uv_layer is not None else 0.5
            du = abs(u_coord - 0.5) * 2.0
            # Soft natural ambient darkening at petiole insertion inside dense crown collar
            base_ao = lerp(0.76, 1.0, min(1.0, max(0.0, v_coord / 0.24))) if not is_cotyledon else 1.0
            # Slight warm vitality toward sunlit distal center
            vitality = 1.0 + 0.03 * (1.0 - du) * max(0.0, v_coord - 0.30)
            cr = min(1.0, max(0.0, tint_r * base_ao * vitality))
            cg = min(1.0, max(0.0, tint_g * base_ao * vitality))
            cb = min(1.0, max(0.0, tint_b * base_ao * vitality))
            color_attr.data[loop_idx].color = (cr, cg, cb, 1.0)


def _eval_leaf_point(
    t: float,
    u: float,
    length: float,
    width: float,
    arch: float,
    wave_amp: float,
    seed: int,
    stage: str = "basis",
) -> Vector:
    """Compute 3D ovate-cordate bullate leaf vertex for stage in ('basis', 'bud', 'unfurl', 'mature')."""
    pet_base_w = max(0.0064, width * 0.048)
    pet_neck_w = max(0.0092, width * 0.068)

    if t < 0.0:
        neg_t = min(1.0, (-t) / 0.055)
        x_plug = t * 0.22
        half_w = pet_base_w * lerp(1.0, 0.30, neg_t)
        pet_thick = lerp(0.0130, 0.0040, neg_t)
        y_plug = u * half_w
        z_plug = (
            -pet_thick * math.sqrt(max(0.0, 1.0 - (u * 0.92) ** 2))
            + 0.0045 * (abs(u) ** 1.45) * (1.0 - 0.6 * neg_t)
            - 0.0045 * neg_t
        )
        return Vector((x_plug, y_plug, z_plug))

    h1 = math.sin(seed * 12.9898) * 43758.5453
    r1 = h1 - math.floor(h1)
    h2 = math.sin(seed * 78.233 + 1.7) * 19341.123
    r2 = h2 - math.floor(h2)
    h3 = math.sin(seed * 39.425 + 3.1) * 29173.719
    r3 = h3 - math.floor(h3)
    # Coherent spiral chirality per whorl (5 tiers: 1..5, 6..9, 10..14, 15..19, 20..24)
    if seed <= 5:
        sign_lat = 1.0
    elif seed <= 9:
        sign_lat = -1.0
    elif seed <= 14:
        sign_lat = 1.0
    elif seed <= 19:
        sign_lat = -1.0
    else:
        sign_lat = 1.0
    spread_factor = max(0.32, min(1.0, (length - 0.24) / 0.36))

    if t < 0.28:
        pt = t / 0.28
        half_w = lerp(pet_base_w, pet_neck_w, pt)
        pet_thick = lerp(0.0130, 0.0072, pt)
        # Fleshy semi-circular abaxial petiole keel + adaxial U-channel groove
        u_channel = 0.0052 * (abs(u) ** 1.45) * (1.0 - 0.30 * pt)
        z_cross = -pet_thick * math.sqrt(max(0.0, 1.0 - (u * 0.92) ** 2)) + u_channel
        wave = 0.0
    else:
        bt = (t - 0.28) / 0.72
        peak_pow = 0.54 + 0.18 * r1
        base_env = (math.sin(min(1.0, bt ** peak_pow) * math.pi)) ** (0.68 + 0.14 * r2)
        # Characteristic Beta vulgaris ovate-cordate basal lobes ("ears")
        cordate_lobe = 0.15 * math.exp(-(((bt - 0.13) / 0.105) ** 2))
        blade_env = min(1.12, base_env + cordate_lobe)
        side_asym = 1.0 + 0.075 * sign_lat * (1.0 if u >= 0.0 else -1.0) * math.sin(bt * math.pi)
        edge_lobes = 1.0 + (0.048 + 0.036 * r2) * math.sin(
            bt * math.pi * (3.2 + 2.0 * r1) + seed * 1.7
        ) * (abs(u) ** 1.35)
        half_w = max(
            0.005, (pet_neck_w + (width * 0.5 - pet_neck_w) * blade_env) * side_asym * edge_lobes
        )
        midrib_ridge = -0.0082 * math.exp(-(u ** 2) / 0.055) * (1.0 - 0.68 * bt)
        cup_profile = 0.013 * (1.0 - 0.55 * bt) - 0.006 * (max(0.0, bt - 0.55) / 0.45)
        cup = cup_profile * (u ** 2)
        wave_mask = math.sin(bt * math.pi)
        phase_side = 0.85 if u >= 0.0 else 0.0
        wave1 = math.sin(t * math.pi * (5.2 + 1.6 * r1) + seed * 1.3 + phase_side)
        wave2 = 0.40 * math.sin(t * math.pi * (11.2 + 2.6 * r2) - seed * 0.9 - phase_side)
        wave = wave_amp * wave_mask * (abs(u) ** 1.38) * (wave1 + wave2)

        # 3D geometric interveinal bullation (savoyed pillows bulging upward between arcuate veins)
        bay_phase = bt * math.pi * 8.8 - abs(u) * 3.4
        vein_sin = math.sin(bay_phase)
        pillow = (max(0.0, vein_sin) ** 1.55) * math.sin(min(1.0, abs(u) * 3.2) * math.pi * 0.5)
        micro_pucker = 0.58 + 0.42 * math.sin(bt * 19.0 + u * 11.0 + seed * 1.3)
        bullate_z = (
            0.0052 * wave_mask * (1.0 - 0.62 * (u ** 2)) * pillow * micro_pucker
            - 0.0020 * wave_mask * (1.0 - max(0.0, vein_sin)) * (1.0 - 0.5 * (u ** 2))
        )
        z_cross = midrib_ridge + cup + bullate_z

    if stage == "bud":
        t_eff = 0.26 * (t ** 1.25)
        open_w = 0.16 + 0.06 * (1.0 - t)
        y_local = u * half_w * open_w
        z_local = z_cross * 0.40 + 0.016 * (u ** 2) * math.sin(t * math.pi)
        x_spine = t_eff * length - 0.010 * length * (max(0.0, t - 0.35) ** 1.8)
        z_spine = 0.014 * length * (t ** 1.05) + 0.008 * length * math.sin(t * math.pi * 0.95)
        y_spine = 0.16 * (0.009 + 0.011 * r2) * spread_factor * sign_lat * math.sin(t * math.pi)
        return Vector((x_spine, y_spine + y_local, z_spine + z_local))

    if stage == "unfurl":
        t_eff = 0.72 * t - 0.08 * (t ** 2)
        open_wave = max(0.24, min(1.0, 1.15 - 0.85 * t))
        y_local = u * half_w * open_wave
        unfurl_cup = 0.020 * (1.0 - open_wave) * (u ** 2)
        z_local = z_cross * lerp(0.55, 1.0, open_wave) + unfurl_cup + wave * open_wave * 0.65
        x_spine = t_eff * length - 0.024 * length * (max(0.0, t - 0.35) ** 1.9)
        z_rise = arch * 1.48 * (t ** 1.02) * (1.0 - 0.40 * t)
        z_fountain = 0.020 * length * math.sin((t ** 0.85) * math.pi)
        z_spine = z_rise + z_fountain
        lat_amp = 0.65 * (0.009 + 0.011 * r2) * spread_factor * sign_lat
        y_spine = lat_amp * math.sin((t ** 1.08) * math.pi * (0.80 + 0.30 * r3))
        twist_ang = 0.55 * sign_lat * (0.08 + 0.10 * r3) * spread_factor * max(0.0, (t - 0.20) / 0.80)
        ca, sa = math.cos(twist_ang), math.sin(twist_ang)
        y_rot = y_local * ca - z_local * sa
        z_rot = y_local * sa + z_local * ca
        return Vector((x_spine, y_spine + y_rot, z_spine + z_rot))

    sen = 1.0 if stage == "mature" else 0.0
    y_shrink = 1.0 - 0.13 * sen * max(0.0, t - 0.35)
    y_local = u * half_w * y_shrink
    curl_z = 0.028 * (abs(u) ** 2.0) * max(0.0, t - 0.32) * sen
    z_local = z_cross + wave + curl_z

    twist_ang = sign_lat * (0.08 + 0.11 * r3) * spread_factor * max(0.0, (t - 0.18) / 0.82)
    ca, sa = math.cos(twist_ang), math.sin(twist_ang)
    y_rot = y_local * ca - z_local * sa
    z_rot = y_local * sa + z_local * ca

    lat_amp = (0.009 + 0.011 * r2) * spread_factor * sign_lat
    y_spine = lat_amp * math.sin((t ** 1.08) * math.pi * (0.80 + 0.30 * r3))

    z_rise = arch * 1.55 * (t ** 1.06) * (1.0 - 0.46 * t)
    tip_reflex = -(0.036 + 0.038 * r1) * spread_factor * (max(0.0, (t - 0.42) / 0.58) ** 2.0)
    droop_z = -0.034 * (max(0.0, t - 0.36) ** 1.45) * sen
    z_spine = z_rise + tip_reflex + droop_z

    x_foreshorten = (
        (0.030 + 0.022 * r1) * length * (max(0.0, t - 0.28) ** 2.05)
        + 0.015 * length * sen * (max(0.0, t - 0.38) ** 1.8)
    )
    x_spine = t * length - x_foreshorten
    return Vector((x_spine, y_spine + y_rot, z_spine + z_rot))


def create_beet_leaf_object(
    name: str,
    mat: bpy.types.Material,
    length: float,
    width: float,
    arch: float,
    wave_amp: float,
    seed: int,
    rad_off: float,
    yaw: float,
    f_start: int,
    f_full: int,
    pitch_open: float,
    z_tier_offset: float,
    is_outer_senescing: bool,
) -> bpy.types.Object:
    """Create smooth high-res bullate leaf mesh with COLOR_0 and 3-stage unfurling shape keys."""
    bm = bmesh.new()
    uv_layer = ensure_uv_layer(bm)
    l_segs = 44
    w_segs = 18
    t_values = [-0.055, -0.025] + [li / l_segs for li in range(l_segs + 1)]

    grid: list[list[bmesh.types.BMVert]] = []
    for t in t_values:
        row = []
        for wi in range(w_segs + 1):
            u = (wi / w_segs) * 2.0 - 1.0
            co = _eval_leaf_point(t, u, length, width, arch, wave_amp, seed, "basis")
            row.append(bm.verts.new(co))
        grid.append(row)

    for li in range(len(t_values) - 1):
        v0 = max(0.0, t_values[li])
        v1 = max(0.0, t_values[li + 1])
        for wi in range(w_segs):
            u0, u1 = wi / w_segs, (wi + 1) / w_segs
            f = bm.faces.new(
                (grid[li][wi], grid[li + 1][wi], grid[li + 1][wi + 1], grid[li][wi + 1])
            )
            for l, uv in zip(f.loops, [(u0, v0), (u0, v1), (u1, v1), (u1, v0)]):
                l[uv_layer].uv = uv

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    set_smooth_shading(mesh, True)
    apply_leaf_vertex_colors(mesh, seed=seed, is_cotyledon=False)

    pitch_bud = -(pitch_open + 0.07)
    pitch_final = -pitch_open
    pitch_droop = -(pitch_open - 0.04) if is_outer_senescing else pitch_final
    init_loc = leaf_socket_location(rad_off, yaw, z_tier_offset, 0.0)

    obj = link_object(
        name,
        mesh,
        mat,
        location=init_loc,
        rotation=(0.0, pitch_bud, yaw),
        scale=(0.0005, 0.0005, 0.0005),
    )

    obj.shape_key_add(name="Basis", from_mix=False)
    sk_bud = obj.shape_key_add(name="Stage1_Bud", from_mix=False)
    sk_unfurl = obj.shape_key_add(name="Stage2_Unfurl", from_mix=False)
    sk_mature = obj.shape_key_add(name="Stage3_Mature", from_mix=False)

    idx_v = 0
    for t in t_values:
        for wi in range(w_segs + 1):
            u = (wi / w_segs) * 2.0 - 1.0
            sk_bud.data[idx_v].co = _eval_leaf_point(
                t, u, length, width, arch, wave_amp, seed, "bud"
            )
            sk_unfurl.data[idx_v].co = _eval_leaf_point(
                t, u, length, width, arch, wave_amp, seed, "unfurl"
            )
            sk_mature.data[idx_v].co = _eval_leaf_point(
                t, u, length, width, arch, wave_amp, seed, "mature"
            )
            idx_v += 1

    f_mid = int(lerp(f_start, f_full, 0.48))

    for frame_val, bud_w, unf_w in (
        (0, 1.0, 0.0),
        (f_start, 1.0, 0.0),
        (f_mid, 0.0, 1.0),
        (f_full, 0.0, 0.0),
        (150, 0.0, 0.0),
    ):
        sk_bud.value = bud_w
        sk_bud.keyframe_insert(data_path="value", frame=frame_val)
        sk_unfurl.value = unf_w
        sk_unfurl.keyframe_insert(data_path="value", frame=frame_val)

    sk_mature.value = 0.0
    sk_mature.keyframe_insert(data_path="value", frame=0)
    mat_start_f = 105 if is_outer_senescing else min(144, f_full)
    if mat_start_f < 150:
        sk_mature.value = 0.0
        sk_mature.keyframe_insert(data_path="value", frame=mat_start_f)
        sk_mature.value = 0.88 if is_outer_senescing else 0.18
        sk_mature.keyframe_insert(data_path="value", frame=150)
    else:
        sk_mature.value = 0.0
        sk_mature.keyframe_insert(data_path="value", frame=150)
    smooth_datablock_fcurves(mesh.shape_keys)

    hide_until = max(1, f_start - 3)
    key_frames = sorted(
        {0, hide_until, f_start, f_mid, f_full}
        | {m for m in (45, 58, 75, 90, 120, 150) if m > f_start}
    )
    final_scale = 1.02 if is_outer_senescing else 1.05
    for kf in key_frames:
        loc_k = leaf_socket_location(rad_off, yaw, z_tier_offset, float(kf))
        if kf <= hide_until:
            sc_val = 0.0005
            pitch_val = pitch_bud
            loc_k = (loc_k[0], loc_k[1], loc_k[2] - 0.004)
        elif kf < f_full:
            u_grow = (kf - f_start) / max(1, f_full - f_start)
            sc_val = lerp(0.74, 1.0, u_grow ** 0.85)
            pitch_val = lerp(pitch_bud, pitch_final, u_grow)
        else:
            t_mat = (kf - f_full) / max(1.0, 150.0 - f_full)
            sc_val = lerp(1.0, final_scale, t_mat)
            pitch_val = lerp(pitch_final, pitch_droop, t_mat)
        keyframe_transform(
            obj,
            kf,
            scale=(sc_val, sc_val, sc_val),
            location=loc_k,
            rotation=(0.0, pitch_val, yaw),
        )
    smooth_datablock_fcurves(obj)
    return obj


def build_rosette_leaves(
    mat_outer: bpy.types.Material,
    mat_mid: bpy.types.Material,
    mat_heart: bpy.types.Material,
) -> list[bpy.types.Object]:
    """Generate 24 uniquely curved, bullate, wide-spreading leaves anchored to the growing collar."""
    leaves: list[bpy.types.Object] = []

    # 5-tier specs (5 + 4 + 5 + 5 + 5 = 24 leaves):
    # (f_start, f_full, length, width, arch, pitch_open, wave_amp, yaw_deg, rad_off, z_tier, tier)
    specs = [
        # Tier 0 (5 wide outer basal-skirt leaves, golden-angle emergence sequence +144 deg)
        (34, 60, 0.44, 0.175, 0.056, 0.24, 0.015, 16.0, 0.047, -0.004, "outer"),
        (38, 64, 0.43, 0.172, 0.054, 0.22, 0.014, 160.0, 0.047, -0.004, "outer"),
        (44, 70, 0.47, 0.186, 0.058, 0.25, 0.016, 304.0, 0.047, -0.004, "outer"),
        (50, 76, 0.48, 0.190, 0.060, 0.23, 0.016, 88.0, 0.047, -0.004, "outer"),
        (54, 80, 0.46, 0.184, 0.056, 0.26, 0.015, 232.0, 0.047, -0.004, "outer"),
        # Tier 1 (4 lower-mid spreading leaves staggered cleanly between Tier 0)
        (56, 84, 0.50, 0.194, 0.064, 0.45, 0.016, 52.0, 0.041, -0.001, "outer"),
        (60, 88, 0.52, 0.198, 0.066, 0.47, 0.017, 196.0, 0.041, -0.001, "outer"),
        (64, 92, 0.51, 0.196, 0.065, 0.46, 0.016, 124.0, 0.041, -0.001, "outer"),
        (68, 96, 0.53, 0.200, 0.068, 0.48, 0.017, 268.0, 0.041, -0.001, "outer"),
        # Tier 2 (5 lush mid-canopy spiral leaves)
        (70, 98, 0.57, 0.214, 0.072, 0.68, 0.018, 2.0, 0.033, 0.002, "mid"),
        (74, 102, 0.59, 0.220, 0.075, 0.70, 0.018, 146.0, 0.033, 0.002, "mid"),
        (78, 106, 0.60, 0.222, 0.076, 0.72, 0.019, 290.0, 0.033, 0.002, "mid"),
        (82, 110, 0.58, 0.216, 0.073, 0.71, 0.017, 74.0, 0.033, 0.002, "mid"),
        (86, 114, 0.56, 0.212, 0.071, 0.69, 0.018, 218.0, 0.033, 0.002, "mid"),
        # Tier 3 (5 mid-upper staggered spiral leaves)
        (90, 118, 0.54, 0.160, 0.066, 0.86, 0.015, 40.0, 0.026, 0.004, "mid"),
        (94, 122, 0.56, 0.164, 0.068, 0.88, 0.015, 184.0, 0.026, 0.004, "mid"),
        (98, 126, 0.54, 0.158, 0.065, 0.90, 0.016, 328.0, 0.026, 0.004, "mid"),
        (102, 130, 0.52, 0.154, 0.062, 0.89, 0.014, 112.0, 0.026, 0.004, "heart"),
        (106, 134, 0.50, 0.148, 0.060, 0.87, 0.013, 256.0, 0.026, 0.004, "heart"),
        # Tier 4 (5 inner heart leaves seated in the green crown center)
        (112, 140, 0.41, 0.088, 0.044, 1.04, 0.010, 76.0, 0.020, 0.006, "heart"),
        (116, 144, 0.37, 0.078, 0.040, 1.09, 0.009, 220.0, 0.019, 0.006, "heart"),
        (120, 147, 0.33, 0.068, 0.036, 1.14, 0.008, 4.0, 0.018, 0.006, "heart"),
        (124, 149, 0.28, 0.056, 0.028, 1.19, 0.007, 148.0, 0.016, 0.007, "heart"),
        (128, 150, 0.22, 0.044, 0.022, 1.29, 0.006, 292.0, 0.014, 0.007, "heart"),
    ]

    mat_map = {"outer": mat_outer, "mid": mat_mid, "heart": mat_heart}

    for idx, (
        f_start,
        f_full,
        length,
        width,
        arch,
        pitch_open,
        wave_amp,
        yaw_deg,
        rad_off,
        z_tier,
        tier,
    ) in enumerate(specs):
        yaw = math.radians(yaw_deg)
        leaf_obj = create_beet_leaf_object(
            name=f"Leaf_{idx + 1:02d}",
            mat=mat_map[tier],
            length=length,
            width=width,
            arch=arch,
            wave_amp=wave_amp,
            seed=idx + 1,
            rad_off=rad_off,
            yaw=yaw,
            f_start=f_start,
            f_full=f_full,
            pitch_open=pitch_open,
            z_tier_offset=z_tier,
            is_outer_senescing=(tier == "outer"),
        )
        leaves.append(leaf_obj)

    return leaves


def apply_blender_maturation_state(mat_controls: dict, progress: float) -> None:
    """Sync Blender EEVEE material tints & roughness across maturation progress [0..1]."""
    mat_phase = max(0.0, min(1.0, (progress - 0.55) / 0.45))

    def set_mix_tint(mix_node: bpy.types.ShaderNodeMix, col: tuple[float, float, float, float]) -> None:
        rgba_in = [s for s in mix_node.inputs if s.type == "RGBA"]
        rgba_in[1].default_value = col

    outer_tint, outer_rough, _ = mat_controls["outer"]
    c_fresh = hex_rgba("#edf5df")
    c_mature = hex_rgba("#d8be56")
    set_mix_tint(outer_tint, tuple(lerp(c_fresh[i], c_mature[i], mat_phase) for i in range(4)))
    outer_rough.inputs[1].default_value = lerp(0.95, 1.55, mat_phase)

    mid_tint, mid_rough, _ = mat_controls["mid"]
    c_mid_0 = hex_rgba("#f5faef")
    c_mid_1 = hex_rgba("#dce8a8")
    set_mix_tint(mid_tint, tuple(lerp(c_mid_0[i], c_mid_1[i], mat_phase * 0.55) for i in range(4)))
    mid_rough.inputs[1].default_value = lerp(0.88, 1.15, mat_phase)

    root_tint, root_rough, _ = mat_controls["root"]
    c_r0 = hex_rgba("#ffffff")
    c_r1 = hex_rgba("#f4ecd8")
    set_mix_tint(root_tint, tuple(lerp(c_r0[i], c_r1[i], progress * 0.7) for i in range(4)))
    root_rough.inputs[1].default_value = lerp(1.05, 0.88, progress)


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
    target.location = (0.0, 0.0, -0.08)
    scene.collection.objects.link(target)
    studio_objs.append(target)

    cam_data = bpy.data.cameras.new("Hero_Camera")
    cam_data.lens = 40.0
    cam_obj = bpy.data.objects.new("Hero_Camera", cam_data)
    cam_obj.location = (0.38, -2.85, 0.34)
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

    add_light(
        "Key_Sun",
        "SUN",
        3.5,
        (2.2, -2.6, 3.6),
        (math.radians(46), math.radians(16), math.radians(34)),
        color=(1.0, 0.97, 0.90),
    )
    add_light(
        "Fill_Area",
        "AREA",
        55.0,
        (-2.2, -1.9, 1.2),
        (math.radians(66), 0.0, math.radians(-48)),
        color=(0.82, 0.92, 1.0),
        size=2.8,
    )
    add_light(
        "Rim_Area",
        "AREA",
        70.0,
        (0.2, 2.5, 1.8),
        (math.radians(-55), 0.0, math.radians(180)),
        color=(0.95, 1.0, 0.90),
        size=2.4,
    )
    return cam_obj, studio_objs


def blender_to_gltf(v: Vector) -> list[float]:
    """Convert Blender Z-up coordinates to glTF Y-up coordinates."""
    return [round(float(v.x), 4), round(float(v.z), 4), round(float(-v.y), 4)]


def collect_stats_and_export(
    export_objs: list[bpy.types.Object],
    glb_path: Path,
    blend_path: Path,
) -> dict:
    """Save .blend, export plant-only animated WebP-textured .glb, and compute bounds."""
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
        export_tangents=True,
        export_vertex_color="ACTIVE",
        export_vertex_color_name="Color",
        export_materials="EXPORT",
        export_image_format="WEBP",
        export_image_quality=95,
        export_image_webp_fallback=False,
        export_animations=True,
        export_animation_mode="SCENE",
        export_bake_animation=True,
        export_anim_slide_to_zero=True,
        export_optimize_animation_size=True,
        export_morph=True,
        export_morph_normal=False,
        export_morph_animation=True,
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
        export_draco_color_quantization=10,
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

    # Audit 4 geometric invariants: leaves, blades-root, floating leaf bases, floating rootlet bases
    leaf_overlaps: list[str] = []
    leaf_blade_root_clipping: list[str] = []
    floating_leaf_bases: list[str] = []
    floating_rootlet_bases: list[str] = []

    def _filtered_bvh(
        eval_obj: bpy.types.Object, min_local_x: float
    ) -> tuple[BVHTree | None, list[Vector]]:
        me = eval_obj.to_mesh()
        bm_tmp = bmesh.new()
        bm_tmp.from_mesh(me)
        bm_tmp.verts.ensure_lookup_table()
        plug_pts = [eval_obj.matrix_world @ bm_tmp.verts[0].co.copy()] if bm_tmp.verts else []
        if min_local_x > -10.0:
            del_faces = [
                f for f in bm_tmp.faces if min(v.co.x for v in f.verts) < min_local_x
            ]
            if del_faces:
                bmesh.ops.delete(bm_tmp, geom=del_faces, context="FACES_ONLY")
        bmesh.ops.transform(bm_tmp, matrix=eval_obj.matrix_world, verts=bm_tmp.verts)
        bvh = BVHTree.FromBMesh(bm_tmp) if bm_tmp.faces else None
        bm_tmp.free()
        eval_obj.to_mesh_clear()
        return bvh, plug_pts

    full_audit = ("--full-audit" in sys.argv) or (os.environ.get("PERISCOPE_FULL_AUDIT") == "1")
    bvh_frames = tuple(range(0, 151, 5)) if full_audit else (60, 90, 120, 150)
    gap_frames = tuple(range(0, 151, 5)) if full_audit else (40, 60, 77, 90, 120, 150)

    for check_frame in bvh_frames:
        scene.frame_set(check_frame)
        depsgraph.update()
        leaf_ext_bvhs: list[tuple[str, BVHTree]] = []
        leaf_blade_bvhs: list[tuple[str, BVHTree]] = []
        root_bvh: BVHTree | None = None
        for obj in export_objs:
            if obj.type != "MESH" or max(obj.scale) < 0.15:
                continue
            eval_obj = obj.evaluated_get(depsgraph)
            if obj.name.startswith("Leaf_"):
                ext_bvh, _ = _filtered_bvh(eval_obj, min_local_x=0.015)
                blade_bvh, _ = _filtered_bvh(eval_obj, min_local_x=0.060)
                if ext_bvh is not None:
                    leaf_ext_bvhs.append((obj.name, ext_bvh))
                if blade_bvh is not None:
                    leaf_blade_bvhs.append((obj.name, blade_bvh))
            elif obj.name == "Taproot_Main":
                root_bvh, _ = _filtered_bvh(eval_obj, min_local_x=-99.0)

        for i in range(len(leaf_ext_bvhs)):
            for j in range(i + 1, len(leaf_ext_bvhs)):
                if leaf_ext_bvhs[i][1].overlap(leaf_ext_bvhs[j][1]):
                    leaf_overlaps.append(
                        f"f{check_frame}:{leaf_ext_bvhs[i][0]}<->{leaf_ext_bvhs[j][0]}"
                    )
        if root_bvh is not None:
            for lname, lbvh in leaf_blade_bvhs:
                if lbvh.overlap(root_bvh):
                    leaf_blade_root_clipping.append(f"f{check_frame}:{lname}")

        for obj in export_objs:
            if not obj.name.startswith("Rootlet_") or max(obj.scale) < 0.15:
                continue
            s_est = taproot_s_from_local_z(obj.location.z)
            bend_x_z = 0.032 * (max(0.0, s_est - 0.48) / 0.52) ** 1.55
            bend_y_z = -0.018 * (max(0.0, s_est - 0.60) / 0.40) ** 1.50
            dx_loc = obj.location.x - bend_x_z
            dy_loc = obj.location.y - bend_y_z
            theta_loc = math.atan2(dy_loc, dx_loc)
            surf_r_z, _, _, _ = taproot_surface_sample(s_est, theta_loc)
            r_from_bend = math.hypot(dx_loc, dy_loc)
            if r_from_bend > surf_r_z * 0.85:
                floating_rootlet_bases.append(
                    f"f{check_frame}:{obj.name}(r={r_from_bend:.4f}>max={surf_r_z * 0.85:.4f})"
                )

    for gap_frame in gap_frames:
        scene.frame_set(gap_frame)
        depsgraph.update()
        hypo_obj = next((o for o in export_objs if o.name == "Hypocotyl_Stem"), None)
        hypo_top_z = -1e9
        if hypo_obj is not None and max(hypo_obj.scale) >= 0.15:
            heval = hypo_obj.evaluated_get(depsgraph)
            hypo_top_z = max((heval.matrix_world @ Vector(c)).z for c in heval.bound_box)

        for obj in export_objs:
            if not obj.name.startswith("Leaf_") or max(obj.scale) < 0.15:
                continue
            eval_obj = obj.evaluated_get(depsgraph)
            _, plug_pts = _filtered_bvh(eval_obj, min_local_x=-99.0)
            if not plug_pts:
                continue
            wp = plug_pts[0]
            r_xy = math.hypot(wp.x, wp.y)
            crown_z = taproot_crown_world_z(r_xy, float(gap_frame))
            collar_z = max(crown_z, hypo_top_z)
            if wp.z > collar_z + 0.004:
                floating_leaf_bases.append(
                    f"f{gap_frame}:{obj.name}(gap={wp.z - collar_z:.4f})"
                )

    return {
        "crop_id": "sugar_beet",
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
        "leaf_root_overlaps": leaf_blade_root_clipping,
        "floating_leaf_bases": floating_leaf_bases,
        "floating_rootlet_bases": floating_rootlet_bases,
        "phase_bounds": phase_bounds,
    }


def render_phase_previews(mat_controls: dict) -> list[str]:
    """Render 6 EEVEE preview PNGs while syncing maturation colors for each BBCH frame."""
    scene = bpy.context.scene
    rendered = []
    for idx, frame in enumerate(PHASE_FRAMES):
        scene.frame_set(frame)
        apply_blender_maturation_state(mat_controls, frame / float(FRAME_END))
        out_path = RENDERS_DIR / f"phase_{idx}.png"
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        rendered.append(str(out_path))
    apply_blender_maturation_state(mat_controls, 0.0)
    return rendered


def main() -> None:
    """Build plant-only PBR sugar beet scene, export GLB, render 6 previews, save stats."""
    ensure_dirs()
    clear_scene()

    # Remove stale soil textures if present from earlier prototype
    for old_soil in (ASSETS_DIR / "textures").glob("soil_*.png"):
        old_soil.unlink(missing_ok=True)

    tex_sets = generate_all_pbr_textures(ASSETS_DIR)

    mat_seed, _, _, _ = make_pbr_material(
        "Seed_PBR", tex_sets["seed"], "#ffffff", roughness_factor=1.0, normal_strength=1.1, specular=0.18
    )
    mat_root, root_tint, root_rough, root_bsdf = make_pbr_material(
        "Taproot_PBR",
        tex_sets["root"],
        "#ffffff",
        roughness_factor=1.0,
        normal_strength=0.58,
        subsurface=0.14,
        specular=0.30,
    )
    mat_outer, outer_tint, outer_rough, outer_bsdf = make_pbr_material(
        "Outer_Leaf_PBR",
        tex_sets["leaf"],
        "#edf5df",
        roughness_factor=0.95,
        normal_strength=1.15,
        subsurface=0.18,
        double_sided=True,
        specular=0.40,
        use_vertex_color=True,
    )
    mat_mid, mid_tint, mid_rough, mid_bsdf = make_pbr_material(
        "Mid_Leaf_PBR",
        tex_sets["leaf"],
        "#f5faef",
        roughness_factor=0.88,
        normal_strength=1.15,
        subsurface=0.20,
        double_sided=True,
        specular=0.42,
        use_vertex_color=True,
    )
    mat_heart, heart_tint, heart_rough, heart_bsdf = make_pbr_material(
        "Heart_Leaf_PBR",
        tex_sets["leaf"],
        "#e2ffad",
        roughness_factor=0.80,
        normal_strength=0.95,
        subsurface=0.24,
        double_sided=True,
        specular=0.45,
        use_vertex_color=True,
    )

    mat_controls = {
        "root": (root_tint, root_rough, root_bsdf),
        "outer": (outer_tint, outer_rough, outer_bsdf),
        "mid": (mid_tint, mid_rough, mid_bsdf),
        "heart": (heart_tint, heart_rough, heart_bsdf),
    }

    export_objs: list[bpy.types.Object] = []
    export_objs.append(build_seed_pellet(mat_seed))
    export_objs.extend(build_taproot_and_rootlets(mat_root))
    export_objs.extend(build_hypocotyl_and_cotyledons(mat_heart, tex_sets["root"]))
    export_objs.extend(build_rosette_leaves(mat_outer, mat_mid, mat_heart))

    setup_studio_lighting_and_camera()

    glb_path = ASSETS_DIR / "sugar_beet.glb"
    blend_path = ASSETS_DIR / "sugar_beet.blend"
    apply_blender_maturation_state(mat_controls, 0.0)
    stats = collect_stats_and_export(export_objs, glb_path, blend_path)
    stats["renders"] = render_phase_previews(mat_controls)

    stats_path = ASSETS_DIR / "export_stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PERISKOPE_EXPORT_OK:", json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
