/**
 * Backend client with graceful degradation to mock data.
 *
 * The demo has to survive the backend being down -- during a jury
 * presentation, on a laptop with no Earth Engine credentials, or when the
 * Colab tunnel has expired. Every call therefore resolves to a payload of
 * the same shape; `source` says whether it came from the pipeline or from
 * mockData.js, so the UI can label it honestly rather than silently
 * presenting fabricated numbers as real ones.
 */

import { MOCK_REGIONS } from '../data/mockData';

// Relative by default so Vite's proxy handles it (no CORS preflight).
// Override with VITE_API_BASE to point at a backend on another host.
const API_BASE = import.meta.env?.VITE_API_BASE ?? '';

// GEE in restricted mode answers the liveness probe in 1.5-3.4 s, so a
// 2.5 s budget aborted the first poll on every page load and the UI fell
// back to mock data against a backend that was up the whole time.
const HEALTH_TIMEOUT_MS = 15000;
const SIMULATE_TIMEOUT_MS = 15 * 60 * 1000; // a cold Colab T4 can take minutes

async function fetchWithTimeout(url, options = {}, timeoutMs = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** Is the backend reachable? Never throws. */
export async function checkHealth() {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/health`, {},
      HEALTH_TIMEOUT_MS);
    if (!res.ok) return { online: false };
    return { online: true, ...(await res.json()) };
  } catch {
    return { online: false };
  }
}

/**
 * Build a mock payload matching the backend response contract.
 * Shape parity matters: the UI must not need to branch on data source.
 */
export function buildMockResult(regionId, interventionText) {
  const region = MOCK_REGIONS.find((r) => r.id === regionId) || MOCK_REGIONS[0];
  const preset =
    region.presets.find((p) => p.text === interventionText) || region.presets[0];
  const d = preset.metricsDelta;

  const logs = [
    { step: 1, agent: 'Input Handler', type: 'info',
      text: `Ingested Sentinel-2 L2A composite for ${region.name}.` },
    { step: 2, agent: 'Intervention-Planner', type: 'info',
      text: 'Identified drainage network and sited structures on the main stem.' },
    { step: 3, agent: 'Eco-Hydrological Dynamics', type: 'info',
      text: 'Recharge plume and NDVI growth envelope computed.' },
    { step: 4, agent: 'Generator (Diffusion)', type: 'info',
      text: 'Synthesizing candidate future scene.' },
  ];
  if (d.criticIterations > 1) {
    logs.push({ step: 5, agent: 'Physical-Plausibility Critic', type: 'reject',
      text: d.rejectionReason });
    logs.push({ step: 6, agent: 'Generator (Diffusion)', type: 'info',
      text: 'Re-synthesizing with corrected elevation mask.' });
  }
  logs.push({ step: logs.length + 1, agent: 'Physical-Plausibility Critic',
    type: 'success',
    text: `Passed with ${d.plausibilityScore}% plausibility score.` });

  return {
    source: 'mock',
    status: 'success',
    execution_time_sec: 3.8,
    plausibility_score: d.plausibilityScore,
    is_approved: true,
    critic_iterations: d.criticIterations,
    critic_rejections: Math.max(0, d.criticIterations - 1),
    violations: [],
    scene_source: 'mock',
    generator_backend: 'mock',
    metrics_delta: {
      ndvi_delta: d.ndviDelta,
      soil_moisture_delta: d.soilMoistureDelta,
      water_retention_delta: d.waterRetentionDelta,
    },
    imagery: null, // null => SatelliteSlider keeps its SVG rendering
    execution_logs: logs,
  };
}

/** Synchronous simulation. Falls back to mock data on any failure. */
export async function simulate({ regionId, interventionText, targetYears = 5,
                                 bbox = null }) {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        region_id: regionId,
        intervention_text: interventionText,
        target_years: targetYears,
        bbox,
      }),
    }, SIMULATE_TIMEOUT_MS);

    if (!res.ok) throw new Error(`Backend returned ${res.status}`);
    return { ...(await res.json()), source: 'backend' };
  } catch (err) {
    console.warn('[GeoCounterfactual] Backend unavailable, using mock data:',
      err.message);
    return { ...buildMockResult(regionId, interventionText),
             fallback_reason: err.message };
  }
}

/**
 * Streaming simulation over SSE.
 *
 * onNode({node, logs}) fires as each agent finishes, which is what makes the
 * critic's reject-and-retry visible while it happens rather than as a
 * transcript after the fact.
 *
 * Returns the final payload. Falls back to mock data if the backend or the
 * stream is unavailable.
 */
export async function simulateStreaming({ regionId, interventionText,
                                          targetYears = 5, bbox = null,
                                          onNode = () => {} }) {
  let jobId;
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/simulate/async`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        region_id: regionId,
        intervention_text: interventionText,
        target_years: targetYears,
        bbox,
      }),
    }, HEALTH_TIMEOUT_MS * 2);
    if (!res.ok) throw new Error(`Backend returned ${res.status}`);
    ({ job_id: jobId } = await res.json());
  } catch (err) {
    console.warn('[GeoCounterfactual] Cannot start job, using mock data:',
      err.message);
    const mock = buildMockResult(regionId, interventionText);
    // Replay the mock logs through the same callback so the terminal
    // animates identically whether the data is real or not.
    for (const log of mock.execution_logs) {
      onNode({ node: 'mock', logs: [log] });
      await new Promise((r) => setTimeout(r, 450));
    }
    return { ...mock, fallback_reason: err.message };
  }

  return new Promise((resolve) => {
    const source = new EventSource(`${API_BASE}/api/stream/${jobId}`);
    let settled = false;

    const finish = (payload) => {
      if (settled) return;
      settled = true;
      source.close();
      resolve(payload);
    };

    source.addEventListener('node', (evt) => {
      try {
        onNode(JSON.parse(evt.data));
      } catch (err) {
        console.warn('[GeoCounterfactual] Bad node event:', err);
      }
    });

    source.addEventListener('complete', (evt) => {
      try {
        finish({ ...JSON.parse(evt.data), source: 'backend' });
      } catch (err) {
        finish({ ...buildMockResult(regionId, interventionText),
                 fallback_reason: err.message });
      }
    });

    source.addEventListener('error', async (evt) => {
      if (settled) return;
      // Close first: EventSource otherwise auto-reconnects, the server
      // refuses the replay with 409, and that 409 lands here a second time.
      source.close();

      // A named 'error' event carries data: the pipeline itself failed, so
      // there is no result to recover.
      if (evt?.data) {
        let message = 'pipeline error';
        try { message = JSON.parse(evt.data).message ?? message; } catch { /* keep default */ }
        console.warn('[GeoCounterfactual] Pipeline failed:', message);
        finish({ ...buildMockResult(regionId, interventionText),
                 fallback_reason: message });
        return;
      }

      // A transport drop carries no data. The graph keeps running in its
      // server thread regardless, so a Wi-Fi blip during a multi-minute T4
      // run must not discard a real result for mock numbers.
      console.warn('[GeoCounterfactual] Stream dropped; recovering job', jobId);
      const recovered = await recoverResult(jobId);
      if (recovered.payload) {
        finish({ ...recovered.payload, source: 'backend', recovered: true });
      } else {
        finish({ ...buildMockResult(regionId, interventionText),
                 fallback_reason: `stream lost: ${recovered.reason}` });
      }
    });
  });
}

