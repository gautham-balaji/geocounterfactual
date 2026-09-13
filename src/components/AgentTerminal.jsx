import React, { useEffect, useRef } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Terminal } from 'lucide-react';
import { cn, Label } from './ui/primitives';

/**
 * The live agent chatter stream.
 *
 * This is the one surface where monospace is unambiguously correct: the
 * logs are machine output, and aligned step numbers make the reject ->
 * regenerate -> pass sequence scannable at a glance.
 */

// Left edge marker per log type. A coloured rule reads more like a console
// than a filled card does, and keeps the eye on the text.
const TONE = {
  reject: { rule: 'bg-critical', text: 'text-critical', agent: 'text-critical/80' },
  warn: { rule: 'bg-caution', text: 'text-caution', agent: 'text-caution/80' },
  warning: { rule: 'bg-caution', text: 'text-caution', agent: 'text-caution/80' },
  success: { rule: 'bg-positive', text: 'text-positive', agent: 'text-positive/80' },
  info: { rule: 'bg-line-strong', text: 'text-ink-secondary', agent: 'text-ink-tertiary' },
};

export default function AgentTerminal({
  logs = [],
  visibleCount = null,
  isLive = false,
  isRunning = false,
  heightClass = 'h-[500px]',
  title = 'Agent stream',
}) {
  const ref = useRef(null);
  const reduce = useReducedMotion();
  const shown = visibleCount == null ? logs.length : visibleCount;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? 'auto' : 'smooth' });
  }, [shown, reduce]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-ink-tertiary" strokeWidth={1.75} />
          <Label>{title}</Label>
        </div>
        <div className="flex items-center gap-2">
          {isRunning && (
            <span className="flex items-center gap-1.5 text-micro text-ink-tertiary">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              running
            </span>
          )}
          {shown > 0 && (
            <span className="font-mono text-micro text-ink-tertiary">
              {shown} {shown === 1 ? 'entry' : 'entries'}
            </span>
          )}
        </div>
      </div>

      <div
        ref={ref}
        className={cn(
          'rounded-lg bg-surface-1 border border-line overflow-y-auto',
          'divide-y divide-line/60',
          heightClass,
        )}
      >
        {shown === 0 && (
          <div className="h-full flex items-center justify-center">
            <span className="font-mono text-micro text-ink-tertiary">
              idle
            </span>
          </div>
        )}

        <AnimatePresence initial={false}>
          {logs.slice(0, shown).map((log, index) => {
            const tone = TONE[log.type] ?? TONE.info;
            return (
              <motion.div
                key={`${log.step}-${index}`}
                // Enter from slightly below rather than from the left: the
                // stream reads top-to-bottom, so downward settle matches the
                // direction the eye is already travelling.
                initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                className="relative flex gap-3 px-3.5 py-2.5"
              >
                <span className={cn('absolute left-0 top-0 bottom-0 w-0.5',
                  tone.rule)} />
                <span className="font-mono text-micro text-ink-tertiary tabular-nums pt-px w-6 shrink-0 text-right">
                  {log.step}
                </span>
                <div className="min-w-0 flex-1">
                  <div className={cn('font-mono text-micro mb-0.5', tone.agent)}>
                    {log.agent}
                  </div>
                  <div className={cn('font-mono text-label leading-relaxed break-words',
                    tone.text)}>
                    {log.text}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}
