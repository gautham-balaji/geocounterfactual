import React from 'react';
import { AlertTriangle, Droplets, Mountain, Sprout, Square } from 'lucide-react';

/**
 * Stack of transparent RGBA overlays rendered above the AFTER scene.
 *
 * These are NOT the four band views. Each is an RGBA PNG with alpha 0
 * outside the region it describes, so they compose over the optical image
 * and fade independently. The previous critic layer was a tint baked onto an
 * opaque base, which could only ever replace the view, never annotate it.
 */

export const OVERLAY_DEFS = [
  {
    id: 'rejection',
    label: 'Critic rejection',
    icon: AlertTriangle,
    colour: 'text-rose-300 border-rose-500/50 bg-rose-500/15',
    // The headline artifact: what the Critic threw out on its first pass.
    // Sourced from rejection_history[0], not the final feedback mask, which
    // is empty by definition on an approved run.
    describe: (s) => s?.rejection_px
      ? `${s.rejection_px.toLocaleString()} px rejected at iteration ${s.rejection_iteration}`
      : 'no rejections this run',
    modelled: false,
  },
  {
    id: 'footprint',
    label: 'Intervention footprint',
    icon: Square,
    colour: 'text-cyan-300 border-cyan-500/50 bg-cyan-500/15',
    describe: (s) => s?.footprint_px
      ? `${((s.footprint_px * 100) / 1e4).toFixed(1)} ha treated`
      : 'no footprint',
    modelled: false,
  },
  {
    id: 'impoundment',
    label: 'Impounded water',
    icon: Droplets,
    colour: 'text-blue-300 border-blue-500/50 bg-blue-500/15',
    describe: (s) => s?.impoundment_px
      ? `${((s.impoundment_px * 100) / 1e4).toFixed(2)} ha surface water`
      : 'no impoundment',
    modelled: true,
  },
  {
    id: 'ndvi_delta',
    label: 'NDVI change',
    icon: Sprout,
    colour: 'text-emerald-300 border-emerald-500/50 bg-emerald-500/15',
    describe: () => 'greening / browning, |Δ| ≥ 0.05',
    modelled: true,
  },
  {
    id: 'steep_terrain',
    label: 'Slope > 2.5°',
    icon: Mountain,
    colour: 'text-amber-300 border-amber-500/50 bg-amber-500/15',
    describe: () => 'where rule R1 forbids standing water',
    modelled: false,
  },
];

export default function XAIOverlay({ overlays, active, opacity = 0.85 }) {
  if (!overlays) return null;

  return (
    <>
      {OVERLAY_DEFS.filter((d) => active.has(d.id) && overlays[d.id]).map((d) => (
        <img
          key={d.id}
          src={overlays[d.id]}
          alt={d.label}
          draggable={false}
          style={{ opacity }}
          className="absolute inset-0 w-full h-full object-cover pointer-events-none select-none"
        />
      ))}
    </>
  );
}

/** Toolbar of overlay toggles. Kept next to the definitions so they cannot drift. */
export function XAIToolbar({ overlays, stats, active, onToggle,
                             opacity, onOpacity,
                             amplify, onAmplify, gain, onGain,
                             blink, onBlink, loupe, onLoupe }) {
  const disabled = !overlays;

  return (
    <div className="glass-panel p-3 rounded-xl border border-slate-800 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono font-semibold text-slate-300">
          EXPLAINABILITY OVERLAYS
        </span>
        {disabled && (
          <span className="text-[10px] font-mono text-slate-500">
            run a simulation to enable
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {OVERLAY_DEFS.map((d) => {
          const on = active.has(d.id);
          const Icon = d.icon;
          const has = Boolean(overlays?.[d.id]);
          return (
            <button
              key={d.id}
              disabled={disabled || !has}
              onClick={() => onToggle(d.id)}
              title={d.describe(stats)}
              className={`text-[11px] px-2.5 py-1.5 rounded-lg font-mono border transition flex items-center gap-1.5 ${
                on ? d.colour + ' font-semibold'
                   : 'bg-slate-800/60 text-slate-400 border-transparent hover:text-slate-200'
              } ${(disabled || !has) ? 'opacity-40 cursor-not-allowed' : ''}`}
            >
              <Icon className="w-3.5 h-3.5" />
              {d.label}
              {d.modelled && (
                <span className="px-1 rounded text-[8px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  MODELLED
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-4 pt-1 border-t border-slate-800">
        <button
          disabled={disabled}
          onClick={onAmplify}
          className={`text-[11px] px-2.5 py-1.5 rounded-lg font-mono border transition ${
            amplify ? 'bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/50 font-semibold'
                    : 'bg-slate-800/60 text-slate-400 border-transparent hover:text-slate-200'
          } ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
        >
          Δ Amplify
        </button>

        {amplify && (
          <label className="flex items-center gap-2 text-[10px] font-mono text-slate-400">
            gain {gain}×
            <input type="range" min="1" max="20" value={gain}
                   onChange={(e) => onGain(Number(e.target.value))}
                   className="w-24 accent-fuchsia-400" />
          </label>
        )}

        <button
          disabled={disabled}
          onClick={onBlink}
          className={`text-[11px] px-2.5 py-1.5 rounded-lg font-mono border transition ${
            blink ? 'bg-violet-500/20 text-violet-300 border-violet-500/50 font-semibold'
                  : 'bg-slate-800/60 text-slate-400 border-transparent hover:text-slate-200'
          } ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
          title="Alternate before/after in place - far better than a slider for spotting small changes"
        >
          A/B Blink
        </button>

        <button
          disabled={disabled}
          onClick={onLoupe}
          className={`text-[11px] px-2.5 py-1.5 rounded-lg font-mono border transition ${
            loupe ? 'bg-sky-500/20 text-sky-300 border-sky-500/50 font-semibold'
                  : 'bg-slate-800/60 text-slate-400 border-transparent hover:text-slate-200'
          } ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
        >
          Loupe 3×
        </button>

        <label className="flex items-center gap-2 text-[10px] font-mono text-slate-400 ml-auto">
          opacity
          <input type="range" min="0.2" max="1" step="0.05" value={opacity}
                 onChange={(e) => onOpacity(Number(e.target.value))}
                 className="w-24 accent-cyan-400" />
        </label>
      </div>

      {stats?.rejection_violations?.length > 0 && (
        <div className="text-[10px] font-mono text-rose-300/90 bg-rose-950/40 border border-rose-500/30 rounded-lg p-2 leading-relaxed">
          <span className="font-bold">Rejected at iteration {stats.rejection_iteration}:</span>{' '}
          {stats.rejection_violations[0]}
        </div>
      )}
    </div>
  );
}
