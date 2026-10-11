# Architecture decisions

Supplementary material for the GeoCounterfactual paper: what the system is,
and why each major component takes the form it does.

## How to read this document

Provenance tags (as in `data_methodology.md`):

- **[M]** Measured from the data or code in this repository; the source is
  given.
- **[D]** A design decision and its rationale. Not an empirical claim.
- **[P]** Measured during development and recorded in code comments, but
  not regenerated for this document.
- **[N]** Not yet measured. Do not state it as a result.

Paths are relative to the repository root. Figures were verified on
2026-10-11.

---

## 0. The system in one paragraph

A user names a watershed (or uploads a scene) and describes an intervention
in plain language, such as "build 3 check dams along the main stream". The
system then:

1. retrieves a co-registered Sentinel-2 and DEM stack;
2. turns the request into a spatial change mask by routing flow over the
   DEM;
3. derives a physically bounded envelope of how vegetation and moisture can
   respond over the stated horizon;
4. generates a future scene with a fine-tuned latent-diffusion inpainting
   model;
5. judges that scene against four deterministic physical rules.

A violation sends a pixel-exact feedback mask back to the generator, and the
loop repeats until the scene passes or a retry budget is spent. **The
research contribution is this closed critic loop, not the diffusion
model.** The model is a replaceable component behind a fixed interface
(§3.1), and the critic is the instrument the paper's main experiment
measures with (§6).

---

## 1. The cyclic agent graph

**Topology [M; `backend/agents/workflow.py`].** Five nodes:

    input_handler → planner → dynamics → generator → critic
                                            ↑            │
                                            └────────────┘
                                 rejected, budget left

`check_critic_decision` routes the critic's output four ways:

| Condition | Next step |
|---|---|
| Approved | End |
| Shadow mode (§6.2) | End; the verdict is recorded but not enforced |
| Rejected, retry budget left | Back to the generator, with a feedback mask |
| Rejected, budget spent (3 iterations, `settings.max_critic_iterations`) | End, with the scene **still marked unapproved** |

**Why LangGraph [D].** The defining structure is a **cycle**: the critic
must be able to return control to the generator with new information. Many
agent frameworks model pipelines as directed acyclic graphs or
conversations. LangGraph's `StateGraph` treats conditional back-edges as
first-class, and keeps typed shared state across iterations.

**Accumulating state [D; `backend/agents/state.py`].** LangGraph's default
channel reducer *replaces* a value. On a cyclic graph, that would erase the
first iteration's rejection when the second iteration writes. The execution
log and the rejection history therefore use an `operator.add` reducer: each
node returns only its new entries, and the graph accumulates them. The
first rejection is exactly what the interface, and a reader of the paper,
most needs to see.

**The verdict is never laundered [D; `backend/agents/critic_node.py`].**
When the retry budget runs out, the scene is released (the loop must
terminate) but `is_approved` stays false. Approval and termination are
separate. Folding them together would report physics-violating scenes as
passing, and would zero the very violation rate the ablation measures.

**No checkpointer [D].** State carries raw numpy rasters. A serialising
checkpointer cannot persist them, and a run is a synchronous request of
seconds (GPU) to minutes (CPU), so runs are in-memory and non-resumable.

---

## 2. The hybrid planner: language model for intent, geometry from the DEM

**The design [D; `backend/agents/planner.py`].** Planning is split into two
stages with a deliberate boundary between them:

1. **Intent (language model).** A plain-language instruction is parsed into
   a small typed object (`InterventionPlan`): structure type, count,
   placement strategy, buffer radius, crest height, optional area. Gemini is
   called with schema-constrained output at temperature 0. A deterministic
   keyword parser is the fallback.
2. **Geometry (deterministic).** Every pixel of the change mask comes from
   terrain analysis of the DEM, never from the language model.

**Why not let the language model place structures [D].** A language model
asked for check-dam coordinates will return plausible-looking rows and
columns with no access to the terrain, for example a dam on a ridge. Limiting
it to intent has three consequences:

1. **A hallucinated coordinate cannot reach the generator.**
2. **Geometry is reproducible.** The same intent on the same DEM always
   gives the same mask, which the ablation requires.
3. **The system works without the language model.** With no key, or during
   an outage, the keyword parser supplies the intent. The language model is
   called once with bounded retries; an availability error (HTTP 503 or 429,
   or a timeout) ends the call immediately and falls back.

   [M] During development, a 503 burst held the planner for 51 s across
   four calls. Fail-fast reduced this to one call; the regression is tested
   in `backend/tests/test_planner_fallback.py`.

