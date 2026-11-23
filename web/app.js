import * as THREE from "three";
import {
  abs,
  builtinAOContext,
  clamp,
  color,
  distance,
  float,
  Fn,
  frontFacing,
  If,
  mix,
  mrt,
  mx_fractal_noise_float,
  mx_worley_noise_float,
  normalView,
  packNormalToRGB,
  pass,
  positionWorld,
  sample,
  screenUV,
  select,
  sin,
  smoothstep,
  texture,
  uniform,
  unpackRGBToNormal,
  uv,
  vec3,
  vec4,
  vertexColor,
} from "three/tsl";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { HDRLoader } from "three/addons/loaders/HDRLoader.js";
import { ssao } from "three/addons/tsl/display/SSAONode.js";

const CAMERA_PRESETS = {
  overview: {
    pos: new THREE.Vector3(0.44, 0.14, 3.28),
    target: new THREE.Vector3(0.0, -0.18, 0.0),
  },
  root: {
    pos: new THREE.Vector3(0.24, -0.32, 1.95),
    target: new THREE.Vector3(0.0, -0.36, 0.0),
  },
  canopy: {
    pos: new THREE.Vector3(0.55, 1.05, 1.85),
    target: new THREE.Vector3(0.0, 0.24, 0.0),
  },
};

const SEVERITY_LABELS = {
  critical: "Критично",
  high: "Высокий риск",
  medium: "Средний риск",
};

const THREAT_ICONS = {
  beetle:
    '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="13" rx="5" ry="6"/><path d="M12 7V19M8 10L4 8M16 10L20 8M7 14L3 15M17 14L21 15M10 6L8 3M14 6L16 3"/></svg>',
  worm:
    '<svg viewBox="0 0 24 24"><path d="M4 16c2-5 5-5 7-1s5 3 9-4"/><circle cx="19.5" cy="10.5" r="1.2"/></svg>',
  aphid:
    '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="13" rx="4" ry="5"/><circle cx="12" cy="7" r="2"/><path d="M9 10L5 7M15 10L19 7M8 14L4 15M16 14L20 15M10 18L7 21M14 18L17 21"/></svg>',
  moth:
    '<svg viewBox="0 0 24 24"><path d="M12 6v12"/><path d="M12 9C8 5 3 6 4 11c1 3 4 3 8 1M12 9c4-4 9-3 8 2-1 3-4 3-8 1"/><path d="M12 13c-3 1-5 4-3 6 1.5 1 3-1 3-3M12 13c3 1 5 4 3 6-1.5 1-3-1-3-3"/></svg>',
  fungus:
    '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"/><circle cx="9.5" cy="10.5" r="1.3"/><circle cx="14.5" cy="12.5" r="1.5"/><circle cx="11.5" cy="15.5" r="1.1"/></svg>',
  weed:
    '<svg viewBox="0 0 24 24"><path d="M12 20V8M12 14C9 12 7 9 8 6c3 1 4 4 4 8M12 15c3-2 6-4 6-8-3 0-5 3-6 8"/></svg>',
};

const canvas = document.getElementById("viewport-canvas");
const stageContainer = document.getElementById("stage-container");
const hotspotsLayer = document.getElementById("hotspots-layer");
const loadingOverlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");
const errorBanner = document.getElementById("error-banner");

const statSize = document.getElementById("stat-size");
const statTris = document.getElementById("stat-tris");
const statFps = document.getElementById("stat-fps");
const statBbch = document.getElementById("stat-bbch");

const phaseSlider = document.getElementById("phase-slider");
const phaseButtonsEl = document.getElementById("phase-buttons");
const btnPrev = document.getElementById("btn-prev");
const btnNext = document.getElementById("btn-next");
const btnAutoplay = document.getElementById("btn-autoplay");
const toggleSymptomsBtn = document.getElementById("toggle-symptoms");
const toggleHotspotsBtn = document.getElementById("toggle-hotspots");
const presetButtons = Array.from(document.querySelectorAll("[data-preset]"));

const readoutBbch = document.getElementById("readout-bbch");
const readoutPhase = document.getElementById("readout-phase");
const readoutFrame = document.getElementById("readout-frame");
const phaseBbchEl = document.getElementById("phase-bbch");
const maturityLabelEl = document.getElementById("maturity-label");
const phaseTitleEl = document.getElementById("phase-title");
const phaseSummaryEl = document.getElementById("phase-summary");
const metricLabelEls = [
  document.getElementById("metric-label-0"),
  document.getElementById("metric-label-1"),
  document.getElementById("metric-label-2"),
];
const metricBrixEl = document.getElementById("metric-brix");
const metricDiamEl = document.getElementById("metric-diam");
const metricLeavesEl = document.getElementById("metric-leaves");
const cropSelectEl = document.getElementById("crop-select");
const cropNameEl = document.getElementById("crop-name");
const cropLatinEl = document.getElementById("crop-latin");
const threatCountEl = document.getElementById("threat-count");
const threatsListEl = document.getElementById("threats-list");

const SYMPTOM_MODE_MAP = {
  none: 0,
  rhizoctonia_rot: 1,
  cercospora_spots: 2,
  powdery_mildew: 3,
  phoma_rings: 4,
  pest_damage: 5,
};

const SYMPTOM_TARGET_MAP = {
  both: 0,
  root: 1,
  leaf: 2,
};

const state = {
  crop: null,
  activePhaseIndex: 0,
  activeThreatId: null,
  showHotspots: true,
  showSymptoms: true,
  symptomTargetIntensity: 0.0,
  symptomCurrentIntensity: 0.0,
  autoPlaying: false,
  currentTime: 0,
  targetTime: 0,
  durationSec: 6.25,
  cameraLerpActive: false,
  cameraGoalPos: CAMERA_PRESETS.overview.pos.clone(),
  cameraGoalTarget: CAMERA_PRESETS.overview.target.clone(),
};

let renderer = null;
let renderPipeline = null;
let scene = null;
let camera = null;
let controls = null;
let mixer = null;
let actions = [];
let hotspotItems = [];
let targetMarkerGroup = null;
let targetHaloMesh = null;
const matHandles = {
  outer: null,
  mid: null,
  heart: null,
  root: null,
};

// Reactive TSL uniforms shared across upgraded MeshSSSNodeMaterial instances
const uOuterSenescence = uniform(0.0);
const uSymptomCenter = uniform(new THREE.Vector3(0, 0, 0));
const uSymptomRadius = uniform(0.18);
const uSymptomIntensity = uniform(0.0);
const uSymptomMode = uniform(0.0); // 0=none, 1=rhizoctonia/korneed, 2=cercospora, 3=mildew, 4=phoma, 5=pest
const uSymptomTarget = uniform(0.0); // 0=both, 1=root, 2=leaf

