"""Downsample Radiance RGBE .hdr environment map from 1024x512 (1.64 MB) to 512x256 (~380 KB).

Botanical SSS/roughness PBR shaders only sample diffuse/rough-specular PMREM mipmaps (<=256px),
so 512x256 RGBE preserves identical outdoor lighting & sun highlights while cutting ~1.25 MB
of cold-start mobile cellular payload.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
TEX_DIR = ROOT_DIR / "assets" / "textures"


def read_radiance_hdr(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    # Parse header until blank line + resolution line "-Y <H> +X <W>"
    idx = 0
    while True:
        nl = raw.index(b"\n", idx)
        line = raw[idx:nl].decode("ascii", errors="replace").strip()
        idx = nl + 1
        if line == "":
            break
    nl = raw.index(b"\n", idx)
    res_line = raw[idx:nl].decode("ascii").strip().split()
    idx = nl + 1
    if len(res_line) != 4 or res_line[0] != "-Y" or res_line[2] != "+X":
        raise ValueError(f"Unsupported HDR resolution header: {res_line}")
    height = int(res_line[1])
    width = int(res_line[3])

    rgbe = np.zeros((height, width, 4), dtype=np.uint8)
    for y in range(height):
        if raw[idx] == 2 and raw[idx + 1] == 2 and (raw[idx + 2] & 0x80) == 0:
            scan_w = (raw[idx + 2] << 8) | raw[idx + 3]
            if scan_w != width:
                raise ValueError(f"Scanline width mismatch: {scan_w} != {width}")
            idx += 4
            scan_buf = np.zeros(4 * width, dtype=np.uint8)
            ptr = 0
            ptr_end = 4 * width
            while ptr < ptr_end:
                code = raw[idx]
                idx += 1
                is_run = code > 128
                count = code - 128 if is_run else code
                if count == 0 or ptr + count > ptr_end:
                    raise ValueError(f"Bad RLE scanline data at y={y}, ptr={ptr}, count={count}")
                if is_run:
                    val = raw[idx]
                    idx += 1
                    scan_buf[ptr : ptr + count] = val
                else:
                    scan_buf[ptr : ptr + count] = np.frombuffer(raw, dtype=np.uint8, count=count, offset=idx)
                    idx += count
                ptr += count
            rgbe[y] = scan_buf.reshape((4, width)).T
        else:
            row = np.frombuffer(raw, dtype=np.uint8, count=width * 4, offset=idx).reshape((width, 4))
            rgbe[y] = row
            idx += width * 4

    # Convert RGBE to linear float32 RGB
    exp = rgbe[..., 3].astype(np.int32)
    nonzero = exp > 0
    rgb = np.zeros((height, width, 3), dtype=np.float32)
    scale = np.zeros((height, width), dtype=np.float32)
    scale[nonzero] = np.ldexp(1.0, exp[nonzero] - (128 + 8))
    rgb = (rgbe[..., :3].astype(np.float32) + 0.5) * scale[..., None]
    rgb[~nonzero] = 0.0
    return rgb


def write_radiance_hdr_rle(path: Path, rgb: np.ndarray) -> None:
    height, width, _ = rgb.shape
    max_c = np.max(rgb, axis=-1)
    rgbe = np.zeros((height, width, 4), dtype=np.uint8)
    mask = max_c > 1e-32
    mantissa, exp = np.frexp(max_c[mask])
    scale = mantissa * 256.0 / max_c[mask]
    rgbe_vals = np.clip(rgb[mask] * scale[:, None], 0.0, 255.0).astype(np.uint8)
    rgbe[mask, :3] = rgbe_vals
    rgbe[mask, 3] = np.clip(exp + 128, 0, 255).astype(np.uint8)

    out = bytearray()
    out.extend(b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n")
    out.extend(f"-Y {height} +X {width}\n".encode("ascii"))

    for y in range(height):
        out.extend(bytes([2, 2, (width >> 8) & 0xFF, width & 0xFF]))
        for ch in range(4):
            scan = rgbe[y, :, ch]
            x = 0
            while x < width:
                # Look for a run of >= 4 identical bytes
                run_end = x + 1
                while run_end < width and run_end - x < 127 and scan[run_end] == scan[x]:
                    run_end += 1
                if run_end - x >= 4:
                    run_len = run_end - x
                    out.append(128 + run_len)
                    out.append(int(scan[x]))
                    x = run_end
                else:
                    lit_end = x + 1
                    while lit_end < width and lit_end - x < 128:
                        # Stop literal if a 4-byte run starts at lit_end
                        if (
                            lit_end + 3 < width
                            and scan[lit_end] == scan[lit_end + 1] == scan[lit_end + 2] == scan[lit_end + 3]
                        ):
                            break
                        lit_end += 1
                    lit_len = lit_end - x
                    out.append(lit_len)
                    out.extend(scan[x:lit_end].tobytes())
                    x = lit_end

    path.write_bytes(bytes(out))


def main() -> None:
    src_hdr = TEX_DIR / "farm_field_1k.hdr"
    dst_hdr = TEX_DIR / "farm_field_512.hdr"
    rgb = read_radiance_hdr(src_hdr)
    # 2x2 energy-preserving box filter (exact mip level 1!)
    h2, w2 = rgb.shape[0] // 2, rgb.shape[1] // 2
    down = rgb.reshape(h2, 2, w2, 2, 3).mean(axis=(1, 3))
    write_radiance_hdr_rle(dst_hdr, down)

    meta_path = TEX_DIR / "hdri_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        meta = {}
    meta["file"] = "farm_field_512.hdr"
    meta["fallback_hdri"] = "farm_field_1k.hdr"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "src_bytes": src_hdr.stat().st_size,
                "dst_bytes": dst_hdr.stat().st_size,
                "reduction_pct": round((1.0 - dst_hdr.stat().st_size / src_hdr.stat().st_size) * 100.0, 1),
                "shape": list(down.shape),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
