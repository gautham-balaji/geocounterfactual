# Limitations

Supplementary material for the GeoCounterfactual paper: known constraints,
their measured size where we have it, and what would remove them.

## How to read this document

Provenance tags (as in `data_methodology.md`):

- **[M]** Measured in this repository; the source is given.
- **[D]** A consequence of a design decision.
- **[P]** Recorded in code during development, not regenerated here.
- **[N]** Not yet measured.

Paths are relative to the repository root. Figures were verified on
2026-10-11.

---

## 1. Rule R4 cannot fail on the diffusion backends (composite masking)

**What happens [M].** Both diffusion backends write generated pixels into
the output **only inside the editable mask**. In patch mode, `generated =
base_rgb.copy()`, and only the window's editable pixels are replaced. In
whole-scene mode an explicit hard composite does the same
(`composite_unchanged=True`). Every pixel outside the footprint is
therefore **byte-identical** to the baseline. The CPU generator test
measures **0 pixels altered outside the mask** (`test_phase4_generator`,
2026-10-11).

**Consequence [D].** R4 asks whether terrain outside the intervention
survived. On these backends the answer is yes by construction. Outside-mask
SSIM is about 1.0 apart from the 3-pixel collar R4 already excludes, and R4
cannot fail. It is a **regression guard on mask handling**, not a
measurement of how well the model conserves its surroundings.

**What the paper must not do.** Report R4's pass rate as evidence that the
fine-tuned model preserves context, or count R4 toward a "four rules
satisfied" claim for diffusion output without this qualification. In the
ablation, R4 failures are expected only where the stub generator runs.

**Why composite at all [D].** The VAE round trip that every latent-diffusion
edit passes through perturbs every pixel it encodes. Without compositing, R4
would fail across the whole frame for a reason unrelated to the semantic
edit. Compositing keeps R4 from penalising the autoencoder, at the cost of
not measuring the model.

**What would make R4 informative [N].** Run an arm with compositing off and
report outside-mask SSIM against a VAE-only round trip of the unedited
scene. The difference isolates drift caused by the model.

---

## 2. Rules R3 and R2 judge an NDVI predicted from RGB

**What happens [M].** The generator produces RGB, but R2 (growth) and R3
(red edge) need NDVI. NDVI for a generated scene is predicted by a
quadratic least-squares model, f(R, G, B) with 10 terms, fitted on each
baseline scene, and anchored:

    NDVI_future = NDVI_baseline + f(RGB_future) − f(RGB_baseline)

(`backend/generator/diffusion_local.py`, `_fit_ndvi_model` and
`_predict_ndvi`; mirrored in `colab_server.py`). R1 likewise recovers NIR
algebraically from red and this NDVI to compute NDWI.

**How much information that leaves [M].** On the 15 baseline scenes,
RGB explains this share of NDVI variance:

| Statistic | R² | Region |
|---|---|---|
| Median | **0.716** | — |
| Minimum | 0.276 | Jalna |
| Maximum | 0.912 | Chitradurga |

Fit RMSE ranges from 0.018 to 0.073 NDVI. A median of about 28% of NDVI's
variance, more in some regions, is **NIR-specific information an RGB
generator cannot represent**. That is exactly the information the red-edge
test exists to examine.

**Consequences [D].**

1. **R3 is partially circular.** It compares visible greening with an NDVI
   change that is itself a function of the same RGB. It catches greening
   whose colour this scene's RGB–NDVI relationship does not associate with
   vegetation: out-of-distribution greens, or paint that lowers fitted NDVI.
   **It cannot catch a hallucination with realistic RGB statistics**,
   because f assigns such pixels a realistic NDVI. Stated plainly, R3
   verifies that a generated greening is *spectrally consistent with this
   scene's vegetation in RGB*, not that a red edge exists.
2. **R2 has an uncertainty comparable to its tolerance.** Anchoring cancels
   the fit's error on unchanged pixels exactly, so untouched terrain keeps
   its measured NDVI. On changed pixels the error in the *difference*
   remains, and the fit's RMSE (0.018–0.073) is mostly larger than R2's 0.02
   tolerance. R2 verdicts on generated canopy therefore carry fit
   uncertainty.
