# Botanical 3D Crop Archetypes Guide (Periscope Multi-Crop Scaling)

Use these structural blueprints when onboarding a new agricultural crop into Periscope. Every crop shares the same **6-phase timeline** (`frames 0, 30, 60, 90, 120, 150` at `24 fps` = `6.25 s`), **glTF Y-up convention** (`y = 0` at soil/collar horizon line), **plant-only presentation (no 3D soil)**, and **4-invariant QA audit**.

---

## Archetype 1: `root_crop` (Сахарная свекла, морковь, кормовая свекла)
- **Reference Implementation:** `blender/generate_sugar_beet.py`, `data/sugar_beet.json`.
- **Key Organs:**
  - Coated seed pellet (`Shape Key: Split`, `y < 0`) -> pinkish hypocotyl (capped!) + decussate glossy cotyledons (`yaw = 60° / 240°`) contracting flush into the swelling crown by frame `68`.
  - Plump flat-domed taproot (`rings >= 76` clustered at top crown) with helical sugar grooves (`0.825 * base_r`) and curved lower tail (`bend_x`, `bend_y`).
  - `16–24` tapered fibrous lateral rootlets anchored at `(bend_x + 0.68*base_r*cos, bend_y + 0.68*base_r*sin)` with `r_start` and `length` tapering down toward tail tip.
  - `16–20` phyllotactic rosette leaves in 4 staggered elevation tiers with `Folded` + `MatureCurl` shape keys and tapered basal plugs (`t < 0`) tracking `taproot_crown_world_z`.
- **BBCH Phases:** `00–05` Seed -> `09–10` Cotyledons -> `12–14` 2–4 leaves -> `16–19` Rosette -> `35–39` Canopy closure -> `49` Harvest maturity.

---

## Archetype 2: `cereal_grass` (Пшеница, ячмень, рожь, овёс)
- **Key Organs:**
  - Caryopsis (grain kernel) + coleoptile spike (`BBCH 00–10`) -> **fibrous crown/nodal root bush** radiating from the tillering node (`y ≈ -0.04`), NOT a single thick taproot! Every root strand gets a unique random-walk 3D curve and fine secondary root hairs.
  - Segmented hollow-capped culms (main stem + `2–3` staggered tillers emerging from the basal tillering node at `BBCH 21–29` with subtle outward lean `6–14°`).
  - Alternate linear grass leaves (`180°` distichous phyllotaxis) whose **cylindrical leaf sheath** wraps tightly around the parent culm node (`r_sheath = r_culm * 1.04`, zero air gap!) before curving gracefully outward into a slender tapering ribbon blade with unique arching droop and twist.
  - Terminal **spike / ear (`BBCH 51–89`)** emerging cleanly out of the flag-leaf sheath (`booting -> heading -> flowering -> milk/dough ripening`): layered overlapping glumes/spikelets + delicate barbed awns (for awned wheat/barley) shifting color from vibrant glaucous green -> golden amber straw at maturity (`BBCH 89`).
- **Metrics Example:** `protein_pct` / `moisture_pct`, `tillers_count`, `ear_length_mm`, `maturity_label`.
- **BBCH Phases:** `00–09` Grain/Emergence -> `11–13` 1–3 Leaves -> `21–29` Tillering -> `31–39` Stem Elongation -> `51–65` Heading/Flowering -> `85–89` Ripening.

---

## Archetype 3: `tall_row_grass` (Кукуруза — *Zea mays*)
- **Key Organs:**
  - Kernel -> primary radicle + seminal roots -> thick segmented cylindrical stalk with prominent swollen **nodes** (`rings` pinched/flared smoothly at each node).
  - **Brace / prop roots (`BBCH 32+`):** arching downward-curving adventitious roots emerging cleanly from the lowest 1–2 above-ground nodes into the subsoil zone (`y < 0`), anchored inside the node radius.
  - Broad, long alternate lance-shaped leaves (`8–12` leaves) with prominent white central midrib, ruffled edges, and varied downward gravity arch; every sheath wraps around its exact node height `stalk_node_z(node_idx, frame)`.
  - **Apical male tassel (`BBCH 55+`)** branching at stalk top + **1–2 axillary husked ears/cobs (`BBCH 63–89`)** nestled tight against mid-stalk nodes with silk tufts (tan/golden darkening during ripening).
- **Camera Framing Note:** Taller vertical aspect ratio (`height ~ 1.8–2.2` scene units) — pull `CAMERA_PRESETS.overview.pos.z` back (`~3.8–4.2`) and lower `target.y` so root crown aligns cleanly with `--soil-line-y`.

---

## Archetype 4: `broadleaf_oilseed` (Рапс, подсолнечник, соя)
- **Key Organs:**
  - **Root system:** Taproot (stronger in rapeseed/sunflower; nodulated lateral network with small spherical rhizobia nodules in soybean!) with deeply recessed, tapered branching laterals.
  - **Stem & Branching:** Upright central herbaceous stem with smooth tapered side branches (`r_branch` embedded `5 mm` inside parent stem node at every frame).
  - **Foliage:**
    - *Sunflower:* Large heart-shaped rough-textured alternate leaves with prominent palmate-pinnate venation + large terminal **capitulum** (sunflower head with golden ray florets + phyllotactic spiral disc florets turning heavy and nodding gently by `BBCH 89`).
    - *Rapeseed:* Basal lyrate rosette -> elongated branching stem -> bright yellow 4-petal racemes (`BBCH 60–65`) -> slender ascending **siliques (pods)** (`BBCH 71–89`) ripening to golden tan.
    - *Soybean:* Trifoliate compound leaves (3 articulated leaflets per petiole, each socketed onto a shared rachis tip!) -> axillary hairy pods (`BBCH 71–89`) yellowing at maturity.

---

## Archetype 5: `tuber_crop` (Картофель — *Solanum tuberosum*)
- **Key Organs:**
  - Mother seed tuber (`y ≈ -0.18`) -> multiple sprouting underground stems (`BBCH 09–19`) rising through `y = 0` into leafy above-ground haulm with **compound odd-pinnate leaves** (`5–7` leaflets per rachis + tiny interjected leaflets).
  - **Underground stolons (`BBCH 40–49`):** thin curving rhizomes growing radially from subterranean stem nodes, swelling smoothly at their tips into `5–8` varied daughter tubers (no 3D soil — clearly visible in the dark subsoil band!).
  - **Canopy maturation (`BBCH 60–95`):** star-shaped white/violet flowers (`BBCH 65`) -> foliage yellowing/senescence (`BBCH 91–95`) while daughter tubers reach full size and mature russet/creamy skin.

---

## Universal Adaptation Checklist When Creating a New Crop
1. Keep `y = 0` in glTF (`z = 0` in Blender) strictly at the **root-to-shoot soil horizon collar**.
2. Normalize total mature vertical span (`y_min` to `y_max`) to roughly `[-0.85 .. +0.85]` scene units (height `~1.6–1.8` units) so the Periscope radar reticle, camera presets, and horizon band align seamlessly across ALL crops without rewriting `web/style.css`.
3. Reuse the 6 Periscope `icon_type` SVGs (`beetle`, `worm`, `aphid`, `moth`, `fungus`, `weed`) or extend `THREAT_ICONS` in `web/app.js` if a new pest class is introduced.
4. Keep `data/<crop_id>.json` backward-compatible with `web/app.js` (same top-level keys; adapt `metrics` labels cleanly if a crop uses protein/moisture/pods instead of Brix/root diameter).
