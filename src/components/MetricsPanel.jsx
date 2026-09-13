import React, { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { TrendingUp, Droplets, Activity, CheckCircle2, AlertTriangle } from 'lucide-react';
import { cn, Label, Panel, Badge, ModelledBadge, Divider } from './ui/primitives';

const RULE_ROWS = [
  { id: 'R1', label: 'Gravity / slope', detail: 'Water restricted to slope < 2.5°' },
  { id: 'R2', label: 'Growth ceiling', detail: 'Capped by rate, moisture, terrain' },
  { id: 'R3', label: 'Spectral consistency', detail: 'Greening must show NIR response' },
  { id: 'R4', label: 'Area conservation', detail: 'SSIM outside footprint ≥ 0.90' },
];

const RING_R = 30;
const RING_C = 2 * Math.PI * RING_R;

export default function MetricsPanel({ selectedRegion, activePreset,
                                       simulationResult, liveResult = null }) {
  const reduce = useReducedMotion();
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
            ? 'Approved on the first pass. No physics violations detected.'
            : 'Retry budget exhausted. Violations outstanding.'),
      }
    : activePreset?.metricsDelta || {
        ndviDelta: '+0.18', soilMoistureDelta: '+14%', waterRetentionDelta: '+28%',
        plausibilityScore: 94, criticIterations: 2,
        rejectionReason: 'Iteration 1 rejected: water body detected on a steep slope.',
      };

  const score = metrics.plausibilityScore;
  const failedIds = new Set();
  (liveResult?.violations ?? []).forEach((v) => {
    if (/Gravity/i.test(v)) failedIds.add('R1');
    if (/Biological/i.test(v)) failedIds.add('R2');
    if (/Spectral/i.test(v)) failedIds.add('R3');
    if (/Drift/i.test(v)) failedIds.add('R4');
  });
  const passCount = RULE_ROWS.length - (isLive ? failedIds.size : 0);

  const tone = score >= 90 ? 'positive' : score >= 70 ? 'caution' : 'critical';
  const ringStroke = { positive: '#4ADE80', caution: '#FBBF24', critical: '#F87171' }[tone];
  const textTone = { positive: 'text-positive', caution: 'text-caution', critical: 'text-critical' }[tone];

  /**
   * Replaces the confetti burst. A full-marks run gets one quiet pulse of
   * the ring. The celebration belonged to a consumer app, and a physics
   * validation result reporting 100% should look like an instrument
   * settling, not a party.
   */
  const perfect = isLive && score >= 100 && liveResult?.is_approved;
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (!perfect) return;
    setFlash(true);
    const id = setTimeout(() => setFlash(false), 1100);
    return () => clearTimeout(id);
  }, [perfect, liveResult?.run_id]);

  return (
    <div className="space-y-6">
      {/* ---- Plausibility ---- */}
      <Panel className="space-y-5" inset>
        <div className="flex items-start justify-between gap-6">
          <div className="min-w-0 space-y-2">
            <Label>Plausibility</Label>
            <h3 className="text-h2 font-medium text-ink-primary">
              Critic verdict
            </h3>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Badge tone={isLive ? 'positive' : 'neutral'}>
                {isLive ? 'Live' : 'Mock'}
              </Badge>
              {isLive && liveResult?.scene_source && (
                <Badge tone="info">
                  {liveResult.scene_source === 'gee'
                    ? 'Sentinel-2'
                    : String(liveResult.scene_source)}
                </Badge>
              )}
              {isLive && liveResult?.generator_backend && (
                <Badge tone="neutral">{liveResult.generator_backend}</Badge>
              )}
            </div>
          </div>

          {/* Score ring */}
          <div className="relative w-[76px] h-[76px] shrink-0">
            <motion.div
              className="absolute inset-0 rounded-full"
              animate={flash && !reduce
                ? { boxShadow: ['0 0 0 0 rgba(74,222,128,0)',
                                '0 0 0 7px rgba(74,222,128,0.10)',
                                '0 0 0 0 rgba(74,222,128,0)'] }
                : {}}
              transition={{ duration: 1.1, ease: 'easeOut' }}
            />
            <svg className="w-full h-full -rotate-90" viewBox="0 0 76 76">
              <circle cx="38" cy="38" r={RING_R} fill="none"
                      stroke="#26262B" strokeWidth="2" />
              <motion.circle
                cx="38" cy="38" r={RING_R} fill="none"
                stroke={ringStroke} strokeWidth="2" strokeLinecap="round"
                strokeDasharray={RING_C}
                initial={false}
                animate={{ strokeDashoffset: RING_C - (RING_C * score) / 100 }}
                transition={{ duration: reduce ? 0 : 0.9, ease: [0.16, 1, 0.3, 1] }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className={cn('font-mono text-h2 font-medium leading-none',
                textTone)}>
                {score}
              </span>
              <span className="text-micro text-ink-tertiary mt-1">score</span>
            </div>
          </div>
        </div>

        <Divider />

        <div className="flex items-start gap-3">
          {liveResult?.is_approved !== false
            ? <CheckCircle2 className="w-4 h-4 text-positive shrink-0 mt-0.5" strokeWidth={1.75} />
            : <AlertTriangle className="w-4 h-4 text-caution shrink-0 mt-0.5" strokeWidth={1.75} />}
          <div className="min-w-0 space-y-1">
            <div className="text-label text-ink-primary">
              {metrics.criticIterations} critic{' '}
              {metrics.criticIterations === 1 ? 'iteration' : 'iterations'}
            </div>
            <p className="text-micro text-ink-tertiary leading-relaxed">
              {metrics.rejectionReason}
            </p>
          </div>
        </div>
      </Panel>

      {/* ---- Deltas ---- */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-px bg-line rounded-xl overflow-hidden border border-line">
        {[
          { icon: TrendingUp, label: 'NDVI delta', value: metrics.ndviDelta,
            caption: 'Biomass index, 5 yr', modelled: false },
          { icon: Droplets, label: 'Soil moisture', value: metrics.soilMoistureDelta,
            caption: 'Recharge plume', modelled: true },
          { icon: Activity, label: 'Runoff retention', value: metrics.waterRetentionDelta,
            caption: 'Monsoon capture', modelled: true },
        ].map(({ icon: Icon, label, value, caption, modelled }) => (
          <div key={label} className="bg-surface-1 px-4 py-4 space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>{label}</Label>
              <Icon className="w-3.5 h-3.5 text-ink-tertiary" strokeWidth={1.75} />
            </div>
            <div className="font-mono text-h1 font-medium text-ink-primary">
              {value}
            </div>
            <div className="text-micro text-ink-tertiary">{caption}</div>
            {modelled && <ModelledBadge className="mt-1" />}
          </div>
        ))}
      </div>

      {/* ---- Rule matrix ---- */}
      <Panel className="space-y-3" inset>
        <div className="flex items-center justify-between">
          <Label>Rule compliance</Label>
          <span className={cn('font-mono text-micro',
            passCount === 4 ? 'text-positive' : 'text-critical')}>
            {passCount}/4 passed
          </span>
        </div>

        <div className="space-y-px">
          {RULE_ROWS.map((item) => {
            const failed = isLive && failedIds.has(item.id);
            return (
              <div
                key={item.id}
                className="flex items-center justify-between gap-4 py-2 border-b border-line/60 last:border-0"
              >
                <div className="min-w-0 flex items-start gap-3">
                  <span className="font-mono text-micro text-ink-tertiary pt-0.5 w-5 shrink-0">
                    {item.id}
                  </span>
                  <div className="min-w-0">
                    <div className="text-label text-ink-primary">{item.label}</div>
                    <div className="text-micro text-ink-tertiary">{item.detail}</div>
                  </div>
                </div>
                <Badge tone={failed ? 'critical' : 'positive'}
                       icon={failed ? AlertTriangle : CheckCircle2}>
                  {failed ? 'Fail' : 'Pass'}
                </Badge>
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
