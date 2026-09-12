# GeoCounterfactual — Onboarding Doc

**Last updated:** July 29, 2026
**Maintainers:** Naren (student). Project guide/supervisor: female faculty member (name not mentioned). Teammate(s) referenced but unnamed ("we", "our team").
**Timeline:** Final-year project. Originally framed as a 6-month project; timelines were subsequently drafted for 4-month, 2-month, and (interim) 4-month versions on request. The **2-month (8-week) plan is the most recent stated timeline** (see Section 8).

---

## 1. Project Overview

**One-line summary**
Several AI agents work together to *generate* a satellite image of the future — showing what a piece of land will look like years after an environmental intervention (e.g., building check-dams or planting a forest) — so planners can literally *see* the outcome before spending money. It is not analysis or a recommendation; the system generates a new image, and a critic agent ensures that image is physically believable.

**Problem statement (full version for the guide)**
Environmental and rural-development interventions in India — watershed treatment, check-dam construction for groundwater recharge, afforestation, soil-and-water conservation under schemes like MGNREGA — are approved and funded *without any way to visualize their likely outcome*. Officials rely on text reports and intuition. There is no tool that lets a decision-maker look at a region today and see a credible picture of that same region several years after a proposed intervention.

The problem is twofold:
1. There is no *visual* counterfactual tool for land interventions (existing AI classifies land or predicts a number like "NDVI will rise 0.2," but a number doesn't communicate to a village council or funding committee).
2. Naive generation is physically untrustworthy — a single generative model asked to "imagine the future" would hallucinate (e.g., grow a forest where the soil can't support one).

The system solves both using **multiple cooperating agents plus a physics critic** to generate a future satellite image that is both realistic *and* constrained to be physically plausible.

**Goal / success criteria**
- Produce a working multi-agent generative pipeline that outputs a plausible future satellite image conditioned on a current image + a proposed intervention.
- Demonstrate a *measurable* benefit from the critic loop (plausibility-violation rate with critic on vs. off) — this is the headline research result.
- Validate credibly on *past* interventions where the "future" already happened (objective metrics: SSIM, spectral fidelity, NDVI error).
- Deliver a working end-to-end demo on at least one example for the jury.
- Produce a conference paper draft + final report + jury presentation.

**Target users / audience**
- End users (the social-cause framing): government bodies, NGOs, panchayats, forest departments, and rural-development planners who approve land interventions and currently do so blind.
- Immediate audience: the final-year **jury/review panel** and the **project guide**.
- Secondary audience: a **conference** (paper submission).

---

## 2. Scope

**In scope**
- One intervention type only (watershed/afforestation — e.g., check-dams for groundwater recharge OR afforestation).
- One region / agro-climatic zone (single-region proof-of-concept).
- The five-agent generative pipeline with a critic feedback (reject → regenerate) loop.
- Conditioned generative model (pretrained diffusion + ControlNet-style conditioning; light fine-tuning).
- Evaluation on historical (past) interventions.
- A Streamlit/Gradio demo with before/after comparison.
- The critic-on vs. critic-off experiment.

**Out of scope / explicitly rejected**
- **Commercial problem statements** — rejected by the guide (she does not like commercial framing; wants a social cause / public-good problem). This killed the original idea (agentic workflows in customer service / customer experience).
- **"Easy" project types** — CRM, ERP, management software explicitly ruled out (not novel/complex enough).
- **First batch of ideas rejected by Naren** — the earlier "domain" ideas (water/groundwater advisories, med-tech triage, agriculture advisory, accessibility, disaster/civic, etc.) were rejected as *not truly novel*. His critique: they all reduce to the same pattern — (a) pull live/dataset info, (b) analyze input to give recommendations, (c) set up alerts/guardrails. He considers these "feel-good additions," not real problems, and not "first-ever" implementations.
- **Decision-making systems** — deliberately avoided in favor of *generation*. Reason: a system that "gives a decision" invites the panel critique "how is this different from what ChatGPT/Claude could do?" Generation is more defensible as a novelty aspect.
- **Training a diffusion model from scratch** — cut in the compressed (2-month) plan in favor of a pretrained model + light fine-tuning, to save ~3 weeks. Academically costless because the novelty is the agent+critic loop, not the diffusion weights.
- The other two candidate projects (Cloud-obscured reconstruction; Agentic map generation) were considered and set aside in favor of Idea 1.

**Stretch goals**
- Historical-Analog agent (6th agent) that retrieves real before/after pairs from past interventions to ground generation.
- Two-scenario side-by-side generation (e.g., minimal vs. aggressive intervention).
- GeoTIFF export of the generated future scene.
- Change summary panel (projected NDVI / water-area deltas).
- Polished UI.

---

## 3. Methodology / Approach

**Overall approach**
A "society of specialized agents" that negotiate and critique each other to generate a physical artifact (a future satellite image), where a single generative model alone would hallucinate and can't self-correct. The defining structure is a **closed feedback loop**: specialist agents contribute different evidence, a critic agent physically validates the output and rejects/forces regeneration until the artifact is consistent.

**Key methodology / algorithms / frameworks decided on**
- Latent diffusion model (Stable Diffusion / diffusion backbone) with **ControlNet-style conditioning** so generation respects the current image + change map rather than inventing freely.
- Multi-agent orchestration with a **cyclic** graph (critic → generator regeneration loop), favoring **LangGraph** (handles cyclic graphs; CrewAI / AutoGen named as alternatives).
- LLM-driven reasoning agents for planning/interpretation steps (open-weight like Llama, or an API).
- Physics-based validation using NDVI / soil-moisture computed from spectral bands.

**Why this approach over alternatives we discussed**
- **Generation over decision/recommendation:** chosen specifically to defend novelty against the "ChatGPT could do this" critique. A generated, georeferenced image artifact is not something a chatbot produces.
- **Multi-agent + critic over a single model:** a lone diffusion model produces one unverifiable, hallucination-prone guess; the critic + dynamics agents keep generation physically honest, and the difference is *measurable* (the headline metric).
- **Idea 1 (counterfactual intervention imagery) over Ideas 2 and 3:** highest novelty and best jury "wow," strong social angle, tangible artifact. (Idea 2 = safest metrics paper; Idea 3 = cleanest social story/tangible map artifact — both set aside.)
- **Pretrained + light fine-tune over from-scratch training (2-month plan):** saves ~3 weeks, novelty unaffected.

---

## 4. System Architecture

**High-level architecture description**
Five agents in an assembly line with a feedback loop (plus an optional sixth):
1. **Input Handler** — takes the current satellite image + the user's proposed intervention (plain language, e.g., "build check-dams along this stream, afforest these 200 hectares").
2. **Intervention-Planner agent** — translates the intervention into a spatial "change map": where water pools, where vegetation appears, which pixels are affected.
3. **Eco-Hydrological Dynamics agent** — the domain-knowledge brain; encodes how land evolves over years (NDVI growth, check-dam → soil moisture & water-body extent, realistic rates of change). Turns "add forest" into "here's how forest realistically fills in over 5 years."
4. **Generator agent** — the trained/fine-tuned diffusion model; conditioned on current image + change map + dynamics guidance, synthesizes the future scene.
5. **Physical-Plausibility Critic agent** — inspects output against hard constraints (NDVI can't jump beyond a natural rate; water can't sit on a slope; spectral signatures must be valid for real land cover; unchanged areas must stay consistent). On failure, sends feedback → Generator regenerates. **This loop is the heart of the project.**
6. *(Optional/stretch)* **Historical-Analog agent** — retrieves real before/after pairs from similar past interventions to ground generation.

**Tech stack table**

| Layer | Choice |
|---|---|
| Frontend / Demo | Streamlit or Gradio web app (map input, generate button, visible agent-loop progress, before/after slider, plausibility score) |
| Backend / Orchestration | LangGraph (preferred, cyclic graphs) — alternatives CrewAI / AutoGen; Python |
| Database / Storage | [not yet discussed — no explicit database chosen; imagery handled as files/GeoTIFF] |
| Models / AI | Latent diffusion model (Stable Diffusion / diffusion backbone) + ControlNet-style conditioning; LLM for reasoning agents (open-weight e.g. Llama, or API); PyTorch |
| Geospatial / Physics | rasterio, GDAL, GeoPandas; NDVI / soil-moisture computation from spectral bands |
| Data access | Google Earth Engine; Copernicus / Sentinel Hub APIs; ISRO Bhuvan |
| Hosting | [not yet discussed] |
| Compute | GPU available; team can train/fine-tune models (stated capability) |

**Data flow description**
Current satellite image + plain-language intervention → Input Handler → Intervention-Planner produces change map → Eco-Hydrological Dynamics adds realistic evolution guidance → Generator (diffusion + ControlNet conditioning) synthesizes future image → Physical-Plausibility Critic validates → (if fail) feedback loops back to Generator to regenerate; (if pass) output future scene → demo renders before/after slider + plausibility score + change deltas.

---

## 5. Models / Algorithms

**Latent diffusion model (Generator)**
- *Purpose:* synthesize the future satellite scene conditioned on the current image + change map + dynamics guidance.
- *Why chosen over alternatives:* diffusion is state-of-the-art for image generation; ControlNet-style conditioning keeps it faithful to the input layout instead of freely inventing. In the 2-month plan, a **pretrained** model + light fine-tuning is chosen over training from scratch to save time (novelty lies elsewhere).
- *Input:* current satellite image + change map (+ dynamics guidance).
- *Output:* generated future satellite image (georeferenced; GeoTIFF/PNG as stretch export).
- *Limitations/risks:* generation quality bounded by training data → project scoped to a specific intervention type + region as a proof-of-concept; training the generator (weeks 5–8 in 4-month plan / weeks 3–4 in 2-month plan) is the riskiest deliverable and most likely to slip; naive/unconstrained generation hallucinates (mitigated by the critic).

**ControlNet-style conditioning**
- *Purpose:* force the generator to respect the current image and the change-map layout.
- *Why:* prevents free-form hallucination; makes generation spatially controllable.
- *Input/Output:* conditioning maps (current image + change map) → constrained generation.

**LLM-driven reasoning agents (Intervention-Planner, Eco-Hydrological Dynamics)**
- *Purpose:* interpret the plain-language intervention and produce the change map + realistic evolution guidance.
- *Why chosen:* language understanding + domain reasoning to bridge "human intent → spatial/physical spec."
- *Input/Output:* text intervention → structured change map + dynamics guidance.
- *Options:* open-weight (e.g., Llama) or API.

**Physical-Plausibility Critic (algorithmic + rule-based checks)**
- *Purpose:* validate generated output against physical constraints; reject and trigger regeneration.
- *Why chosen:* the core research contribution and the defense against "a single model could do this"; a monolithic model cannot enforce this self-correction.
- *Checks:* NDVI rate limits; no water on slopes; valid spectral signatures for real land cover; unchanged-area consistency.
- *Input/Output:* generated image → pass/fail + feedback for regeneration.

**Baseline model**
- *Purpose:* a naive single-model (image-to-image / single diffusion, no agents) to benchmark against and to lock evaluation metrics early.
- *Metrics:* SSIM, spectral fidelity, NDVI error.

---

## 6. Key Decisions Log

| Decision | Reasoning | Alternatives considered |
|---|---|---|
| Project must be a social cause / public good, not commercial | Guide dislikes commercial problem statements; social projects perform well with the jury | Original commercial idea: agentic workflows in customer service / customer experience (rejected) |
| Project must be novel + complex, not "easy" | Guide wants novelty and complexity; enables a potential conference paper | CRM / ERP / management software (explicitly ruled out as too easy) |
| Reject the first batch of "domain" ideas | Naren judged them not truly novel — all reduce to fetch-data → analyze → recommend/alert; "feel-good," not real "first-ever" problems | Water/groundwater advisories, med-tech triage, agriculture advisory, accessibility, disaster/civic, etc. |
| Use satellite imagery as the input substrate | Naren's explicit steer; strong social + technical framing | Other data sources (sensor streams, text, etc.) from earlier ideas |
| Favor *generation* over *decision-making* | A decision system invites "how is this different from ChatGPT/Claude?"; generation is its own novelty aspect and harder to dismiss | Decision/recommendation/analysis systems |
| Require multiple agents working together | Naren's explicit requirement; core to novelty and the "not a single model" defense | Single-model approaches |
| Choose Idea 1 (Counterfactual Intervention Imagery) | Highest novelty, best jury "wow," strong social angle, tangible artifact; feasible in the window | Idea 2 (Cloud-obscured reconstruction — safest metrics paper); Idea 3 (Agentic map generation — cleanest social story) |
| Adopt a multi-agent + critic-loop architecture | Single generative model hallucinates and can't self-correct; a critic that rejects/regenerates keeps output physically honest and yields a measurable result | Single diffusion/GAN model |
| Validate on *past* interventions | Cannot get ground truth for a hypothetical future; using historical interventions where the future already happened gives objective metrics and answers "how do you know it's right?" | (No workable alternative for hypothetical futures) |
| Lock evaluation metrics early via a naive baseline | Gives every later step a number to beat; keeps evaluation objective | — |
| Use ControlNet-style conditioning | Keeps generation faithful to current image + change map; prevents free hallucination | Unconditioned generation |
| Prefer LangGraph for orchestration | Handles cyclic graphs — exactly what the critic→generator regeneration loop needs | CrewAI, AutoGen |
| Scope to one intervention type + one region | Generation quality bounded by training data; proof-of-concept framing is a strength, not a weakness | Claiming general/everywhere capability |
| (2-month plan) Use pretrained diffusion + light fine-tune, not from-scratch training | Saves ~3 weeks; novelty is the agent+critic loop, not the diffusion weights — so academically costless | Training a diffusion model from scratch |
| Timeline compression on request | User requested progressively shorter plans | 6-month (original) → 4-month → 2-month (latest); a 4-month plan was also drafted |
| Protect three deliverables if behind (in order): critic-on/off result, working end-to-end demo on one example, evaluation on past interventions | These are, respectively, the paper, the jury demo, and the credibility | Cutting: multiple scenarios, GeoTIFF export, extra agents (Historical-Analog), polished UI |
| Fall back to stronger pretrained model if generator training struggles by ~week 7 (4-month) / weeks 3–4 (2-month) | De-risks the schedule; novelty unaffected | Persisting with from-scratch training |

---

## 7. Open Questions / Unresolved Issues

- **Novelty verification not yet done.** Claude repeatedly recommended a literature check to confirm the "first-ever" / novelty claim holds before committing; this has NOT been run yet. Flagged as strongly recommended.
- **Exact intervention type not finalized** — check-dams (groundwater recharge) vs. afforestation vs. general watershed treatment; scope says "pick one" but the specific one is not locked.
- **Exact region / agro-climatic zone** not chosen.
- **Which LLM** for the reasoning agents (open-weight like Llama vs. API) — not finalized.
- **Diffusion backbone specifics** (which pretrained model) — not finalized.
- **Database / storage layer and hosting** — not discussed.
- **Team size and named members** — not specified beyond Naren.
- **Guide's name** — not mentioned.
- **Target conference** — venues suggested (IGARSS, ACM SIGSPATIAL, EarthVision/CVPR workshop, AI-for-social-good), but none chosen.
- **Which timeline is final** — 6-month, 4-month, and 2-month plans all exist; the operative one is not explicitly confirmed (2-month is most recent).

---

## 8. Milestones & Timeline

Multiple timelines were produced on request. The **2-month (8-week) plan is the most recent**. The 4-month plan is retained below for reference. (A 6-month framing was the original context.)

### 2-Month (8-Week) Plan — MOST RECENT
Strategic cut up front: use a pretrained diffusion model + light fine-tuning (no from-scratch training).

- **Weeks 1–2 — Setup, data, baseline:** lock scope to one intervention type + one small region; quick literature check; GPU env + repo; pull Sentinel-2 via Google Earth Engine + compute NDVI; assemble small set of past interventions with real before/after pairs; stand up naive single-model baseline; lock metrics (SSIM, spectral fidelity, NDVI error). *Milestone: data ready, baseline running, metrics defined.*
- **Weeks 3–4 — Generative core (pretrained):** get pretrained latent diffusion generating satellite-style scenes; add ControlNet-style conditioning on current image + change map; light fine-tune on intervention pairs; evaluate vs. baseline. *Milestone: conditioned generator that beats baseline (riskiest part).*
- **Weeks 5–6 — Agents & critic loop (core contribution):** wire pipeline in LangGraph (Intervention-Planner + Eco-Hydrological Dynamics agents); build Physical-Plausibility Critic; close reject→regenerate loop; run critic-on vs. critic-off experiment (headline result). *Milestone: full multi-agent loop end-to-end with measurable critic benefit.*
- **Weeks 7–8 — Demo, evaluation, writeup:** Gradio/Streamlit demo (map input, generate, visible agent-loop progress, before/after slider, plausibility score; two-scenario if time); final evaluation on held-out interventions; figures/tables; freeze code; write paper + report; prep jury demo. *Milestone: working demo + evaluation + paper draft + presentation.*

### 4-Month (16-Week) Plan — reference
- **Month 1 — Foundations & data (W1–4):** W1 literature check + scope + tooling; W2 data pipeline (Sentinel-2 via GEE, NDVI/soil-moisture, cloud filter, co-registration); W3 assemble past-intervention before/after set; W4 dumb baseline + lock metrics. *Milestone: clean dataset + baseline + metrics.*
- **Month 2 — Generative core (W5–8):** W5–6 fine-tune diffusion on satellite imagery; W7 add ControlNet conditioning; W8 evaluate vs. baseline on historical test set. *Milestone: conditioned generator beats baseline (riskiest deliverable, target by week 8).*
- **Month 3 — Agents & critic loop (W9–12):** W9 LangGraph orchestration + Planner & Dynamics agents; W10 build critic; W11 close the loop (full week); W12 critic-on vs. critic-off experiment. *Milestone: full pipeline with measurable critic benefit.*
- **Month 4 — Demo, evaluation, writeup (W13–16):** W13 demo; W14 polish (two-scenario, change summary, GeoTIFF export); W15 full evaluation + figures + freeze code; W16 paper + report + jury prep + buffer. *Milestone: demo + evaluation + paper draft + presentation.*

**Schedule-protection notes (both plans):** generator training is where projects slip — if it's fighting the team by ~week 7 (4-mo) / weeks 3–4 (2-mo), fall back to a stronger pretrained model with light fine-tuning. Keep the critic-on/off experiment sacred — even a rough demo is fine if that result exists.

**Original context:** 6-month final-year project.

---

## 9. Roles & Responsibilities

[not yet discussed] — Work division among team members was not specified. Only Naren is named as a participant; a project guide (unnamed) supervises and reviews. A jury/review panel evaluates the final project.

---

## 10. Resources & References

**Data sources**
- Sentinel-2 (10 m optical, primary workhorse) — via Google Earth Engine / Copernicus (free)
- Landsat (longer time series) — via Google Earth Engine / Copernicus (free)
- Sentinel-1 (SAR) — referenced for Idea 2 (not the chosen project)
- ISRO Bhuvan (Indian context)
- MGNREGA watershed & afforestation project records; state watershed-mission data (locations of real past interventions → before/after imagery)
- NDVI / soil-moisture products (derived from satellite bands)

**Tools / frameworks**
- Google Earth Engine; Copernicus / Sentinel Hub APIs
- LangGraph (preferred); CrewAI; AutoGen
- PyTorch; Stable Diffusion / diffusion backbone; ControlNet
- rasterio, GDAL, GeoPandas
- Streamlit / Gradio
- LLMs: Llama (open-weight) or API

**Benchmarks referenced (for the other, non-chosen ideas)**
- SEN12MS-CR (cloud removal — Idea 2)
- SpaceNet (building/road extraction — Idea 3)
- OpenStreetMap / Humanitarian OpenStreetMap Team (Idea 3)

**Suggested conference venues (none chosen)**
- IGARSS; ACM SIGSPATIAL; EarthVision (CVPR workshop); AI-for-social-good workshops; Remote Sensing journals

**Papers/links:** [not yet discussed] — no specific papers or repository links were cited; a literature review is still pending.

---

## 11. Glossary

- **GeoCounterfactual** — the working project name/title; the multi-agent generative framework for visualizing land-intervention outcomes from satellite imagery.
- **Counterfactual (imagery)** — a generated image showing a "what-if" future state of a region under a hypothetical intervention, rather than an observed image.
- **Land intervention** — an environmental/rural-development action on land: e.g., check-dam construction, afforestation, watershed treatment, soil-and-water conservation.
- **Check-dam** — a small dam built to slow water flow and recharge groundwater.
- **Afforestation** — establishing forest/tree cover on land.
- **MGNREGA** — Mahatma Gandhi National Rural Employment Guarantee Act; an Indian scheme under which watershed and afforestation works are carried out (source of real past-intervention records).
- **NDVI** — Normalized Difference Vegetation Index; a satellite-derived measure of vegetation health/greenness, computed from spectral bands. Used by the critic to bound plausible vegetation change.
- **Change map** — a spatial map of which pixels/areas change and how, produced by the Intervention-Planner agent from the plain-language intervention.
- **Critic loop / reject→regenerate loop** — the closed feedback cycle where the Physical-Plausibility Critic rejects an implausible generated image and forces the Generator to regenerate; the project's core contribution.
- **Physical-Plausibility Critic** — the agent that validates generated output against physical constraints (NDVI rate limits, no water on slopes, valid spectral signatures, unchanged-area consistency).
- **Eco-Hydrological Dynamics agent** — the domain-knowledge agent encoding how land/water/vegetation realistically evolve over years.
- **Historical-Analog agent** — optional agent retrieving real before/after pairs from similar past interventions to ground generation.
- **Diffusion model / latent diffusion** — a generative image model; here fine-tuned to synthesize satellite scenes.
- **ControlNet** — a conditioning method that constrains a diffusion model to respect an input layout (here, the current image + change map).
- **LangGraph** — an agent-orchestration framework supporting cyclic graphs (needed for the critic→generator loop). Alternatives: CrewAI, AutoGen.
- **SAR** — Synthetic Aperture Radar (e.g., Sentinel-1); can see through cloud (relevant to a non-chosen idea).
- **SSIM** — Structural Similarity Index; an image-similarity metric used for evaluation.
- **Spectral fidelity** — how faithfully generated pixel spectra match real land-cover spectra; an evaluation criterion and a critic check.
- **Sentinel-2 / Sentinel-1 / Landsat** — Earth-observation satellites providing the imagery.
- **ISRO Bhuvan** — India's geospatial data/imagery platform.
- **Google Earth Engine (GEE)** — cloud platform for accessing/processing satellite imagery.
- **Critic-on vs. critic-off experiment** — the headline evaluation comparing plausibility-violation rate with the critic loop enabled vs. disabled.