const COLOR_OUTER_FRESH = new THREE.Color("#edf5df");
const COLOR_OUTER_MATURE = new THREE.Color("#d8be56");
const COLOR_MID_FRESH = new THREE.Color("#f5faef");
const COLOR_MID_MATURE = new THREE.Color("#dce8a8");
const COLOR_HEART_FRESH = new THREE.Color("#e2ffad");
const COLOR_HEART_MATURE = new THREE.Color("#cce87a");
const COLOR_ROOT_EARLY = new THREE.Color("#ffffff");
const COLOR_ROOT_MATURE = new THREE.Color("#f4ecd8");
const tmpColor = new THREE.Color();

function showError(message) {
  loadingOverlay.hidden = true;
  errorBanner.hidden = false;
  errorBanner.innerHTML = `<strong>Не удалось запустить 3D-сцену:</strong><br>${message}`;
}

function upgradeToPhotorealNodeMaterial(srcMat, tier, leafThickTex, rootThickTex, hasVertexColor) {
  const nodeMat = new THREE.MeshSSSNodeMaterial();
  nodeMat.name = srcMat.name;
  nodeMat.map = srcMat.map || null;
  nodeMat.normalMap = srcMat.normalMap || null;
  nodeMat.normalScale = srcMat.normalScale ? srcMat.normalScale.clone() : new THREE.Vector2(1, 1);
  nodeMat.roughnessMap = srcMat.roughnessMap || null;
  nodeMat.roughness = typeof srcMat.roughness === "number" ? srcMat.roughness : 0.85;
  nodeMat.metalness = 0.0;
  nodeMat.color = srcMat.color ? srcMat.color.clone() : new THREE.Color(0xffffff);
  nodeMat.side = srcMat.side;

  const uMatTint = uniform(nodeMat.color.clone());
  const uRoughMul = uniform(nodeMat.roughness);
  nodeMat.userData.uMatTint = uMatTint;
  nodeMat.userData.uRoughMul = uRoughMul;

  const isLeaf = tier === "outer" || tier === "mid" || tier === "heart";
  const isRoot = tier === "root";

  const texRgb = srcMat.map ? texture(srcMat.map, uv()).rgb : vec3(1.0, 1.0, 1.0);
  const vColRgb = hasVertexColor ? vertexColor().rgb : vec3(1.0, 1.0, 1.0);
  let baseCol = texRgb.mul(vColRgb).mul(uMatTint);
  let baseRough = srcMat.roughnessMap ? texture(srcMat.roughnessMap, uv()).g.mul(uRoughMul) : uRoughMul;
  let clearcoatVal = float(isLeaf ? 0.16 : isRoot ? 0.06 : 0.0);

  if (isLeaf) {
    nodeMat.clearcoat = 0.22;
    nodeMat.clearcoatRoughness = 0.36;
    nodeMat.sheen = 0.08;
    nodeMat.sheenRoughness = 0.54;
    nodeMat.sheenColor = new THREE.Color(0x8bc34a);

    // Botanical adaxial (upper glossy deep-emerald) vs abaxial (lower paler matte) side differentiation
    const adaxialCol = baseCol.mul(vec3(0.95, 0.99, 0.94));
    const abaxialCol = mix(baseCol.mul(float(1.14)), vec3(0.42, 0.56, 0.24), float(0.24));
    baseCol = select(frontFacing, adaxialCol, abaxialCol);
    baseRough = select(frontFacing, baseRough.mul(float(0.86)), baseRough.mul(float(1.24)));
    clearcoatVal = select(frontFacing, float(0.22), float(0.05));

    // Edge-first organic leaf senescence on outer tier at BBCH 39 -> 49
    const edgeDist = abs(uv().x.sub(float(0.5))).mul(float(2.0));
    const tipDist = clamp(uv().y.sub(float(0.26)).div(float(0.74)), float(0.0), float(1.0));
    const senNoise = mx_fractal_noise_float(positionWorld.mul(float(6.5))).mul(float(0.32));
    let senDryMask = float(0.0);
    if (tier === "outer") {
      const edgeCoord = edgeDist.mul(float(0.68)).add(tipDist.mul(float(0.50))).add(senNoise);
      const chlorosisMask = smoothstep(float(0.72), float(1.18), edgeCoord).mul(uOuterSenescence);
      const crispBrownMask = smoothstep(float(0.96), float(1.28), edgeCoord)
        .mul(clamp(uOuterSenescence.sub(float(0.45)).div(float(0.55)), float(0.0), float(1.0)));
      baseCol = mix(baseCol, vec3(0.74, 0.64, 0.17), chlorosisMask.mul(float(0.78)));
      baseCol = mix(baseCol, vec3(0.36, 0.24, 0.09), crispBrownMask.mul(float(0.85)));
      baseRough = mix(baseRough, float(0.86), crispBrownMask.mul(float(0.85)));
      clearcoatVal = clearcoatVal.mul(float(1.0).sub(chlorosisMask.mul(float(0.75))));
      senDryMask = crispBrownMask;
    }

    // Calibrated Three.js 0.187.0 MeshSSSNodeMaterial translucency (vein-detailed backlit glow)
    const thickSample = leafThickTex ? texture(leafThickTex, uv()).r : float(0.75);
    const sssTint = color(tier === "heart" ? 0x6eb81e : tier === "mid" ? 0x3b9a14 : 0x4b8f12);
    const sssSideBoost = select(frontFacing, float(1.0), float(1.18));
    nodeMat.thicknessColorNode = sssTint
      .mul(thickSample)
      .mul(sssSideBoost)
      .mul(float(1.0).sub(senDryMask.mul(float(0.82))));
    nodeMat.thicknessDistortionNode = float(0.36);
    nodeMat.thicknessAmbientNode = float(0.0);
    nodeMat.thicknessAttenuationNode = float(0.085);
    nodeMat.thicknessPowerNode = float(3.2);
    nodeMat.thicknessScaleNode = float(2.3);

    // Dynamic rosette & crown funnel ambient occlusion (augments SSAO in deep collar)
    const radialDist = positionWorld.xz.length();
    const heightAboveCrown = clamp(positionWorld.y.add(float(0.02)).div(float(0.28)), float(0.0), float(1.0));
    const radialOpen = clamp(radialDist.div(float(0.18)), float(0.0), float(1.0));
    nodeMat.aoNode = mix(
      float(0.70),
      float(1.0),
      clamp(heightAboveCrown.mul(float(0.62)).add(radialOpen.mul(float(0.58))), float(0.0), float(1.0))
    );
  } else if (isRoot) {
    nodeMat.clearcoat = 0.06;
    nodeMat.clearcoatRoughness = 0.58;
    nodeMat.sheen = 0.05;
    nodeMat.sheenRoughness = 0.68;
    nodeMat.sheenColor = new THREE.Color(0xeaddc4);

    const rThick = rootThickTex ? texture(rootThickTex, uv()).r : float(0.30);
    nodeMat.thicknessColorNode = color(0xd9c296).mul(rThick);
    nodeMat.thicknessDistortionNode = float(0.24);
    nodeMat.thicknessAmbientNode = float(0.0);
    nodeMat.thicknessAttenuationNode = float(0.04);
    nodeMat.thicknessPowerNode = float(3.6);
    nodeMat.thicknessScaleNode = float(1.15);
  }

  // Uniform-branched GPU symptom overlay (skips 100% of noise work when symptoms off or non-target)
  const targetMatch = isRoot
    ? select(uSymptomTarget.lessThan(float(1.5)), float(1.0), float(0.0))
    : isLeaf
      ? select(uSymptomTarget.equal(float(0.0)).or(uSymptomTarget.greaterThan(float(1.5))), float(1.0), float(0.0))
      : select(uSymptomTarget.lessThan(float(1.5)), float(1.0), float(0.0));

  const evalSymptomColorRough = Fn(() => {
    const outCol = baseCol.toVar();
    const outRough = baseRough.toVar();

    If(
      uSymptomIntensity.greaterThan(float(0.005)).and(targetMatch.greaterThan(float(0.5))),
      () => {
        const distToFocus = distance(positionWorld, uSymptomCenter);
        const orgNoise = mx_fractal_noise_float(positionWorld.mul(float(14.0)));
        const warpedDist = distToFocus.add(orgNoise.mul(uSymptomRadius).mul(float(0.32)));
        const focusMask = float(1.0)
          .sub(smoothstep(uSymptomRadius.mul(float(0.26)), uSymptomRadius, warpedDist))
          .mul(uSymptomIntensity);

        If(uSymptomMode.lessThan(float(1.5)), () => {
          // Mode 1: Rhizoctonia / Korneed dark dry cracked necrosis
          const crackN = mx_fractal_noise_float(positionWorld.mul(float(36.0)));
          const m1 = focusMask.mul(smoothstep(float(-0.35), float(0.45), crackN.add(float(0.35))));
          outCol.assign(mix(outCol, vec3(0.065, 0.036, 0.022), m1.mul(float(0.92))));
          outRough.assign(mix(outRough, float(0.95), m1));
        })
          .ElseIf(uSymptomMode.lessThan(float(2.5)), () => {
            // Mode 2: Cercospora beticola 2-4mm ash-grey spots with sharp crimson-purple halo
            const wCell = mx_worley_noise_float(positionWorld.mul(float(44.0)));
            const spotCore = float(1.0).sub(smoothstep(float(0.16), float(0.25), wCell));
            const spotHalo = smoothstep(float(0.18), float(0.24), wCell).mul(
              float(1.0).sub(smoothstep(float(0.28), float(0.38), wCell))
            );
            const m2Core = focusMask.mul(spotCore);
            const m2Halo = focusMask.mul(spotHalo);
            outCol.assign(mix(outCol, vec3(0.38, 0.07, 0.10), m2Halo.mul(float(0.92))));
            outCol.assign(mix(outCol, vec3(0.56, 0.51, 0.45), m2Core.mul(float(0.90))));
            outRough.assign(mix(outRough, float(0.92), clamp(m2Core.add(m2Halo), float(0.0), float(1.0))));
          })
          .ElseIf(uSymptomMode.lessThan(float(3.5)), () => {
            // Mode 3: Erysiphe betae white-grey powdery mildew predominantly on upper surface
            const mPatch = smoothstep(
              float(-0.18),
              float(0.36),
              mx_fractal_noise_float(positionWorld.mul(float(22.0)))
            );
            const upperBias = select(frontFacing, float(1.0), float(0.20));
            const m3 = focusMask.mul(mPatch).mul(upperBias);
            outCol.assign(mix(outCol, vec3(0.86, 0.87, 0.83), m3.mul(float(0.82))));
            outRough.assign(mix(outRough, float(0.96), m3));
          })
          .ElseIf(uSymptomMode.lessThan(float(4.5)), () => {
            // Mode 4: Phoma betae concentric target-board dark dry rot rings
            const ringW = sin(distToFocus.mul(float(105.0)).add(orgNoise.mul(float(4.5))))
              .mul(float(0.5))
              .add(float(0.5));
            const phCol = mix(vec3(0.10, 0.065, 0.040), vec3(0.42, 0.29, 0.17), ringW);
            outCol.assign(mix(outCol, phCol, focusMask.mul(float(0.92))));
            outRough.assign(mix(outRough, float(0.92), focusMask));
          })
          .Else(() => {
            // Mode 5: Flea beetle / leaf-miner / cutworm / aphid lesions & chlorosis
            const pCell = mx_worley_noise_float(positionWorld.mul(float(34.0)));
            const pCen = float(1.0).sub(smoothstep(float(0.18), float(0.27), pCell));
            const pRim = smoothstep(float(0.22), float(0.28), pCell).mul(
              float(1.0).sub(smoothstep(float(0.30), float(0.39), pCell))
            );
            const m5C = focusMask.mul(pCen);
            const m5R = focusMask.mul(pRim);
            outCol.assign(mix(outCol, vec3(0.68, 0.67, 0.34), focusMask.mul(float(0.36))));
            outCol.assign(mix(outCol, vec3(0.32, 0.18, 0.08), m5R.mul(float(0.86))));
            outCol.assign(mix(outCol, vec3(0.78, 0.74, 0.46), m5C.mul(float(0.84))));
            outRough.assign(mix(outRough, float(0.86), clamp(m5C.add(m5R), float(0.0), float(1.0))));
          });
      }
    );

    return vec4(outCol.x, outCol.y, outCol.z, clamp(outRough, float(0.16), float(0.98)));
  })();

  const symRes = evalSymptomColorRough.toVar();
  const lesionMatteFactor = smoothstep(float(0.78), float(0.93), symRes.w).mul(uSymptomIntensity);

  if ((isLeaf || isRoot) && nodeMat.thicknessColorNode) {
    nodeMat.thicknessColorNode = nodeMat.thicknessColorNode.mul(
      float(1.0).sub(lesionMatteFactor.mul(float(0.85)))
    );
  }

  nodeMat.colorNode = symRes.rgb;
  nodeMat.roughnessNode = symRes.w;
  if (isLeaf || isRoot) {
    nodeMat.clearcoatNode = clamp(clearcoatVal.mul(float(1.0).sub(lesionMatteFactor)), float(0.0), float(0.35));
  }
  return nodeMat;
}