**Terrain pipeline [M; `backend/agents/terrain.py`].**

| Step | Method | Parameter |
|---|---|---|
| Depression filling | Priority-Flood with an ε gradient (Barnes, Lehman & Mulla 2014) | ε = 1e-4 m per step |
| Flow direction | D8 steepest descent, drop ÷ step length (diagonals √2) (O'Callaghan & Mark 1984) | — |
| Flow accumulation | Upstream cell count | — |
| Stream network | Cells draining ≥ threshold | 400 cells = 4 ha |
| Dam siting | On-stream, slope < 5°, in descending contributing area, minimum spacing, border exclusion | 300 m spacing; 400 m border |
| Impoundment | Connected cells within 400 m of the dam, at or below crest elevation, channelised, slope ≤ 2.5°, 8-connected | crest height from intent (default 3 m) |

Points to report:

- **The ε gradient is necessary [P; `fill_depressions` docstring].** Plain
  priority-flood leaves filled flats with zero drop, and D8 then has no
  downstream cell. Bilinear resampling of the 30 m DEM to 10 m makes large
  equal-valued runs. Without ε, "roughly half the grid" had no defined
  downstream neighbour and flow accumulation was "capped at single digits".
  With ε the main stem reaches about 106,000 contributing cells
  (`impoundment_mask` docstring). At ε = 1e-4 m, even a 1,000-cell flat
  accrues only 0.1 m, well below the DEM's vertical error.
- **Border exclusion.** Flow accumulation is largest where flow *leaves*
  the tile, so ranking by accumulation alone always sites the first dam on
  the boundary pixel. That is an artefact of the analysis window, not the
  watershed.
- **The planner and the critic share physics.** The impoundment mask
  excludes ground steeper than the critic's 2.5° limit. Without this, the
  planner places water that rule R1 rejects every iteration (the generator
  is told to remove water that the planner keeps putting back), and the loop
  can never converge.
- **Rejections accumulate across iterations [P; `diffusion_local.py`].**
  Each generator excludes the *union* of all pixels rejected so far, not
  only the latest pass's. Applying only the newest mask made pixels
  corrected at iteration 1 editable again at iteration 3. The code records
  the resulting oscillation in pool area as 57,800 → 2,700 → 4,800 m².
- **8-connectivity.** The main channels run diagonally (e.g. NE–SW). Under
  the default 4-connectivity a diagonal pool falls apart into single pixels.

---

## 3. The generator: SD 1.5 inpainting + ControlNet + LoRA

### 3.1 A replaceable generator behind one interface [D]

`BaseGenerator.generate(GenerationRequest) -> GenerationResult`
(`backend/generator/base.py`) has three implementations:

| Backend | What it is | Role |
|---|---|---|
| `stub` | Procedural | Graph testing, plumbing checks |
| `local` | CPU diffusion | Local development |
| `remote` | Colab T4 over HTTP | Experiments and demos |

The graph never learns which backend is running. This is a structural
argument for where the contribution lies: the generator can be swapped for a
procedural stub without the architecture noticing.

### 3.2 Why an inpainting model, and the 9-channel UNet [M/D]

The base model is `stable-diffusion-v1-5/stable-diffusion-inpainting`. Its
UNet has **859,535,364 parameters** and **`in_channels = 9`**
[M; HF model config and safetensors header]:

| Channels | Content |
|---|---|
| 4 | Noisy image latent |
| 1 | Inpainting mask, downsampled to the latent grid |
| 4 | VAE latent of the masked image (the context the model may see) |

Latent `sample_size` is 64 (512 px ÷ the VAE factor of 8). Text conditioning
is through CLIP ViT-L/14 (`cross_attention_dim` 768).

**Why inpainting [D].** The task is "keep this, change that": the surrounding
landscape must survive (rule R4) while the structure and its pool appear. An
inpainting UNet takes the mask and the masked image as inputs, so preserving
context is part of its native objective rather than a constraint bolted onto
text-to-image or image-to-image generation. Image-to-image would re-noise the
whole frame and perturb every pixel.

### 3.3 ControlNet [M/D]

`lllyasviel/control_v11p_sd15_canny`, **361,279,120 parameters**, frozen
[M]. The control image is a Canny edge map (σ = 1.6) of the baseline scene's
luminance. Conditioning scale 0.8.

**Why [D].** ControlNet holds the scene's *geometry* (field boundaries,
tracks, the channel line) in place, so the model cannot redraw the landscape
around the structure. The paper should separate three mechanisms with three
jobs:

