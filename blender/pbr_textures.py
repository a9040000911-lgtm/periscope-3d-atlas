"""Photorealistic 2K PBR texture & CC0 farmland HDRI generator using NumPy + Blender.

Generates:
- 2K bullate (interveinal Voronoi pillowed) Beta vulgaris leaf Albedo, Normal, Roughness, & 1K Thickness
- 2K anatomical taproot skin with short anisotropic lenticels, crown leaf scars, & groove soil residue
- 512px porous coated seed pellet maps
- Real Poly Haven CC0 agricultural field HDRI (farm_field_1k.hdr) with MD5 check & offline procedural fallback
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import TypedDict

import bpy
import numpy as np

POLYHAVEN_HDRI_NAME = "farm_field_1k.hdr"
POLYHAVEN_HDRI_URL = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/farm_field_1k.hdr"
POLYHAVEN_HDRI_MD5 = "03fe310d5e14e3a65e1bb08d4c08720b"


class PBRTextureSet(TypedDict):
    albedo: bpy.types.Image
    normal: bpy.types.Image
    roughness: bpy.types.Image


def _smoothstep(t: np.ndarray) -> np.ndarray:
    return t * t * (3.0 - 2.0 * t)


def value_noise_2d_aniso(
    size: int,
    freq_y: int,
    freq_x: int,
    seed: int,
    tile_x: bool = True,
) -> np.ndarray:
    """Vectorized anisotropic bilinear 2D value noise on [0..1] in NumPy."""
    rng = np.random.default_rng(seed)
    grid = rng.random((freq_y + 1, freq_x + 1), dtype=np.float32)
    if tile_x:
        grid[:, -1] = grid[:, 0]

    coords_y = np.linspace(0.0, float(freq_y), size, endpoint=False, dtype=np.float32)
    coords_x = np.linspace(0.0, float(freq_x), size, endpoint=False, dtype=np.float32)
    iy = np.floor(coords_y).astype(np.int32)
    ix = np.floor(coords_x).astype(np.int32)
    fy = _smoothstep(coords_y - iy)[:, None]
    fx = _smoothstep(coords_x - ix)[None, :]

    n00 = grid[iy[:, None], ix[None, :]]
    n10 = grid[iy[:, None], (ix + 1)[None, :]]
    n01 = grid[(iy + 1)[:, None], ix[None, :]]
    n11 = grid[(iy + 1)[:, None], (ix + 1)[None, :]]

    nx0 = n00 + (n10 - n00) * fx
    nx1 = n01 + (n11 - n01) * fx
    return nx0 + (nx1 - nx0) * fy


def value_noise_2d(size: int, freq: int, seed: int, tile_x: bool = True) -> np.ndarray:
    """Vectorized isotropic bilinear-interpolated 2D value noise on [0..1] in NumPy."""
    return value_noise_2d_aniso(size, freq, freq, seed, tile_x=tile_x)


def fbm_2d(
    size: int, base_freq: int = 4, octaves: int = 4, seed: int = 1, tile_x: bool = True
) -> np.ndarray:
    """Multi-octave fractal Brownian motion noise normalized to [0..1]."""
    acc = np.zeros((size, size), dtype=np.float32)
    amp = 0.5
    norm = 0.0
    freq = base_freq
    for idx in range(octaves):
        acc += amp * value_noise_2d(size, freq, seed + idx * 97, tile_x=tile_x)
        norm += amp
        amp *= 0.5
        freq *= 2
    return np.clip(acc / max(1e-6, norm), 0.0, 1.0)


def worley_cells_2d(
    size: int,
    cells_y: int,
    cells_x: int,
    seed: int,
    tile_x: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Fast vectorized 2D Worley/Voronoi cell distances (f1, edge=f2-f1) in pure NumPy."""
    rng = np.random.default_rng(seed)
    pts_y = rng.uniform(0.14, 0.86, size=(cells_y + 2, cells_x + 2)).astype(np.float32)
    pts_x = rng.uniform(0.14, 0.86, size=(cells_y + 2, cells_x + 2)).astype(np.float32)
    if tile_x:
        pts_y[:, -2:] = pts_y[:, :2]
        pts_x[:, -2:] = pts_x[:, :2]

    gy = np.linspace(0.0, float(cells_y), size, endpoint=False, dtype=np.float32)[:, None]
    gx = np.linspace(0.0, float(cells_x), size, endpoint=False, dtype=np.float32)[None, :]
    iy = np.floor(gy).astype(np.int32)
    ix = np.floor(gx).astype(np.int32)
    fy = gy - iy
    fx = gx - ix

    d1 = np.full((size, size), 1e4, dtype=np.float32)
    d2 = np.full((size, size), 1e4, dtype=np.float32)

    for dy in (-1, 0, 1):
        ny = np.clip(iy + dy + 1, 0, cells_y + 1)
        for dx in (-1, 0, 1):
            if tile_x:
                nx = ((ix + dx) % cells_x) + 1
            else:
                nx = np.clip(ix + dx + 1, 0, cells_x + 1)
            py = pts_y[ny, nx] + float(dy) - fy
            px = pts_x[ny, nx] + float(dx) - fx
            dist = np.sqrt(px * px + py * py + 1e-8)

            mask1 = dist < d1
            d2 = np.where(mask1, d1, np.minimum(d2, dist))
            d1 = np.where(mask1, dist, d1)

    edge = np.clip(d2 - d1, 0.0, 1.0)
    return np.clip(d1, 0.0, 1.4), edge