async function initScene() {
  const isMobile = window.innerWidth < 768;
  renderer = new THREE.WebGPURenderer({ canvas, antialias: true, alpha: true });
  await renderer.init();
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 2));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = 1.04;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  scene = new THREE.Scene();

  const w = stageContainer.clientWidth || 800;
  const h = stageContainer.clientHeight || 540;
  camera = new THREE.PerspectiveCamera(36, w / h, 0.05, 40);
  camera.position.copy(CAMERA_PRESETS.overview.pos);

  controls = new OrbitControls(camera, canvas);
  controls.target.copy(CAMERA_PRESETS.overview.target);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 0.85;
  controls.maxDistance = 6.0;
  controls.maxPolarAngle = Math.PI * 0.88;
  controls.addEventListener("start", () => {
    state.cameraLerpActive = false;
  });

  // Outdoor sunlight aligned with farm_field HDRI + sky-to-chernozem bounce + crisp soft self-shadows
  const hemi = new THREE.HemisphereLight(0xe4f3ff, 0x3b2c1e, 0.48);
  scene.add(hemi);

  const shadowRes = isMobile ? 1024 : 2048;
  const keyLight = new THREE.DirectionalLight(0xfff6e8, 2.30);
  keyLight.position.set(2.2, 3.6, 2.6);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(shadowRes, shadowRes);
  keyLight.shadow.camera.near = 0.4;
  keyLight.shadow.camera.far = 9.0;
  const d = 1.25;
  keyLight.shadow.camera.left = -d;
  keyLight.shadow.camera.right = d;
  keyLight.shadow.camera.top = d;
  keyLight.shadow.camera.bottom = -d;
  keyLight.shadow.bias = -0.0003;
  keyLight.shadow.normalBias = 0.018;
  keyLight.shadow.radius = 2.5;
  scene.add(keyLight);

  // Load outdoor Poly Haven HDRI asynchronously in parallel (never blocks First Paint of 3D model)
  (async () => {
    try {
      let hdrUrl = "../assets/textures/farm_field_1k.hdr";
      try {
        const metaRes = await fetch("../assets/textures/hdri_meta.json");
        if (metaRes.ok) {
          const meta = await metaRes.json();
          if (meta.file) hdrUrl = `../assets/textures/${meta.file}`;
          if (Array.isArray(meta.sun_dir_gltf) && meta.sun_dir_gltf.length === 3) {
            keyLight.position.set(meta.sun_dir_gltf[0], meta.sun_dir_gltf[1], meta.sun_dir_gltf[2]);
          }
        }
      } catch {
        // use default farm_field_1k.hdr
      }
      const hdrLoader = new HDRLoader();
      let hdrTex = null;
      try {
        hdrTex = await hdrLoader.loadAsync(hdrUrl);
      } catch {
        hdrTex = await hdrLoader.loadAsync("../assets/textures/daylight_field.hdr");
      }
      hdrTex.mapping = THREE.EquirectangularReflectionMapping;
      scene.environment = hdrTex;
      scene.environmentIntensity = 0.90;
    } catch (hdrErr) {
      console.warn("HDR environment load skipped:", hdrErr);
    }
  })();

  const fillLight = new THREE.DirectionalLight(0xd2e6ff, 0.62);
  fillLight.position.set(-2.4, 1.3, 2.2);
  scene.add(fillLight);

  const rimLight = new THREE.DirectionalLight(0xf3fee4, 1.10);
  rimLight.position.set(0.3, 1.8, -2.8);
  scene.add(rimLight);

  // Desktop WebGPU RenderPipeline + SSAONode (depthAwareBlur, builtinAOContext, 4x MSAA, transparent alpha)
  if (!isMobile && typeof THREE.RenderPipeline === "function") {
    try {
      const prePass = pass(scene, camera);
      prePass.transparent = false;
      prePass.setMRT(mrt({ output: packNormalToRGB(normalView) }));
      const normalTex = prePass.getTexture("output");
      normalTex.type = THREE.UnsignedByteType;
      const prePassNormal = sample((u) => unpackRGBToNormal(prePass.getTextureNode().sample(u)));
      const prePassDepth = prePass.getTextureNode("depth");

      const aoPass = ssao(prePassDepth, prePassNormal, camera);
      aoPass.resolutionScale = 0.5;
      aoPass.samples.value = 10;
      aoPass.radius.value = 0.18;
      aoPass.intensity.value = 1.35;

      const scenePass = pass(scene, camera);
      scenePass.options.samples = 4;
      scenePass.contextNode = builtinAOContext(aoPass.getTextureNode().sample(screenUV).r);

      renderPipeline = new THREE.RenderPipeline(renderer, scenePass);
      renderPipeline.outputColorTransform = true;
    } catch (pipeErr) {
      console.warn("RenderPipeline SSAO fallback to direct render:", pipeErr);
      renderPipeline = null;
    }
  }

  // 3D pulsing target marker attached at active threat anchor
  targetMarkerGroup = new THREE.Group();
  const coreGeo = new THREE.SphereGeometry(0.018, 16, 16);
  const coreMat = new THREE.MeshBasicMaterial({ color: 0xff5a5f });
  const coreMesh = new THREE.Mesh(coreGeo, coreMat);
  const haloGeo = new THREE.RingGeometry(0.028, 0.042, 24);
  const haloMat = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.78,
  });
  targetHaloMesh = new THREE.Mesh(haloGeo, haloMat);
  targetMarkerGroup.add(coreMesh);
  targetMarkerGroup.add(targetHaloMesh);
  targetMarkerGroup.visible = false;
  scene.add(targetMarkerGroup);

  resizeRenderer();
  window.addEventListener("resize", resizeRenderer);
}

