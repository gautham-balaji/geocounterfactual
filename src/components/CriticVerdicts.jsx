import React from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ShieldCheck, ShieldAlert, CornerUpLeft, Eye } from 'lucide-react';
import { cn, Label, Badge } from './ui/primitives';

/**
 * The critic's verdict on each pass, as it is given.
 *
 * The loop is the project's contribution, so its reasoning gets its own
 * surface rather than living only in the log stream: which rules failed,
 * why, and how much of the scene went back to the generator. Rules a scene
 * could not be judged on (an RGB upload has no NIR for R2 and R3) are left
 * out, never shown as passed.
 */

const OUTCOME = {
  retry: { label: 'Rejected', tone: 'critical', icon: ShieldAlert },
  exhausted: { label: 'Released unapproved', tone: 'caution', icon: ShieldAlert },
  recorded: { label: 'Recorded (shadow)', tone: 'neutral', icon: Eye },
  approved: { label: 'Approved', tone: 'positive', icon: ShieldCheck },
};

const RULE_NAMES = { R1: 'gravity', R2: 'growth', R3: 'red edge',
                     R4: 'conservation' };

function RuleChips({ evaluated, failed }) {
  if (!evaluated?.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {evaluated.map((id) => {
        const bad = failed.includes(id);
        return (
          <span
            key={id}
            title={`${id} ${RULE_NAMES[id] ?? ''}: ${bad ? 'failed' : 'passed'}`}
            className={cn(
              'font-mono text-micro px-1.5 py-px rounded border',
              bad ? 'border-critical/40 bg-critical/10 text-critical'
                  : 'border-line text-ink-tertiary')}
          >
            {id}
          </span>
        );
      })}
    </div>
  );
}

export default function CriticVerdicts({ verdicts = [], isRunning = false,
                                         replay = false }) {
  const reduce = useReducedMotion();

  return (
    <div className="rounded-lg border border-line bg-surface-1 p-3.5 space-y-3">
      <div className="flex items-center justify-between">
        <Label>Critic verdicts</Label>
        {replay && <Badge tone="neutral">mock replay</Badge>}
      </div>

      {verdicts.length === 0 ? (
        <p className="font-mono text-micro text-ink-tertiary">
          {isRunning ? 'awaiting the first verdict' : 'no run yet'}
        </p>
      ) : (
        <ol className="space-y-2">
          <AnimatePresence initial={false}>
            {verdicts.map((v, i) => {
              const o = OUTCOME[v.outcome] ?? OUTCOME.approved;
              const failed = v.failed_rules ?? [];
              return (
                <motion.li
                  key={`${v.iteration}-${i}`}
                  initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                  className={cn(
                    'rounded-md border px-3 py-2.5 space-y-2',
                    v.outcome === 'retry' ? 'border-critical/25 bg-critical/5'
                      : 'border-line bg-surface-2/50')}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-micro text-ink-tertiary tabular-nums">
                      pass {v.iteration}
                    </span>
                    <Badge tone={o.tone} icon={o.icon}>{o.label}</Badge>
                    {v.score != null && (
                      <span className="ml-auto font-mono text-micro text-ink-secondary tabular-nums">
                        {v.score.toFixed(1)}%
                      </span>
                    )}
                  </div>

                  <RuleChips evaluated={v.evaluated_rules} failed={failed} />

                  {v.violations?.length > 0 && (
                    <ul className="space-y-1">
                      {v.violations.map((text, k) => (
                        <li key={k}
                            className="font-mono text-micro leading-relaxed text-ink-secondary break-words">
                          {text}
                        </li>
                      ))}
                    </ul>
                  )}

                  {v.outcome === 'retry' && v.feedback_px > 0 && (
                    <div className="flex items-center gap-1.5 font-mono text-micro text-critical">
                      <CornerUpLeft className="w-3 h-3" strokeWidth={2} />
                      {v.feedback_px.toLocaleString()} px sent back to the generator
                    </div>
                  )}
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ol>
      )}
    </div>
  );
}
