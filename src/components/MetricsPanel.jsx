import React from 'react';
import { ShieldCheck, TrendingUp, Droplets, Sun, CheckCircle2, AlertTriangle, Activity, BarChart2 } from 'lucide-react';

// Rule ids -> audit-matrix rows, so the checklist reflects what the Critic
// actually evaluated instead of four hardcoded PASS badges.
const RULE_ROWS = [
  { id: 'R1', label: 'Copernicus DEM Slope Constraint', detail: 'Water bodies restricted to slope < 2.5°' },
  { id: 'R2', label: 'NDVI Biological Ceiling Check', detail: 'Growth capped by rate, moisture and terrain' },
  { id: 'R3', label: 'Spectral Signature Continuity', detail: 'Visible greening must show an NIR response' },
  { id: 'R4', label: 'Unchanged Terrain Conservation', detail: 'SSIM outside the footprint >= 0.90' },
];

export default function MetricsPanel({ selectedRegion, activePreset, simulationResult, liveResult = null }) {
  // Live backend payload wins; mock deltas are the offline fallback. Before
  // this the panel ALWAYS rendered mockData, so a real 100% run still showed
  // a hardcoded 94% next to a terminal saying otherwise.
  const isLive = Boolean(liveResult && liveResult.source === 'backend');
  const md = liveResult?.metrics_delta;

  const metrics = isLive
    ? {
        ndviDelta: md?.ndvi_delta ?? '+0.00',
        soilMoistureDelta: md?.soil_moisture_delta ?? '+0%',
        waterRetentionDelta: md?.water_retention_delta ?? '+0%',
        plausibilityScore: Math.round(liveResult.plausibility_score ?? 0),
        criticIterations: liveResult.critic_iterations ?? 0,
        rejectionReason:
          liveResult.rejection_history?.[0]?.violations?.[0] ??
          (liveResult.is_approved
            ? 'Approved on the first pass - no physics violations detected.'
            : 'Retry budget exhausted with violations outstanding.'),
      }
    : activePreset?.metricsDelta || {
        ndviDelta: '+0.18',
        soilMoistureDelta: '+14%',
        waterRetentionDelta: '+28%',
        plausibilityScore: 94,
        criticIterations: 2,
        rejectionReason: 'Iteration 1 rejected: Water body detected on steep 14° slope.'
      };

  const score = metrics.plausibilityScore;
  const ringColour = score >= 90 ? '#10b981' : score >= 70 ? '#f59e0b' : '#f43f5e';
  const scoreText = score >= 90 ? 'text-emerald-400' : score >= 70 ? 'text-amber-400' : 'text-rose-400';

  // Which rules failed on the FINAL pass, read from the live payload.
  const failedIds = new Set();
  (liveResult?.violations ?? []).forEach((v) => {
    if (/Gravity/i.test(v)) failedIds.add('R1');
    if (/Biological/i.test(v)) failedIds.add('R2');
    if (/Spectral/i.test(v)) failedIds.add('R3');
    if (/Drift/i.test(v)) failedIds.add('R4');
  });
  const passCount = RULE_ROWS.length - (isLive ? failedIds.size : 0);

  return (
    <div className="flex flex-col gap-4">
      {/* 1. Primary Header & Plausibility Score HUD */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 relative overflow-hidden">
        {/* Glow backdrop */}
        <div className="absolute -top-10 -right-10 w-40 h-40 bg-emerald-500/10 rounded-full blur-3xl" />

        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-emerald-400 uppercase tracking-wider">
              <ShieldCheck className="w-4 h-4" /> PHYSICAL PLAUSIBILITY AUDIT
            </div>
            <h3 className="text-lg font-bold text-white mt-1">Critic Validation Index</h3>
            <div className="flex items-center gap-2 mt-1">
              <span className={isLive
                ? 'px-2 py-0.5 rounded text-[10px] font-mono font-bold border bg-emerald-500/20 text-emerald-300 border-emerald-500/50'
                : 'px-2 py-0.5 rounded text-[10px] font-mono font-bold border bg-slate-700/40 text-slate-300 border-slate-600'}>
                {isLive ? 'LIVE PIPELINE' : 'MOCK DATA'}
              </span>
              {isLive && liveResult?.scene_source && (
                <span className="px-2 py-0.5 rounded text-[10px] font-mono border bg-sky-500/15 text-sky-300 border-sky-500/40">
                  {liveResult.scene_source === 'gee' ? 'SENTINEL-2' : String(liveResult.scene_source).toUpperCase()}
                </span>
              )}
            </div>
          </div>

          {/* Radial Circular Badge / Score Display */}
          <div className="relative w-20 h-20 flex items-center justify-center">
            <svg className="w-full h-full transform -rotate-90">
              <circle
                cx="40"
                cy="40"
                r="34"
                stroke="#1e293b"
                strokeWidth="6"
                fill="transparent"
              />
              <circle
                cx="40"
                cy="40"
                r="34"
                stroke={ringColour}
                strokeWidth="6"
                strokeDasharray={213}
                strokeDashoffset={213 - (213 * score) / 100}
                strokeLinecap="round"
                fill="transparent"
                className="transition-all duration-1000 ease-out"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className={"text-xl font-extrabold font-mono " + scoreText}>{score}%</span>
              <span className="text-[9px] font-mono text-slate-400 uppercase">SCORE</span>
            </div>
          </div>
        </div>

        {/* Critic Feedback Iteration Banner */}
        <div className="mt-4 p-3 rounded-xl bg-darkbg-800/80 border border-slate-700/60 flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <div className="font-mono text-amber-300 font-semibold">
              Critic Iterations Required: <span className="text-white">{metrics.criticIterations} Pass(es)</span>
            </div>
            <div className="text-slate-400 mt-0.5 leading-relaxed">
              {metrics.rejectionReason}
            </div>
          </div>
        </div>
      </div>

      {/* 2. Projected Change Deltas Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Metric 1: NDVI Delta */}
        <div className="glass-panel p-4 rounded-xl border border-slate-800 hover:border-emerald-500/40 transition">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>NDVI DELTA</span>
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-extrabold font-mono text-emerald-400 mt-2">
            {metrics.ndviDelta}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Biomass growth index (5-yr)
          </div>
        </div>

        {/* Metric 2: Soil Moisture */}
        <div className="glass-panel p-4 rounded-xl border border-slate-800 hover:border-cyan-500/40 transition">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>SOIL MOISTURE</span>
            <Droplets className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-extrabold font-mono text-cyan-400 mt-2">
            {metrics.soilMoistureDelta}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Groundwater recharge plume
          </div>
          <span className="mt-2 inline-block px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-500/15 text-amber-300 border border-amber-500/40">
            MODELLED
          </span>
        </div>

        {/* Metric 3: Water Retention */}
        <div className="glass-panel p-4 rounded-xl border border-slate-800 hover:border-indigo-500/40 transition">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>RUNOFF RETENTION</span>
            <Activity className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-extrabold font-mono text-indigo-400 mt-2">
            {metrics.waterRetentionDelta}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Monsoon capture volume
          </div>
          <span className="mt-2 inline-block px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-500/15 text-amber-300 border border-amber-500/40">
            MODELLED
          </span>
        </div>
      </div>

      {/* 3. Detailed Physical Constraint Matrix */}
      <div className="glass-panel p-4 rounded-xl border border-slate-800 flex flex-col gap-2.5">
        <div className="text-xs font-mono font-semibold text-slate-300 flex items-center justify-between border-b border-slate-800 pb-2">
          <span className="flex items-center gap-1.5">
            <BarChart2 className="w-3.5 h-3.5 text-cyan-400" /> PHYSICAL AUDIT COMPLIANCE MATRIX
          </span>
          <span className={passCount === 4 ? "text-emerald-400 text-[11px]" : "text-rose-400 text-[11px]"}>{passCount} / 4 PASSED</span>
        </div>

        <div className="space-y-2 text-xs">
          {RULE_ROWS.map((item) => {
            const failed = isLive && failedIds.has(item.id);
            return (
              <div key={item.id} className="flex items-center justify-between p-2 rounded-lg bg-darkbg-800/50 border border-slate-800/80">
                <div>
                  <div className="font-mono text-slate-200 font-medium">
                    <span className="text-slate-500 mr-1.5">{item.id}</span>{item.label}
                  </div>
                  <div className="text-[11px] text-slate-400">{item.detail}</div>
                </div>
                <span className={failed
                  ? 'px-2 py-0.5 rounded text-[10px] font-mono font-bold border flex items-center gap-1 bg-rose-500/20 text-rose-300 border-rose-500/40'
                  : 'px-2 py-0.5 rounded text-[10px] font-mono font-bold border flex items-center gap-1 bg-emerald-500/20 text-emerald-300 border-emerald-500/40'}>
                  {failed ? <AlertTriangle className="w-3 h-3" /> : <CheckCircle2 className="w-3 h-3" />}
                  {failed ? 'FAIL' : 'PASS'}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