function resizeRenderer() {
  if (!renderer || !camera) return;
  const w = Math.max(100, stageContainer.clientWidth);
  const h = Math.max(100, stageContainer.clientHeight);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
}

function applyCameraPreset(presetName) {
  const preset = CAMERA_PRESETS[presetName];
  if (!preset) return;
  state.cameraGoalPos.copy(preset.pos);
  state.cameraGoalTarget.copy(preset.target);
  state.cameraLerpActive = true;
  for (const btn of presetButtons) {
    btn.classList.toggle("is-active", btn.dataset.preset === presetName);
  }
}

function renderPhaseButtons() {
  phaseButtonsEl.innerHTML = "";
  state.crop.phases.forEach((phase, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "phase-row-btn";
    btn.setAttribute("role", "tab");
    btn.dataset.index = String(idx);
    btn.innerHTML = `
      <span class="phase-dot" aria-hidden="true"></span>
      <span class="phase-row-text">
        <span class="phase-row-bbch">${phase.bbch}</span>
        <span class="phase-row-label">${phase.short_label}</span>
      </span>
    `;
    btn.addEventListener("click", () => {
      stopAutoplay();
      selectPhase(idx, true);
    });
    phaseButtonsEl.appendChild(btn);
  });
}

function syncSliderVisual(labelText) {
  phaseSlider.style.setProperty("--attr-min", phaseSlider.min || "0");
  phaseSlider.style.setProperty("--attr-max", phaseSlider.max || "100");
  phaseSlider.style.setProperty("--control-value", phaseSlider.value);
  if (labelText) {
    phaseSlider.setAttribute("aria-valuetext", labelText);
  }
}