def height_to_normal_rgb(height: np.ndarray, strength: float = 2.6) -> np.ndarray:
    """Convert scalar height [0..1] into OpenGL/glTF tangent-space RGB normal map."""
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5 * strength
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5 * strength
    nx = -dx
    ny = -dy
    nz = np.ones_like(height, dtype=np.float32)
    inv_len = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz + 1e-8)
    rgb = np.stack((nx * inv_len, ny * inv_len, nz * inv_len), axis=-1)
    return np.clip(rgb * 0.5 + 0.5, 0.0, 1.0)


def _save_blender_image(
    name: str,
    rgb: np.ndarray,
    out_path: Path,
    is_data: bool,
) -> bpy.types.Image:
    """Create a Blender image from HxWx3 [0..1] float array, save PNG, and pack it."""
    h, w, _ = rgb.shape
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(rgb, 0.0, 1.0)

    img = bpy.data.images.new(name=name, width=w, height=h, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color" if is_data else "sRGB"
    img.pixels.foreach_set(rgba.ravel())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(out_path)
    img.file_format = "PNG"
    img.save()
    img.pack()
    return img


def _save_disk_png(name: str, rgb: np.ndarray, out_path: Path) -> Path:
    """Save a linear scalar/RGB map to disk as PNG without packing into .blend."""
    h, w, _ = rgb.shape
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(rgb, 0.0, 1.0)
    img = bpy.data.images.new(name=name, width=w, height=h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(rgba.ravel())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(out_path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return out_path


def generate_leaf_textures(tex_dir: Path, size: int = 2048) -> PBRTextureSet:
    """Generate 2K bullate Beta vulgaris leaf albedo, Voronoi pillow normal, waxy roughness, & 1K thickness."""
    v = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None]  # 0=petiole base -> 1=tip
    u = np.linspace(0.0, 1.0, size, dtype=np.float32)[None, :]  # 0.5=midrib
    du = np.abs(u - 0.5) * 2.0

    n_macro = fbm_2d(size, base_freq=5, octaves=4, seed=101, tile_x=False)
    n_micro = fbm_2d(size, base_freq=26, octaves=3, seed=202, tile_x=False)
    n_cell = value_noise_2d(size, freq=96, seed=215, tile_x=False)

    blade_t = np.clip((v - 0.25) / 0.75, 0.0, 1.0)
    is_blade = _smoothstep(np.clip((v - 0.22) / 0.07, 0.0, 1.0))

    # Fleshy central midrib + subtle petiole-base celery-to-blush tint + longitudinal collenchyma ribs
    midrib_half_w = 0.148 * (1.0 - 0.80 * blade_t) + 0.036 * (1.0 - is_blade)
    midrib = np.exp(-((du / np.maximum(0.013, midrib_half_w)) ** 2))
    petiole_blush = _smoothstep(np.clip((0.12 - v) / 0.12, 0.0, 1.0)) * (1.0 - du * 0.28)
    petiole_ribs = (np.sin(du * np.pi * 7.0) * 0.5 + 0.5) * (1.0 - is_blade)

    # 9 pairs of curved arcuate lateral veins branching out from midrib
    vein_field = np.zeros((size, size), dtype=np.float32)
    for k in range(9):
        v0 = 0.275 + k * 0.076
        curve_v = v0 + 0.175 * (du ** 1.32) + 0.012 * np.sin(du * 6.5 + k)
        dist = np.abs(v - curve_v)
        thickness = 0.0076 * (1.0 - 0.56 * du)
        vein_k = np.exp(-((dist / thickness) ** 2)) * np.clip(1.0 - du * 0.86, 0.0, 1.0)
        vein_field = np.maximum(vein_field, vein_k)
    vein_field *= is_blade

    # Two-scale Worley/Voronoi cellular venation & interveinal bullate cushions (characteristic Beta vulgaris!)
    f1_coarse, edge_coarse = worley_cells_2d(size, cells_y=28, cells_x=18, seed=311, tile_x=False)
    f1_fine, edge_fine = worley_cells_2d(size, cells_y=64, cells_x=44, seed=419, tile_x=False)

    vein_3rd = np.exp(-((edge_coarse / 0.062) ** 2)) * is_blade * np.clip(1.0 - midrib * 0.85, 0.0, 1.0)
    vein_4th = np.exp(-((edge_fine / 0.080) ** 2)) * is_blade * 0.62 * np.clip(1.0 - midrib * 0.9, 0.0, 1.0)
    cap_net = np.clip(vein_3rd * 0.82 + vein_4th * 0.52, 0.0, 1.0)

    # Interveinal bullate pillows bulging UPWARD between recessed secondary & tertiary veins
    bullate_macro = _smoothstep(np.clip(edge_coarse / 0.34, 0.0, 1.0)) * np.clip(
        1.0 - 0.34 * (f1_coarse ** 2), 0.25, 1.0
    )
    bullate_micro = _smoothstep(np.clip(edge_fine / 0.36, 0.0, 1.0)) * np.clip(
        1.0 - 0.30 * (f1_fine ** 2), 0.35, 1.0
    )
    bullate_mask = is_blade * np.clip(1.0 - midrib * 1.15 - vein_field * 0.95, 0.0, 1.0)
    bullate_dome = (0.72 * bullate_macro + 0.28 * bullate_micro) * bullate_mask

    col_petiole = np.array([0.72, 0.83, 0.44], dtype=np.float32)
    col_blush = np.array([0.78, 0.63, 0.47], dtype=np.float32)
    col_midrib = np.array([0.63, 0.80, 0.35], dtype=np.float32)
    col_cap_vein = np.array([0.36, 0.61, 0.21], dtype=np.float32)
    col_blade_rich = np.array([0.12, 0.43, 0.13], dtype=np.float32)
    col_blade_bright = np.array([0.25, 0.58, 0.18], dtype=np.float32)
    col_margin = np.array([0.18, 0.49, 0.13], dtype=np.float32)

    lamina = col_blade_rich + (col_blade_bright - col_blade_rich) * (
        0.46 * n_macro + 0.34 * (1.0 - blade_t) + 0.20 * bullate_dome
    )[..., None]
    lamina = lamina + (col_margin - lamina) * (
        _smoothstep(np.clip((du - 0.72) / 0.28, 0.0, 1.0)) * 0.56
    )[..., None]
    lamina *= (0.90 + 0.18 * n_micro + 0.04 * (n_cell - 0.5))[..., None]

    petiole_col = col_petiole * (1.0 - petiole_blush[..., None] * 0.40) + col_blush * (
        petiole_blush[..., None] * 0.40
    )
    petiole_col *= (0.95 + 0.08 * petiole_ribs)[..., None]

    albedo = petiole_col * (1.0 - is_blade)[..., None] + lamina * is_blade[..., None]
    albedo = albedo * (1.0 - cap_net[..., None] * 0.38) + col_cap_vein * (cap_net[..., None] * 0.38)
    vein_mix = np.clip(midrib * 0.92 + vein_field * 0.66, 0.0, 1.0)
    albedo = albedo * (1.0 - vein_mix[..., None]) + col_midrib * vein_mix[..., None]

    edge_warm = _smoothstep(np.clip((du - 0.91) / 0.09, 0.0, 1.0)) * is_blade
    albedo = np.clip(albedo + edge_warm[..., None] * np.array([0.07, 0.06, -0.02]), 0.0, 1.0)

    # Local cavity micro-AO in recessed vein channels, petiole groove, and bullate crease valleys
    pet_cavity = np.exp(-((du / np.maximum(0.03, midrib_half_w * 1.45)) ** 2)) * (1.0 - is_blade)
    vein_axil_ao = np.exp(-(((du - midrib_half_w * 0.95) / 0.045) ** 2)) * vein_field
    crease_ao = 0.09 * vein_3rd + 0.05 * vein_4th
    cavity_ao = np.clip(
        1.0 - 0.16 * pet_cavity - 0.14 * vein_axil_ao - crease_ao - 0.05 * (1.0 - n_cell),
        0.70,
        1.0,
    )
    albedo = np.clip(albedo * cavity_ao[..., None], 0.0, 1.0)

    # Anatomically true adaxial height: bullate pillows bulge UP while 2nd/3rd/4th veins sit sunken
    height = (
        0.20 * n_macro
        + 0.10 * n_micro
        + 0.05 * n_cell
        + 0.24 * midrib * (1.0 - 0.65 * is_blade)
        + 0.09 * petiole_ribs
        + 0.36 * bullate_dome
        - 0.22 * vein_field
        - 0.14 * vein_3rd
        - 0.07 * vein_4th
    )
    normal_rgb = height_to_normal_rgb(height, strength=4.2)

    # Waxy cuticle roughness: glossy bullate crests (0.22..0.29) vs matte recessed veins (0.42..0.52)
    rough = np.clip(
        0.37
        - 0.12 * bullate_dome
        + 0.11 * vein_field
        + 0.08 * cap_net
        + 0.06 * (1.0 - is_blade)
        + 0.05 * (n_micro - 0.5)
        + 0.03 * (n_cell - 0.5),
        0.19,
        0.56,
    )
    rough_rgb = np.repeat(rough[..., None], 3, axis=-1)

    # Physical translucency / inverse thickness map: dark opaque vascular ribs, bright glowing mesophyll
    lamina_thin = np.clip(0.86 + 0.10 * bullate_dome - 0.20 * vein_3rd - 0.12 * vein_4th, 0.42, 0.98)
    vein_shield = np.clip(midrib * 0.90 + vein_field * 0.68, 0.0, 0.90)
    translucency = (0.12 * (1.0 - is_blade) + lamina_thin * is_blade) * (1.0 - vein_shield * 0.80)
    translucency = np.clip(translucency, 0.08, 0.96)
    thick_down = translucency[::2, ::2] if size >= 1024 else translucency
    _save_disk_png(
        "Leaf_Thickness",
        np.repeat(thick_down[..., None], 3, axis=-1),
        tex_dir / "leaf_thickness.png",
    )

    return {
        "albedo": _save_blender_image("Leaf_Albedo", albedo, tex_dir / "leaf_albedo.png", False),
        "normal": _save_blender_image("Leaf_Normal", normal_rgb, tex_dir / "leaf_normal.png", True),
        "roughness": _save_blender_image(
            "Leaf_Roughness", rough_rgb, tex_dir / "leaf_roughness.png", True
        ),
    }


def generate_root_textures(tex_dir: Path, size: int = 2048) -> PBRTextureSet:
    """Generate 2K Beta vulgaris taproot skin with crisp lenticels, crown leaf scars, & groove soil."""
    v = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None]  # 0=crown top -> 1=tail tip
    u = np.linspace(0.0, 1.0, size, dtype=np.float32)[None, :]  # circumference [0..1]
    theta = u * (2.0 * np.pi)

    n_macro = fbm_2d(size, base_freq=6, octaves=4, seed=303, tile_x=True)
    n_micro = fbm_2d(size, base_freq=24, octaves=3, seed=404, tile_x=True)
    n_grit = value_noise_2d(size, freq=128, seed=455, tile_x=True)

    # Short crisp horizontal lenticel dashes (replaces blurry circular sine bands!)
    lent_a = value_noise_2d_aniso(size, freq_y=210, freq_x=34, seed=511, tile_x=True)
    lent_b = value_noise_2d_aniso(size, freq_y=340, freq_x=58, seed=523, tile_x=True)
    lent_gate = _smoothstep(np.clip((n_macro - 0.28) / 0.45, 0.0, 1.0))
    lenticels = (
        0.72 * _smoothstep(np.clip((lent_a - 0.67) / 0.21, 0.0, 1.0))
        + 0.48 * _smoothstep(np.clip((lent_b - 0.72) / 0.19, 0.0, 1.0))
    ) * lent_gate
    lenticels = np.clip(lenticels, 0.0, 1.0)

    # Fine transverse corky neck wrinkles concentrated on shoulder/upper root
    neck_wrinkles = value_noise_2d_aniso(size, freq_y=130, freq_x=10, seed=541, tile_x=True)
    neck_zone = _smoothstep(np.clip((v - 0.11) / 0.07, 0.0, 1.0)) * _smoothstep(
        np.clip((0.52 - v) / 0.24, 0.0, 1.0)
    )
    wrinkles = _smoothstep(np.clip((neck_wrinkles - 0.48) / 0.32, 0.0, 1.0)) * neck_zone

    # Helically twisted opposite sugar grooves aligned EXACTLY with theta - 0.24 * s in geometry
    u_shifted = (u - (0.24 / (2.0 * np.pi)) * v) % 1.0
    groove_dist = np.minimum(np.abs(u_shifted - 0.5), np.minimum(u_shifted, 1.0 - u_shifted))
    groove_band = np.exp(-((groove_dist / 0.088) ** 2)) * _smoothstep(np.clip((v - 0.16) / 0.12, 0.0, 1.0))
    groove_band *= _smoothstep(np.clip((1.0 - v) / 0.14, 0.0, 1.0))

    # Earthy chernozem soil crumbs nestled inside the sugar grooves and deeper lenticel pores
    _, soil_edge = worley_cells_2d(size, cells_y=72, cells_x=48, seed=617, tile_x=True)
    soil_crumbs = _smoothstep(np.clip((soil_edge - 0.18) / 0.45, 0.0, 1.0))
    groove_soil = np.clip(groove_band * (0.55 + 0.45 * soil_crumbs * n_grit), 0.0, 1.0)

    # Olive-green sun-exposed conical crown + phyllotactic crescent leaf scars matching 3D sculpture
    crown_mask = _smoothstep(np.clip((0.165 - v + 0.022 * (n_macro - 0.5)) / 0.075, 0.0, 1.0))
    crown_rings = (np.sin(v * 165.0 + n_macro * 2.2) * 0.5 + 0.5) * crown_mask
    bud_center_blend = _smoothstep(np.clip((0.048 - v) / 0.048, 0.0, 1.0))

    scar_rim = np.zeros((size, size), dtype=np.float32)
    for k in range(14):
        s_k = 0.028 + (0.132 - 0.028) * (k / 13.0)
        th_k = k * 2.39996323
        d_th = np.arctan2(np.sin(theta - th_k), np.cos(theta - th_k))
        s_arc = s_k - 0.009 * ((d_th / 0.44) ** 2)
        scar_k = np.exp(-((d_th / 0.28) ** 2) - (((v - s_arc) / 0.0068) ** 2))
        scar_rim = np.maximum(scar_rim, scar_k)
    scar_rim *= crown_mask

    col_cream = np.array([0.94, 0.90, 0.80], dtype=np.float32)
    col_warm = np.array([0.85, 0.78, 0.65], dtype=np.float32)
    col_lent = np.array([0.64, 0.54, 0.40], dtype=np.float32)
    col_groove = np.array([0.52, 0.42, 0.30], dtype=np.float32)
    col_soil = np.array([0.33, 0.26, 0.18], dtype=np.float32)
    col_crown = np.array([0.50, 0.64, 0.32], dtype=np.float32)
    col_crown_dark = np.array([0.37, 0.48, 0.22], dtype=np.float32)
    col_scar = np.array([0.46, 0.42, 0.27], dtype=np.float32)
    col_crown_center = np.array([0.57, 0.71, 0.36], dtype=np.float32)

    albedo = col_cream * (1.0 - 0.42 * n_macro)[..., None] + col_warm * (0.42 * n_macro)[..., None]
    # Subtle warm shoulder blush / soil rubbing
    albedo = albedo * (1.0 - wrinkles[..., None] * 0.14) + col_warm * (wrinkles[..., None] * 0.14)
    # Crisp horizontal lenticels + tiny skin specks
    speck = np.clip(lenticels * 0.52 + np.clip((n_micro - 0.62) / 0.38, 0.0, 1.0) * 0.18, 0.0, 0.72)
    albedo = albedo * (1.0 - speck[..., None]) + col_lent * speck[..., None]
    # Sugar groove base darkening + gritty dark chernozem crumbs inside grooves
    albedo = albedo * (1.0 - groove_band[..., None] * 0.56) + col_groove * (groove_band[..., None] * 0.56)
    albedo = albedo * (1.0 - groove_soil[..., None] * 0.45) + col_soil * (groove_soil[..., None] * 0.45)

    crown_col = col_crown * (1.0 - 0.30 * crown_rings)[..., None] + col_crown_dark * (
        0.30 * crown_rings
    )[..., None]
    crown_col = crown_col * (1.0 - scar_rim[..., None] * 0.52) + col_scar * (scar_rim[..., None] * 0.52)
    crown_col = crown_col * (1.0 - bud_center_blend[..., None] * 0.55) + col_crown_center * (
        bud_center_blend[..., None] * 0.55
    )
    albedo = albedo * (1.0 - crown_mask[..., None]) + crown_col * crown_mask[..., None]

    # Local groove, lenticel, and leaf-scar cavity micro-AO
    root_cavity_ao = np.clip(
        1.0 - 0.22 * groove_band - 0.12 * lenticels - 0.10 * scar_rim - 0.05 * wrinkles,
        0.66,
        1.0,
    )
    albedo = np.clip(albedo * root_cavity_ao[..., None], 0.0, 1.0)

    height = (
        0.30 * n_macro
        + 0.12 * n_micro
        + 0.05 * n_grit
        - 0.18 * lenticels
        - 0.08 * wrinkles
        - 0.30 * groove_band
        + 0.12 * groove_soil
        + 0.16 * scar_rim
        + 0.08 * crown_rings
    )
    normal_rgb = height_to_normal_rgb(height, strength=2.2)

    # Clean damp creamy flanks (0.38..0.50) vs gritty matte soil-filled sugar grooves (0.84..0.94)
    rough = np.clip(
        0.43
        + 0.22 * groove_band
        + 0.24 * groove_soil
        + 0.14 * lenticels
        + 0.10 * scar_rim
        + 0.08 * (n_micro - 0.5),
        0.32,
        0.94,
    )
    rough_rgb = np.repeat(rough[..., None], 3, axis=-1)

    root_sss = np.clip(
        0.24 + 0.16 * crown_mask + 0.18 * v * (1.0 - groove_band) * (1.0 - 0.5 * groove_soil),
        0.12,
        0.52,
    )
    rthick_down = root_sss[::2, ::2] if size >= 1024 else root_sss
    _save_disk_png(
        "Root_Thickness",
        np.repeat(rthick_down[..., None], 3, axis=-1),
        tex_dir / "root_thickness.png",
    )

    return {
        "albedo": _save_blender_image("Root_Albedo", albedo, tex_dir / "root_albedo.png", False),
        "normal": _save_blender_image("Root_Normal", normal_rgb, tex_dir / "root_normal.png", True),
        "roughness": _save_blender_image(
            "Root_Roughness", rough_rgb, tex_dir / "root_roughness.png", True
        ),
    }


def generate_seed_textures(tex_dir: Path, size: int = 512) -> PBRTextureSet:
    """Generate porous coated sugar beet pellet albedo, normal, and matte roughness."""
    n_macro = fbm_2d(size, base_freq=6, octaves=3, seed=909, tile_x=True)
    n_pores = fbm_2d(size, base_freq=22, octaves=3, seed=919, tile_x=True)

    col_coat = np.array([0.82, 0.65, 0.38], dtype=np.float32)
    col_pore = np.array([0.54, 0.39, 0.20], dtype=np.float32)
    mix = np.clip((n_pores - 0.35) / 0.5 + 0.3 * (n_macro - 0.5), 0.0, 1.0)
    albedo = col_pore * (1.0 - mix[..., None]) + col_coat * mix[..., None]

    height = 0.6 * n_pores + 0.4 * n_macro
    normal_rgb = height_to_normal_rgb(height, strength=3.6)
    rough = np.clip(0.76 + 0.14 * (0.5 - n_pores), 0.62, 0.94)
    rough_rgb = np.repeat(rough[..., None], 3, axis=-1)

    return {
        "albedo": _save_blender_image("Seed_Albedo", albedo, tex_dir / "seed_albedo.png", False),
        "normal": _save_blender_image("Seed_Normal", normal_rgb, tex_dir / "seed_normal.png", True),
        "roughness": _save_blender_image(
            "Seed_Roughness", rough_rgb, tex_dir / "seed_roughness.png", True
        ),
    }


def generate_daylight_field_hdri(
    tex_dir: Path, width: int = 1024, height: int = 512
) -> Path:
    """Generate offline fallback outdoor agricultural daylight equirectangular HDR map (.hdr)."""
    u = np.linspace(0.0, 1.0, width, endpoint=False, dtype=np.float32)[None, :]
    v = np.linspace(0.0, 1.0, height, endpoint=False, dtype=np.float32)[:, None]

    az = u * (2.0 * np.pi)
    el = (0.5 - v) * np.pi

    sky_clouds = fbm_2d(width, base_freq=4, octaves=4, seed=707, tile_x=True)[:height, :]
    horizon_glow = np.exp(-np.abs(el) / 0.18)

    el_sky = np.clip(el / (0.5 * np.pi), 0.0, 1.0)
    col_zenith = np.array([0.26, 0.54, 1.15], dtype=np.float32)
    col_sky_horizon = np.array([1.32, 1.44, 1.48], dtype=np.float32)
    sky_grad = col_zenith * (el_sky ** 0.58)[..., None] + col_sky_horizon * (
        1.0 - (el_sky ** 0.58)
    )[..., None]
    cloud_mask = _smoothstep(np.clip((sky_clouds - 0.44) / 0.36, 0.0, 1.0)) * np.clip(
        el / 0.25, 0.0, 1.0
    )
    sky_rgb = sky_grad + np.array([0.85, 0.88, 0.90], dtype=np.float32) * cloud_mask[..., None]

    sun_az = 0.72
    sun_el = 0.78
    cos_sun = np.sin(el) * np.sin(sun_el) + np.cos(el) * np.cos(sun_el) * np.cos(az - sun_az)
    cos_sun = np.clip(cos_sun, -1.0, 1.0)
    ang_sun = np.arccos(cos_sun)
    sun_corona = 2.8 * np.exp(-((ang_sun / 0.24) ** 2)) + 14.0 * np.exp(-((ang_sun / 0.055) ** 2))
    sun_rgb = sun_corona[..., None] * np.array([1.05, 0.97, 0.84], dtype=np.float32)
    sky_rgb = sky_rgb + sun_rgb + horizon_glow[..., None] * np.array([0.28, 0.30, 0.26], dtype=np.float32)

    el_ground = np.clip(-el / (0.5 * np.pi), 0.0, 1.0)
    col_field_bounce = np.array([0.34, 0.56, 0.22], dtype=np.float32)
    col_soil_nadir = np.array([0.15, 0.11, 0.08], dtype=np.float32)
    ground_rgb = col_field_bounce * (1.0 - (el_ground ** 0.52))[..., None] + col_soil_nadir * (
        el_ground ** 0.52
    )[..., None]
    ground_rgb = ground_rgb + horizon_glow[..., None] * np.array([0.22, 0.28, 0.16], dtype=np.float32)

    is_sky = _smoothstep(np.clip((el + 0.03) / 0.06, 0.0, 1.0))[..., None]
    hdr_rgb = np.maximum(1e-4, ground_rgb * (1.0 - is_sky) + sky_rgb * is_sky).astype(np.float32)

    max_ch = np.maximum.reduce([hdr_rgb[..., 0], hdr_rgb[..., 1], hdr_rgb[..., 2]])
    mantissa, exponent = np.frexp(max_ch)
    safe_v = np.where(max_ch > 1e-32, max_ch, 1.0)
    scale = np.where(max_ch > 1e-32, (mantissa * 256.0) / safe_v, 0.0)[..., None]

    rgbe = np.zeros((height, width, 4), dtype=np.uint8)
    rgbe[..., :3] = np.clip(np.floor(hdr_rgb * scale), 0, 255).astype(np.uint8)
    rgbe[..., 3] = np.where(max_ch > 1e-32, np.clip(exponent + 128, 0, 255), 0).astype(np.uint8)
    if rgbe[0, 0, 0] == 2:
        rgbe[0, 0, 0] = 3

    out_path = tex_dir / "daylight_field.hdr"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {height} +X {width}\n".encode("ascii")
    out_path.write_bytes(header + rgbe.tobytes())
    return out_path


def _file_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_field_hdri(tex_dir: Path) -> Path:
    """Cache real CC0 Poly Haven farm_field_1k.hdr (MD5 verified) + procedural backup & metadata."""
    tex_dir.mkdir(parents=True, exist_ok=True)
    fallback_path = generate_daylight_field_hdri(tex_dir, width=1024, height=512)
    ph_path = tex_dir / POLYHAVEN_HDRI_NAME

    active_file = fallback_path.name
    source = "procedural_fallback"
    md5_hex = _file_md5(fallback_path)

    try:
        need_download = (not ph_path.exists()) or (_file_md5(ph_path) != POLYHAVEN_HDRI_MD5)
        if need_download:
            req = urllib.request.Request(
                POLYHAVEN_HDRI_URL,
                headers={"User-Agent": "Periscope3DAtlas/1.0"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw_bytes = resp.read()
            actual_md5 = hashlib.md5(raw_bytes).hexdigest()
            if actual_md5 == POLYHAVEN_HDRI_MD5:
                ph_path.write_bytes(raw_bytes)
        if ph_path.exists() and _file_md5(ph_path) == POLYHAVEN_HDRI_MD5:
            active_file = ph_path.name
            source = "polyhaven_cc0_farm_field_1k"
            md5_hex = POLYHAVEN_HDRI_MD5
    except (urllib.error.URLError, TimeoutError, OSError):
        pass

    meta = {
        "file": active_file,
        "fallback_file": fallback_path.name,
        "source": source,
        "md5": md5_hex,
        "sun_dir_gltf": [2.2, 3.6, 2.6],
    }
    (tex_dir / "hdri_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return tex_dir / active_file


def generate_all_pbr_textures(assets_dir: Path) -> dict[str, PBRTextureSet]:
    """Generate 2K bullate plant PBR texture sets (leaf, root, seed) and cache CC0 field HDRI."""
    tex_dir = assets_dir / "textures"
    tex_dir.mkdir(parents=True, exist_ok=True)
    ensure_field_hdri(tex_dir)
    return {
        "leaf": generate_leaf_textures(tex_dir, size=2048),
        "root": generate_root_textures(tex_dir, size=2048),
        "seed": generate_seed_textures(tex_dir, size=512),
    }