3. **The critic is not vacuous.** The change-based R3 detected an internally
   inconsistent generator: the procedural stub's unanchored NDVI fell on
   canopy it greened, which blocked convergence in 9 of 15 regions until
   fixed. R3 discriminates; it is **weaker than a multispectral test**, not
   empty.

**What would remove it [N].**

- Fine-tune a 4-channel generator that emits NIR (B8) alongside RGB, so
  NDVI is generated rather than inferred.
- Or train an RGB→NIR predictor on real Sentinel-2 pairs held out from
  generation, and report its error.
- Either way, also evaluate R3 on held-out *real* after-images, where true
  NIR exists.

---

## 3. Visual softness: 10 m information, upsampled 4×

**The resolution chain [M].**

| Stage | Training (`notebooks/geocf_lora_finetune.ipynb`, `extract_pairs.py`) | Inference (`diffusion_local.py`, `colab_server.py`) |
|---|---|---|
| Source | Sentinel-2, 10 m; window ≈ 129–130 px for 1,280 m | Same, 128 px window |
| To model resolution | Percentile-stretched to 8-bit, **Lanczos** to 512 px | Same per-window 2–98% stretch, decoded with the same bounds; **bilinear** to 512 px |
| ControlNet hint | — | Canny on the **native 128 px** conditioning luminance, **nearest-neighbour** to 512 px |
| Back to the scene | — | Output **bilinear** to 128 px, composited at 10 m |

**Consequences [D].**

1. **There is no sub-10 m information to recover.** The model works at a
   nominal 2.5 m/px, but its input is a 4× interpolation of 10 m data. It
   can only invent finer texture, and that texture is averaged away when
   the output is resampled back to the 10 m grid.
2. **Outputs are soft at the level of the structure.** A 1 ha impoundment
   is about 100 pixels; the dam wall itself (a few metres of masonry) is
   never resolved, and pool boundaries are smooth. This is Sentinel-2's
   information limit, not a model failure. The alternative framing, a wider
   window at native scale, makes the structure too small a fraction of the
   frame to learn (`data_methodology.md` §6.3).
3. **Two smaller train–inference mismatches.**
   - The resampling kernel differs: Lanczos in training, bilinear at
     inference, so the model sees slightly smoother inputs than it was
     trained on.
   - The ControlNet hint is blocky: edges are extracted at 10 m and
     upsampled with nearest-neighbour, so its edges have 4-pixel steps at
     model resolution.

   Neither has been measured for its effect on output quality [N].

**What the paper should say.** Present outputs as 10 m products. Do not
describe structure-level detail finer than about two pixels (20 m).
Visualisations upsampled for display should be labelled as such.

---

## 4. What the fine-tuned adapter learned

**Training design [M; `notebooks/geocf_lora_finetune.ipynb`,
`PairDataset`].**

- Each example is the **after** image only. The before image is never used.
- The inpainting mask is **synthetic**: a centred ellipse with the
  structure's area, an aspect ratio from its circularity, **capped at
  4:1**, and a **random orientation**.

**Consequences [D/M].**

1. **No before→after mapping is learned.** The adapter learns how
   post-construction landscapes look inside and around a structure-sized
   hole, given post-construction context. At inference it is conditioned on
   *before* context. Whether a model trained on (before → after) pairs would
   do better is untested [N].
2. **Mask shape does not match inference.** 79% of training structures have
   circularity below 0.25; they are elongated channel impoundments (median
   circularity 0.159). Their ellipses hit the 4:1 cap and are randomly
   rotated, so the hole does not follow the real channel. At inference the
   hole is the planner's impoundment, which *does* follow the channel.
   Coverage matches (training 0.78–3.45%, median 1.36%; inference core
   about 1.1%); shape and orientation do not.
3. **Training images are display renders.** They are 8-bit
   percentile-stretched images, not reflectance. A per-patch stretch makes
   the brightness scale differ between patches, which the model must
   absorb.

---

## 5. Data and ground truth

- **Structures are detections, not verified records.** MGNREGA asset
  records were inaccessible (`data_methodology.md` §4). Training and
  held-out sets consist of persistent post-monsoon water bodies that pass
  morphological and terrain filters. Other persistent small water bodies
  that pass the same filters (for example excavated pits or farm ponds
  outside the scheme) cannot be distinguished; precision against ground
  truth is unknown [N].