function selectPhase(index, updateTargetTime = true) {
  const phases = state.crop.phases;
  const clamped = Math.max(0, Math.min(phases.length - 1, index));
  const changed = clamped !== state.activePhaseIndex || threatsListEl.childElementCount === 0;
  state.activePhaseIndex = clamped;
  const phase = phases[clamped];

  if (updateTargetTime) {
    state.targetTime = phase.time_sec;
    const pct = (phase.time_sec / state.durationSec) * 100;
    phaseSlider.value = pct.toFixed(1);
  }
  syncSliderVisual(`${phase.bbch} — ${phase.title}`);

  for (const btn of phaseButtonsEl.querySelectorAll(".phase-row-btn")) {
    const isSel = Number(btn.dataset.index) === clamped;
    btn.classList.toggle("is-active", isSel);
    btn.setAttribute("aria-selected", isSel ? "true" : "false");
  }
  btnPrev.disabled = clamped === 0;
  btnNext.disabled = clamped === phases.length - 1;

  readoutBbch.textContent = phase.bbch;
  readoutPhase.textContent = `Фаза ${clamped + 1} из ${phases.length}`;
  statBbch.textContent = phase.bbch;

  if (changed) {
    state.activeThreatId = phase.threats[0]?.id || null;
    phaseBbchEl.textContent = phase.bbch;
    maturityLabelEl.textContent = phase.metrics?.maturity_label || "";
    phaseTitleEl.textContent = phase.title;
    phaseSummaryEl.textContent = phase.summary;
    renderThreats(phase.threats);
    renderHotspots(phase.threats);
    updateTarget3DMarker();
    applyThreatSymptom(phase.threats[0] || null);
  }
}

function updateLiveMetrics(timeSec) {
  const phases = state.crop?.phases;
  if (!phases || phases.length < 2) return;
  let i0 = 0;
  for (let i = 0; i < phases.length - 1; i++) {
    if (timeSec >= phases[i].time_sec) i0 = i;
  }
  const i1 = Math.min(phases.length - 1, i0 + 1);
  const p0 = phases[i0];
  const p1 = phases[i1];
  const span = Math.max(1e-4, p1.time_sec - p0.time_sec);
  const alpha = i0 === i1 ? 0 : Math.max(0, Math.min(1, (timeSec - p0.time_sec) / span));

  const m0 = p0.metrics || { brix_pct: 0, root_diam_mm: 4, leaves_count: 0 };
  const m1 = p1.metrics || m0;
  const defs = Array.isArray(state.crop.metric_defs) && state.crop.metric_defs.length >= 3
    ? state.crop.metric_defs
    : [
        { key: "brix_pct", label: "Сахаристость", unit: "%", decimals: 1 },
        { key: "root_diam_mm", label: "Диаметр корня", unit: " мм", decimals: 0 },
        { key: "leaves_count", label: "Листьев", unit: " шт", decimals: 0 },
      ];
  const valEls = [metricBrixEl, metricDiamEl, metricLeavesEl];

  for (let k = 0; k < 3; k++) {
    const def = defs[k];
    const v0 = Number(m0[def.key] ?? 0);
    const v1 = Number(m1[def.key] ?? v0);
    const val = v0 + (v1 - v0) * alpha;
    const dec = Number(def.decimals ?? 0);
    const formatted = dec > 0 ? val.toFixed(dec) : String(Math.round(val));
    if (valEls[k]) valEls[k].textContent = `${formatted}${def.unit || ""}`;
  }
}

function renderThreats(threats) {
  threatCountEl.textContent = String(threats.length);
  threatsListEl.innerHTML = "";

  threats.forEach((threat) => {
    const card = document.createElement("article");
    card.className = "threat-card";
    card.tabIndex = 0;
    card.dataset.threatId = threat.id;
    card.dataset.severity = threat.severity;
    if (threat.id === state.activeThreatId) {
      card.classList.add("is-active");
    }

    const sevLabel = SEVERITY_LABELS[threat.severity] || threat.severity;
    const iconSvg = THREAT_ICONS[threat.icon_type] || THREAT_ICONS.fungus;
    card.innerHTML = `
      <div class="threat-top">
        <div class="threat-title-wrap">
          <span class="threat-card-icon" aria-hidden="true">${iconSvg}</span>
          <h4 class="threat-name">${threat.name}</h4>
        </div>
        <span class="severity-badge ${threat.severity}">${sevLabel}</span>
      </div>
      <div class="threat-latin">${threat.latin}</div>
      <div class="threat-zone">Зона: ${threat.target_zone}</div>
      <p class="threat-desc">${threat.description}</p>
      <p class="threat-tip"><strong>Защита:</strong> ${threat.protection_tip}</p>
    `;

    const activate = () => setActiveThreat(threat.id, false, true);
    card.addEventListener("click", activate);
    card.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        activate();
      }
    });
    threatsListEl.appendChild(card);
  });
}

function renderHotspots(threats) {
  hotspotsLayer.innerHTML = "";
  hotspotItems = threats.map((threat) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "hotspot-pin";
    btn.dataset.threatId = threat.id;
    btn.dataset.severity = threat.severity;
    if (threat.id === state.activeThreatId) {
      btn.classList.add("is-active");
    }
    const iconSvg = THREAT_ICONS[threat.icon_type] || THREAT_ICONS.fungus;
    btn.innerHTML = `<span class="hotspot-icon" aria-hidden="true">${iconSvg}</span><span>${threat.name}</span>`;
    btn.addEventListener("click", () => setActiveThreat(threat.id, true, true));
    hotspotsLayer.appendChild(btn);
    return {
      id: threat.id,
      severity: threat.severity,
      anchor: new THREE.Vector3(...threat.anchor),
      symptom: threat.symptom || null,
      el: btn,
    };
  });
}