const RECOVER_POLL_MS = 3000;
const RECOVER_DEADLINE_MS = 5 * 60 * 1000;

/**
 * Poll /api/result for a job whose SSE stream dropped.
 *
 * Resolves {payload} when the job finishes, or {reason} when it failed,
 * never started, or outlived the deadline. Never throws.
 */
async function recoverResult(jobId) {
  const deadline = Date.now() + RECOVER_DEADLINE_MS;
  let pendingPolls = 0;
  while (Date.now() < deadline) {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/result/${jobId}`,
        {}, 10000);
      if (res.status === 404) return { reason: 'job no longer tracked' };
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        return { reason: body.detail || `backend returned ${res.status}` };
      }
      const body = await res.json();
      // Unfinished jobs answer {status: "pending"|"running"}; a finished one
      // is the full payload, which carries status "success" and a run_id.
      if (body.status === 'success' || body.run_id) return { payload: body };
      // "pending" means the worker never started -- the stream dropped
      // before the graph launched, so waiting will not help.
      if (body.status === 'pending' && ++pendingPolls >= 3) {
        return { reason: 'job never started' };
      }
    } catch {
      // Network still down; keep trying until the deadline.
    }
    await new Promise((r) => setTimeout(r, RECOVER_POLL_MS));
  }
  return { reason: 'recovery timed out' };
}

export async function fetchRegions() {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/regions`, {},
      HEALTH_TIMEOUT_MS);
    if (!res.ok) throw new Error(`Backend returned ${res.status}`);
    return (await res.json()).regions;
  } catch {
    return null; // caller keeps MOCK_REGIONS
  }
}
