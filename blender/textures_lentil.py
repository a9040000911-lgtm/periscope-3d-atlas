"""High-detail 2K botanical PBR texture generator for Lentil (Lens culinaris Medik.) in NumPy + Blender.

Generates WebP-ready PBR sets balancing macro close-up photorealism with fast WebGPU loading (< 3.5 MB GLB):
- lentil_leaf: 2K glaucous pubescent leaflet & stem Albedo/Normal, 1K Roughness, 512px Thickness
- lentil_pod: 2K parchment reticulate-veined pod valve Albedo/Normal, 1K Roughness, 512px 2-seed Thickness
- lentil_flower: 1K creamy pearl-white papilionaceous petals with violet-lilac nectar-guide veins
- lentil_root: 2K fibrous legume taproot bark Albedo/Normal, 1K Roughness, 512px Thickness
- lentil_nodule: 1K pinkish-coral Rhizobium nodule skin with pale white aeration lenticel ridges
- lentil_seed: 1K marbled olive-chestnut flat lens seed coat with recessed ivory hilum scar
Reuses cached Poly Haven CC0 agricultural field HDRI (farm_field_1k.hdr) via pbr_textures.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BLENDER_DIR = Path(__file__).resolve().parent
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

from pbr_textures import (  # noqa: E402
    PBRTextureSet,
    _save_blender_image,
    _save_disk_png,
    _smoothstep,
    ensure_field_hdri,
    fbm_2d,
    height_to_normal_rgb,
    value_noise_2d,
    value_noise_2d_aniso,
    worley_cells_2d,
)


def _downsample_to_512(arr: np.ndarray) -> np.ndarray:
    step = max(1, arr.shape[0] // 512)
    return arr[::step, ::step]


def generate_lentil_leaf_textures(tex_dir: Path, size: int = 2048) -> PBRTextureSet:
    """Generate 2K sunlit glaucous pubescent lentil leaflet/stem PBR maps + 512px SSS thickness."""
    v = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None]  # 0=base -> 1=mucronate tip
    u = np.linspace(0.0, 1.0, size, dtype=np.float32)[None, :]  # 0.5=midvein
    du = np.abs(u - 0.5) * 2.0

    n_macro = fbm_2d(size, base_freq=6, octaves=4, seed=1101, tile_x=False)
    n_micro = fbm_2d(size, base_freq=28, octaves=3, seed=1109, tile_x=False)
    n_pub = value_noise_2d(size, freq=180, seed=1117, tile_x=False)

    # Crisp tapering central midvein
    midvein_w = 0.072 * (1.0 - 0.72 * v) + 0.011
    midvein = np.exp(-((du / np.maximum(0.008, midvein_w)) ** 2))

    # 9 pairs of delicate arcuate pinnate lateral veins curving toward apex
    vein_field = np.zeros((size, size), dtype=np.float32)
    for k in range(9):
        v0 = 0.08 + k * 0.095
        curve_v = v0 + 0.21 * (du ** 1.18) + 0.008 * np.sin(du * 5.0 + k)
        dist = np.abs(v - curve_v)
        thickness = 0.0065 * (1.0 - 0.54 * du)
        vk = np.exp(-((dist / thickness) ** 2)) * np.clip(1.0 - du * 0.86, 0.0, 1.0)
        vein_field = np.maximum(vein_field, vk)

    # Two-scale Voronoi tertiary reticulate venation + gentle epidermal cushions
    f1_c, edge_c = worley_cells_2d(size, cells_y=46, cells_x=32, seed=1129, tile_x=False)
    _, edge_f = worley_cells_2d(size, cells_y=96, cells_x=68, seed=1141, tile_x=False)
    vein_3rd = np.exp(-((edge_c / 0.068) ** 2)) * np.clip(1.0 - midvein * 0.85, 0.0, 1.0)
    vein_4th = np.exp(-((edge_f / 0.082) ** 2)) * 0.55 * np.clip(1.0 - midvein * 0.90, 0.0, 1.0)
    cell_net = np.clip(vein_3rd * 0.78 + vein_4th * 0.45, 0.0, 1.0)
    cushion = _smoothstep(np.clip(edge_c / 0.34, 0.0, 1.0)) * np.clip(1.0 - 0.28 * (f1_c ** 2), 0.35, 1.0)

    # Sunlit glaucous pea-green Lens culinaris palette + subtle hyaline leaflet rim & basal stem hue
    col_deep = np.array([0.26, 0.55, 0.21], dtype=np.float32)
    col_fresh = np.array([0.41, 0.71, 0.28], dtype=np.float32)
    col_glaucous = np.array([0.50, 0.75, 0.43], dtype=np.float32)
    col_vein = np.array([0.66, 0.85, 0.44], dtype=np.float32)
    col_tip_warm = np.array([0.54, 0.68, 0.26], dtype=np.float32)

    albedo = col_deep + (col_fresh - col_deep) * (
        0.44 * n_macro + 0.32 * (1.0 - v) + 0.14 * (1.0 - du) + 0.10 * cushion
    )[..., None]
    bloom = _smoothstep(np.clip((n_micro - 0.28) / 0.54, 0.0, 1.0)) * 0.22 * (1.0 - midvein)
    albedo = albedo * (1.0 - bloom[..., None]) + col_glaucous * bloom[..., None]
    albedo *= (0.93 + 0.12 * n_micro + 0.05 * (n_pub - 0.5))[..., None]

    vein_mix = np.clip(midvein * 0.76 + vein_field * 0.48 + cell_net * 0.18, 0.0, 0.88)
    albedo = albedo * (1.0 - vein_mix[..., None]) + col_vein * vein_mix[..., None]

    # Delicate warm sunlit margin & mucronate apex tint
    rim_mask = _smoothstep(np.clip((du - 0.86) / 0.14, 0.0, 1.0)) * 0.35 + _smoothstep(
        np.clip((v - 0.90) / 0.10, 0.0, 1.0)
    ) * 0.32
    albedo = albedo * (1.0 - np.clip(rim_mask, 0.0, 0.5)[..., None]) + col_tip_warm * (
        np.clip(rim_mask, 0.0, 0.5)[..., None]
    )

    # Crisp micro-cavity AO along vein channels
    ao = np.clip(1.0 - 0.14 * vein_field - 0.09 * vein_3rd - 0.05 * vein_4th, 0.74, 1.0)
    albedo = np.clip(albedo * ao[..., None], 0.0, 1.0)

    # Fine adaxial botanical height: gentle mesophyll cushions, sunken pinnate veins, silky pubescence
    height = (
        0.16 * n_macro
        + 0.09 * n_micro
        + 0.08 * n_pub
        + 0.20 * midvein
        + 0.18 * cushion * (1.0 - midvein)
        - 0.19 * vein_field
        - 0.10 * vein_3rd
        - 0.05 * vein_4th
    )
    normal_rgb = height_to_normal_rgb(height, strength=3.4)

    # Satin-velvet pubescent cuticle roughness (1K packed for lean GLB)
    rough = np.clip(
        0.43 + 0.11 * bloom + 0.08 * vein_field + 0.06 * vein_3rd + 0.06 * (n_micro - 0.5) + 0.05 * (n_pub - 0.5),
        0.28,
        0.66,
    )
    rough_down = rough[::2, ::2] if size >= 2048 else rough
    rough_rgb = np.repeat(rough_down[..., None], 3, axis=-1)

    # High-contrast backlit mesophyll vs opaque vascular veins (512px disk PNG for WebGPU SSS)
    translucency = np.clip(
        (0.90 + 0.06 * cushion - 0.18 * vein_3rd - 0.10 * vein_4th)
        * (1.0 - np.clip(midvein * 0.82 + vein_field * 0.52, 0.0, 0.86)),
        0.12,
        0.96,
    )
    thick_down = _downsample_to_512(translucency)
    _save_disk_png(
        "Lentil_Leaf_Thickness",
        np.repeat(thick_down[..., None], 3, axis=-1),
        tex_dir / "lentil_leaf_thickness.png",
    )

    normal_down = normal_rgb[::2, ::2] if size >= 2048 else normal_rgb
    return {
        "albedo": _save_blender_image("Lentil_Leaf_Albedo", albedo, tex_dir / "lentil_leaf_albedo.png", False),
        "normal": _save_blender_image("Lentil_Leaf_Normal", normal_down, tex_dir / "lentil_leaf_normal.png", True),
        "roughness": _save_blender_image("Lentil_Leaf_Roughness", rough_rgb, tex_dir / "lentil_leaf_roughness.png", True),
    }


def generate_lentil_pod_textures(tex_dir: Path, size: int = 2048) -> PBRTextureSet:
    """Generate 2K parchment-veined lentil pod maps + 512px internal 2-seed backlit thickness map."""
    v = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None]  # 0=calyx base -> 1=beak tip
    u = np.linspace(0.0, 1.0, size, dtype=np.float32)[None, :]  # 0/1=sutures, 0.5=center valve
    edge_dist = np.minimum(u, 1.0 - u) * 2.0  # 0 at dorsal/ventral suture rim -> 1 at valve center

    n_macro = fbm_2d(size, base_freq=6, octaves=4, seed=1201, tile_x=True)
    n_micro = fbm_2d(size, base_freq=28, octaves=3, seed=1213, tile_x=True)
    n_grain = value_noise_2d(size, freq=140, seed=1219, tile_x=True)

    # Multi-scale oblique sclerenchyma pod fibers & parchment reticulate venation (crisp at 300% zoom!)
    fiber_a = value_noise_2d_aniso(size, freq_y=48, freq_x=16, seed=1223, tile_x=True)
    fiber_b = value_noise_2d_aniso(size, freq_y=20, freq_x=64, seed=1229, tile_x=True)
    _, cell_c = worley_cells_2d(size, cells_y=34, cells_x=24, seed=1231, tile_x=True)
    _, cell_f = worley_cells_2d(size, cells_y=76, cells_x=52, seed=1237, tile_x=True)

    diag_a = (np.sin((u * 18.0 + v * 15.0 + n_macro * 1.6) * np.pi) * 0.5 + 0.5) ** 3.2
    diag_b = (np.sin((-u * 15.0 + v * 13.0 + n_micro * 1.1) * np.pi) * 0.5 + 0.5) ** 3.6
    retic_coarse = np.exp(-((cell_c / 0.072) ** 2))
    retic_fine = np.exp(-((cell_f / 0.088) ** 2)) * 0.55
    retic_veins = np.clip(
        retic_coarse * 0.72 + retic_fine * 0.42 + (diag_a * fiber_a + diag_b * fiber_b) * 0.34,
        0.0,
        1.0,
    )

    # Thickened dorsal/ventral pod sutures with recessed dehiscence seam line
    suture_rib = np.exp(-((edge_dist / 0.13) ** 2))
    suture_crease = np.exp(-((edge_dist / 0.032) ** 2))

    # Subtle internal twin-seed shading right over the 2 lenticular seed chambers (v=0.34 and v=0.66)
    seed_chamber_1 = np.exp(-(((v - 0.31) / 0.13) ** 2) - (((u - 0.5) / 0.28) ** 2))
    seed_chamber_2 = np.exp(-(((v - 0.60) / 0.13) ** 2) - (((u - 0.5) / 0.28) ** 2))
    seed_bulges = np.clip(seed_chamber_1 + seed_chamber_2, 0.0, 1.0)

    # Fine stippled pod epidermis specks/stomata
    specks = _smoothstep(np.clip((n_grain - 0.72) / 0.20, 0.0, 1.0)) * 0.32

    # Neutral-bright parchment-ivory albedo so Pod_PBR tint drives BOTH luminous emerald green & warm golden straw!
    col_valve = np.array([0.87, 0.92, 0.80], dtype=np.float32)
    col_mottle = np.array([0.74, 0.80, 0.66], dtype=np.float32)
    col_vein = np.array([0.95, 0.98, 0.89], dtype=np.float32)
    col_suture = np.array([0.66, 0.71, 0.54], dtype=np.float32)
    col_seam = np.array([0.46, 0.49, 0.36], dtype=np.float32)
    col_speck = np.array([0.56, 0.57, 0.42], dtype=np.float32)

    albedo = col_valve * (1.0 - 0.40 * n_macro)[..., None] + col_mottle * (0.40 * n_macro)[..., None]
    albedo = albedo * (1.0 - retic_veins[..., None] * 0.36) + col_vein * (retic_veins[..., None] * 0.36)
    albedo = albedo * (1.0 - suture_rib[..., None] * 0.45) + col_suture * (suture_rib[..., None] * 0.45)
    albedo = albedo * (1.0 - suture_crease[..., None] * 0.55) + col_seam * (suture_crease[..., None] * 0.55)
    albedo = albedo * (1.0 - specks[..., None] * 0.35) + col_speck * (specks[..., None] * 0.35)
    # Gentle warm highlight over seed pillows + micro-AO in interveinal crevices
    albedo *= (0.93 + 0.09 * seed_bulges + 0.10 * n_micro - 0.12 * retic_coarse)[..., None]
    albedo = np.clip(albedo, 0.0, 1.0)

    # Rich tactile macro normal map: raised fibrous veins, keeled sutures, recessed dehiscence groove, papery grain
    height = (
        0.22 * n_macro
        + 0.10 * n_micro
        + 0.06 * n_grain
        + 0.32 * retic_veins
        + 0.28 * suture_rib
        - 0.24 * suture_crease
        + 0.12 * seed_bulges
    )
    normal_rgb = height_to_normal_rgb(height, strength=4.2)

    # Papery-waxy legume pod sheen (1K packed)
    rough = np.clip(
        0.46 + 0.14 * retic_veins + 0.10 * suture_rib + 0.08 * specks + 0.07 * (n_micro - 0.5),
        0.32,
        0.76,
    )
    rough_down = rough[::2, ::2] if size >= 2048 else rough
    rough_rgb = np.repeat(rough_down[..., None], 3, axis=-1)

    # Backlit 2-seed pod thickness map: thin glowing parchment rim vs dark opaque internal lentil seeds!
    pod_translucency = np.clip(
        (0.84 - 0.22 * retic_veins - 0.35 * suture_rib) * (1.0 - 0.72 * seed_bulges),
        0.10,
        0.92,
    )
    pthick_down = _downsample_to_512(pod_translucency)
    _save_disk_png(
        "Lentil_Pod_Thickness",
        np.repeat(pthick_down[..., None], 3, axis=-1),
        tex_dir / "lentil_pod_thickness.png",
    )

    return {
        "albedo": _save_blender_image("Lentil_Pod_Albedo", albedo, tex_dir / "lentil_pod_albedo.png", False),
        "normal": _save_blender_image("Lentil_Pod_Normal", normal_rgb, tex_dir / "lentil_pod_normal.png", True),
        "roughness": _save_blender_image("Lentil_Pod_Roughness", rough_rgb, tex_dir / "lentil_pod_roughness.png", True),
    }


def generate_lentil_flower_textures(tex_dir: Path, size: int = 1024) -> PBRTextureSet:
    """Generate 1K silky pearl-white papilionaceous petal maps with crisp violet-lilac nectar veins."""
    v = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None]  # 0=claw base -> 1=petal margin
    u = np.linspace(0.0, 1.0, size, dtype=np.float32)[None, :]  # 0.5=petal centerline
    du = np.abs(u - 0.5) * 2.0

    n_micro = fbm_2d(size, base_freq=14, octaves=3, seed=1301, tile_x=False)
    n_cell = value_noise_2d(size, freq=120, seed=1307, tile_x=False)

    # Crisp fan of 9 delicate violet-lilac nectar-guide veins radiating from petal throat
    fan_angle = (u - 0.5) / np.maximum(0.16, 0.24 + 0.88 * v)
    vein_main = (np.cos(fan_angle * np.pi * 9.0) * 0.5 + 0.5) ** 9.0
    vein_sub = (np.cos(fan_angle * np.pi * 18.0 + 0.4) * 0.5 + 0.5) ** 12.0 * 0.45
    vein_fade = _smoothstep(np.clip((v - 0.05) / 0.12, 0.0, 1.0)) * _smoothstep(
        np.clip((0.90 - v) / 0.26, 0.0, 1.0)
    )
    vein_mask = np.clip((vein_main + vein_sub) * vein_fade * np.clip(1.0 - du * 0.62, 0.0, 1.0), 0.0, 1.0)

    # Delicate pale-lavender rim blush + pearl-white body + greenish-cream claw throat
    col_claw = np.array([0.82, 0.90, 0.68], dtype=np.float32)
    col_white = np.array([0.97, 0.97, 1.00], dtype=np.float32)
    col_blush = np.array([0.86, 0.82, 0.98], dtype=np.float32)
    col_lilac = np.array([0.48, 0.42, 0.84], dtype=np.float32)

    claw_blend = _smoothstep(np.clip((0.15 - v) / 0.15, 0.0, 1.0))
    margin_blush = _smoothstep(np.clip((v - 0.62) / 0.36, 0.0, 1.0)) * 0.48
    albedo = col_white * (1.0 - margin_blush[..., None]) + col_blush * margin_blush[..., None]
    albedo = albedo * (1.0 - claw_blend[..., None]) + col_claw * claw_blend[..., None]
    albedo = albedo * (1.0 - vein_mask[..., None] * 0.74) + col_lilac * (vein_mask[..., None] * 0.74)
    albedo *= (0.96 + 0.05 * n_micro + 0.02 * (n_cell - 0.5))[..., None]
    albedo = np.clip(albedo, 0.0, 1.0)

    height = 0.14 * n_micro + 0.08 * n_cell + 0.24 * vein_mask
    normal_rgb = height_to_normal_rgb(height, strength=1.9)
    rough = np.clip(0.38 + 0.09 * (n_micro - 0.5) + 0.04 * (n_cell - 0.5), 0.30, 0.52)
    rough_down = rough[::2, ::2] if size >= 1024 else rough
    rough_rgb = np.repeat(rough_down[..., None], 3, axis=-1)

    return {
        "albedo": _save_blender_image("Lentil_Flower_Albedo", albedo, tex_dir / "lentil_flower_albedo.png", False),
        "normal": _save_blender_image("Lentil_Flower_Normal", normal_rgb, tex_dir / "lentil_flower_normal.png", True),
        "roughness": _save_blender_image("Lentil_Flower_Roughness", rough_rgb, tex_dir / "lentil_flower_roughness.png", True),
    }


def generate_lentil_root_textures(tex_dir: Path, size: int = 2048) -> PBRTextureSet:
    """Generate 2K fibrous tan-ivory legume taproot bark maps + 512px thickness map."""
    v = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None]
    n_macro = fbm_2d(size, base_freq=7, octaves=4, seed=1401, tile_x=True)
    n_micro = fbm_2d(size, base_freq=26, octaves=3, seed=1409, tile_x=True)
    n_grit = value_noise_2d(size, freq=144, seed=1417, tile_x=True)
    fibers = value_noise_2d_aniso(size, freq_y=22, freq_x=128, seed=1423, tile_x=True)
    rings = value_noise_2d_aniso(size, freq_y=160, freq_x=22, seed=1433, tile_x=True)

    col_ivory = np.array([0.85, 0.76, 0.59], dtype=np.float32)
    col_tan = np.array([0.64, 0.51, 0.35], dtype=np.float32)
    col_speck = np.array([0.42, 0.32, 0.21], dtype=np.float32)
    col_collar_green = np.array([0.44, 0.62, 0.28], dtype=np.float32)

    albedo = col_ivory * (1.0 - 0.48 * n_macro)[..., None] + col_tan * (0.48 * n_macro)[..., None]
    albedo = albedo * (0.89 + 0.18 * fibers)[..., None]
    flecks = _smoothstep(np.clip((rings - 0.66) / 0.24, 0.0, 1.0)) * 0.40
    albedo = albedo * (1.0 - flecks[..., None]) + col_speck * flecks[..., None]
    # Organic soil-collar blend right at v=0..0.09 matching Main_Stem seamlessly
    collar_mask = _smoothstep(np.clip((0.09 - v) / 0.09, 0.0, 1.0)) * 0.76
    albedo = albedo * (1.0 - collar_mask[..., None]) + col_collar_green * collar_mask[..., None]
    ao = np.clip(1.0 - 0.14 * flecks - 0.08 * (1.0 - fibers), 0.72, 1.0)
    albedo = np.clip(albedo * ao[..., None], 0.0, 1.0)

    height = 0.24 * n_macro + 0.20 * fibers + 0.10 * n_micro + 0.05 * n_grit - 0.18 * flecks
    normal_rgb = height_to_normal_rgb(height, strength=3.0)

    rough = np.clip(0.56 + 0.18 * flecks + 0.10 * (n_micro - 0.5) + 0.06 * (1.0 - fibers), 0.42, 0.88)
    rough_down = rough[::2, ::2] if size >= 2048 else rough
    rough_rgb = np.repeat(rough_down[..., None], 3, axis=-1)

    root_sss = np.clip(0.28 + 0.22 * v * (1.0 - flecks), 0.14, 0.54)
    rthick_down = _downsample_to_512(root_sss)
    _save_disk_png(
        "Lentil_Root_Thickness",
        np.repeat(rthick_down[..., None], 3, axis=-1),
        tex_dir / "lentil_root_thickness.png",
    )

    return {
        "albedo": _save_blender_image("Lentil_Root_Albedo", albedo, tex_dir / "lentil_root_albedo.png", False),
        "normal": _save_blender_image("Lentil_Root_Normal", normal_rgb, tex_dir / "lentil_root_normal.png", True),
        "roughness": _save_blender_image("Lentil_Root_Roughness", rough_rgb, tex_dir / "lentil_root_roughness.png", True),
    }


def generate_lentil_nodule_textures(tex_dir: Path, size: int = 1024) -> PBRTextureSet:
    """Generate 1K active pinkish-coral Rhizobium nodule skin with pale white aeration lenticels."""
    u = np.linspace(0.0, 1.0, size, dtype=np.float32)[None, :]
    n_macro = fbm_2d(size, base_freq=6, octaves=3, seed=1501, tile_x=True)
    n_micro = fbm_2d(size, base_freq=24, octaves=3, seed=1507, tile_x=True)
    _, edge = worley_cells_2d(size, cells_y=26, cells_x=26, seed=1511, tile_x=True)
    bumps = _smoothstep(np.clip(edge / 0.34, 0.0, 1.0))

    # Characteristic pale-ivory aerated lenticel streaks on living Rhizobium nodules
    lent_streaks = value_noise_2d_aniso(size, freq_y=14, freq_x=54, seed=1523, tile_x=True)
    white_lent = _smoothstep(np.clip((lent_streaks - 0.68) / 0.20, 0.0, 1.0)) * 0.58

    col_coral_tip = np.array([0.89, 0.50, 0.46], dtype=np.float32)
    col_buff_base = np.array([0.84, 0.68, 0.54], dtype=np.float32)
    col_lenticel = np.array([0.96, 0.91, 0.84], dtype=np.float32)

    albedo = col_coral_tip * (1.0 - 0.44 * n_macro)[..., None] + col_buff_base * (0.44 * n_macro)[..., None]
    ridge = np.clip(np.exp(-((edge / 0.09) ** 2)) * 0.28 + white_lent, 0.0, 0.78)
    albedo = albedo * (1.0 - ridge[..., None]) + col_lenticel * ridge[..., None]
    albedo *= (0.94 + 0.10 * n_micro)[..., None]
    albedo = np.clip(albedo, 0.0, 1.0)

    height = 0.30 * n_macro + 0.34 * bumps + 0.20 * white_lent + 0.08 * n_micro
    normal_rgb = height_to_normal_rgb(height, strength=3.4)
    rough = np.clip(0.54 + 0.18 * white_lent + 0.08 * (0.5 - bumps), 0.38, 0.84)
    rough_down = rough[::2, ::2] if size >= 1024 else rough
    rough_rgb = np.repeat(rough_down[..., None], 3, axis=-1)

    return {
        "albedo": _save_blender_image("Lentil_Nodule_Albedo", albedo, tex_dir / "lentil_nodule_albedo.png", False),
        "normal": _save_blender_image("Lentil_Nodule_Normal", normal_rgb, tex_dir / "lentil_nodule_normal.png", True),
        "roughness": _save_blender_image("Lentil_Nodule_Roughness", rough_rgb, tex_dir / "lentil_nodule_roughness.png", True),
    }


def generate_lentil_seed_textures(tex_dir: Path, size: int = 1024) -> PBRTextureSet:
    """Generate 1K marbled olive-chestnut flat lens seed coat with crisp ivory linear hilum scar."""
    v = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None]
    u = np.linspace(0.0, 1.0, size, dtype=np.float32)[None, :]
    n_macro = fbm_2d(size, base_freq=7, octaves=4, seed=1601, tile_x=True)
    n_mottle = fbm_2d(size, base_freq=22, octaves=3, seed=1613, tile_x=True)
    n_speck = value_noise_2d(size, freq=96, seed=1627, tile_x=True)

    col_olive = np.array([0.48, 0.45, 0.24], dtype=np.float32)
    col_bronze = np.array([0.60, 0.45, 0.23], dtype=np.float32)
    col_dark = np.array([0.19, 0.15, 0.09], dtype=np.float32)
    col_hilum = np.array([0.92, 0.88, 0.76], dtype=np.float32)

    albedo = col_olive * (1.0 - 0.46 * n_macro)[..., None] + col_bronze * (0.46 * n_macro)[..., None]
    spots = _smoothstep(np.clip((n_mottle - 0.54) / 0.22, 0.0, 1.0)) * 0.68
    micro_dots = _smoothstep(np.clip((n_speck - 0.72) / 0.16, 0.0, 1.0)) * 0.45
    albedo = albedo * (1.0 - np.clip(spots + micro_dots, 0.0, 0.82)[..., None]) + col_dark * (
        np.clip(spots + micro_dots, 0.0, 0.82)[..., None]
    )

    # Dark micropylar halo + crisp pale linear hilum scar along equatorial lens rim
    hilum_halo = np.exp(-(((v - 0.5) / 0.044) ** 2) - (((u - 0.5) / 0.115) ** 2))
    hilum = np.exp(-(((v - 0.5) / 0.019) ** 2) - (((u - 0.5) / 0.088) ** 2))
    albedo = albedo * (1.0 - hilum_halo[..., None] * 0.55) + col_dark * (hilum_halo[..., None] * 0.55)
    albedo = albedo * (1.0 - hilum[..., None] * 0.90) + col_hilum * (hilum[..., None] * 0.90)
    albedo = np.clip(albedo, 0.0, 1.0)

    height = 0.22 * n_macro + 0.14 * n_mottle + 0.06 * n_speck + 0.12 * hilum_halo - 0.26 * hilum
    normal_rgb = height_to_normal_rgb(height, strength=2.2)
    rough = np.clip(0.36 + 0.12 * spots + 0.22 * hilum + 0.06 * (n_mottle - 0.5), 0.28, 0.72)
    rough_down = rough[::2, ::2] if size >= 1024 else rough
    rough_rgb = np.repeat(rough_down[..., None], 3, axis=-1)

    return {
        "albedo": _save_blender_image("Lentil_Seed_Albedo", albedo, tex_dir / "lentil_seed_albedo.png", False),
        "normal": _save_blender_image("Lentil_Seed_Normal", normal_rgb, tex_dir / "lentil_seed_normal.png", True),
        "roughness": _save_blender_image("Lentil_Seed_Roughness", rough_rgb, tex_dir / "lentil_seed_roughness.png", True),
    }


def generate_all_lentil_textures(assets_dir: Path) -> dict[str, PBRTextureSet]:
    """Generate macro-grade 2K hero (leaf/pod) + 1K/512px companion lentil PBR sets and cache CC0 field HDRI."""
    tex_dir = assets_dir / "textures"
    tex_dir.mkdir(parents=True, exist_ok=True)
    ensure_field_hdri(tex_dir)
    return {
        "leaf": generate_lentil_leaf_textures(tex_dir, size=2048),
        "pod": generate_lentil_pod_textures(tex_dir, size=2048),
        "flower": generate_lentil_flower_textures(tex_dir, size=1024),
        "root": generate_lentil_root_textures(tex_dir, size=1024),
        "nodule": generate_lentil_nodule_textures(tex_dir, size=512),
        "seed": generate_lentil_seed_textures(tex_dir, size=512),
    }