function updateTarget3DMarker() {
  if (!targetMarkerGroup) return;
  const active = hotspotItems.find((item) => item.id === state.activeThreatId);
  if (!active || !state.showHotspots) {
    targetMarkerGroup.visible = false;
    return;
  }
  targetMarkerGroup.visible = true;
  targetMarkerGroup.position.copy(active.anchor);
}

function getActiveThreatData() {
  const phase = state.crop?.phases?.[state.activePhaseIndex];
  if (!phase || !Array.isArray(phase.threats)) return null;
  return phase.threats.find((t) => t.id === state.activeThreatId) || null;
}

function applyThreatSymptom(threat) {
  const sym = threat?.symptom;
  const modeNum = sym ? (SYMPTOM_MODE_MAP[sym.mode] ?? 0) : 0;
  if (!state.showSymptoms || !threat || modeNum === 0) {
    state.symptomTargetIntensity = 0.0;
    return;
  }
  const anchor = Array.isArray(threat.anchor) ? threat.anchor : [0, 0, 0];
  uSymptomCenter.value.set(anchor[0], anchor[1], anchor[2]);
  uSymptomRadius.value = typeof sym.radius === "number" ? sym.radius : 0.20;
  uSymptomMode.value = modeNum;
  uSymptomTarget.value = SYMPTOM_TARGET_MAP[sym.target] ?? 0;
  state.symptomTargetIntensity = 1.0;
}

