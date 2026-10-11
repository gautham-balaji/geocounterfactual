import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { FileText, MapPin, Trees, Cpu, ShieldCheck, CornerUpLeft,
         Check } from 'lucide-react';
import { cn, Label, Badge } from './ui/primitives';
import { PIPELINE_NODES } from '../services/pipelineState';

/**
 * The five agents and where the run is among them.
 *
 * State comes from the server's own routing (see pipelineState.js): the
 * highlighted node is the one RUNNING, not the one that last logged. The
 * critic -> generator edge lights when a rejection actually sends the scene
 * back, which is the moment the panel should be looking at.
 */

const ICONS = {
  input_handler: FileText, planner: MapPin, dynamics: Trees,
  generator: Cpu, critic: ShieldCheck,
};

function nodeState(id, pipeline, isRunning) {
  if (isRunning && pipeline.active === id) return 'active';
  if (pipeline.completed.includes(id)) return 'done';
  return 'pending';
}

export default function PipelineRail({ pipeline, isRunning = false }) {
  const reduce = useReducedMotion();
  const { pass, maxIterations, verdicts } = pipeline;
  const last = verdicts[verdicts.length - 1];
  const looped = verdicts.some((v) => v.outcome === 'retry');
  // Hot while the generator is redoing a pass the critic just rejected.
  const loopFiring = isRunning && last?.outcome === 'retry'
    && pipeline.active === 'generator';

  return (
    <div className="rounded-lg border border-line bg-surface-1 p-3.5 space-y-3">
      <div className="flex items-center justify-between">
        <Label>Agent pipeline</Label>
        {pass > 0 && (
          <span className="font-mono text-micro text-ink-secondary tabular-nums">
            pass {pass}
            <span className="text-ink-tertiary"> / {maxIterations}</span>
          </span>
        )}
      </div>

      <ol className="space-y-1">
        {PIPELINE_NODES.map((node, i) => {
          const state = nodeState(node.id, pipeline, isRunning);
          const Icon = ICONS[node.id];
          // Only on the row doing the work: a finished critic labelled with
          // the pass the generator is now redoing would claim a verdict it
          // has not given yet.
          const showPass = pass > 0 && state === 'active'
            && (node.id === 'generator' || node.id === 'critic');
          return (
            <li key={node.id}>
              <div
                aria-current={state === 'active' ? 'step' : undefined}
                className={cn(
                  'relative flex items-center gap-2.5 rounded-md px-2.5 py-2',
                  'border transition-colors duration-300',
                  state === 'active' && 'border-accent/40 bg-accent-subtle',
                  state === 'done' && 'border-line bg-surface-2/60',
                  state === 'pending' && 'border-transparent opacity-50',
                )}
              >
                {state === 'active' && !reduce && (
                  <motion.span
                    className="absolute inset-0 rounded-md border border-accent/50"
                    animate={{ opacity: [0.25, 0.9, 0.25] }}
                    transition={{ duration: 1.6, repeat: Infinity,
                                  ease: 'easeInOut' }}
                  />
                )}
                <Icon
                  className={cn('w-3.5 h-3.5 shrink-0',
                    state === 'active' ? 'text-accent-soft'
                      : state === 'done' ? 'text-ink-secondary'
                        : 'text-ink-tertiary')}
                  strokeWidth={1.75}
                />
                <span className={cn('text-label flex-1 min-w-0 truncate',
                  state === 'pending' ? 'text-ink-tertiary' : 'text-ink-primary')}>
                  {node.label}
                </span>
                {showPass && (
                  <span className="font-mono text-micro text-ink-tertiary tabular-nums">
                    #{pass}
                  </span>
                )}
                {state === 'active' && (
                  <Badge tone="accent">running</Badge>
                )}
                {state === 'done' && (
                  <Check className="w-3.5 h-3.5 text-positive shrink-0"
                         strokeWidth={2} />
                )}
              </div>

              {/* The feedback edge, drawn between Generator and Critic. */}
              {i === 3 && looped && (
                <div className={cn(
                  'flex items-center gap-1.5 pl-3 py-1 font-mono text-micro',
                  loopFiring ? 'text-critical' : 'text-critical/50')}>
                  <CornerUpLeft
                    className={cn('w-3 h-3',
                      loopFiring && !reduce && 'animate-pulse')}
                    strokeWidth={2} />
                  {loopFiring
                    ? `rejected, regenerating (pass ${pass})`
                    : 'critic feedback loop'}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
