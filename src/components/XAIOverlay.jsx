import React from 'react';
import { AlertTriangle, Droplets, Mountain, Sprout, Square } from 'lucide-react';
import { cn, Label, Badge } from './ui/primitives';

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
    colour: 'text-critical border-critical/40 bg-critical/10',
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
    colour: 'text-info border-info/40 bg-info/10',
    describe: (s) => s?.footprint_px
      ? `${((s.footprint_px * 100) / 1e4).toFixed(1)} ha treated`
      : 'no footprint',
    modelled: false,
  },
  {
    id: 'impoundment',
    label: 'Impounded water',
    icon: Droplets,
    colour: 'text-accent-soft border-accent/40 bg-accent-subtle',
    describe: (s) => s?.impoundment_px
      ? `${((s.impoundment_px * 100) / 1e4).toFixed(2)} ha surface water`
      : 'no impoundment',
    modelled: true,
  },
  {
    id: 'ndvi_delta',
    label: 'NDVI change',
    icon: Sprout,
    colour: 'text-positive border-positive/40 bg-positive/10',
    describe: () => 'greening / browning, |Δ| ≥ 0.05',
    modelled: true,
  },
  {
    id: 'steep_terrain',
    label: 'Slope > 2.5°',
    icon: Mountain,
    colour: 'text-caution border-caution/40 bg-caution/10',
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
    <div className="rounded-xl bg-surface-1 border border-line p-5 space-y-5">
      <div className="flex items-center justify-between">
        <Label>Explainability overlays</Label>
        {disabled && (
          <span className="text-micro text-ink-tertiary">
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
              className={cn(
                'text-label px-2.5 h-8 rounded-lg border flex items-center gap-1.5',
                'transition-colors duration-150',
                on ? d.colour + ' font-medium'
                   : 'bg-transparent text-ink-tertiary border-line hover:bg-surface-2 hover:text-ink-secondary',
                (disabled || !has) && 'opacity-40 cursor-not-allowed',
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {d.label}
              {d.modelled && (
                <span className="px-1 rounded text-[9px] font-medium bg-caution/15 text-caution border border-caution/30">
                  MODELLED
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-4 pt-4 border-t border-line">
        <button
          disabled={disabled}
          onClick={onAmplify}
          className={cn(
            'text-label px-3 h-8 rounded-lg border transition-colors duration-150',
            amplify
              ? 'bg-accent-subtle text-accent-soft border-accent/40 font-medium'
              : 'bg-transparent text-ink-tertiary border-line hover:bg-surface-2 hover:text-ink-secondary',
            disabled && 'opacity-40 cursor-not-allowed',
          )}
        >
          Δ Amplify
        </button>

        {amplify && (
          <label className="flex items-center gap-2 text-micro text-ink-tertiary">
            gain {gain}×
            <input type="range" min="1" max="20" value={gain}
                   onChange={(e) => onGain(Number(e.target.value))}
                   className="w-24 accent-accent" />
          </label>
        )}

        <button
          disabled={disabled}
          onClick={onBlink}
          className={cn(
            'text-label px-3 h-8 rounded-lg border transition-colors duration-150',
            blink
              ? 'bg-accent-subtle text-accent-soft border-accent/40 font-medium'
              : 'bg-transparent text-ink-tertiary border-line hover:bg-surface-2 hover:text-ink-secondary',
            disabled && 'opacity-40 cursor-not-allowed',
          )}
          title="Alternate before/after in place - far better than a slider for spotting small changes"
        >
          A/B Blink
        </button>

        <button
          disabled={disabled}
          onClick={onLoupe}
          className={cn(
            'text-label px-3 h-8 rounded-lg border transition-colors duration-150',
            loupe
              ? 'bg-accent-subtle text-accent-soft border-accent/40 font-medium'
              : 'bg-transparent text-ink-tertiary border-line hover:bg-surface-2 hover:text-ink-secondary',
            disabled && 'opacity-40 cursor-not-allowed',
          )}
        >
          Loupe 3×
        </button>

        <label className="flex items-center gap-2 text-micro text-ink-tertiary ml-auto">
          opacity
          <input type="range" min="0.2" max="1" step="0.05" value={opacity}
                 onChange={(e) => onOpacity(Number(e.target.value))}
                 className="w-24 accent-accent" />
        </label>
      </div>

      {stats?.rejection_violations?.length > 0 && (
        <div className="rounded-lg border border-critical/25 bg-critical/5 px-3 py-2.5">
          <div className="text-micro text-critical/80 mb-1">
            Rejected at iteration {stats.rejection_iteration}
          </div>
          <div className="font-mono text-micro text-critical leading-relaxed">
            {stats.rejection_violations[0]}
          </div>
        </div>
      )}
    </div>
  );
}
