"""Automated Zero-Trust QA audit script for Periscope 3D crop pipelines.

Validates:
1. Python syntax (AST), Blender 5.2 API rules, bare-except ban, deprecated-model ban,
   and Windows UTF-8 encoding safety on open()/read_text()/write_text().
2. Crop passport JSON schema, monotonic BBCH timing, 3D threat anchor separation,
   and model_url file existence on disk.
3. Three.js 0.187+ WebGPU importmap consistency (no Dual-Package Hazard), HDRI asset presence,
   multi-crop routing readiness, and web/app.js syntax via node --check (UTF-8 safe on Cyrillic paths).
4. Local server MIME types (.glb, .wasm, .hdr, .webp) in serve.py.
5. Strict crop_id matching, 4-invariant geometric QA, GLB payload budget, AND 3D threat anchor
   containment inside phase_bounds in assets/<crop>_stats.json / export_stats.json.
6. Built-in --self-test Canary & Negative-Trap suite verifying detector sensitivity.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

VALID_ICONS = {"beetle", "worm", "aphid", "moth", "fungus", "weed"}
VALID_SEVERITIES = {"critical", "high", "medium"}
VALID_SYMPTOM_MODES = {
    "none",
    "rhizoctonia_rot",
    "cercospora_spots",
    "powdery_mildew",
    "phoma_rings",
    "pest_damage",
}
VALID_SYMPTOM_TARGETS = {"both", "root", "leaf"}
REQUIRED_MIMES = (".glb", ".wasm", ".hdr", ".webp")
REQUIRED_STAT_LISTS = (
    "leaf_overlap_pairs",
    "leaf_blade_root_clipping",
    "floating_leaf_bases",
    "floating_rootlet_bases",
)
DEPRECATED_MODEL_RE = re.compile(r"gemini" + r"-(?:1\.5|2\.0|2\.5)", re.IGNORECASE)
ANCHOR_BOUNDS_MARGIN = 0.16


def _check_open_utf8(node: ast.Call) -> bool:
    """Return True if node is a text-mode open() call missing explicit encoding."""
    is_open = (isinstance(node.func, ast.Name) and node.func.id == "open") or (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "open"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in ("io", "builtins")
    )
    if not is_open:
        return False
    if len(node.args) >= 4 or any(isinstance(a, ast.Starred) for a in node.args):
        return False
    if any(kw.arg in ("encoding", None) for kw in node.keywords):
        return False
    mode_val = "r"
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
        mode_val = node.args[1].value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            mode_val = kw.value.value
    return "b" not in mode_val


def audit_python_files(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    blender_dir = root / "blender"
    py_files = sorted(blender_dir.glob("*.py")) if blender_dir.exists() else []
    serve_py = root / "serve.py"
    if serve_py.exists():
        py_files.append(serve_py)

    for py_path in py_files:
        text = py_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(py_path))
        except SyntaxError as exc:
            errors.append(f"AST syntax error in {py_path.name}: {exc}")
            continue

        if "BLENDER_EEVEE_NEXT" in text:
            errors.append(f"{py_path.name}: uses removed 'BLENDER_EEVEE_NEXT' (use 'BLENDER_EEVEE' for Blender 5.2).")
        if DEPRECATED_MODEL_RE.search(text):
            errors.append(f"{py_path.name}: references deprecated legacy Gemini model identifier.")
        if re.search(r"\baction\.fcurves\b", text):
            warnings.append(f"{py_path.name}: references '.fcurves' directly; verify Blender 5.2 channelbag API is used.")

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                errors.append(f"{py_path.name}:{node.lineno}: bare 'except:' clause prohibited.")
            if isinstance(node, ast.Call):
                if _check_open_utf8(node):
                    errors.append(f"{py_path.name}:{node.lineno}: text-mode open() missing explicit encoding='utf-8'.")
                if isinstance(node.func, ast.Attribute) and node.func.attr in ("read_text", "write_text"):
                    kw_names = {kw.arg for kw in node.keywords}
                    if "encoding" not in kw_names:
                        errors.append(
                            f"{py_path.name}:{node.lineno}: {node.func.attr}() missing explicit encoding='utf-8'."
                        )

    if serve_py.exists():
        serve_text = serve_py.read_text(encoding="utf-8")
        missing_mimes = [ext for ext in REQUIRED_MIMES if ext not in serve_text]
        if missing_mimes:
            warnings.append(f"serve.py missing recommended MIME entries for: {', '.join(missing_mimes)}")

    return errors, warnings


def audit_crop_json(
    root: Path, crop_id: str
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    errors: list[str] = []
    warnings: list[str] = []
    json_path = root / "data" / f"{crop_id}.json"
    if not json_path.exists():
        return [f"Missing crop passport: {json_path}"], warnings, None

    try:
        data: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON in {json_path.name}: {exc}"], warnings, None

    for key in ("crop_id", "name", "latin", "model_url", "fps", "total_frames", "duration_sec", "phases"):
        if key not in data:
            errors.append(f"{json_path.name}: missing required top-level key '{key}'.")

    if data.get("crop_id") != crop_id:
        errors.append(f"{json_path.name}: crop_id '{data.get('crop_id')}' does not match requested '{crop_id}'.")

    model_url = str(data.get("model_url", ""))
    if model_url:
        resolved_glb = (root / "web" / model_url).resolve()
        if not resolved_glb.exists():
            errors.append(f"{json_path.name}: model_url target does not exist on disk: {resolved_glb}")

    phases = data.get("phases", [])
    if not isinstance(phases, list) or len(phases) != 6:
        errors.append(
            f"{json_path.name}: expected 6 BBCH phases, found {len(phases) if isinstance(phases, list) else 'invalid'}."
        )
        return errors, warnings, data

    prev_frame = -1
    prev_time = -1.0
    for idx, phase in enumerate(phases):
        frame = phase.get("frame")
        t_sec = phase.get("time_sec")
        if not isinstance(frame, (int, float)) or frame <= prev_frame:
            errors.append(f"{json_path.name} phase[{idx}]: non-monotonic frame {frame}.")
        if not isinstance(t_sec, (int, float)) or t_sec <= prev_time:
            errors.append(f"{json_path.name} phase[{idx}]: non-monotonic time_sec {t_sec}.")
        prev_frame = frame if isinstance(frame, (int, float)) else prev_frame
        prev_time = t_sec if isinstance(t_sec, (int, float)) else prev_time

        threats = phase.get("threats", [])
        anchors: list[tuple[str, list[float]]] = []
        for t_idx, th in enumerate(threats):
            icon = th.get("icon_type")
            sev = th.get("severity")
            anchor = th.get("anchor")
            tid = str(th.get("id", f"t{t_idx}"))
            if icon not in VALID_ICONS:
                warnings.append(
                    f"{json_path.name} phase[{idx}].{tid}: custom icon_type '{icon}' (verify THREAT_ICONS in app.js)."
                )
            if sev not in VALID_SEVERITIES:
                errors.append(f"{json_path.name} phase[{idx}].{tid}: invalid severity '{sev}'.")
            if not (isinstance(anchor, list) and len(anchor) == 3 and all(isinstance(v, (int, float)) for v in anchor)):
                errors.append(f"{json_path.name} phase[{idx}].{tid}: anchor must be [x, y, z] numeric list.")
            else:
                anchors.append((tid, [float(v) for v in anchor]))

            sym = th.get("symptom")
            if sym is not None:
                if not isinstance(sym, dict):
                    errors.append(f"{json_path.name} phase[{idx}].{tid}: symptom must be an object.")
                else:
                    smode = sym.get("mode")
                    starget = sym.get("target")
                    srad = sym.get("radius")
                    scam = sym.get("cam_offset")
                    if smode not in VALID_SYMPTOM_MODES:
                        errors.append(f"{json_path.name} phase[{idx}].{tid}: invalid symptom.mode '{smode}'.")
                    if starget not in VALID_SYMPTOM_TARGETS:
                        errors.append(f"{json_path.name} phase[{idx}].{tid}: invalid symptom.target '{starget}'.")
                    if not isinstance(srad, (int, float)) or srad <= 0.0:
                        errors.append(f"{json_path.name} phase[{idx}].{tid}: symptom.radius must be positive number.")
                    if not (
                        isinstance(scam, list)
                        and len(scam) == 3
                        and all(isinstance(v, (int, float)) for v in scam)
                    ):
                        errors.append(f"{json_path.name} phase[{idx}].{tid}: symptom.cam_offset must be [x, y, z].")

        for i in range(len(anchors)):
            for j in range(i + 1, len(anchors)):
                dist = math.dist(anchors[i][1], anchors[j][1])
                if dist < 0.08:
                    warnings.append(
                        f"{json_path.name} phase[{idx}]: close anchors {anchors[i][0]} & {anchors[j][0]} (dist={dist:.3f} < 0.08)."
                    )

    idx_path = root / "data" / "crops_index.json"
    if idx_path.exists():
        try:
            idx_data = json.loads(idx_path.read_text(encoding="utf-8"))
            ids = {c.get("id") for c in idx_data.get("crops", []) if isinstance(c, dict)}
            if crop_id not in ids:
                warnings.append(f"data/crops_index.json: active crop '{crop_id}' not registered in crops list.")
        except json.JSONDecodeError as exc:
            errors.append(f"data/crops_index.json: invalid JSON: {exc}")

    return errors, warnings, data


def audit_web_stack(root: Path, crop_id: str, check_node: bool = True) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    index_path = root / "web" / "index.html"
    app_js = root / "web" / "app.js"

    html = ""
    if index_path.exists():
        html = index_path.read_text(encoding="utf-8")
        if "three.module.js" in html and "three.webgpu.js" in html:
            errors.append("web/index.html: Dual-Package Hazard! Do not mix three.module.js and three.webgpu.js in importmap.")
        if "three@0.170" in html:
            warnings.append("web/index.html: still referencing legacy Three.js 0.170 (recommended: 0.187.0+ WebGPURenderer).")
    else:
        errors.append("Missing web/index.html.")

    if app_js.exists():
        js_text = app_js.read_text(encoding="utf-8")
        if "RGBELoader" in js_text and "three@0.187" in html:
            warnings.append("web/app.js: RGBELoader referenced with Three.js 0.187+ (use HDRLoader or UltraHDRLoader).")
        if crop_id != "sugar_beet" and '"../data/sugar_beet.json"' in js_text and "URLSearchParams" not in js_text:
            warnings.append(
                f"web/app.js: still hardcodes '../data/sugar_beet.json'; add ?crop={crop_id} URLSearchParams routing."
            )
        hdr_match = re.search(r'loadAsync\(["\'](\.\./assets/textures/[^"\']+\.hdr)["\']\)', js_text)
        if hdr_match:
            hdr_file = (root / "web" / hdr_match.group(1)).resolve()
            if not hdr_file.exists():
                warnings.append(f"web/app.js: referenced HDRI file missing on disk: {hdr_file}")

        if check_node:
            node_bin = shutil.which("node")
            if node_bin:
                proc = subprocess.run(
                    [node_bin, "--check", str(app_js)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if proc.returncode != 0:
                    errors.append(f"node --check failed on web/app.js: {proc.stderr.strip()}")
            else:
                warnings.append("node binary not found on PATH; skipped JS syntax check.")
    else:
        errors.append("Missing web/app.js.")

    return errors, warnings


def audit_export_stats(
    root: Path,
    crop_id: str = "sugar_beet",
    max_glb_bytes: int = 4_404_019,
    crop_data: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    candidates = [root / "assets" / f"{crop_id}_stats.json", root / "assets" / "export_stats.json"]
    stats_path = next((p for p in candidates if p.exists()), None)
    if stats_path is None:
        return [f"Missing export stats JSON (checked {[str(c) for c in candidates]})."], warnings, {}

    stats: dict[str, Any] = json.loads(stats_path.read_text(encoding="utf-8"))
    if stats.get("crop_id") != crop_id:
        errors.append(
            f"{stats_path.name}: stats belong to crop_id '{stats.get('crop_id')}', expected '{crop_id}' "
            f"(write assets/{crop_id}_stats.json or regenerate export_stats.json for '{crop_id}')."
        )

    for key in REQUIRED_STAT_LISTS:
        val = stats.get(key)
        if val is None:
            warnings.append(f"{stats_path.name}: missing geometric QA field '{key}'.")
        elif isinstance(val, list) and len(val) > 0:
            errors.append(f"{stats_path.name}: QA failure — {key} has {len(val)} issue(s): {val[:5]}")

    glb_bytes = int(stats.get("glb_bytes", 0))
    if glb_bytes <= 0:
        errors.append(f"{stats_path.name}: invalid glb_bytes ({glb_bytes}).")
    elif glb_bytes > max_glb_bytes:
        errors.append(
            f"{stats_path.name}: GLB payload {glb_bytes / (1024 * 1024):.2f} MB exceeds budget {max_glb_bytes / (1024 * 1024):.2f} MB."
        )

    # Cross-check 3D threat anchors against evaluated phase_bounds in glTF Y-up space
    phase_bounds = stats.get("phase_bounds", {})
    if crop_data and isinstance(phase_bounds, dict) and stats.get("crop_id") == crop_id:
        for idx, phase in enumerate(crop_data.get("phases", [])):
            pb = phase_bounds.get(f"phase_{idx}")
            if not pb or "gltf_min" not in pb or "gltf_max" not in pb:
                continue
            lo = [min(pb["gltf_min"][k], pb["gltf_max"][k]) - ANCHOR_BOUNDS_MARGIN for k in range(3)]
            hi = [max(pb["gltf_min"][k], pb["gltf_max"][k]) + ANCHOR_BOUNDS_MARGIN for k in range(3)]
            for th in phase.get("threats", []):
                anc = th.get("anchor")
                if isinstance(anc, list) and len(anc) == 3 and all(isinstance(v, (int, float)) for v in anc):
                    if not all(lo[k] <= anc[k] <= hi[k] for k in range(3)):
                        warnings.append(
                            f"phase_{idx}.{th.get('id')}: anchor {anc} lies outside phase_bounds "
                            f"[{[round(x, 3) for x in lo]} .. {[round(x, 3) for x in hi]}]."
                        )

    summary = {
        "stats_file": str(stats_path),
        "crop_id": stats.get("crop_id"),
        "blender_version": stats.get("blender_version"),
        "triangle_count": stats.get("triangle_count"),
        "glb_bytes": glb_bytes,
    }
    return errors, warnings, summary


def run_audit(root: Path, crop_id: str, max_glb_mb: float, check_node: bool = True) -> dict[str, Any]:
    all_errors: list[str] = []
    all_warnings: list[str] = []

    py_errs, py_warns = audit_python_files(root)
    json_errs, json_warns, crop_data = audit_crop_json(root, crop_id)
    web_errs, web_warns = audit_web_stack(root, crop_id, check_node=check_node)
    stat_errs, stat_warns, stat_summary = audit_export_stats(
        root, crop_id, int(max_glb_mb * 1024 * 1024), crop_data
    )

    for errs in (py_errs, json_errs, web_errs, stat_errs):
        all_errors.extend(errs)
    for warns in (py_warns, json_warns, web_warns, stat_warns):
        all_warnings.extend(warns)

    return {
        "status": "PASS" if not all_errors else "FAIL",
        "project_root": str(root),
        "crop": crop_id,
        "summary": stat_summary,
        "errors_count": len(all_errors),
        "warnings_count": len(all_warnings),
        "errors": all_errors,
        "warnings": all_warnings,
    }


def run_self_test() -> dict[str, Any]:
    """Run positive Canary control + 6 synthetic negative bug traps."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        for sub in ("blender", "data", "web", "assets"):
            (tmp / sub).mkdir(parents=True, exist_ok=True)

        (tmp / "serve.py").write_text(
            'MIMES = {".glb": 1, ".wasm": 1, ".hdr": 1, ".webp": 1}\n', encoding="utf-8"
        )
        (tmp / "blender" / "gen_wheat.py").write_text(
            'from pathlib import Path\nENGINE = "BLENDER_EEVEE"\n', encoding="utf-8"
        )
        (tmp / "web" / "index.html").write_text(
            '<script type="importmap">{"imports":{"three":"three.webgpu.js"}}</script>',
            encoding="utf-8",
        )
        (tmp / "web" / "app.js").write_text("const ok = URLSearchParams;\n", encoding="utf-8")
        (tmp / "assets" / "wheat.glb").write_bytes(b"glTF" * 64)

        valid_phases = [
            {
                "id": f"phase_{i}",
                "index": i,
                "bbch": f"BBCH {i * 10}",
                "title": f"P{i}",
                "short_label": f"P{i}",
                "frame": i * 30,
                "time_sec": i * 1.25,
                "metrics": {},
                "summary": "ok",
                "threats": [
                    {
                        "id": f"th_{i}",
                        "icon_type": "fungus",
                        "name": "T",
                        "latin": "L",
                        "severity": "high",
                        "target_zone": "Z",
                        "description": "D",
                        "protection_tip": "P",
                        "anchor": [0.0, 0.0, 0.0],
                    }
                ],
            }
            for i in range(6)
        ]
        (tmp / "data" / "wheat.json").write_text(
            json.dumps(
                {
                    "crop_id": "wheat",
                    "name": "Пшеница",
                    "latin": "Triticum aestivum",
                    "model_url": "../assets/wheat.glb",
                    "fps": 24,
                    "total_frames": 150,
                    "duration_sec": 6.25,
                    "phases": valid_phases,
                }
            ),
            encoding="utf-8",
        )
        valid_stats = {
            "crop_id": "wheat",
            "blender_version": "5.2.2 LTS",
            "triangle_count": 32000,
            "glb_bytes": 1_500_000,
            "leaf_overlap_pairs": [],
            "leaf_blade_root_clipping": [],
            "floating_leaf_bases": [],
            "floating_rootlet_bases": [],
            "phase_bounds": {
                f"phase_{i}": {"frame": i * 30, "gltf_min": [-0.3, -0.5, -0.3], "gltf_max": [0.3, 0.5, 0.3]}
                for i in range(6)
            },
        }
        (tmp / "assets" / "wheat_stats.json").write_text(json.dumps(valid_stats), encoding="utf-8")

        canary = run_audit(tmp, "wheat", max_glb_mb=4.2, check_node=False)

        # Inject 6 simultaneous negative bug traps
        legacy_tag = "gemini-" + "2" + ".0-flash"
        (tmp / "blender" / "gen_wheat.py").write_text(
            f'ENG = "BLENDER_EEVEE_NEXT"\nMODEL = "{legacy_tag}"\n'
            'try:\n    f = open("x.txt", "w")\nexcept:\n    pass\n',
            encoding="utf-8",
        )
        (tmp / "web" / "index.html").write_text(
            "three.module.js and three.webgpu.js", encoding="utf-8"
        )
        bad_stats = dict(valid_stats)
        bad_stats["crop_id"] = "sugar_beet"
        bad_stats["leaf_overlap_pairs"] = ["f150:Leaf_01<->Leaf_02"]
        bad_stats["floating_rootlet_bases"] = ["f150:Rootlet_12"]
        bad_stats["glb_bytes"] = 9_000_000
        (tmp / "assets" / "wheat_stats.json").write_text(json.dumps(bad_stats), encoding="utf-8")

        trap_res = run_audit(tmp, "wheat", max_glb_mb=4.2, check_node=False)

    passed = (canary["status"] == "PASS" and canary["errors_count"] == 0) and (
        trap_res["status"] == "FAIL" and trap_res["errors_count"] >= 7
    )
    return {
        "self_test_passed": passed,
        "canary_positive_control": {"status": canary["status"], "errors": canary["errors_count"]},
        "negative_trap_control": {
            "status": trap_res["status"],
            "errors_caught": trap_res["errors_count"],
            "sample_errors": trap_res["errors"],
        },
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Audit Periscope 3D crop pipeline artifacts and code.")
    parser.add_argument("--project-root", type=str, default=str(Path(__file__).resolve().parents[4]), help="Project root path")
    parser.add_argument("--crop", type=str, default="sugar_beet", help="Crop slug (matches data/<crop>.json)")
    parser.add_argument("--max-glb-mb", type=float, default=4.2, help="Maximum allowed GLB size in MiB")
    parser.add_argument("--self-test", action="store_true", help="Run built-in Canary + Negative-Trap self-test")
    args = parser.parse_args()

    if args.self_test:
        res = run_self_test()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["self_test_passed"] else 1

    report = run_audit(Path(args.project_root).resolve(), args.crop, args.max_glb_mb, check_node=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