- **The rainfall tier is a district property.** CHIRPS (about 5.5 km) is
  coarser than the structures, so tiers separate districts and rainfall
  regimes as much as evidential strength (`data_methodology.md` §5.4).
  Bellary, Kurnool and Sagar contribute no training pairs; Kolar contributes
  33%.
- **Coverage.** Candidate detection ran in 12 of 15 regions; Bundelkhand,
  Jhansi and Pali have none.
- **One baseline window.** Each region's scene is a median of January–June
  2019. Seasonal state at the baseline (pre-monsoon dryness) is fixed, and
  the counterfactual represents a single horizon rather than a seasonal
  cycle.
- **Rainfall window.** The monsoon total is 1 June–29 September; the Earth
  Engine end date is exclusive, so 30 September is omitted. The effect is
  negligible, but it is not the conventional June–September total.

---

## 6. Physical model: parameters set by reasoning, not calibration

Every parameter below is set from domain reasoning and is **not fitted to
observations**. No sensitivity analysis has been run [N]. The paper should
present them as stated assumptions, ideally with a one-at-a-time
sensitivity sweep.

| Parameter | Value | Where |
|---|---|---|
| Water may rest on slopes up to | 2.5° | R1, planner, detection |
| Minimum water body | 500 m² | R1 |
| Absolute NDVI growth cap | 0.35 per year | R2, dynamics |
| Semi-arid canopy saturation | NDVI 0.75 | dynamics |
| Recharge decay / cutoff | 120 m / 250 m | dynamics |
| Root zone above pool surface | 3 m | dynamics |
| Growth rate by structure type | 1.00 (check dam) to 0.45 (afforestation) | dynamics |
| Slope attenuation of growth | 1 − slope/30°, floored at 0.2 | dynamics |
| SSIM floor outside footprint | 0.90 | R4 |
| Critic weights | R1 30 / R2 25 / R3 25 / R4 20 | critic score |

**Terrain.** Slope is computed on the 30 m Copernicus DEM, so R1 cannot see
steep features narrower than about 30 m. Impoundments are approximated as
the connected, channelised ground below the crest elevation. There is no
hydrological simulation: no evaporation, seepage, or storage dynamics, and
no rainfall scenario. Recharge is a static spatial envelope, not a
groundwater model.

---

## 7. Evaluation

- **[N] No historical validation yet.** The held-out `strong` tier has not
  been evaluated against observed outcomes (SSIM, spectral fidelity, NDVI
  error). The paper must not report it until it is.
- **The ablation is descriptive.**
  - About 30 runs per arm, a single seed, Wilson 95% intervals. No
    significance tests.
  - Shadow and gating arms share a first pass, so they are paired, not
    independent samples. Paired tests (e.g. McNemar on first-pass versus
    final verdicts) would be the right next step.
- **No perceptual study.** Plausibility is defined by the four rules.
  Whether the critic's verdicts agree with expert human judgement is
  untested [N].
- **Numerical precision differs between backends.** The T4 runs fp16; the
  CPU runs fp32. Results are reproducible within a backend; all ablation
  arms use one backend.
- **The ablation uses the keyword planner.** This keeps arms comparable.
  The language-model planner's effect on outcomes is not part of the
  ablation.

---

## 8. Uploaded scenes

- **RGB-only uploads are judged on R1 and R4.** R2 and R3 are reported as
  not evaluated.
- **The NDVI layer for RGB scenes is a visible-band proxy (GLI)** with a
  different scale and no red edge. It is labelled as a proxy in the
  interface and the API.
- **Visible-band water detection is conservative.** It misses turbid,
  green-dominant water. Terrain shadow is its main false positive, which R1
  neutralises by judging only water introduced relative to the baseline
  (13,838 shadow pixels on one RGB test scene would otherwise have been
  flagged [M; `backend/tests/test_upload.py`]).
- **8-bit uploads are display brightness, not reflectance.** Ratio-based
  tests still work, but absolute thresholds are not calibrated for them.
- **No synthetic terrain fallback.** Uploads without an elevation band need
  Earth Engine; uploads are refused rather than given invented terrain.