| Mechanism | What it constrains |
|---|---|
| ControlNet | Geometry |
| LoRA | Appearance in this domain |
| Critic | Physics |

### 3.4 The LoRA, and the 12.8 MB figure [M]

| Property | Value |
|---|---|
| Rank / α | 16 / 16, Gaussian initialisation |
| Target modules | Attention projections `to_q`, `to_k`, `to_v`, `to_out.0`, in all 32 attention modules (self- and cross-attention) |
| Tensors | 256 (128 low-rank pairs) |
| Trainable parameters | **3,188,736**, which is **0.37%** of the UNet's 859.5 M |
| Stored precision | fp32 |
| Checkpoint size | **12.79 MB** |

[M; `backend/generator/weights/geocf_lora.safetensors`.]

**Why low-rank adaptation rather than full fine-tuning [D, with arithmetic].**

- **Memory.** Full fine-tuning would update 859.5 M parameters. Their fp32
  master copy and two AdamW moment buffers alone are about 10.3 GB
  (859.5 M × 12 bytes) before activations, on a shared 16 GB T4. The LoRA's
  equivalent state is about 38 MB (3.19 M × 12 bytes).
- **Checkpointing on a preemptible free tier.** Free Colab runtimes end
  without warning. Training saved a checkpoint every 250 steps, including
  optimizer and learning-rate-scheduler state; restoring weights alone
  silently restarts the cosine schedule. A 12.8 MB adapter makes that cost
  seconds. A full UNet checkpoint is about 1.7 GB in fp16 or about 3.4 GB in
  fp32, before optimizer state.
- **Where adaptation happens.** Attention projections decide *what content
  goes where*. The convolutional layers already render plausible imagery, so
  that is not what needed to change.

**The base weights are never modified.** Selecting the base model is
setting the adapter weight to 0. [M] On a UNet forward pass, adapter weight
0 equals the unloaded base model with **zero** maximum absolute difference;
re-enabling restores the fine-tuned output exactly; and the adapter moves
the output by a maximum of 0.056. This is what lets the ablation run base
and fine-tuned arms on one loaded pipeline (§6).

### 3.5 Training [M; `notebooks/geocf_lora_finetune.ipynb`]

| Setting | Value |
|---|---|
| Data | The 1,155 pairs of `data_methodology.md` §6 |
| Resolution | 512 px |
| Epochs / optimizer steps | 6 / **1,728** (1,155 ÷ 4 = 288 steps per epoch) |
| Batch | 1, gradient accumulation 4 (effective 4) |
| Optimizer | AdamW, lr 1e-4, β = (0.9, 0.999) |
| Schedule | Cosine with 100 warm-up steps |
| Gradient clip | 1.0 |
| Precision | Base weights fp16; LoRA parameters fp32 (fp16 updates underflow at lr 1e-4) |
| Augmentation | Horizontal and vertical flips only; rotation would resample patches already upsampled 4× |
| Objective | Noise-prediction MSE, mask-weighted (below) |

**Mask-weighted loss.** The per-element squared error is weighted by
`1 + 9 · mask` and normalised by the mean weight, so **latents inside the
mask count 10× as much as context**. A structure covers 0.78–3.45% of the
frame (median 1.36%). Under a plain full-latent MSE, the loss is dominated
by context the model can copy from the masked-image input, and the easiest
solution is to change nothing.

**What the model is trained to do. The paper must state this precisely.**
Each training example is the **"after" image only**, inpainted through a
**synthetic mask**: a centred ellipse with the structure's area, an aspect
ratio derived from its circularity (capped at 4:1), and a random
orientation. The "before" image is not used in training. The LoRA therefore
learns **how post-construction landscapes look inside and around a
structure-sized hole, given post-construction context**. It does not learn
an explicit before→after transformation. At inference it is given the
*before* scene as context and the planner's impoundment as the hole.

This is a standard domain-adaptation design for inpainting. Describing it as
"trained on before/after pairs" without qualification would overstate it.
`limitations.md` §4 covers the consequences.

### 3.6 Patch-based inference at the training scale [M/D]

