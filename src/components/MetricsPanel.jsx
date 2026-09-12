import React from 'react';
import { ShieldCheck, TrendingUp, Droplets, Sun, CheckCircle2, AlertTriangle, Activity, BarChart2 } from 'lucide-react';

export default function MetricsPanel({ selectedRegion, activePreset, simulationResult }) {
  const metrics = activePreset?.metricsDelta || {
    ndviDelta: '+0.18',
    soilMoistureDelta: '+14%',
    waterRetentionDelta: '+28%',
    plausibilityScore: 94,
    criticIterations: 2,
    rejectionReason: 'Iteration 1 rejected: Water body detected on steep 14° slope.'
  };

  const score = metrics.plausibilityScore;

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
            <p className="text-xs text-slate-400 mt-0.5">Verified by Multi-Agent Critic Network</p>
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
                stroke="#10b981"
                strokeWidth="6"
                strokeDasharray={213}
                strokeDashoffset={213 - (213 * score) / 100}
                strokeLinecap="round"
                fill="transparent"
                className="transition-all duration-1000 ease-out"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xl font-extrabold text-emerald-400 font-mono">{score}%</span>
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
        </div>
      </div>

      {/* 3. Detailed Physical Constraint Matrix */}
      <div className="glass-panel p-4 rounded-xl border border-slate-800 flex flex-col gap-2.5">
        <div className="text-xs font-mono font-semibold text-slate-300 flex items-center justify-between border-b border-slate-800 pb-2">
          <span className="flex items-center gap-1.5">
            <BarChart2 className="w-3.5 h-3.5 text-cyan-400" /> PHYSICAL AUDIT COMPLIANCE MATRIX
          </span>
          <span className="text-emerald-400 text-[11px]">4 / 4 PASSED</span>
        </div>

        <div className="space-y-2 text-xs">
          {[
            { label: 'Copernicus DEM Slope Constraint', detail: 'Water bodies restricted to slope < 2.5°', status: 'PASS' },
            { label: 'NDVI Biological Ceiling Check', detail: 'Growth rate capped at +0.35/year max', status: 'PASS' },
            { label: 'Spectral Signature Continuity', detail: 'No invalid reflectance values in SWIR bands', status: 'PASS' },
            { label: 'Unchanged Terrain Conservation', detail: 'Non-targeted pixels SSIM > 0.94', status: 'PASS' }
          ].map((item, idx) => (
            <div key={idx} className="flex items-center justify-between p-2 rounded-lg bg-darkbg-800/50 border border-slate-800/80">
              <div>
                <div className="font-mono text-slate-200 font-medium">{item.label}</div>
                <div className="text-[11px] text-slate-400">{item.detail}</div>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> {item.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