function setActiveThreat(threatId, scrollToCard, focusCamera = false) {
  state.activeThreatId = threatId;
  for (const card of threatsListEl.querySelectorAll(".threat-card")) {
    const match = card.dataset.threatId === threatId;
    card.classList.toggle("is-active", match);
    if (match && scrollToCard) {
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }
  for (const item of hotspotItems) {
    item.el.classList.toggle("is-active", item.id === threatId);
  }
  updateTarget3DMarker();

  const threat = getActiveThreatData();
  applyThreatSymptom(threat);

  if (focusCamera && threat && Array.isArray(threat.anchor) && threat.symptom?.cam_offset) {
    const [ax, ay, az] = threat.anchor;
    const [ox, oy, oz] = threat.symptom.cam_offset;
    state.cameraGoalTarget.set(ax, ay, az);
    state.cameraGoalPos.set(ax + ox, ay + oy, az + oz);
    state.cameraLerpActive = true;
    for (const btn of presetButtons) {
      btn.classList.remove("is-active");
    }
  }
}

function updateBackdropSoilHorizon() {
  if (!camera) return;
  const origin = new THREE.Vector3(0, 0, 0).project(camera);
  if (origin.z >= -1 && origin.z <= 1) {
    const stageRect = stageContainer.getBoundingClientRect();
    const screenX = stageRect.left + (origin.x * 0.5 + 0.5) * stageRect.width;
    const screenY = stageRect.top + (-origin.y * 0.5 + 0.5) * stageRect.height;
    const pctX = Math.max(12, Math.min(88, (screenX / Math.max(1, window.innerWidth)) * 100));
    const pctY = Math.max(24, Math.min(78, (screenY / Math.max(1, window.innerHeight)) * 100));
    document.documentElement.style.setProperty("--plant-center-x", `${pctX.toFixed(1)}%`);
    document.documentElement.style.setProperty("--soil-line-y", `${pctY.toFixed(1)}%`);
  }
}

function updateHotspotPositions() {
  if (!camera || !state.showHotspots) {
    hotspotsLayer.hidden = true;
    return;
  }
  hotspotsLayer.hidden = false;
  const width = stageContainer.clientWidth;
  const height = stageContainer.clientHeight;
  const proj = new THREE.Vector3();

  for (const item of hotspotItems) {
    proj.copy(item.anchor).project(camera);
    if (proj.z > 1 || proj.z < -1) {
      item.el.style.display = "none";
      continue;
    }
    const x = (proj.x * 0.5 + 0.5) * width;
    const y = (-proj.y * 0.5 + 0.5) * height;
    if (x < 24 || x > width - 24 || y < 52 || y > height - 92) {
      item.el.style.display = "none";
      continue;
    }
    item.el.style.display = "inline-flex";
    item.el.dataset.align = item.anchor.x < -0.05 ? "left" : item.anchor.x > 0.05 ? "right" : "center";
    item.el.style.left = `${x.toFixed(1)}px`;
    item.el.style.top = `${y.toFixed(1)}px`;
  }
}

function updateMaturationMaterials(progress) {
  const matPhase = Math.max(0, Math.min(1, (progress - 0.52) / 0.48));
  uOuterSenescence.value = matPhase;

  if (matHandles.outer) {
    tmpColor.copy(COLOR_OUTER_FRESH).lerp(COLOR_OUTER_MATURE, matPhase * 0.58);
    matHandles.outer.color.copy(tmpColor);
    if (matHandles.outer.userData.uMatTint) matHandles.outer.userData.uMatTint.value.copy(tmpColor);
    if (matHandles.outer.userData.uRoughMul) matHandles.outer.userData.uRoughMul.value = 0.95 + 0.32 * matPhase;
  }
  if (matHandles.mid) {
    tmpColor.copy(COLOR_MID_FRESH).lerp(COLOR_MID_MATURE, matPhase * 0.50);
    matHandles.mid.color.copy(tmpColor);
    if (matHandles.mid.userData.uMatTint) matHandles.mid.userData.uMatTint.value.copy(tmpColor);
    if (matHandles.mid.userData.uRoughMul) matHandles.mid.userData.uRoughMul.value = 0.88 + 0.22 * matPhase;
  }
  if (matHandles.heart) {
    tmpColor.copy(COLOR_HEART_FRESH).lerp(COLOR_HEART_MATURE, matPhase * 0.42);
    matHandles.heart.color.copy(tmpColor);
    if (matHandles.heart.userData.uMatTint) matHandles.heart.userData.uMatTint.value.copy(tmpColor);
  }
  if (matHandles.root) {
    tmpColor.copy(COLOR_ROOT_EARLY).lerp(COLOR_ROOT_MATURE, progress * 0.65);
    matHandles.root.color.copy(tmpColor);
    if (matHandles.root.userData.uMatTint) matHandles.root.userData.uMatTint.value.copy(tmpColor);
  }
}

function findClosestPhaseIndex(timeSec) {
  const phases = state.crop.phases;
  let bestIdx = 0;
  let bestDist = Infinity;
  phases.forEach((p, idx) => {
    const d = Math.abs(p.time_sec - timeSec);
    if (d < bestDist) {
      bestDist = d;
      bestIdx = idx;
    }
  });
  return bestIdx;
}

function stopAutoplay() {
  state.autoPlaying = false;
  btnAutoplay.textContent = "▶ Авто-рост";
}

function toggleAutoplay() {
  state.autoPlaying = !state.autoPlaying;
  if (state.autoPlaying) {
    if (state.targetTime >= state.durationSec - 0.05) {
      state.targetTime = 0;
      state.currentTime = 0;
    }
    btnAutoplay.textContent = "⏸ Пауза";
  } else {
    btnAutoplay.textContent = "▶ Авто-рост";
  }
}

function bindUI() {
  phaseSlider.addEventListener("input", () => {
    stopAutoplay();
    const pct = Number(phaseSlider.value) / 100;
    state.targetTime = pct * state.durationSec;
    const nearest = findClosestPhaseIndex(state.targetTime);
    selectPhase(nearest, false);
  });

  btnPrev.addEventListener("click", () => {
    stopAutoplay();
    selectPhase(state.activePhaseIndex - 1, true);
  });

  btnNext.addEventListener("click", () => {
    stopAutoplay();
    selectPhase(state.activePhaseIndex + 1, true);
  });

  btnAutoplay.addEventListener("click", toggleAutoplay);

  if (toggleSymptomsBtn) {
    toggleSymptomsBtn.addEventListener("click", () => {
      state.showSymptoms = !state.showSymptoms;
      toggleSymptomsBtn.classList.toggle("is-active", state.showSymptoms);
      toggleSymptomsBtn.setAttribute("aria-pressed", state.showSymptoms ? "true" : "false");
      toggleSymptomsBtn.textContent = `Симптомы 3D: ${state.showSymptoms ? "Вкл" : "Выкл"}`;
      applyThreatSymptom(getActiveThreatData());
    });
  }

  toggleHotspotsBtn.addEventListener("click", () => {
    state.showHotspots = !state.showHotspots;
    toggleHotspotsBtn.classList.toggle("is-active", state.showHotspots);
    toggleHotspotsBtn.setAttribute("aria-pressed", state.showHotspots ? "true" : "false");
    toggleHotspotsBtn.textContent = `Радар угроз: ${state.showHotspots ? "Вкл" : "Выкл"}`;
    updateHotspotPositions();
    updateTarget3DMarker();
  });

  for (const btn of presetButtons) {
    btn.addEventListener("click", () => applyCameraPreset(btn.dataset.preset));
  }
}

async function resolveCropConfig() {
  const params = new URLSearchParams(window.location.search);
  let requestedId = params.get("crop") || "sugar_beet";
  let passportUrl = `../data/${requestedId}.json`;
  let statsUrl = requestedId === "sugar_beet" ? "../assets/export_stats.json" : `../assets/${requestedId}_stats.json`;

  try {
    const idxRes = await fetch("../data/crops_index.json");
    if (idxRes.ok) {
      const idxData = await idxRes.json();
      const readyCrops = Array.isArray(idxData.crops) ? idxData.crops.filter((c) => c.ready) : [];
      const chosen =
        readyCrops.find((c) => c.id === requestedId) ||
        readyCrops.find((c) => c.id === idxData.default_crop) ||
        readyCrops[0];
      if (chosen) {
        requestedId = chosen.id;
        passportUrl = chosen.passport_url || passportUrl;
        statsUrl = chosen.stats_url || statsUrl;
      }
      if (cropSelectEl && readyCrops.length > 1) {
        cropSelectEl.innerHTML = "";
        for (const c of readyCrops) {
          const opt = document.createElement("option");
          opt.value = c.id;
          opt.textContent = c.name;
          opt.selected = c.id === requestedId;
          cropSelectEl.appendChild(opt);
        }
        cropSelectEl.hidden = false;
        if (cropNameEl) cropNameEl.hidden = true;
        cropSelectEl.addEventListener("change", () => {
          const next = new URL(window.location.href);
          next.searchParams.set("crop", cropSelectEl.value);
          window.location.href = next.toString();
        });
      }
    }
  } catch {
    // Graceful fallback to direct sugar_beet passport
  }
  return { cropId: requestedId, passportUrl, statsUrl };
}

async function loadDataAndModel() {
  // Start Draco WASM preload + SSS thickness maps immediately in parallel with JSON metadata
  const dracoLoader = new DRACOLoader();
  dracoLoader.setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.187.0/examples/jsm/libs/draco/gltf/");
  dracoLoader.preload();

  const texLoader = new THREE.TextureLoader();
  const loadLinearMap = async (url) => {
    try {
      const tex = await texLoader.loadAsync(url);
      tex.flipY = false;
      tex.colorSpace = THREE.NoColorSpace;
      return tex;
    } catch {
      return null;
    }
  };
  const thicknessPromise = Promise.all([
    loadLinearMap("../assets/textures/leaf_thickness.png"),
    loadLinearMap("../assets/textures/root_thickness.png"),
  ]);

  const { passportUrl, statsUrl } = await resolveCropConfig();
  const [cropRes, statsRes] = await Promise.all([
    fetch(passportUrl),
    fetch(statsUrl).catch(() => null),
  ]);
  if (!cropRes.ok) {
    throw new Error(`Ошибка загрузки паспорта культуры (HTTP ${cropRes.status}).`);
  }
  state.crop = await cropRes.json();
  state.durationSec = state.crop.duration_sec || 6.25;

  if (cropNameEl) cropNameEl.textContent = state.crop.name;
  if (cropLatinEl) cropLatinEl.textContent = state.crop.latin;
  document.title = `Перископ — 3D-атлас фаз роста: ${state.crop.name}`;

  if (Array.isArray(state.crop.metric_defs)) {
    state.crop.metric_defs.slice(0, 3).forEach((def, idx) => {
      if (metricLabelEls[idx] && def.label) {
        metricLabelEls[idx].textContent = def.label;
      }
    });
  }

  renderPhaseButtons();
  selectPhase(0, true);

  let expectedGlbBytes = 0;
  try {
    if (statsRes && statsRes.ok) {
      const stats = await statsRes.json();
      expectedGlbBytes = Number(stats.glb_bytes || 0);
      const kb = (expectedGlbBytes / 1024).toFixed(0);
      statSize.textContent = `GLB ${kb} КБ`;
      statTris.textContent = `${stats.triangle_count.toLocaleString("ru-RU")} треуг.`;
    }
  } catch {
    statSize.textContent = "GLB готов";
  }

  loadingText.textContent = "Загружаем 3D-модель (0%)…";
  const loader = new GLTFLoader();
  loader.setDRACOLoader(dracoLoader);
  const gltfPromise = loader.loadAsync(state.crop.model_url, (xhr) => {
    const total = xhr.total || expectedGlbBytes;
    if (total > 0 && xhr.loaded > 0) {
      const pct = Math.min(99, Math.round((xhr.loaded / total) * 100));
      const loadedMb = (xhr.loaded / (1024 * 1024)).toFixed(1);
      const totalMb = (total / (1024 * 1024)).toFixed(1);
      loadingText.textContent =
        pct >= 99
          ? "Распаковываем геометрию и TSL-шейдеры…"
          : `Загружаем 3D-модель: ${pct}% (${loadedMb} / ${totalMb} МБ)…`;
    }
  });

  const [[leafThickTex, rootThickTex], gltf] = await Promise.all([thicknessPromise, gltfPromise]);

  const upgradedMaterials = new Map();
  gltf.scene.traverse((obj) => {
    if (obj.isMesh && obj.material) {
      obj.castShadow = true;
      obj.receiveShadow = true;
      const srcMat = obj.material;
      let tier = "other";
      if (srcMat.name === "Outer_Leaf_PBR") tier = "outer";
      else if (srcMat.name === "Mid_Leaf_PBR") tier = "mid";
      else if (srcMat.name === "Heart_Leaf_PBR") tier = "heart";
      else if (srcMat.name === "Taproot_PBR") tier = "root";

      let nodeMat = upgradedMaterials.get(srcMat);
      if (!nodeMat) {
        const hasVCol = Boolean(obj.geometry && obj.geometry.attributes && obj.geometry.attributes.color);
        nodeMat = upgradeToPhotorealNodeMaterial(srcMat, tier, leafThickTex, rootThickTex, hasVCol);
        upgradedMaterials.set(srcMat, nodeMat);
        if (tier !== "other") {
          matHandles[tier] = nodeMat;
        }
      }
      obj.material = nodeMat;
    }
  });
  scene.add(gltf.scene);

  mixer = new THREE.AnimationMixer(gltf.scene);
  actions = gltf.animations.map((clip) => {
    const action = mixer.clipAction(clip);
    action.setLoop(THREE.LoopOnce);
    action.clampWhenFinished = true;
    action.enabled = true;
    action.play();
    action.paused = true;
    action.time = 0;
    return action;
  });
  mixer.update(0);

  if (statSize.textContent.includes("Загрузка")) {
    statSize.textContent = "GLB загружен";
  }
  loadingOverlay.hidden = true;
}

function startLoop() {
  let prevTs = performance.now();
  let fpsCount = 0;
  let fpsAccum = 0;

  function tick(now) {
    const dt = Math.min(0.05, (now - prevTs) / 1000);
    prevTs = now;
    const elapsedSec = now / 1000;

    fpsCount += 1;
    fpsAccum += dt;
    if (fpsAccum >= 0.5) {
      statFps.textContent = `${Math.round(fpsCount / fpsAccum)} FPS`;
      fpsCount = 0;
      fpsAccum = 0;
    }

    if (state.autoPlaying && state.crop) {
      state.targetTime += dt * 0.95;
      if (state.targetTime >= state.durationSec) {
        state.targetTime = state.durationSec;
        stopAutoplay();
      }
      const pct = (state.targetTime / state.durationSec) * 100;
      phaseSlider.value = pct.toFixed(1);
      syncSliderVisual();
      const nearest = findClosestPhaseIndex(state.targetTime);
      if (nearest !== state.activePhaseIndex) {
        selectPhase(nearest, false);
      }
    }

    if (mixer && actions.length > 0) {
      const diff = state.targetTime - state.currentTime;
      if (Math.abs(diff) > 0.0005) {
        state.currentTime += diff * Math.min(1, dt * 8.5);
      } else {
        state.currentTime = state.targetTime;
      }

      for (const action of actions) {
        const clipDur = action.getClip().duration || state.durationSec;
        action.enabled = true;
        action.paused = true;
        action.time = Math.max(0, Math.min(state.currentTime, Math.max(0, clipDur - 1e-5)));
      }
      mixer.update(0);

      const progress = Math.max(0, Math.min(1, state.currentTime / state.durationSec));
      updateMaturationMaterials(progress);
      updateLiveMetrics(state.currentTime);

      if (state.crop) {
        const currentFrame = Math.round(state.currentTime * (state.crop.fps || 24));
        readoutFrame.textContent = `Кадр ${currentFrame} / ${state.crop.total_frames}`;
      }
    }

    const symDiff = state.symptomTargetIntensity - state.symptomCurrentIntensity;
    if (Math.abs(symDiff) > 0.002) {
      state.symptomCurrentIntensity += symDiff * Math.min(1, dt * 7.5);
    } else {
      state.symptomCurrentIntensity = state.symptomTargetIntensity;
    }
    uSymptomIntensity.value = state.symptomCurrentIntensity;

    if (targetMarkerGroup && targetMarkerGroup.visible && camera) {
      targetMarkerGroup.lookAt(camera.position);
      const pulse = 1.0 + 0.22 * Math.sin(elapsedSec * 4.2);
      if (targetHaloMesh) targetHaloMesh.scale.set(pulse, pulse, 1);
    }

    if (state.cameraLerpActive && camera && controls) {
      const k = Math.min(1, dt * 6.0);
      camera.position.lerp(state.cameraGoalPos, k);
      controls.target.lerp(state.cameraGoalTarget, k);
      if (
        camera.position.distanceTo(state.cameraGoalPos) < 0.01 &&
        controls.target.distanceTo(state.cameraGoalTarget) < 0.01
      ) {
        state.cameraLerpActive = false;
      }
    }

    if (controls) controls.update();
    if (renderer && scene && camera) {
      updateBackdropSoilHorizon();
      if (renderPipeline) {
        try {
          renderPipeline.render();
        } catch (renderErr) {
          console.warn("RenderPipeline runtime fallback:", renderErr);
          renderPipeline = null;
          renderer.render(scene, camera);
        }
      } else {
        renderer.render(scene, camera);
      }
      updateHotspotPositions();
    }
  }

  renderer.setAnimationLoop(tick);
}

async function bootstrap() {
  try {
    await initScene();
    bindUI();
    await loadDataAndModel();
    startLoop();
  } catch (err) {
    console.error(err);
    showError(
      `${err?.message || err}<br><small>Откройте страницу через локальный сервер <code>python serve.py</code> и проверьте доступ к CDN Three.js.</small>`
    );
  }
}

bootstrap();