The adapter was trained on 1,280 m windows rendered at 512 px (2.5 m/px).
Running it over a whole 4.4 km scene resized to about 448 px would be
10 m/px, **a 4× scale mismatch** with everything it learned. Inference
therefore works per window [M; `backend/generator/diffusion_local.py`,
`colab_server.py`]:

1. Windows of 1,280 m (128 px at 10 m) are centred on connected components
   of the editable mask, largest first. A component already more than 80%
   covered is skipped. At most 8 windows per scene.
2. Each window is resampled to 512 px and inpainted.
   - 20 steps, UniPC multistep scheduler
   - guidance 7.5, strength 0.85, ControlNet scale 0.8
   - seed = run seed + iteration
3. Results are resampled back to the native 10 m grid and composited **only
   inside the window's editable pixels**, using stretch bounds from the
   whole scene, so patches do not tone-shift against their surroundings.

**Inpaint the structure, not the buffer [P; recorded in
`diffusion_local.py`].** The planner's change mask is the impoundment *plus*
a riparian buffer of about 200 m. Inside a 1,280 m window that is **43.5%**
of the frame. A model trained on masks of 0.8–3.5% is out of distribution
at 43.5%, and in development it produced amorphous blobs and destroyed field
texture. Restricting diffusion to the impoundment core gives **1.1%**,
inside the training range. The buffer's vegetation response is handled by
the dynamics model's greening (§4), not by diffusion.

### 3.7 NDVI for an RGB generator [M/D]

The generator emits RGB, but rules R2 and R3 need NDVI. NDVI is predicted by
a least-squares model fitted **on each baseline scene**, where reflectance
and true NDVI are both known. The model is a 10-term quadratic in (R, G, B):
constant, linear, squared and cross terms. Its prediction is **anchored**:

    NDVI_future = NDVI_baseline + f(RGB_future) − f(RGB_baseline)

The fit's residual cancels on unchanged pixels, so a pixel the generator did
not touch keeps its *measured* NDVI exactly.

[P; `diffusion_local.py`, `_predict_ndvi`] Before anchoring, the fit's
residual read as vegetation growth: the first real run produced **45,659**
rule-R2 violations on a frame where the generator had altered only
**7,129** pixels, so the critic was rejecting untouched terrain for the
fit's error. Anchoring removes this by construction.

The procedural stub generator is anchored the same way. Its earlier,
unanchored NDVI fell on dense canopy that it greened, and was caught by the
change-based R3 (§5).

This dependency is the main limitation of R3; `limitations.md` §2
quantifies it.

### 3.8 Compute [M/P]

| Configuration | Time per 20-step 512 × 512 pass |
|---|---|
| Laptop CPU (Intel Iris Xe, fp32), weights resident | 328 s [M; `test_phase4_generator`, 2026-10-11] |
| Laptop CPU, an earlier whole-scene measurement | 509 s [P; development log, not in repository] |
| Colab NVIDIA T4 (fp16) | 5.6 s [P; development log, not in repository] |

The implied speed-up is about 59–91×, depending on which CPU figure is used.
**[N]** The two GPU/CPU figures were not measured under identical
conditions. The paper should report a fresh like-for-like timing (same
window, same steps, both devices) rather than either ratio.

The weights are loaded once per process. A fresh Colab runtime first
downloads about 5 GB of weights, so experiments call `/warmup` before the
first run.

---

## 4. Eco-hydrological dynamics: a rules engine, not a model

`backend/agents/dynamics.py` turns "N structures, Y years" into the bounds
the generator must respect. These are the same numbers the critic enforces,
so the generator is told the rules before it is judged by them.

**Recharge influence [D].** Recharge from an impoundment decays with
distance: `exp(−d / 120 m)`, cut off at 250 m. These are empirical scales
for shallow, hard-rock aquifers, not fitted (`limitations.md` §6).

Recharge is also **limited by hydraulic head**. A check dam's groundwater
mound cannot rise above the pool that feeds it. So influence is scaled from
full at or below the pool surface down to zero where the ground stands 3 m
(an assumed root-zone and capillary-fringe depth) above it. Each pool's
water level is the highest ground inside its connected impoundment, because
the impoundment fills to the crest.

[M] Before this constraint, **31.4%** of greened cells across the 15
regions sat more than 2 m above the pool feeding them, some up to 58 m up a
hillside. After it, **no greened cell is more than 3 m above its pool**, and
total greened area fell 27% (99,867 to 72,671 cells).

