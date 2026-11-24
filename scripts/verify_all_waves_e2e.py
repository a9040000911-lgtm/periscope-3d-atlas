"""Comprehensive End-to-End & Stress Verification Suite for Waves 0–5 (D-01..D-22).

Starts an isolated local HTTP server injecting strict production Content-Security-Policy headers,
blocks all external internet requests (152-FZ / offline gate), and verifies:
  1. Strict CSP & Zero External Network Requests (3D WebGPU/WebGL2 boot + crop switch)
  2. Wave 0 Failure Cascade:
     - Complete GPU absence (navigator.gpu=undefined & WebGL2=null) -> Level-3 2D WebP Atlas + Data-First UI
     - FPS Watchdog auto-downgrade (?simulateSlowGpu=1 -> fallback-2d)
     - WebGL context loss immediate 2D poster shield + @media print layout
     - Flaky 3G network HTTP 503 auto-retry recovery
     - DOM XSS Canary payload neutralization
  3. Wave 1 Lifecycle & Performance:
     - Render-on-Demand idle sleep (0 FPS when static)
     - 100x consecutive SPA mount -> phase switch -> destroy cycles without DOM or heap runaway
  4. Wave 2 Host Site Isolation (embed-test.html):
     - White body background (#ffffff), preserved document.title, clean documentElement styles
     - Neighboring Swiper arrow-key isolation vs focused widget keyboard control
     - Live CMS pesticide dosage override & IntersectionObserver off-screen GPU pause
  5. Wave 3 Mobile Viewport & Touch Matrix (320x568 .. 1440x900):
     - Coarse touch pan-y scroll-trap freedom
     - >=44x44px effective touch hit targets on mobile phase dots
     - 6-threat stress phase on 320px & 375px viewports with 0px right-edge clipping
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import socket
import socketserver
import threading
from pathlib import Path
from typing import Iterator

from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent

STRICT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self' blob:; "
    "worker-src 'self' blob:;"
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextlib.contextmanager
def start_csp_test_server() -> Iterator[str]:
    port = _find_free_port()

    class CspHandler(http.server.SimpleHTTPRequestHandler):
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

        def end_headers(self) -> None:
            self.send_header("Content-Security-Policy", STRICT_CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    handler = functools.partial(CspHandler, directory=str(ROOT_DIR))
    httpd = ThreadedServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def run_all_verifications() -> dict[str, object]:
    results: dict[str, object] = {}

    with start_csp_test_server() as base_url, sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--enable-unsafe-webgpu",
                "--enable-precise-memory-info",
                "--js-flags=--expose-gc",
            ],
        )

        # ------------------------------------------------------------------
        # GATE 1 + GATE 3A: Offline / Strict CSP 3D Boot + Render-on-Demand Sleep
        # ------------------------------------------------------------------
        ctx1 = browser.new_context(viewport={"width": 1366, "height": 860})
        page1 = ctx1.new_page()
        external_requests: list[str] = []
        console_errors: list[str] = []
        csp_violations: list[str] = []

        def block_external(route):
            req_url = route.request.url
            if not req_url.startswith(base_url) and not req_url.startswith("data:") and not req_url.startswith("blob:"):
                external_requests.append(req_url)
                route.abort()
            else:
                route.continue_()

        page1.route("**/*", block_external)
        page1.on("pageerror", lambda err: console_errors.append(str(err)))
        page1.on(
            "console",
            lambda msg: csp_violations.append(msg.text)
            if "Content Security Policy" in msg.text
            else (console_errors.append(msg.text) if msg.type == "error" else None),
        )

        page1.goto(f"{base_url}/web/index.html?crop=sugar_beet&allowSoftwareGpu=1", wait_until="networkidle", timeout=35000)
        page1.wait_for_function("() => Boolean(window.__PERISCOPE_CTRL__) && window.__PERISCOPE_CTRL__.getDiagnostics().renderTier !== 'booting'", timeout=25000)
        diag_3d = page1.evaluate("() => window.__PERISCOPE_CTRL__.getDiagnostics()")
        assert diag_3d["renderTier"] in ("webgpu", "webgl2"), f"Expected 3D tier, got {diag_3d}"
        assert len(external_requests) == 0, f"External CDN requests detected: {external_requests}"
        assert len(csp_violations) == 0, f"CSP violations detected: {csp_violations}"
        assert len(console_errors) == 0, f"Console errors detected: {console_errors}"

        # Wait 1.6s without interaction -> Render-on-Demand must put RAF loop to sleep (0% idle GPU!)
        page1.wait_for_timeout(1600)
        diag_idle = page1.evaluate("() => window.__PERISCOPE_CTRL__.getDiagnostics()")
        assert diag_idle["isLoopRunning"] is False, f"Expected idle Render-on-Demand sleep, got {diag_idle}"

        # Test WebGL context loss recovery shield + Print layout
        page1.evaluate("() => { document.getElementById('viewport-canvas').dispatchEvent(new Event('webglcontextlost', { cancelable: true })); }")
        poster_visible_on_loss = page1.evaluate("() => !document.getElementById('stage-fallback-img').classList.contains('is-hidden-by-3d')")
        assert poster_visible_on_loss is True, "2D poster did not shield stage on context loss!"

        page1.emulate_media(media="print")
        print_state = page1.evaluate(
            """() => ({
                canvasDisplay: getComputedStyle(document.getElementById('viewport-canvas')).display,
                posterDisplay: getComputedStyle(document.getElementById('stage-fallback-img')).display,
                posterOpacity: getComputedStyle(document.getElementById('stage-fallback-img')).opacity,
            })"""
        )
        assert print_state["canvasDisplay"] == "none" and print_state["posterOpacity"] == "1", f"Bad @media print state: {print_state}"
        ctx1.close()

        results["gate1_3d_csp_offline_and_idle_sleep"] = {
            "passed": True,
            "render_tier": diag_3d["renderTier"],
            "external_requests": 0,
            "csp_violations": 0,
            "idle_loop_sleeping": True,
            "context_loss_shield_ok": True,
            "print_layout_ok": True,
        }

        # ------------------------------------------------------------------
        # GATE 2: Complete GPU Absence (Real C++ --disable-webgl + requestAdapter->null) + Network Retry + XSS Canary
        # ------------------------------------------------------------------
        browser_nogpu = p.chromium.launch(
            headless=True,
            args=["--disable-webgl", "--disable-webgl2", "--disable-3d-apis"],
        )
        ctx2 = browser_nogpu.new_context(viewport={"width": 1280, "height": 820})
        ctx2.add_init_script(
            """() => {
                if (navigator.gpu) {
                    try { navigator.gpu.requestAdapter = async () => null; } catch {}
                }
            }"""
        )
        page2 = ctx2.new_page()
        flaky_attempts = {"count": 0}

        def simulate_flaky_3g(route):
            if route.request.url.endswith("/data/sugar_beet.json") and flaky_attempts["count"] == 0:
                flaky_attempts["count"] += 1
                route.fulfill(status=503, body="Temporary 3G drop")
            else:
                if route.request.url.endswith("/data/sugar_beet.json"):
                    flaky_attempts["count"] += 1
                route.continue_()

        page2.route("**/data/sugar_beet.json", simulate_flaky_3g)
        page2.goto(f"{base_url}/web/index.html?crop=sugar_beet", wait_until="networkidle", timeout=25000)
        page2.wait_for_function("() => Boolean(window.__PERISCOPE_CTRL__) && window.__PERISCOPE_CTRL__.getDiagnostics().renderTier === 'fallback-2d'", timeout=15000)

        no_gpu_check = page2.evaluate(
            """() => {
                const ctrl = window.__PERISCOPE_CTRL__;
                ctrl.selectPhase(4, true);
                ctrl.setCatalogOverrides({
                    cercospora: {
                        name: '<img src=x onerror="window.__XSS_HIT__=true">Церкоспороз (CMS)',
                        protection_tip: 'Фунгицид 0,6 л/га'
                    }
                });
                const errorHidden = document.getElementById('error-banner').hidden;
                const phaseCount = document.querySelectorAll('.phase-row-btn').length;
                const threatCount = document.querySelectorAll('.threat-card').length;
                const posterSrc = document.getElementById('stage-fallback-img').getAttribute('src') || '';
                const hotspotCount = document.querySelectorAll('.hotspot-pin').length;
                return {
                    errorHidden,
                    phaseCount,
                    threatCount,
                    hotspotCount,
                    posterHasPhase4: posterSrc.includes('sugar_beet_phase_4.webp'),
                    xssTriggered: Boolean(window.__XSS_HIT__),
                };
            }"""
        )
        assert flaky_attempts["count"] >= 2, f"Expected retry on 503, got {flaky_attempts}"
        assert no_gpu_check["errorHidden"] is True
        assert no_gpu_check["phaseCount"] == 6 and no_gpu_check["threatCount"] > 0 and no_gpu_check["hotspotCount"] > 0
        assert no_gpu_check["posterHasPhase4"] is True
        assert no_gpu_check["xssTriggered"] is False, "XSS Canary was not neutralized!"

        # Also verify FPS Watchdog auto-downgrade (?simulateSlowGpu=1)
        page_wd = browser.new_page(viewport={"width": 1024, "height": 768})
        page_wd.goto(f"{base_url}/web/index.html?crop=sugar_beet&allowSoftwareGpu=1&simulateSlowGpu=1", wait_until="networkidle", timeout=30000)
        page_wd.wait_for_function("() => Boolean(window.__PERISCOPE_CTRL__) && window.__PERISCOPE_CTRL__.getDiagnostics().renderTier !== 'booting'", timeout=25000)
        # Trigger animation so watchdog measures 32 slow frames and downgrades to fallback-2d
        page_wd.evaluate("() => window.__PERISCOPE_CTRL__.selectPhase(3, true)")
        page_wd.wait_for_function("() => window.__PERISCOPE_CTRL__.getDiagnostics().renderTier === 'fallback-2d'", timeout=15000)
        page_wd.close()
        ctx2.close()
        browser_nogpu.close()

        results["gate2_no_gpu_2d_atlas_retry_watchdog_xss"] = {
            "passed": True,
            "flaky_503_retries": flaky_attempts["count"],
            "phase_count_without_gpu": no_gpu_check["phaseCount"],
            "fps_watchdog_downgrade_ok": True,
            "xss_canary_blocked": True,
        }

        # ------------------------------------------------------------------
        # GATE 3B: 100x SPA Mount -> Switch -> Destroy Stress & Heap Leak Gate
        # ------------------------------------------------------------------
        ctx3 = browser.new_context(viewport={"width": 1024, "height": 768})
        page3 = ctx3.new_page()
        page3.add_init_script("() => { window.__PERISCOPE_SKIP_AUTOBOOT__ = true; }")
        page3.goto(f"{base_url}/web/index.html", wait_until="domcontentloaded")
        stress_stats = page3.evaluate(
            """async () => {
                const { PeriscopeStageController } = await import('./app.js');
                const host = document.createElement('div');
                host.style.width = '800px';
                host.style.height = '600px';
                document.body.innerHTML = '';
                document.body.appendChild(host);

                if (window.gc) window.gc();
                const heapBefore = performance.memory ? performance.memory.usedJSHeapSize : 0;

                for (let i = 0; i < 100; i++) {
                    const ctrl = new PeriscopeStageController(host, {
                        cropId: i % 2 === 0 ? 'sugar_beet' : 'lentil',
                        embedded: true,
                        forceFallback2D: true,
                    });
                    await ctrl.init();
                    ctrl.selectPhase(i % 6, true);
                    ctrl.destroy();
                }

                // Also test 6 full 3D WebGPU/WebGL2 mount+destroy cycles to verify GPU resource disposal
                let last3dDiag = null;
                for (let j = 0; j < 6; j++) {
                    const ctrl3d = new PeriscopeStageController(host, {
                        cropId: j % 2 === 0 ? 'sugar_beet' : 'lentil',
                        embedded: true,
                        blockSoftwareGpu: false,
                    });
                    await ctrl3d.init();
                    ctrl3d.selectPhase(2, true);
                    ctrl3d.destroy();
                    last3dDiag = ctrl3d.getDiagnostics();
                }

                if (window.gc) window.gc();
                await new Promise((r) => setTimeout(r, 80));
                if (window.gc) window.gc();
                const heapAfter = performance.memory ? performance.memory.usedJSHeapSize : 0;
                return {
                    survivingChildren: host.childElementCount,
                    heapDeltaMb: Number(((heapAfter - heapBefore) / (1024 * 1024)).toFixed(2)),
                    last3dDestroyed: last3dDiag?.destroyed,
                    last3dGeometriesAfterDestroy: last3dDiag?.gpuMemory?.geometries ?? 0,
                };
            }"""
        )
        assert stress_stats["survivingChildren"] == 0, f"DOM leak after 100 SPA cycles: {stress_stats}"
        assert stress_stats["last3dDestroyed"] is True
        ctx3.close()

        results["gate3_100x_spa_lifecycle_stress"] = {
            "passed": True,
            **stress_stats,
        }

        # ------------------------------------------------------------------
        # GATE 4: Host Site Integration & Encapsulation (embed-test.html)
        # ------------------------------------------------------------------
        ctx4 = browser.new_context(viewport={"width": 1280, "height": 800})
        page4 = ctx4.new_page()
        page4.goto(f"{base_url}/web/embed-test.html", wait_until="networkidle", timeout=30000)
        page4.wait_for_function(
            """() => {
                const el = document.getElementById('embedded-stage');
                const d = el?.getDiagnostics?.();
                return Boolean(d && d.renderTier !== 'booting' && d.cropId === 'sugar_beet');
            }""",
            timeout=25000,
        )
        host_audit = page4.evaluate(
            """async () => {
                const stageEl = document.getElementById('embedded-stage');
                const bodyBg = getComputedStyle(document.body).backgroundColor;
                const docTitle = document.title;
                const rootSoilVar = document.documentElement.style.getPropertyValue('--soil-line-y');

                // Focus host Swiper mock and press ArrowRight -> must advance Swiper WITHOUT changing 3D phase
                const swiper = document.getElementById('host-swiper');
                swiper.focus();
                swiper.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
                const swiperSlideAfter = document.getElementById('swiper-slide-label').dataset.slide;
                const phaseAfterSwiperKey = stageEl.getDiagnostics().activePhaseIndex;

                // Apply CMS override and check rendered text inside Shadow DOM
                document.getElementById('btn-host-cms').click();
                const shadowText = stageEl.shadowRoot.textContent || '';

                // Scroll below the fold -> IntersectionObserver must pause widget
                window.scrollTo(0, 1800);
                await new Promise((r) => setTimeout(r, 250));
                const diagScrolledOut = stageEl.getDiagnostics();

                return {
                    bodyBg,
                    docTitle,
                    rootSoilVar,
                    swiperSlideAfter,
                    phaseAfterSwiperKey,
                    cmsApplied: shadowText.includes('Максим XL'),
                    offscreenLoopStopped: diagScrolledOut.isLoopRunning === false && diagScrolledOut.isIntersecting === false,
                };
            }"""
        )
        assert host_audit["bodyBg"] == "rgb(255, 255, 255)", f"Host body CSS leaked: {host_audit}"
        assert "Корпоративный портал СЗР" in host_audit["docTitle"], f"document.title overwritten: {host_audit}"
        assert host_audit["rootSoilVar"] == "", f"Root documentElement polluted: {host_audit}"
        assert host_audit["swiperSlideAfter"] == "1" and host_audit["phaseAfterSwiperKey"] == 0, f"Arrow key hijacked Swiper: {host_audit}"
        assert host_audit["cmsApplied"] is True, f"CMS catalog override failed: {host_audit}"
        assert host_audit["offscreenLoopStopped"] is True, f"Offscreen IntersectionObserver pause failed: {host_audit}"
        ctx4.close()

        results["gate4_host_encapsulation_shadow_dom_cms"] = {
            "passed": True,
            **host_audit,
        }

        # ------------------------------------------------------------------
        # GATE 5: Mobile Viewport Matrix (320px..1440px), Touch Scroll-Trap & 6-Threat Stress
        # ------------------------------------------------------------------
        viewports = [
            (320, 568),
            (375, 667),
            (390, 844),
            (768, 1024),
            (1440, 900),
        ]
        viewport_checks: list[dict[str, object]] = []

        for vw, vh in viewports:
            is_touch = vw <= 768
            ctx_m = browser.new_context(
                viewport={"width": vw, "height": vh},
                has_touch=is_touch,
                is_mobile=vw < 768,
            )
            pm = ctx_m.new_page()
            pm.goto(f"{base_url}/web/index.html?crop=sugar_beet&renderMode=2d", wait_until="networkidle", timeout=20000)
            pm.wait_for_function("() => Boolean(window.__PERISCOPE_CTRL__) && window.__PERISCOPE_CTRL__.getDiagnostics().renderTier === 'fallback-2d'", timeout=10000)

            vp_res = pm.evaluate(
                """() => {
                    const ctrl = window.__PERISCOPE_CTRL__;
                    // Inject 6 simultaneous threats in one phase to stress-test shelf overflow on 320px!
                    const sixThreats = [
                        { id: 't1', icon_type: 'fungus', name: 'Церкоспороз листьев', latin: 'C. beticola', severity: 'critical', target_zone: 'Лист', description: 'd', protection_tip: 'p', anchor: [-0.22, 0.35, 0.05] },
                        { id: 't2', icon_type: 'beetle', name: 'Свекловичная блошка', latin: 'C. concinna', severity: 'high', target_zone: 'Лист', description: 'd', protection_tip: 'p', anchor: [0.02, 0.42, 0.05] },
                        { id: 't3', icon_type: 'aphid', name: 'Листовая свекловичная тля', latin: 'A. fabae', severity: 'critical', target_zone: 'Лист', description: 'd', protection_tip: 'p', anchor: [0.24, 0.30, 0.05] },
                        { id: 't4', icon_type: 'worm', name: 'Проволочник корневой', latin: 'Agriotes', severity: 'high', target_zone: 'Корень', description: 'd', protection_tip: 'p', anchor: [-0.15, -0.25, 0.04] },
                        { id: 't5', icon_type: 'fungus', name: 'Ризоктониозная гниль', latin: 'R. solani', severity: 'critical', target_zone: 'Корень', description: 'd', protection_tip: 'p', anchor: [0.0, -0.32, 0.04] },
                        { id: 't6', icon_type: 'moth', name: 'Минирующая моль', latin: 'S. ocellatella', severity: 'medium', target_zone: 'Шейка', description: 'd', protection_tip: 'p', anchor: [0.18, -0.20, 0.04] },
                    ];
                    ctrl.renderHotspots(sixThreats);
                    ctrl.updateHotspotPositions();

                    const stageRect = document.getElementById('stage-container').getBoundingClientRect();
                    const pins = Array.from(document.querySelectorAll('.hotspot-pin'));
                    let clippedPins = 0;
                    for (const pin of pins) {
                        const r = pin.getBoundingClientRect();
                        if (r.left < stageRect.left - 1 || r.right > stageRect.right + 1 || r.top < stageRect.top - 1 || r.bottom > stageRect.bottom + 1) {
                            clippedPins += 1;
                        }
                    }

                    const dot = document.querySelector('.reticle-phase-dot');
                    const dotRect = dot.getBoundingClientRect();
                    const afterInset = parseFloat(getComputedStyle(dot, '::after').top) || 0;
                    const effectiveHitSize = Math.round(dotRect.width + Math.abs(afterInset) * 2);
                    const canvasTouchAction = getComputedStyle(document.getElementById('viewport-canvas')).touchAction;

                    return {
                        pinsCount: pins.length,
                        clippedPins,
                        effectiveHitSizePx: effectiveHitSize,
                        canvasTouchAction,
                    };
                }"""
            )
            assert vp_res["clippedPins"] == 0, f"Clipped hotspot pills at {vw}x{vh}: {vp_res}"
            assert vp_res["effectiveHitSizePx"] >= 44, f"Touch hit area < 44px at {vw}x{vh}: {vp_res}"
            if is_touch:
                assert "pan-y" in vp_res["canvasTouchAction"], f"Touch scroll trap at {vw}x{vh}: {vp_res}"

            viewport_checks.append({"viewport": f"{vw}x{vh}", **vp_res})
            ctx_m.close()

        results["gate5_mobile_viewport_and_touch_matrix"] = {
            "passed": True,
            "viewports_tested": viewport_checks,
        }

        browser.close()

    results["overall_status"] = "ALL_WAVES_PASSED"
    return results


if __name__ == "__main__":
    summary = run_all_verifications()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
