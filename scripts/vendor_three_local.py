"""Deterministic local vendorizer for Three.js 0.187.0 ES modules + SHA-384 SRI manifest.

Recursively resolves only the exact ES module graph imported by Periscope (three.webgpu.js,
three.tsl.js, OrbitControls.js, GLTFLoader.js, HDRLoader.js, SSAONode.js, BufferGeometryUtils,
etc.), downloads them in parallel with retry/backoff into web/vendor/three/, rewrites bare
specifiers ('three', 'three/webgpu', 'three/tsl') inside vendor addons to relative paths so
the bundle works WITHOUT a global <script type="importmap"> on third-party Nuxt 3 / Bitrix
host pages, and generates web/vendor/sri_manifest.json.
"""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import json
import posixpath
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT_DIR / "web" / "vendor" / "three"
SRI_MANIFEST_PATH = ROOT_DIR / "web" / "vendor" / "sri_manifest.json"
CDN_ROOT = "https://cdn.jsdelivr.net/npm/three@0.187.0"

SEED_MODULES = [
    "build/three.webgpu.js",
    "build/three.tsl.js",
    "examples/jsm/controls/OrbitControls.js",
    "examples/jsm/loaders/GLTFLoader.js",
    "examples/jsm/loaders/HDRLoader.js",
    "examples/jsm/tsl/display/SSAONode.js",
]

IMPORT_RE = re.compile(
    r"""((?:import|export)\s+(?:[^'"]*?\s+from\s+)?|import\s*\(\s*)(['"])([^'"]+)\2""",
    re.MULTILINE,
)

BARE_TARGETS = {
    "three": "build/three.webgpu.js",
    "three/webgpu": "build/three.webgpu.js",
    "three/tsl": "build/three.tsl.js",
}


def fetch_text_with_retry(rel_posix: str, retries: int = 3, timeout_sec: float = 20.0) -> str:
    url = f"{CDN_ROOT}/{rel_posix}"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Periscope-Vendorizer/1.0"})
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                return resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt + 1 < retries:
                time.sleep(0.7 * (2**attempt))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def resolve_specifier(current_rel: str, spec: str) -> str | None:
    if spec in BARE_TARGETS:
        return BARE_TARGETS[spec]
    if spec.startswith("three/addons/"):
        return "examples/jsm/" + spec[len("three/addons/") :]
    if spec.startswith("."):
        cur_dir = posixpath.dirname(current_rel)
        norm = posixpath.normpath(posixpath.join(cur_dir, spec))
        if not norm.startswith(".."):
            return norm
    return None


def rewrite_bare_imports(current_rel: str, source: str) -> str:
    cur_dir = posixpath.dirname(current_rel)

    def _repl(match: re.Match[str]) -> str:
        prefix, quote, spec = match.group(1), match.group(2), match.group(3)
        target_rel: str | None = None
        if spec in BARE_TARGETS:
            target_rel = BARE_TARGETS[spec]
        elif spec.startswith("three/addons/"):
            target_rel = "examples/jsm/" + spec[len("three/addons/") :]
        if target_rel is None:
            return match.group(0)
        rel_path = posixpath.relpath(target_rel, cur_dir)
        if not rel_path.startswith("."):
            rel_path = "./" + rel_path
        return f"{prefix}{quote}{rel_path}{quote}"

    return IMPORT_RE.sub(_repl, source)


def compute_sri_sha384(data: bytes) -> str:
    digest = hashlib.sha384(data).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def vendorize_all() -> dict[str, object]:
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    fetched: dict[str, str] = {}
    frontier: set[str] = set(SEED_MODULES)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        while frontier:
            batch = sorted(frontier - set(fetched.keys()))
            if not batch:
                break
            future_map = {pool.submit(fetch_text_with_retry, rel): rel for rel in batch}
            next_frontier: set[str] = set()
            for fut in concurrent.futures.as_completed(future_map):
                rel = future_map[fut]
                src = fut.result()
                fetched[rel] = src
                for m in IMPORT_RE.finditer(src):
                    dep = resolve_specifier(rel, m.group(3))
                    if dep and dep not in fetched:
                        next_frontier.add(dep)
            frontier = next_frontier

    manifest_files: dict[str, dict[str, object]] = {}
    total_bytes = 0

    for rel in sorted(fetched.keys()):
        rewritten = rewrite_bare_imports(rel, fetched[rel])
        raw = rewritten.encode("utf-8")
        out_path = VENDOR_DIR / Path(rel)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw)
        total_bytes += len(raw)
        manifest_files[f"vendor/three/{rel}"] = {
            "bytes": len(raw),
            "integrity": compute_sri_sha384(raw),
        }

    manifest = {
        "package": "three",
        "version": "0.187.0",
        "files_count": len(manifest_files),
        "total_bytes": total_bytes,
        "importmap_free": True,
        "files": manifest_files,
    }
    SRI_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    SRI_MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "files_count": len(manifest_files),
        "total_bytes": total_bytes,
        "manifest": str(SRI_MANIFEST_PATH),
    }


if __name__ == "__main__":
    summary = vendorize_all()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
