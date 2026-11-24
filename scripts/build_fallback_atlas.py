"""Generate transparent 2D WebP BBCH phase fallback sprites and precompute 3D extent profiles.

Connects to the local Periscope server (starting a temporary HTTP server if 8080 is free),
renders each crop at a canonical 900x900 (aspect=1.0, fovY=36 deg) transparent viewport
with all HUD layers hidden, captures compositor-direct transparent PNGs -> alpha WebP frames
into assets/fallback/, and precomputes exact 21-sample extent_profile arrays into data/<crop>.json
so runtime startup never blocks the main thread with 21x synchronous Box3 traversals.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import io
import json
import socket
import socketserver
import threading
from pathlib import Path
from typing import Iterator

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
FALLBACK_DIR = ROOT_DIR / "assets" / "fallback"
DATA_DIR = ROOT_DIR / "data"


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


@contextlib.contextmanager
def ensure_local_server(host: str = "127.0.0.1", port: int = 8080) -> Iterator[str]:
    base_url = f"http://{host}:{port}"
    if _is_port_open(host, port):
        yield base_url
        return

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {
            **http.server.SimpleHTTPRequestHandler.extensions_map,
            ".glb": "model/gltf-binary",
            ".json": "application/json; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".hdr": "image/vnd.radiance",
            ".webp": "image/webp",
            ".ktx2": "image/ktx2",
        }

        def log_message(self, format: str, *args: object) -> None:
            pass

    class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    handler = functools.partial(QuietHandler, directory=str(ROOT_DIR))
    httpd = ThreadedServer((host, port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield base_url
    finally:
        httpd.shutdown()
        httpd.server_close()


def build_atlas_and_extents() -> dict[str, object]:
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    crops = ["sugar_beet", "lentil"]
    summary: dict[str, object] = {}

    with ensure_local_server() as base_url, sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--enable-webgl", "--ignore-gpu-blocklist", "--enable-unsafe-webgpu"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
        page = context.new_page()

        for crop_id in crops:
            passport_path = DATA_DIR / f"{crop_id}.json"
            passport = json.loads(passport_path.read_text(encoding="utf-8"))
            phases = passport.get("phases", [])

            url = f"{base_url}/web/index.html?crop={crop_id}"
            page.goto(url, wait_until="networkidle", timeout=45000)
            page.wait_for_function(
                "() => document.getElementById('viewport-canvas')?.classList.contains('is-ready') === true",
                timeout=30000,
            )
            page.wait_for_timeout(800)

            # Precompute exact 21-sample extent_profile via Three.js in browser before stripping UI
            extent_profile = page.evaluate(
                """async ({ modelUrl, durationSec }) => {
                    const THREE = await import('three');
                    const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
                    const gltf = await new GLTFLoader().loadAsync(modelUrl);
                    const root = gltf.scene;
                    const mixer = new THREE.AnimationMixer(root);
                    const actions = gltf.animations.map((clip) => {
                        const act = mixer.clipAction(clip);
                        act.setLoop(THREE.LoopOnce);
                        act.clampWhenFinished = true;
                        act.enabled = true;
                        act.play();
                        act.paused = true;
                        act.time = 0;
                        return act;
                    });
                    const dur = Math.max(0.1, durationSec || 6.25);
                    const samples = 21;
                    const box = new THREE.Box3();
                    const out = [];
                    for (let i = 0; i < samples; i++) {
                        const t = (i / (samples - 1)) * dur;
                        for (const act of actions) {
                            const clipDur = act.getClip().duration || dur;
                            act.time = Math.max(0, Math.min(t, Math.max(0, clipDur - 1e-5)));
                        }
                        mixer.update(0);
                        root.updateMatrixWorld(true);
                        box.setFromObject(root);
                        if (!box.isEmpty()) {
                            const halfW = Math.max(
                                0.04,
                                Math.abs(box.min.x),
                                Math.abs(box.max.x),
                                Math.abs(box.min.z),
                                Math.abs(box.max.z)
                            );
                            const midY = (box.min.y + box.max.y) * 0.5;
                            out.push({
                                t: Number(t.toFixed(4)),
                                halfW: Number(halfW.toFixed(5)),
                                midY: Number(midY.toFixed(5)),
                            });
                        }
                    }
                    return out;
                }""",
                {"modelUrl": passport["model_url"], "durationSec": passport.get("duration_sec", 6.25)},
            )

            # Turn off symptoms & hotspots, set overview camera
            toggle_hotspots = page.locator("#toggle-hotspots")
            if toggle_hotspots.get_attribute("aria-pressed") == "true":
                toggle_hotspots.click()
            toggle_symptoms = page.locator("#toggle-symptoms")
            if toggle_symptoms.get_attribute("aria-pressed") == "true":
                toggle_symptoms.click()
            page.locator("[data-preset='overview']").click()
            page.wait_for_timeout(450)

            # Isolate pure transparent 900x900 canvas for compositor-direct alpha capture
            page.evaluate(
                """() => {
                    document.documentElement.style.background = 'transparent';
                    document.body.style.background = 'transparent';
                    for (const sel of [
                        '#field-backdrop',
                        '.topbar',
                        '#periscope-reticle',
                        '.stage-controls-top',
                        '#hotspot-leaders',
                        '#reticle-phase-ring',
                        '#hotspots-layer',
                        '.stage-bottom-hud',
                        '#loading-overlay',
                        '#error-banner'
                    ]) {
                        const el = document.querySelector(sel);
                        if (el) el.style.display = 'none';
                    }
                    const infoPanel = document.getElementById('info-panel');
                    if (infoPanel) {
                        infoPanel.style.position = 'fixed';
                        infoPanel.style.left = '-9999px';
                        infoPanel.style.opacity = '0';
                    }
                    const ws = document.querySelector('.workspace');
                    if (ws) {
                        ws.style.display = 'block';
                        ws.style.padding = '0';
                    }
                    const st = document.getElementById('stage-container');
                    st.style.width = '900px';
                    st.style.height = '900px';
                    st.style.minHeight = '900px';
                    st.style.maxHeight = '900px';
                    st.style.border = 'none';
                    st.style.borderRadius = '0';
                    st.style.background = 'transparent';
                    st.style.flex = 'none';
                    window.dispatchEvent(new Event('resize'));
                }"""
            )
            page.wait_for_timeout(250)

            crop_files: list[dict[str, object]] = []
            stage_loc = page.locator("#stage-container")

            for idx, phase in enumerate(phases):
                page.evaluate(
                    """(phaseIdx) => {
                        const btns = document.querySelectorAll('.phase-row-btn');
                        if (btns[phaseIdx]) btns[phaseIdx].click();
                    }""",
                    idx,
                )
                page.wait_for_timeout(1100)

                raw_png = stage_loc.screenshot(omit_background=True, type="png")
                img = Image.open(io.BytesIO(raw_png)).convert("RGBA")
                if img.size != (900, 900):
                    img = img.resize((900, 900), Image.Resampling.LANCZOS)

                arr = np.array(img)
                alpha_min = int(arr[..., 3].min())
                alpha_max = int(arr[..., 3].max())
                non_zero_pct = float((arr[..., 3] > 8).mean() * 100.0)

                out_rel = f"../assets/fallback/{crop_id}_phase_{idx}.webp"
                out_file = FALLBACK_DIR / f"{crop_id}_phase_{idx}.webp"
                img.save(out_file, format="WEBP", quality=86, alpha_quality=90, method=6)
                phase["poster_url"] = out_rel
                crop_files.append(
                    {
                        "phase_index": idx,
                        "file": out_file.name,
                        "bytes": out_file.stat().st_size,
                        "alpha_range": [alpha_min, alpha_max],
                        "plant_coverage_pct": round(non_zero_pct, 2),
                    }
                )

            passport["extent_profile"] = extent_profile
            passport["fallback_atlas"] = {
                "aspect": 1.0,
                "fov_deg": 36,
                "resolution": 900,
                "frames": [f"../assets/fallback/{crop_id}_phase_{i}.webp" for i in range(len(phases))],
            }
            passport_path.write_text(
                json.dumps(passport, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            summary[crop_id] = {
                "phases_captured": len(crop_files),
                "extent_samples": len(extent_profile),
                "total_webp_bytes": sum(int(x["bytes"]) for x in crop_files),
                "files": crop_files,
            }

        browser.close()
    return summary


if __name__ == "__main__":
    result = build_atlas_and_extents()
    print(json.dumps(result, ensure_ascii=False, indent=2))
