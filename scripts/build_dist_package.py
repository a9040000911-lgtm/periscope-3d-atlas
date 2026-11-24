"""Build clean, self-hosted, 152-FZ compliant production package in dist/.

Copies only verified runtime files (HTML, JS, CSS, vendor Three.js 0.187.0, JSON passports,
GLB models, 2D WebP fallback atlas, compact HDRI & thickness maps), strictly excluding
authoring files (.blend, .blend1, raw source PNGs, unused daylight_field.hdr, Python scripts),
verifies zero external CDN leaks, and writes dist/release_manifest.json with SHA-384 SRI hashes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"

FORBIDDEN_SUFFIXES = {".blend", ".blend1", ".py", ".pyc", ".pyo", ".map"}
FORBIDDEN_SUBSTRINGS = ("cdn.jsdelivr.net", "unpkg.com", "fonts.googleapis.com")


def compute_hashes(data: bytes) -> dict[str, object]:
    sha256_hex = hashlib.sha256(data).hexdigest()
    sha384_b64 = base64.b64encode(hashlib.sha384(data).digest()).decode("ascii")
    return {
        "bytes": len(data),
        "sha256": sha256_hex,
        "sri": f"sha384-{sha384_b64}",
    }


def copy_clean_file(src: Path, dst: Path) -> None:
    if src.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise ValueError(f"Refusing to package forbidden authoring file: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def build_dist() -> dict[str, object]:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Copy web/ (including vendor/)
    web_src = ROOT_DIR / "web"
    for p in sorted(web_src.rglob("*")):
        if p.is_file() and p.suffix.lower() not in FORBIDDEN_SUFFIXES:
            rel = p.relative_to(ROOT_DIR)
            copy_clean_file(p, DIST_DIR / rel)

    # 2. Copy data/*.json
    for p in sorted((ROOT_DIR / "data").glob("*.json")):
        copy_clean_file(p, DIST_DIR / "data" / p.name)

    # 3. Copy runtime assets (models, stats, fallback WebPs, runtime textures only)
    assets_src = ROOT_DIR / "assets"
    for name in ("sugar_beet.glb", "lentil.glb", "export_stats.json", "lentil_stats.json"):
        p = assets_src / name
        if p.exists():
            copy_clean_file(p, DIST_DIR / "assets" / name)

    fb_src = assets_src / "fallback"
    if fb_src.exists():
        for p in sorted(fb_src.glob("*.webp")):
            copy_clean_file(p, DIST_DIR / "assets" / "fallback" / p.name)

    tex_src = assets_src / "textures"
    allowed_tex = [
        "bg_field_sky.webp",
        "bg_chernozem_subsoil.webp",
        "hdri_meta.json",
        "farm_field_512.hdr",
        "farm_field_1k.hdr",
        "leaf_thickness.png",
        "root_thickness.png",
        "lentil_leaf_thickness.png",
        "lentil_root_thickness.png",
        "lentil_pod_thickness.png",
    ]
    for tname in allowed_tex:
        tp = tex_src / tname
        if tp.exists():
            # If compact farm_field_512.hdr exists, skip redundant 1.64 MB farm_field_1k.hdr in dist
            if tname == "farm_field_1k.hdr" and (tex_src / "farm_field_512.hdr").exists():
                continue
            copy_clean_file(tp, DIST_DIR / "assets" / "textures" / tname)

    # Copy Nginx security header profile
    nginx_conf = ROOT_DIR / "docs" / "nginx_syngenta_headers.conf"
    if nginx_conf.exists():
        copy_clean_file(nginx_conf, DIST_DIR / "docs" / nginx_conf.name)

    # 4. Audit every text file in dist/web for external CDN leaks & record manifest
    manifest_entries: dict[str, dict[str, object]] = {}
    cdn_leaks: list[str] = []
    total_bytes = 0

    for p in sorted(DIST_DIR.rglob("*")):
        if not p.is_file():
            continue
        rel_posix = p.relative_to(DIST_DIR).as_posix()
        if p.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise AssertionError(f"Forbidden file leaked into dist: {rel_posix}")
        raw = p.read_bytes()
        total_bytes += len(raw)
        manifest_entries[rel_posix] = compute_hashes(raw)

        if p.suffix.lower() in {".html", ".js", ".css", ".json"} and not rel_posix.startswith("web/vendor/"):
            txt = raw.decode("utf-8", errors="replace")
            for bad in FORBIDDEN_SUBSTRINGS:
                if bad in txt:
                    cdn_leaks.append(f"{rel_posix}: contains '{bad}'")

    manifest = {
        "package": "periscope-3d-crop-engine",
        "files_count": len(manifest_entries),
        "total_bytes": total_bytes,
        "cdn_leaks": cdn_leaks,
        "authoring_files_present": False,
        "files": manifest_entries,
    }
    (DIST_DIR / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "files_count": len(manifest_entries),
        "total_bytes": total_bytes,
        "cdn_leaks": cdn_leaks,
    }


if __name__ == "__main__":
    print(json.dumps(build_dist(), ensure_ascii=False, indent=2))
