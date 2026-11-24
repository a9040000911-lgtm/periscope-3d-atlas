import * as THREE from "three";
import {
  abs,
  builtinAOContext,
  clamp,
  cos,
  distance,
  dot,
  float,
  Fn,
  fract,
  frontFacing,
  If,
  length,
  mix,
  mrt,
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
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { HDRLoader } from "three/addons/loaders/HDRLoader.js";

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
const stageControlsTop = stageContainer ? stageContainer.querySelector(".stage-controls-top") : null;
const reticleEl = document.getElementById("periscope-reticle");
const reticleProgressLeft = document.getElementById("reticle-progress-left");
const reticleProgressRight = document.getElementById("reticle-progress-right");
const reticlePhaseRing = document.getElementById("reticle-phase-ring");
const hotspotLeadersSvg = document.getElementById("hotspot-leaders");
const hotspotsLayer = document.getElementById("hotspots-layer");
const loadingOverlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");
const errorBanner = document.getElementById("error-banner");

const SVG_NS = "http://www.w3.org/2000/svg";
const FLANK_ARC_LEN = 245 * ((64 * Math.PI) / 180);

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
const toggleSsaoBtn = document.getElementById("toggle-ssao");
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
  ultraAO: false,
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
let fillLightRef = null;
let hemiLightRef = null;
let actions = [];
let hotspotItems = [];
let reticleDotEls = [];
let plantRoot = null;
let plantExtentProfile = [];
let targetMarkerGroup = null;
let targetHaloMesh = null;
const tmpExtCenter = new THREE.Vector3();
const tmpExtSide = new THREE.Vector3();
const tmpCamRight = new THREE.Vector3();
const stageGeo = {
  w: 800,
  h: 600,
  cx: 400,
  cy: 300,
  rPhase: 110,
  targetRPhase: 110,
  minRPhase: 84,
  maxRPhase: 196,
  plantScreenHalfW: 36,
  dotR: 15,
  pillMaxW: 182,
  topSafe: 58,
  botSafe: 546,
  isMobile: false,
  dotPositions: [],
};
const matHandles = {
  outer: null,
  mid: null,
  heart: null,
  root: null,
  pod: null,
  flower: null,
  nodule: null,
  stem: null,
};

// Reactive TSL uniforms shared across upgraded MeshSSSNodeMaterial instances
const uOuterSenescence = uniform(0.0);
const uPodPhase = uniform(0.0);
const uSymptomCenter = uniform(new THREE.Vector3(0, 0, 0));
const uSymptomRadius = uniform(0.18);
const uSymptomIntensity = uniform(0.0);
const uSymptomMode = uniform(0.0); // 0=none, 1=rhizoctonia/korneed, 2=cercospora, 3=mildew, 4=phoma, 5=pest
const uSymptomTarget = uniform(0.0); // 0=both, 1=root, 2=leaf

const activePalette = {
  outerFresh: new THREE.Color("#edf5df"),
  outerMature: new THREE.Color("#d8be56"),
  midFresh: new THREE.Color("#f5faef"),
  midMature: new THREE.Color("#dce8a8"),
  heartFresh: new THREE.Color("#e2ffad"),
  heartMature: new THREE.Color("#cce87a"),
  podFresh: new THREE.Color("#74b632"),
  podMature: new THREE.Color("#d6b562"),
  stemFresh: new THREE.Color("#e9f5d8"),
  stemMature: new THREE.Color("#cfc274"),
  rootEarly: new THREE.Color("#ffffff"),
  rootMature: new THREE.Color("#f4ecd8"),
};
const tmpColor = new THREE.Color();

function applyCropPalette(paletteObj) {
  if (!paletteObj || typeof paletteObj !== "object") return;
  if (paletteObj.outer_fresh) activePalette.outerFresh.set(paletteObj.outer_fresh);
  if (paletteObj.outer_mature) activePalette.outerMature.set(paletteObj.outer_mature);
  if (paletteObj.mid_fresh) activePalette.midFresh.set(paletteObj.mid_fresh);
  if (paletteObj.mid_mature) activePalette.midMature.set(paletteObj.mid_mature);
  if (paletteObj.heart_fresh) activePalette.heartFresh.set(paletteObj.heart_fresh);
  if (paletteObj.heart_mature) activePalette.heartMature.set(paletteObj.heart_mature);
  if (paletteObj.pod_fresh) activePalette.podFresh.set(paletteObj.pod_fresh);
  if (paletteObj.pod_mature) activePalette.podMature.set(paletteObj.pod_mature);
  if (paletteObj.root_early) activePalette.rootEarly.set(paletteObj.root_early);
  if (paletteObj.root_mature) activePalette.rootMature.set(paletteObj.root_mature);
}

function showError(message) {
  loadingOverlay.hidden = true;
  errorBanner.hidden = false;
  errorBanner.innerHTML = `<strong>Не удалось запустить 3D-сцену:</strong><br>${message}`;
}

// Ultra-fast zero-loop analytic TSL noise & organic spot distance (compiles in <10ms vs ~14s MaterialX 3D loops)
function fastNoise3D(p) {
  const a = sin(dot(p, vec3(1.17, 2.31, 1.73)))
    .mul(cos(dot(p.yzx, vec3(1.93, 1.37, 2.11))));
  const p2 = p.mul(float(2.13)).add(vec3(a.mul(float(1.4)), a.mul(float(-1.1)), a.mul(float(0.9))));
  const b = sin(dot(p2, vec3(1.61, 1.29, 2.47)))
    .mul(cos(dot(p2.zxy, vec3(2.07, 1.71, 1.19))));
  return a.mul(float(0.62)).add(b.mul(float(0.38)));
}

function fastSpots3D(p) {
  const warp = vec3(
    sin(p.y.mul(float(1.73)).add(p.z.mul(float(1.19)))),
    cos(p.z.mul(float(1.61)).sub(p.x.mul(float(1.37)))),
    sin(p.x.mul(float(1.49)).add(p.y.mul(float(1.83))))
  ).mul(float(0.28));
  const cell = fract(p.add(warp)).sub(float(0.5));
  return length(cell);
}

function upgradeToPhotorealNodeMaterial(srcMat, tier, leafThickTex, rootThickTex, podThickTex, hasVertexColor) {
  const isAboveGround =
    tier === "outer" ||
    tier === "mid" ||
    tier === "heart" ||
    tier === "stem" ||
    tier === "pod" ||
    tier === "flower";
  const isUnderground = tier === "root" || tier === "nodule";
  // Keep Seed_PBR / Hypocotyl_PBR on lightweight glTF standard PBR (avoids redundant shader compilations)
  if (!isAboveGround && !isUnderground) {
    return srcMat;
  }

  const isLeaf = tier === "outer" || tier === "mid" || tier === "heart";
  const isRoot = tier === "root";
  const isPod = tier === "pod";
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
  const uSenWeight = uniform(tier === "outer" ? 1.0 : 0.0);
  const uPodWeight = uniform(isPod ? 1.0 : 0.0);
  const uBackfaceBlend = uniform(isLeaf ? 1.0 : 0.0);
  const sssHex = isRoot
    ? 0xd9c296
    : tier === "nodule"
      ? 0xf27668
      : tier === "flower"
        ? 0xf0eaff
        : isPod
          ? 0x90c63a
          : tier === "stem"
            ? 0x5ca322
            : tier === "heart"
              ? 0x6eb81e
              : tier === "mid"
                ? 0x3b9a14
                : 0x4b8f12;
  const uSssTint = uniform(new THREE.Color(sssHex));
  const uSssAtten = uniform(
    tier === "flower" ? 0.16 : isLeaf ? 0.09 : isPod ? 0.095 : tier === "nodule" ? 0.08 : 0.04
  );
  const uVelvetTint = uniform(
    new THREE.Color(
      tier === "flower"
        ? 0xf5f0ff
        : isPod
          ? 0xe8dd99
          : tier === "nodule"
            ? 0xffb3a1
            : isRoot
              ? 0xdccaa8
              : 0xc8e898
    )
  );
  const uVelvetStrength = uniform(
    tier === "flower" ? 0.22 : isPod ? 0.14 : isLeaf ? 0.15 : tier === "nodule" ? 0.16 : tier === "stem" ? 0.10 : 0.05
  );
  nodeMat.userData.uMatTint = uMatTint;
  nodeMat.userData.uRoughMul = uRoughMul;

  const texRgb = srcMat.map ? texture(srcMat.map, uv()).rgb : vec3(1.0, 1.0, 1.0);
  const vColRgb = hasVertexColor ? vertexColor().rgb : vec3(1.0, 1.0, 1.0);
  let baseCol = texRgb.mul(vColRgb).mul(uMatTint);
  let baseRough = srcMat.roughnessMap ? texture(srcMat.roughnessMap, uv()).g.mul(uRoughMul) : uRoughMul;
  let clearcoatVal = float(isLeaf ? 0.18 : isPod ? 0.14 : 0.06);

  // Zero-cost analytic grazing velvet pubescence rim (simulates backlit legume trichomes / silk petals!)
  const rimOneMinus = clamp(float(1.0).sub(abs(normalView.z)), float(0.0), float(1.0));
  const velvetRim = rimOneMinus.mul(rimOneMinus).mul(rimOneMinus).mul(uVelvetStrength);

  if (isAboveGround) {
    nodeMat.clearcoat = isLeaf ? 0.22 : isPod ? 0.14 : 0.06;
    nodeMat.clearcoatRoughness = 0.36;
    nodeMat.sheen = tier === "flower" ? 0.18 : isPod ? 0.12 : 0.10;
    nodeMat.sheenRoughness = 0.50;
    nodeMat.sheenColor = new THREE.Color(tier === "flower" ? 0xd9d2ff : isPod ? 0xd8c87a : 0x9bd258);

    // Botanical adaxial/abaxial differentiation on leaf blades (uniform-gated so above-ground shares ONE shader!)
    const adaxialCol = baseCol.mul(vec3(0.95, 0.99, 0.94));
    const abaxialCol = mix(baseCol.mul(float(1.14)), vec3(0.42, 0.56, 0.24), float(0.24));
    const leafCol = select(frontFacing, adaxialCol, abaxialCol);
    baseCol = mix(baseCol, leafCol, uBackfaceBlend);
    const leafRough = select(frontFacing, baseRough.mul(float(0.86)), baseRough.mul(float(1.24)));
    baseRough = mix(baseRough, leafRough, uBackfaceBlend);
    const leafCoat = select(frontFacing, float(0.22), float(0.05));
    clearcoatVal = mix(clearcoatVal, leafCoat, uBackfaceBlend);

    // Unified edge-first senescence on outer leaves + suture-first golden parchment ripening on legume pods
    const edgeDist = abs(uv().x.sub(float(0.5))).mul(float(2.0));
    const tipDist = clamp(uv().y.sub(float(0.26)).div(float(0.74)), float(0.0), float(1.0));
    const orgRipenNoise = fastNoise3D(positionWorld.mul(float(16.0))).mul(float(0.20));
    const edgeCoord = edgeDist.mul(float(0.68)).add(tipDist.mul(float(0.50))).add(orgRipenNoise);
    const senActive = uOuterSenescence.mul(uSenWeight);
    const chlorosisMask = smoothstep(float(0.72), float(1.18), edgeCoord).mul(senActive);
    const crispBrownMask = smoothstep(float(0.96), float(1.28), edgeCoord)
      .mul(clamp(uOuterSenescence.sub(float(0.45)).div(float(0.55)), float(0.0), float(1.0)))
      .mul(uSenWeight);
    baseCol = mix(baseCol, vec3(0.74, 0.64, 0.17), chlorosisMask.mul(float(0.78)));
    baseCol = mix(baseCol, vec3(0.36, 0.24, 0.09), crispBrownMask.mul(float(0.85)));
    baseRough = mix(baseRough, float(0.86), crispBrownMask.mul(float(0.85)));
    clearcoatVal = clearcoatVal.mul(float(1.0).sub(chlorosisMask.mul(float(0.75))));

    // Organic suture- & beak-first drying amber edge gradient on ripening lentil pods
    const podSutureMask = smoothstep(float(0.58), float(1.15), edgeDist.mul(float(0.85)).add(tipDist.mul(float(0.45))).add(orgRipenNoise))
      .mul(uPodPhase)
      .mul(uPodWeight);
    baseCol = mix(baseCol, vec3(0.72, 0.56, 0.24), podSutureMask.mul(float(0.48)));
    baseRough = mix(baseRough, float(0.78), podSutureMask.mul(float(0.55)));
    // Soft backlit velvet pubescence rim highlight
    baseCol = baseCol.add(uVelvetTint.mul(velvetRim));

    // Calibrated Three.js 0.187.0 MeshSSSNodeMaterial translucency (veins on leaves; 2-seed silhouettes inside pods!)
    const activeThickTex = isPod ? podThickTex : isLeaf ? leafThickTex : null;
    const thickSample = activeThickTex ? texture(activeThickTex, uv()).r : float(tier === "flower" ? 0.94 : 0.45);
    const podDryAtten = float(1.0).sub(uPodPhase.mul(uPodWeight).mul(float(0.62)));
    const sssSideBoost = select(frontFacing, float(1.0), float(1.18));
    nodeMat.thicknessColorNode = uSssTint
      .mul(thickSample)
      .mul(sssSideBoost)
      .mul(podDryAtten)
      .mul(float(1.0).sub(crispBrownMask.mul(float(0.82))));
    nodeMat.thicknessDistortionNode = float(0.36);
    nodeMat.thicknessAmbientNode = float(0.0);
    nodeMat.thicknessAttenuationNode = uSssAtten;
    nodeMat.thicknessPowerNode = float(3.1);
    nodeMat.thicknessScaleNode = float(2.3);

    // Deepened zero-cost crown/canopy ambient occlusion (sculptural depth at 0ms GPU cost)
    const radialDist = positionWorld.xz.length();
    const heightAboveCrown = clamp(positionWorld.y.add(float(0.02)).div(float(0.30)), float(0.0), float(1.0));
    const radialOpen = clamp(radialDist.div(float(0.20)), float(0.0), float(1.0));
    nodeMat.aoNode = mix(
      float(0.62),
      float(1.0),
      clamp(heightAboveCrown.mul(float(0.60)).add(radialOpen.mul(float(0.56))), float(0.0), float(1.0))
    );
  } else if (isUnderground) {
    nodeMat.clearcoat = tier === "nodule" ? 0.10 : 0.06;
    nodeMat.clearcoatRoughness = tier === "nodule" ? 0.48 : 0.58;
    nodeMat.sheen = tier === "nodule" ? 0.12 : 0.05;
    nodeMat.sheenRoughness = 0.62;
    nodeMat.sheenColor = new THREE.Color(tier === "nodule" ? 0xf6b8a8 : 0xeaddc4);
    baseCol = baseCol.add(uVelvetTint.mul(velvetRim));

    const rThick = isRoot && rootThickTex ? texture(rootThickTex, uv()).r : float(0.62);
    nodeMat.thicknessColorNode = uSssTint.mul(rThick);
    nodeMat.thicknessDistortionNode = float(0.26);
    nodeMat.thicknessAmbientNode = float(0.0);
    nodeMat.thicknessAttenuationNode = uSssAtten;
    nodeMat.thicknessPowerNode = float(3.4);
    nodeMat.thicknessScaleNode = float(tier === "nodule" ? 1.65 : 1.15);
  }

  // Fast uniform-branched GPU symptom overlay (zero 3D loops -> instant shader compile + 60 FPS)
  const targetMatch = isUnderground
    ? select(uSymptomTarget.lessThan(float(1.5)), float(1.0), float(0.0))
    : select(uSymptomTarget.equal(float(0.0)).or(uSymptomTarget.greaterThan(float(1.5))), float(1.0), float(0.0));

  const evalSymptomColorRough = Fn(() => {
    const outCol = baseCol.toVar();
    const outRough = baseRough.toVar();

    If(
      uSymptomIntensity.greaterThan(float(0.005)).and(targetMatch.greaterThan(float(0.5))),
      () => {
        const distToFocus = distance(positionWorld, uSymptomCenter);
        const orgNoise = fastNoise3D(positionWorld.mul(float(28.0)));
        const warpedDist = distToFocus.add(orgNoise.mul(uSymptomRadius).mul(float(0.28)));
        const focusMask = float(1.0)
          .sub(smoothstep(uSymptomRadius.mul(float(0.24)), uSymptomRadius, warpedDist))
          .mul(uSymptomIntensity);

        If(uSymptomMode.lessThan(float(1.5)), () => {
          // Mode 1: Rhizoctonia / Korneed dark dry cracked necrosis
          const crackN = fastNoise3D(positionWorld.mul(float(68.0)));
          const m1 = focusMask.mul(smoothstep(float(-0.42), float(0.38), crackN.add(float(0.32))));
          outCol.assign(mix(outCol, vec3(0.065, 0.036, 0.022), m1.mul(float(0.92))));
          outRough.assign(mix(outRough, float(0.95), m1));
        })
          .ElseIf(uSymptomMode.lessThan(float(2.5)), () => {
            // Mode 2: Cercospora beticola 2-4mm ash-grey spots with sharp crimson-purple halo
            const spotD = fastSpots3D(positionWorld.mul(float(22.0)));
            const spotCore = float(1.0).sub(smoothstep(float(0.10), float(0.16), spotD));
            const spotHalo = smoothstep(float(0.11), float(0.16), spotD).mul(
              float(1.0).sub(smoothstep(float(0.20), float(0.27), spotD))
            );
            const m2Core = focusMask.mul(spotCore);
            const m2Halo = focusMask.mul(spotHalo);
            outCol.assign(mix(outCol, vec3(0.38, 0.07, 0.10), m2Halo.mul(float(0.92))));
            outCol.assign(mix(outCol, vec3(0.56, 0.51, 0.45), m2Core.mul(float(0.90))));
            outRough.assign(mix(outRough, float(0.92), clamp(m2Core.add(m2Halo), float(0.0), float(1.0))));
          })
          .ElseIf(uSymptomMode.lessThan(float(3.5)), () => {
            // Mode 3: Erysiphe betae white-grey powdery mildew predominantly on upper surface
            const mPatch = smoothstep(float(-0.22), float(0.34), fastNoise3D(positionWorld.mul(float(42.0))));
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
            const pestD = fastSpots3D(positionWorld.mul(float(17.0)));
            const pCen = float(1.0).sub(smoothstep(float(0.11), float(0.18), pestD));
            const pRim = smoothstep(float(0.14), float(0.19), pestD).mul(
              float(1.0).sub(smoothstep(float(0.22), float(0.29), pestD))
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

  if (nodeMat.thicknessColorNode) {
    nodeMat.thicknessColorNode = nodeMat.thicknessColorNode.mul(
      float(1.0).sub(lesionMatteFactor.mul(float(0.85)))
    );
  }

  nodeMat.colorNode = symRes.rgb;
  nodeMat.roughnessNode = symRes.w;
  nodeMat.clearcoatNode = clamp(clearcoatVal.mul(float(1.0).sub(lesionMatteFactor)), float(0.0), float(0.35));
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
  hemiLightRef = hemi;
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
  fillLightRef = fillLight;
  scene.add(fillLight);

  const rimLight = new THREE.DirectionalLight(0xf3fee4, 1.10);
  rimLight.position.set(0.3, 1.8, -2.8);
  scene.add(rimLight);

  // Start with instant direct WebGPU/WebGL2 render (0ms SSAO compile stall, 60 FPS);
  // RenderPipeline + SSAONode is initialized lazily only when user enables "Ультра AO"
  renderPipeline = null;

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
  if (typeof ResizeObserver === "function" && stageContainer) {
    const ro = new ResizeObserver(() => resizeRenderer());
    ro.observe(stageContainer);
    if (stageControlsTop) ro.observe(stageControlsTop);
  }
}

function computeStageGeometry() {
  if (!stageContainer) return;
  const w = Math.max(240, stageContainer.clientWidth || 800);
  const h = Math.max(280, stageContainer.clientHeight || 540);
  const controlsH = stageControlsTop
    ? stageControlsTop.offsetTop + stageControlsTop.offsetHeight
    : (w < 620 ? 84 : 46);
  const topSafe = Math.max(54, controlsH + 10);
  const isMobile = w < 520;
  const botSafe = h - (isMobile ? 50 : 52);
  const availH = Math.max(160, botSafe - topSafe);
  const cx = w * 0.5;
  const cy = topSafe + availH * 0.5;

  let dotR;
  let pillMaxW;
  let minRPhase;
  let maxRPhase;
  if (isMobile) {
    dotR = 13;
    pillMaxW = Math.max(120, Math.floor((w - 24) / 2));
    minRPhase = 60;
    const maxRFromH = Math.max(66, (availH - 86) * 0.5 - dotR - 4);
    maxRPhase = Math.max(66, Math.min(w * 0.5 - dotR - 10, maxRFromH, 146));
  } else {
    dotR = w >= 700 ? 15 : 14;
    pillMaxW = Math.min(186, Math.max(136, Math.floor(w * 0.245)));
    minRPhase = Math.max(78, Math.min(104, w * 0.14));
    maxRPhase = Math.max(minRPhase + 18, Math.min(w * 0.5 - dotR - 22, availH * 0.5 - dotR - 14, 215));
  }

  stageGeo.w = w;
  stageGeo.h = h;
  stageGeo.cx = cx;
  stageGeo.cy = cy;
  stageGeo.minRPhase = minRPhase;
  stageGeo.maxRPhase = maxRPhase;
  stageGeo.dotR = dotR;
  stageGeo.pillMaxW = pillMaxW;
  stageGeo.topSafe = topSafe;
  stageGeo.botSafe = botSafe;
  stageGeo.isMobile = isMobile;
  stageGeo.rPhase = Math.max(minRPhase, Math.min(maxRPhase, stageGeo.rPhase));

  const reticleSize = stageGeo.rPhase / (245 / 800);
  stageContainer.style.setProperty("--reticle-cx", `${cx.toFixed(1)}px`);
  stageContainer.style.setProperty("--reticle-cy", `${cy.toFixed(1)}px`);
  stageContainer.style.setProperty("--reticle-size", `${reticleSize.toFixed(1)}px`);
  stageContainer.style.setProperty("--dot-size", `${(dotR * 2).toFixed(0)}px`);
  stageContainer.style.setProperty("--pill-max-w", `${pillMaxW}px`);

  if (hotspotLeadersSvg) {
    hotspotLeadersSvg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  }
  updateDynamicRingRadius(0, true);
  layoutReticlePhaseDots();
}

function samplePlantExtents() {
  if (!plantRoot || !mixer || actions.length === 0 || !state.crop) return;
  const dur = Math.max(0.1, state.durationSec || 6.25);
  const samples = 21;
  const prevTime = state.currentTime;
  const box = new THREE.Box3();
  const profile = [];

  for (let i = 0; i < samples; i++) {
    const t = (i / (samples - 1)) * dur;
    for (const action of actions) {
      const clipDur = action.getClip().duration || dur;
      action.enabled = true;
      action.paused = true;
      action.time = Math.max(0, Math.min(t, Math.max(0, clipDur - 1e-5)));
    }
    mixer.update(0);
    plantRoot.updateMatrixWorld(true);
    box.setFromObject(plantRoot);
    if (!box.isEmpty()) {
      const halfW = Math.max(
        0.04,
        Math.abs(box.min.x),
        Math.abs(box.max.x),
        Math.abs(box.min.z),
        Math.abs(box.max.z)
      );
      const midY = (box.min.y + box.max.y) * 0.5;
      profile.push({ t, halfW, midY });
    }
  }

  // Restore exact active playback timestamp
  for (const action of actions) {
    const clipDur = action.getClip().duration || dur;
    action.enabled = true;
    action.paused = true;
    action.time = Math.max(0, Math.min(prevTime, Math.max(0, clipDur - 1e-5)));
  }
  mixer.update(0);
  plantExtentProfile = profile;
}

function getInterpolatedPlantExtent(timeSec) {
  if (!plantExtentProfile || plantExtentProfile.length === 0) {
    return { halfW: 0.14, midY: 0 };
  }
  if (timeSec <= plantExtentProfile[0].t) return plantExtentProfile[0];
  const last = plantExtentProfile[plantExtentProfile.length - 1];
  if (timeSec >= last.t) return last;

  for (let i = 0; i < plantExtentProfile.length - 1; i++) {
    const a = plantExtentProfile[i];
    const b = plantExtentProfile[i + 1];
    if (timeSec >= a.t && timeSec <= b.t) {
      const span = Math.max(1e-5, b.t - a.t);
      const alpha = (timeSec - a.t) / span;
      return {
        halfW: a.halfW + (b.halfW - a.halfW) * alpha,
        midY: a.midY + (b.midY - a.midY) * alpha,
      };
    }
  }
  return last;
}

function updateDynamicRingRadius(dt, snap = false) {
  let screenHalf = stageGeo.plantScreenHalfW;
  if (camera) {
    camera.updateMatrixWorld();
    const { halfW, midY } = getInterpolatedPlantExtent(state.currentTime);
    tmpExtCenter.set(0, midY, 0);
    tmpCamRight.setFromMatrixColumn(camera.matrixWorld, 0).normalize();
    tmpExtSide.copy(tmpExtCenter).addScaledVector(tmpCamRight, halfW);
    tmpExtCenter.project(camera);
    tmpExtSide.project(camera);
    if (tmpExtCenter.z >= -1 && tmpExtCenter.z <= 1) {
      screenHalf = Math.max(18, Math.abs(tmpExtSide.x - tmpExtCenter.x) * 0.5 * stageGeo.w);
    }
  }
  stageGeo.plantScreenHalfW = screenHalf;

  const cosFlank = Math.cos((32 * Math.PI) / 180);
  const rNeeded = (screenHalf + stageGeo.dotR + 16) / cosFlank;
  const targetR = Math.max(stageGeo.minRPhase, Math.min(stageGeo.maxRPhase, rNeeded));
  stageGeo.targetRPhase = targetR;

  const prevR = stageGeo.rPhase;
  const nextR = snap
    ? targetR
    : prevR + (targetR - prevR) * Math.min(1, Math.max(0.01, dt || 0.016) * 8.0);
  stageGeo.rPhase = Math.max(stageGeo.minRPhase, Math.min(stageGeo.maxRPhase, nextR));

  if (snap || Math.abs(stageGeo.rPhase - prevR) > 0.25) {
    if (stageContainer) {
      const reticleSize = stageGeo.rPhase / (245 / 800);
      stageContainer.style.setProperty("--reticle-size", `${reticleSize.toFixed(1)}px`);
    }
    layoutReticlePhaseDots();
  }
}

function resizeRenderer() {
  computeStageGeometry();
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

function renderReticlePhaseRing() {
  if (!reticlePhaseRing || !state.crop) return;
  reticlePhaseRing.innerHTML = "";
  const phases = state.crop.phases || [];
  reticleDotEls = phases.map((phase, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "reticle-phase-dot";
    btn.setAttribute("role", "tab");
    btn.dataset.index = String(idx);
    btn.setAttribute("aria-label", `Фаза ${idx + 1}: ${phase.bbch} — ${phase.title}`);
    btn.innerHTML = `<span>${idx + 1}</span><span class="reticle-phase-tooltip">${phase.bbch} · ${phase.short_label}</span>`;
    btn.addEventListener("click", (ev) => {
      if (ev.detail > 0) btn.blur();
      stopAutoplay();
      selectPhase(idx, true);
    });
    reticlePhaseRing.appendChild(btn);
    return btn;
  });
  layoutReticlePhaseDots();
  updateReticlePhaseRing(state.activePhaseIndex);
}

function layoutReticlePhaseDots() {
  const n = reticleDotEls.length;
  stageGeo.dotPositions = [];
  if (!n) return;
  const leftCount = Math.ceil(n / 2);
  const rightCount = n - leftCount;

  for (let idx = 0; idx < n; idx++) {
    const btn = reticleDotEls[idx];
    const isLeft = idx < leftCount;
    let deg;
    if (isLeft) {
      deg = leftCount === 1 ? 180 : 148 + (idx / (leftCount - 1)) * 64;
    } else {
      const j = idx - leftCount;
      deg = rightCount === 1 ? 0 : 328 + (j / (rightCount - 1)) * 64;
    }
    const ang = (deg * Math.PI) / 180;
    const px = stageGeo.cx + Math.cos(ang) * stageGeo.rPhase;
    const py = stageGeo.cy + Math.sin(ang) * stageGeo.rPhase;
    btn.style.left = `${px.toFixed(1)}px`;
    btn.style.top = `${py.toFixed(1)}px`;
    const side = isLeft ? "left" : "right";
    btn.dataset.quadrant = side;
    stageGeo.dotPositions[idx] = { x: px, y: py, side };
  }
}

function updateReticleArcProgress(progress01) {
  if (!state.crop) return;
  const n = Math.max(2, (state.crop.phases || []).length);
  const leftCount = Math.ceil(n / 2);
  const clamped = Math.max(0, Math.min(1, progress01));

  const leftEnd = (leftCount - 1) / Math.max(1, n - 1);
  const rightStart = leftCount / Math.max(1, n - 1);
  const leftFrac = leftEnd > 0 ? Math.max(0, Math.min(1, clamped / leftEnd)) : 1;
  const rightFrac = 1 - rightStart > 0 ? Math.max(0, Math.min(1, (clamped - rightStart) / (1 - rightStart))) : 0;

  if (reticleProgressLeft) {
    const len = leftFrac * FLANK_ARC_LEN;
    reticleProgressLeft.style.strokeDasharray = `${len.toFixed(1)} ${(FLANK_ARC_LEN + 8).toFixed(1)}`;
  }
  if (reticleProgressRight) {
    const len = rightFrac * FLANK_ARC_LEN;
    reticleProgressRight.style.strokeDasharray = `${len.toFixed(1)} ${(FLANK_ARC_LEN + 8).toFixed(1)}`;
  }
}

function updateReticlePhaseRing(activeIdx) {
  for (let idx = 0; idx < reticleDotEls.length; idx++) {
    const btn = reticleDotEls[idx];
    const isSel = idx === activeIdx;
    btn.classList.toggle("is-active", isSel);
    btn.classList.toggle("is-passed", idx < activeIdx);
    btn.setAttribute("aria-selected", isSel ? "true" : "false");
  }
  const phases = state.crop?.phases || [];
  if (phases.length > 1) {
    updateReticleArcProgress(activeIdx / (phases.length - 1));
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
    btn.addEventListener("click", (ev) => {
      if (ev.detail > 0) btn.blur();
      stopAutoplay();
      selectPhase(idx, true);
    });
    phaseButtonsEl.appendChild(btn);
  });
  renderReticlePhaseRing();
}

function syncSliderVisual(labelText) {
  if (!phaseSlider) return;
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
    if (phaseSlider) {
      const pct = (phase.time_sec / state.durationSec) * 100;
      phaseSlider.value = pct.toFixed(1);
    }
  }
  syncSliderVisual(`${phase.bbch} — ${phase.title}`);

  for (const btn of phaseButtonsEl.querySelectorAll(".phase-row-btn")) {
    const isSel = Number(btn.dataset.index) === clamped;
    btn.classList.toggle("is-active", isSel);
    btn.setAttribute("aria-selected", isSel ? "true" : "false");
  }
  updateReticlePhaseRing(clamped);
  if (btnPrev) btnPrev.disabled = clamped === 0;
  if (btnNext) btnNext.disabled = clamped === phases.length - 1;

  if (readoutBbch) readoutBbch.textContent = phase.bbch;
  if (readoutPhase) readoutPhase.textContent = `Фаза ${clamped + 1} из ${phases.length}`;
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
  if (hotspotLeadersSvg) hotspotLeadersSvg.innerHTML = "";
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
    btn.innerHTML = `<span class="hotspot-icon" aria-hidden="true">${iconSvg}</span><span class="hotspot-label">${threat.name}</span>`;
    btn.addEventListener("click", () => setActiveThreat(threat.id, true, true));
    hotspotsLayer.appendChild(btn);

    let lineEl = null;
    let anchorDotEl = null;
    if (hotspotLeadersSvg) {
      lineEl = document.createElementNS(SVG_NS, "polyline");
      lineEl.setAttribute("class", "hotspot-leader-line");
      anchorDotEl = document.createElementNS(SVG_NS, "circle");
      anchorDotEl.setAttribute("class", "hotspot-anchor-dot");
      anchorDotEl.dataset.severity = threat.severity;
      anchorDotEl.setAttribute("r", "3.5");
      hotspotLeadersSvg.appendChild(lineEl);
      hotspotLeadersSvg.appendChild(anchorDotEl);
    }

    return {
      id: threat.id,
      severity: threat.severity,
      anchor: new THREE.Vector3(...threat.anchor),
      symptom: threat.symptom || null,
      el: btn,
      lineEl,
      anchorDotEl,
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

function hideHotspotItem(item) {
  item.el.style.display = "none";
  if (item.lineEl) item.lineEl.style.display = "none";
  if (item.anchorDotEl) item.anchorDotEl.style.display = "none";
}

function updateHotspotPositions() {
  if (!camera || !state.showHotspots) {
    hotspotsLayer.hidden = true;
    if (hotspotLeadersSvg) hotspotLeadersSvg.hidden = true;
    return;
  }
  hotspotsLayer.hidden = false;
  if (hotspotLeadersSvg) hotspotLeadersSvg.hidden = false;

  const { w, h, cx, cy, rPhase, dotR, pillMaxW, topSafe, botSafe, isMobile } = stageGeo;
  const proj = new THREE.Vector3();
  const visible = [];

  for (const item of hotspotItems) {
    proj.copy(item.anchor).project(camera);
    if (proj.z > 1 || proj.z < -1) {
      hideHotspotItem(item);
      continue;
    }
    const ax = (proj.x * 0.5 + 0.5) * w;
    const ay = (-proj.y * 0.5 + 0.5) * h;
    if (ax < -20 || ax > w + 20 || ay < -20 || ay > h + 20) {
      hideHotspotItem(item);
      continue;
    }
    item.el.style.display = "inline-flex";
    const pw = Math.min(pillMaxW, Math.max(88, item.el.offsetWidth || pillMaxW));
    const ph = Math.max(28, item.el.offsetHeight || 34);
    visible.push({ item, ax, ay, pw, ph, x1: 0, y1: 0, x2: 0, y2: 0, side: "right" });
  }

  if (visible.length === 0) return;

  if (isMobile) {
    // Upper anchors stay on the top shelf and lower anchors on the bottom shelf so leader lines never cross
    const byY = [...visible].sort((a, b) => a.ay - b.ay);
    let topShelf;
    let botShelf;
    if (byY.length === 1) {
      topShelf = byY[0].ay <= cy ? [byY[0]] : [];
      botShelf = byY[0].ay <= cy ? [] : [byY[0]];
    } else {
      const topCount = Math.ceil(byY.length / 2);
      topShelf = byY.slice(0, topCount);
      botShelf = byY.slice(topCount);
    }

    const placeShelf = (shelf, isTop) => {
      shelf.sort((a, b) => a.ax - b.ax);
      shelf.forEach((entry, idx) => {
        const y1 = isTop ? topSafe + 4 : botSafe - entry.ph - 4;
        let x1;
        if (shelf.length === 1) {
          x1 = Math.max(8, Math.min(w - entry.pw - 8, entry.ax - entry.pw * 0.5));
        } else if (idx === 0) {
          x1 = 8;
        } else {
          x1 = Math.max(shelf[idx - 1].x2 + 6, w - entry.pw - 8);
        }
        entry.side = isTop ? "top" : "bottom";
        entry.x1 = x1;
        entry.y1 = y1;
        entry.x2 = x1 + entry.pw;
        entry.y2 = y1 + entry.ph;
      });
    };
    placeShelf(topShelf, true);
    placeShelf(botShelf, false);
  } else {
    // 3-Zone Desktop/Tablet solver: push outside phase-ring keep-out radius on Left & Right lanes
    const byX = [...visible].sort((a, b) => a.ax - b.ax);
    let leftGroup = [];
    let rightGroup = [];
    for (const entry of byX) {
      if (entry.ax < cx - 8) leftGroup.push(entry);
      else if (entry.ax > cx + 8) rightGroup.push(entry);
      else if (leftGroup.length <= rightGroup.length) leftGroup.push(entry);
      else rightGroup.push(entry);
    }
    if (byX.length >= 2 && (leftGroup.length === 0 || rightGroup.length === 0)) {
      const mid = Math.floor(byX.length / 2);
      leftGroup = byX.slice(0, mid);
      rightGroup = byX.slice(mid);
    }

    const minGap = 10;
    const plantClear = Math.max(stageGeo.plantScreenHalfW + 16, rPhase * 0.56);

    for (const [side, grp] of [
      ["left", leftGroup],
      ["right", rightGroup],
    ]) {
      if (grp.length === 0) continue;
      grp.sort((a, b) => a.ay - b.ay);
      const sideDots = stageGeo.dotPositions.filter((d) => d.side === side);
      const minDotY = sideDots.length ? Math.min(...sideDots.map((d) => d.y)) : cy;
      const maxDotY = sideDots.length ? Math.max(...sideDots.map((d) => d.y)) : cy;
      const ys = grp.map((e) => Math.max(topSafe + e.ph * 0.5, Math.min(botSafe - e.ph * 0.5, e.ay)));

      const computeNeededXClear = (py, ph) => {
        let xClear = plantClear;
        for (const dot of sideDots) {
          if (Math.abs(py - dot.y) < ph * 0.5 + dotR + 10) {
            xClear = Math.max(xClear, Math.abs(dot.x - cx) + dotR + 12);
          }
        }
        return xClear;
      };

      const nudgeAboveOrBelowDots = (entry, py) => {
        const xClear = computeNeededXClear(py, entry.ph);
        const availLane = side === "left" ? cx - xClear - 10 : w - 10 - (cx + xClear);
        if (availLane >= entry.pw || sideDots.length === 0) return py;

        const aboveY = Math.max(topSafe + entry.ph * 0.5, minDotY - dotR - entry.ph * 0.5 - 10);
        const belowY = Math.min(botSafe - entry.ph * 0.5, maxDotY + dotR + entry.ph * 0.5 + 10);
        const aboveFree = aboveY <= minDotY - dotR - entry.ph * 0.5 - 8;
        const belowFree = belowY >= maxDotY + dotR + entry.ph * 0.5 + 8;
        if (aboveFree && belowFree) {
          return Math.abs(aboveY - entry.ay) <= Math.abs(belowY - entry.ay) ? aboveY : belowY;
        }
        if (aboveFree) return aboveY;
        if (belowFree) return belowY;
        return py;
      };

      const relaxSideY = () => {
        for (let passIdx = 0; passIdx < 4; passIdx++) {
          for (let j = 1; j < grp.length; j++) {
            const minY = ys[j - 1] + grp[j - 1].ph * 0.5 + grp[j].ph * 0.5 + minGap;
            if (ys[j] < minY) ys[j] = minY;
          }
          for (let j = grp.length - 1; j >= 0; j--) {
            const maxY = botSafe - grp[j].ph * 0.5;
            if (ys[j] > maxY) ys[j] = maxY;
            if (j > 0) {
              const maxPrev = ys[j] - grp[j].ph * 0.5 - grp[j - 1].ph * 0.5 - minGap;
              if (ys[j - 1] > maxPrev) ys[j - 1] = maxPrev;
            }
          }
          for (let j = 0; j < grp.length; j++) {
            ys[j] = Math.max(topSafe + grp[j].ph * 0.5, Math.min(botSafe - grp[j].ph * 0.5, ys[j]));
          }
        }
      };

      relaxSideY();
      let nudged = false;
      for (let j = 0; j < grp.length; j++) {
        const ny = nudgeAboveOrBelowDots(grp[j], ys[j]);
        if (Math.abs(ny - ys[j]) > 1) {
          ys[j] = ny;
          nudged = true;
        }
      }
      if (nudged) relaxSideY();

      grp.forEach((entry, j) => {
        const py = ys[j];
        const xClear = computeNeededXClear(py, entry.ph);

        let x1;
        let x2;
        if (side === "left") {
          x2 = cx - xClear;
          x1 = Math.max(10, x2 - entry.pw);
          x2 = x1 + entry.pw;
        } else {
          x1 = cx + xClear;
          x2 = Math.min(w - 10, x1 + entry.pw);
          x1 = x2 - entry.pw;
        }
        entry.side = side;
        entry.x1 = x1;
        entry.x2 = x2;
        entry.y1 = py - entry.ph * 0.5;
        entry.y2 = py + entry.ph * 0.5;
      });
    }
  }

  for (const entry of visible) {
    const { item, ax, ay, x1, y1, x2, y2, side } = entry;
    const isActive = item.id === state.activeThreatId;
    item.el.dataset.align = side;
    item.el.style.left = `${x1.toFixed(1)}px`;
    item.el.style.top = `${y1.toFixed(1)}px`;

    if (item.lineEl && item.anchorDotEl) {
      const anchorVisible = ax >= 4 && ax <= w - 4 && ay >= 4 && ay <= h - 4;
      item.lineEl.style.display = anchorVisible ? "" : "none";
      item.anchorDotEl.style.display = anchorVisible ? "" : "none";
      if (anchorVisible) {
        let pts;
        if (side === "left" || side === "right") {
          const edgeX = side === "left" ? x2 : x1;
          const edgeY = (y1 + y2) * 0.5;
          const elbowX =
            side === "left"
              ? Math.min(Math.max(ax, edgeX), edgeX + 16)
              : Math.max(Math.min(ax, edgeX), edgeX - 16);
          pts = `${ax.toFixed(1)},${ay.toFixed(1)} ${elbowX.toFixed(1)},${edgeY.toFixed(1)} ${edgeX.toFixed(1)},${edgeY.toFixed(1)}`;
        } else {
          const edgeX = (x1 + x2) * 0.5;
          const edgeY = side === "top" ? y2 : y1;
          const stubY = side === "top" ? edgeY + 10 : edgeY - 10;
          pts = `${ax.toFixed(1)},${ay.toFixed(1)} ${edgeX.toFixed(1)},${stubY.toFixed(1)} ${edgeX.toFixed(1)},${edgeY.toFixed(1)}`;
        }
        item.lineEl.setAttribute("points", pts);
        item.lineEl.classList.toggle("is-active", isActive);
        item.anchorDotEl.setAttribute("cx", ax.toFixed(1));
        item.anchorDotEl.setAttribute("cy", ay.toFixed(1));
        item.anchorDotEl.setAttribute("r", isActive ? "5.2" : "3.5");
        item.anchorDotEl.classList.toggle("is-active", isActive);
      }
    }
  }
}

function updateMaturationMaterials(progress) {
  const matPhase = Math.max(0, Math.min(1, (progress - 0.52) / 0.48));
  const podPhase = Math.max(0, Math.min(1, (progress - 0.68) / 0.32));
  uOuterSenescence.value = matPhase;
  uPodPhase.value = podPhase;

  if (matHandles.outer) {
    tmpColor.copy(activePalette.outerFresh).lerp(activePalette.outerMature, matPhase * 0.65);
    matHandles.outer.color.copy(tmpColor);
    if (matHandles.outer.userData.uMatTint) matHandles.outer.userData.uMatTint.value.copy(tmpColor);
    if (matHandles.outer.userData.uRoughMul) matHandles.outer.userData.uRoughMul.value = 0.95 + 0.35 * matPhase;
  }
  if (matHandles.mid) {
    tmpColor.copy(activePalette.midFresh).lerp(activePalette.midMature, matPhase * 0.58);
    matHandles.mid.color.copy(tmpColor);
    if (matHandles.mid.userData.uMatTint) matHandles.mid.userData.uMatTint.value.copy(tmpColor);
    if (matHandles.mid.userData.uRoughMul) matHandles.mid.userData.uRoughMul.value = 0.88 + 0.25 * matPhase;
  }
  if (matHandles.heart) {
    tmpColor.copy(activePalette.heartFresh).lerp(activePalette.heartMature, matPhase * 0.42);
    matHandles.heart.color.copy(tmpColor);
    if (matHandles.heart.userData.uMatTint) matHandles.heart.userData.uMatTint.value.copy(tmpColor);
  }
  if (matHandles.stem) {
    tmpColor.copy(activePalette.stemFresh).lerp(activePalette.stemMature, podPhase * 0.55);
    matHandles.stem.color.copy(tmpColor);
    if (matHandles.stem.userData.uMatTint) matHandles.stem.userData.uMatTint.value.copy(tmpColor);
  }
  if (matHandles.pod) {
    tmpColor.copy(activePalette.podFresh).lerp(activePalette.podMature, podPhase);
    matHandles.pod.color.copy(tmpColor);
    if (matHandles.pod.userData.uMatTint) matHandles.pod.userData.uMatTint.value.copy(tmpColor);
    if (matHandles.pod.userData.uRoughMul) matHandles.pod.userData.uRoughMul.value = 0.85 + 0.40 * podPhase;
  }
  if (matHandles.root) {
    tmpColor.copy(activePalette.rootEarly).lerp(activePalette.rootMature, progress * 0.65);
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
  if (btnAutoplay) {
    btnAutoplay.textContent = "▶";
    btnAutoplay.classList.remove("is-playing");
    btnAutoplay.setAttribute("aria-label", "Запустить авто-рост");
  }
}

function toggleAutoplay() {
  state.autoPlaying = !state.autoPlaying;
  if (state.autoPlaying) {
    if (state.targetTime >= state.durationSec - 0.05) {
      state.targetTime = 0;
      state.currentTime = 0;
    }
    if (btnAutoplay) {
      btnAutoplay.textContent = "⏸";
      btnAutoplay.classList.add("is-playing");
      btnAutoplay.setAttribute("aria-label", "Приостановить авто-рост");
    }
  } else {
    if (btnAutoplay) {
      btnAutoplay.textContent = "▶";
      btnAutoplay.classList.remove("is-playing");
      btnAutoplay.setAttribute("aria-label", "Запустить авто-рост");
    }
  }
}

async function ensureUltraAOPipeline() {
  if (renderPipeline) return true;
  if (!renderer || !scene || !camera || typeof THREE.RenderPipeline !== "function") return false;
  try {
    const { ssao } = await import("three/addons/tsl/display/SSAONode.js");
    const isMobile = window.innerWidth < 768;

    const prePass = pass(scene, camera);
    prePass.transparent = false;
    prePass.setMRT(mrt({ output: packNormalToRGB(normalView) }));
    const normalTex = prePass.getTexture("output");
    normalTex.type = THREE.UnsignedByteType;
    const prePassNormal = sample((u) => unpackRGBToNormal(prePass.getTextureNode().sample(u)));
    const prePassDepth = prePass.getTextureNode("depth");

    const aoPass = ssao(prePassDepth, prePassNormal, camera);
    aoPass.resolutionScale = isMobile ? 0.5 : 0.75;
    aoPass.samples.value = isMobile ? 12 : 16;
    aoPass.radius.value = 0.085;
    aoPass.intensity.value = 2.4;
    if (aoPass.bias) aoPass.bias.value = 0.015;
    aoPass.blurEnabled = true;
    if (aoPass.blurSharpness) aoPass.blurSharpness.value = 12.0;

    const aoSample = clamp(aoPass.getTextureNode().sample(screenUV).r, float(0.0), float(1.0));

    const scenePass = pass(scene, camera);
    scenePass.options.samples = isMobile ? 2 : 4;
    scenePass.contextNode = builtinAOContext(aoSample);

    // Composite sculptural crevice darkening into direct-lit RGB while preserving transparent canvas alpha
    const sceneColor = scenePass.getTextureNode("output");
    const creviceFactor = mix(
      float(0.42),
      float(1.0),
      smoothstep(float(0.08), float(0.96), aoSample)
    );
    const finalOutput = vec4(sceneColor.rgb.mul(creviceFactor), sceneColor.a);

    renderPipeline = new THREE.RenderPipeline(renderer, finalOutput);
    renderPipeline.outputColorTransform = true;
    return true;
  } catch (pipeErr) {
    console.warn("Ultra AO unavailable, keeping fast direct render:", pipeErr);
    renderPipeline = null;
    return false;
  }
}

function syncUltraAOState() {
  if (fillLightRef) fillLightRef.intensity = state.ultraAO ? 0.44 : 0.62;
  if (hemiLightRef) hemiLightRef.intensity = state.ultraAO ? 0.54 : 0.48;
  if (toggleSsaoBtn) {
    toggleSsaoBtn.classList.toggle("is-active", state.ultraAO);
    toggleSsaoBtn.setAttribute("aria-pressed", state.ultraAO ? "true" : "false");
    toggleSsaoBtn.textContent = `Ультра AO: ${state.ultraAO ? "Вкл" : "Выкл"}`;
  }
}

function bindUI() {
  if (phaseSlider) {
    phaseSlider.addEventListener("input", () => {
      stopAutoplay();
      const pct = Number(phaseSlider.value) / 100;
      state.targetTime = pct * state.durationSec;
      const nearest = findClosestPhaseIndex(state.targetTime);
      selectPhase(nearest, false);
    });
  }

  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      stopAutoplay();
      selectPhase(state.activePhaseIndex - 1, true);
    });
  }

  if (btnNext) {
    btnNext.addEventListener("click", () => {
      stopAutoplay();
      selectPhase(state.activePhaseIndex + 1, true);
    });
  }

  if (btnAutoplay) {
    btnAutoplay.addEventListener("click", toggleAutoplay);
  }

  window.addEventListener("keydown", (ev) => {
    if (!state.crop || (ev.target && /^(INPUT|SELECT|TEXTAREA)$/.test(ev.target.tagName))) {
      return;
    }
    if (ev.key === "ArrowLeft") {
      ev.preventDefault();
      stopAutoplay();
      selectPhase(state.activePhaseIndex - 1, true);
    } else if (ev.key === "ArrowRight") {
      ev.preventDefault();
      stopAutoplay();
      selectPhase(state.activePhaseIndex + 1, true);
    }
  });

  if (toggleSymptomsBtn) {
    toggleSymptomsBtn.addEventListener("click", () => {
      state.showSymptoms = !state.showSymptoms;
      toggleSymptomsBtn.classList.toggle("is-active", state.showSymptoms);
      toggleSymptomsBtn.setAttribute("aria-pressed", state.showSymptoms ? "true" : "false");
      toggleSymptomsBtn.textContent = `Симптомы 3D: ${state.showSymptoms ? "Вкл" : "Выкл"}`;
      applyThreatSymptom(getActiveThreatData());
    });
  }

  if (toggleSsaoBtn) {
    toggleSsaoBtn.addEventListener("click", async () => {
      if (!state.ultraAO) {
        toggleSsaoBtn.textContent = "Ультра AO: …";
        const ok = await ensureUltraAOPipeline();
        state.ultraAO = ok;
      } else {
        state.ultraAO = false;
      }
      syncUltraAOState();
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
  const texLoader = new THREE.TextureLoader();
  const loadLinearMap = async (url, fallbackUrl = null) => {
    try {
      const tex = await texLoader.loadAsync(url);
      tex.flipY = false;
      tex.colorSpace = THREE.NoColorSpace;
      return tex;
    } catch {
      if (fallbackUrl) {
        return loadLinearMap(fallbackUrl, null);
      }
      return null;
    }
  };

  const { cropId, passportUrl, statsUrl } = await resolveCropConfig();
  const leafThickUrl =
    cropId === "sugar_beet"
      ? "../assets/textures/leaf_thickness.png"
      : `../assets/textures/${cropId}_leaf_thickness.png`;
  const rootThickUrl =
    cropId === "sugar_beet"
      ? "../assets/textures/root_thickness.png"
      : `../assets/textures/${cropId}_root_thickness.png`;

  const podThickUrl =
    cropId === "sugar_beet" ? null : `../assets/textures/${cropId}_pod_thickness.png`;

  const thicknessPromise = Promise.all([
    loadLinearMap(leafThickUrl, "../assets/textures/leaf_thickness.png"),
    loadLinearMap(rootThickUrl, "../assets/textures/root_thickness.png"),
    podThickUrl ? loadLinearMap(podThickUrl, null) : Promise.resolve(null),
  ]);

  const [cropRes, statsRes] = await Promise.all([
    fetch(passportUrl),
    fetch(statsUrl).catch(() => null),
  ]);
  if (!cropRes.ok) {
    throw new Error(`Ошибка загрузки паспорта культуры (HTTP ${cropRes.status}).`);
  }
  state.crop = await cropRes.json();
  state.durationSec = state.crop.duration_sec || 6.25;
  applyCropPalette(state.crop.maturation_palette);

  if (state.crop.archetype === "legume_pulse") {
    CAMERA_PRESETS.overview.pos.set(0.42, 0.20, 3.05);
    CAMERA_PRESETS.overview.target.set(0.0, 0.04, 0.0);
    CAMERA_PRESETS.root.pos.set(0.28, -0.26, 1.65);
    CAMERA_PRESETS.root.target.set(0.0, -0.32, 0.0);
    CAMERA_PRESETS.canopy.pos.set(0.50, 0.70, 1.78);
    CAMERA_PRESETS.canopy.target.set(0.0, 0.42, 0.0);
    if (camera && controls) {
      camera.position.copy(CAMERA_PRESETS.overview.pos);
      controls.target.copy(CAMERA_PRESETS.overview.target);
      state.cameraGoalPos.copy(CAMERA_PRESETS.overview.pos);
      state.cameraGoalTarget.copy(CAMERA_PRESETS.overview.target);
    }
  }

  if (state.crop.camera_preset_labels && typeof state.crop.camera_preset_labels === "object") {
    for (const btn of presetButtons) {
      const label = state.crop.camera_preset_labels[btn.dataset.preset];
      if (label) btn.textContent = label;
    }
  }

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

  const [[leafThickTex, rootThickTex, podThickTex], gltf] = await Promise.all([thicknessPromise, gltfPromise]);

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
      else if (srcMat.name === "Stem_PBR") tier = "stem";
      else if (srcMat.name === "Pod_PBR") tier = "pod";
      else if (srcMat.name === "Flower_PBR") tier = "flower";
      else if (srcMat.name === "Taproot_PBR") tier = "root";
      else if (srcMat.name === "Nodule_PBR") tier = "nodule";

      let nodeMat = upgradedMaterials.get(srcMat);
      if (!nodeMat) {
        const hasVCol = Boolean(obj.geometry && obj.geometry.attributes && obj.geometry.attributes.color);
        nodeMat = upgradeToPhotorealNodeMaterial(srcMat, tier, leafThickTex, rootThickTex, podThickTex, hasVCol);
        upgradedMaterials.set(srcMat, nodeMat);
        if (tier !== "other") {
          matHandles[tier] = nodeMat;
        }
      }
      obj.material = nodeMat;
    }
  });
  plantRoot = gltf.scene;
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
  samplePlantExtents();
  updateDynamicRingRadius(0, true);

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
      if (phaseSlider) {
        const pct = (state.targetTime / state.durationSec) * 100;
        phaseSlider.value = pct.toFixed(1);
        syncSliderVisual();
      }
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
      updateReticleArcProgress(progress);

      if (state.crop && readoutFrame) {
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
      if (state.ultraAO && renderPipeline) {
        try {
          renderPipeline.render();
        } catch (renderErr) {
          console.warn("RenderPipeline runtime fallback:", renderErr);
          state.ultraAO = false;
          renderPipeline = null;
          syncUltraAOState();
          renderer.render(scene, camera);
        }
      } else {
        renderer.render(scene, camera);
      }
      updateDynamicRingRadius(dt, false);
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