**Growth envelope [D].**

    ceiling = max(NDVI_baseline,
                  min(NDVI_baseline + 0.35/yr · years · rate_type · recharge · f(slope),
                      0.75))

- `rate_type` ranges from 1.00 for check dams to 0.45 for rainfed
  afforestation.
- `f(slope) = clip(1 − slope/30°, 0.2, 1)`.
- **The ceiling is never below the observed baseline.** A pixel already
  above 0.75 (irrigated canopy reaches 0.79) would otherwise violate R2
  with nothing changed. That was a real failure: 34 unfixable pixels
  exhausted the retry budget on every Anantapur run. It is now the
  null-intervention test, `backend/tests/test_null_intervention.py`.

**Other rules.**

- Growth is zeroed over existing open water.
- Growth is confined to the change mask.
- Afforestation, which creates no impoundment, uses a planting field
  instead of a recharge field.

**Conditioning tensor.** Five channels:

| Channel | Content |
|---|---|
| 1 | Luminance |
| 2 | Normalised slope |
| 3 | Change mask |
| 4 | Growth potential |
| 5 | Critic-rejected pixels |

The fifth channel is how feedback reaches a regeneration.

---

## 5. The physical-plausibility critic

Four deterministic rules [M; `backend/critic/rules.py`,
`backend/critic/physics_critic.py`]. Each returns a pass/fail, a severity in
[0, 1], a message naming the quantity and limit breached, and a
**pixel-exact mask of the offending cells**.

| Rule | Constraint | Main thresholds |
|---|---|---|
| R1 Gravity | Water the candidate *introduces* may not rest on steep ground | slope > 2.5°; water bodies ≥ 500 m² |
| R2 Growth | NDVI may not exceed the dynamics ceiling or the absolute cap | 0.35/yr; tolerance 0.02 |
| R3 Red edge | Visible greening must come with an NIR response | Δ greenness > 0.015 with NDVI < 0.15 **or** ΔNDVI ≤ 0 |
| R4 Conservation | Terrain outside the footprint must survive | Mean SSIM ≥ 0.90, outside a 3-pixel collar |

**Design properties to report [D]:**

- **Spatial feedback, not a scalar.** Offending masks are combined into one
  feedback mask that becomes conditioning channel 5 and is removed from the
  editable region on regeneration. A scalar reward can only say "worse"; the
  mask says which pixels, for which law. This is the main difference from
  reward-model or learned-judge approaches.
- **No learned component.** There is nothing to overfit and nothing to
  explain away: a violation is a fact about the raster. A language-model
  judge would add a second hallucinating component to police the first.
- **Continuous, severity-weighted score.** Weights are R1 30, R2 25, R3 25,
  R4 20, normalised by the weight of the rules actually evaluated (identical
  to `100 − penalty` with all four). There is no floor, because a floor
  compresses exactly the range the ablation needs to resolve.
- **Specific corrections, each a methods footnote:**
  - R3 compares visible greenness (G − R)/(G + R), not raw green
    reflectance. Canopy is *darker* than bright semi-arid soil in every
    visible band, so a raw-green test fires on drying, not greening.
  - Water detection requires NDWI > 0 **and** blue ≥ green. Chlorophyll
    absorbs blue, so painted vegetation, whose inferred NIR can make NDWI
    positive, is not mistaken for water.
  - R4 computes SSIM on the full frame and averages the per-pixel map over
    the outside region. The specification's call on boolean-indexed 1-D
    arrays raises. It also excludes a 3-pixel collar: SSIM's 7×7 window
    straddles the footprint boundary, which had scored an unchanged
    exterior at 0.844.
  - R1 judges only water introduced relative to the baseline. On all 15
    unchanged Sentinel-2 scenes the old form flagged 0 pixels, so this
    changes no catalogue result. It matters for scenes without NIR (§7).
  - R3 also tests change, not only level: paint on ground already above
    NDVI 0.15 passed the level-only test.

---

## 6. The ablation design

**Arms [M; `backend/experiments/run_ablation.py`].** A 2 × 2 crossing of
generator and critic mode:

| Arm | Generator | Critic |
|---|---|---|
| A Base-Shadow | SD 1.5 base | Scores, never gates |
| B Base-Gating | SD 1.5 base | Rejects and regenerates |
| C LoRA-Shadow | + LoRA | Scores, never gates |
| D LoRA-Gating | + LoRA | Rejects and regenerates |

**Shadow mode is the measuring control arm [D].** Turning the critic off
(evaluating no rules) records nothing. On a scene breaking all four rules it
reports 100%, and the control arm would have a 0% violation rate by
construction. Shadow mode evaluates every rule and records the honest
verdict, but routes to the end. Approval and gating are separate state
channels.

**Controls so the arms differ in one variable:**

- **The same framing for both generator variants.** Both run in patch mode
  at the training scale. The local backend ties patch mode to the presence
  of an adapter, so without forcing it, base runs would also change scale
  and the adapter would be credited with the effect of framing.
- **A deterministic planner.** The keyword parser is used for the ablation.
  A language model that is available for some cases and rate-limited for
  others would plan different interventions in different arms.
- **A locked seed** for the generator, numpy and torch.
- **One pipeline, adapter switched per request** (§3.4).
- **A determinism check.** Shadow and gating arms share an identical first
  pass (same seed, same inputs, iteration 0), so their first-pass scores
  must agree. The summary reports any disagreement.
- **Validity filtering.** A run is excluded if the stub replaced the
  intended generator, if the imagery was synthetic, or if the parsed
  structure differs from the requested one.

**Hypotheses [D].**

- **H1:** violation rate B < A. The loop reduces implausibility on the base
  model.
- **H2:** (A − B) ≫ (C − D). Fine-tuning absorbs most of what the loop
  enforces.
- **H3:** C > 0. The fine-tuned model still violates, so runtime
  enforcement is not redundant.

If C ≈ A, H2 is false. The fine-tune then learned appearance but not
physics, and the claim narrows to "the critic catches errors".

**[N] Results are pending.** The 120-run sweep (4 arms × 15 regions × 2
interventions) was running at the time of writing. Figures and tables come
from `backend/experiments/plot_benchmarks.py`, which reports Wilson 95%
intervals. At about 30 runs per arm the analysis is descriptive; the paper
should not imply significance testing that was not done.

---

## 7. Uploaded scenes and graceful degradation

`POST /api/upload` accepts a GeoTIFF, PNG or JPEG.

- **Normalisation.** The image is placed on the pipeline's 10 m metric
  grid. A file already at 10 m is used without resampling; otherwise it is
  warped to the local UTM zone, area-averaged when coarsening.
- **Terrain.** Copernicus terrain is fetched and warped onto the upload's
  grid. [M] Fetched on a catalogue region's own grid, it reproduces that
  region's terrain with a median absolute difference of 0.000 m. [M] A
  region exported as a GeoTIFF and uploaded produces a bit-identical run.
- **No NIR band.** Rules R2 and R3 need NIR and are reported as **not
  evaluated**, not as passed. NDVI is replaced by a labelled visible-band
  proxy (the Green Leaf Index; Louhaichi et al. 2001), and water detection
  falls back to a visible-band test.

The principle is the same as the critic's: a rule that did not run is not
evidence that the scene obeys it.

---

## References to cite (verify bibliographic details before submission)

- Rombach, R. et al. (2022). High-resolution image synthesis with latent
  diffusion models. *CVPR*.
- Zhang, L., Rao, A., Agrawala, M. (2023). Adding conditional control to
  text-to-image diffusion models (ControlNet). *ICCV*.
- Hu, E. J. et al. (2022). LoRA: Low-rank adaptation of large language
  models. *ICLR*.
- Radford, A. et al. (2021). Learning transferable visual models from
  natural language supervision (CLIP). *ICML*.
- Barnes, R., Lehman, C., Mulla, D. (2014). Priority-flood: an optimal
  depression-filling and watershed-labeling algorithm for digital elevation
  models. *Computers & Geosciences*.
- O'Callaghan, J. F., Mark, D. M. (1984). The extraction of drainage
  networks from digital elevation data. *CVGIP*.
- Wang, Z. et al. (2004). Image quality assessment: from error visibility to
  structural similarity (SSIM). *IEEE TIP*.
- Canny, J. (1986). A computational approach to edge detection. *IEEE
  TPAMI*.
- Wilson, E. B. (1927). Probable inference, the law of succession, and
  statistical inference. *JASA*.
- Louhaichi, M., Borman, M. M., Johnson, D. E. (2001). Spatially located
  platform and aerial photography for documentation of grazing impacts on
  wheat. *Geocarto International* (GLI).
- LangGraph (LangChain, Inc.), software; cite the version used.
