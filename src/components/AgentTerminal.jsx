import React, { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Terminal } from 'lucide-react';

/**
 * The live agent chatter stream.
 *
 * Extracted from AgentOrchestrationView so the Command Center and the
 * standalone flowchart render the same implementation rather than two
 * copies that drift apart.
 */
export default function AgentTerminal({
  logs = [],
  visibleCount = null,
  isLive = false,
  isRunning = false,
  heightClass = 'h-[500px]',
  title = 'LIVE AGENT CHATTER STREAM',
}) {
  const ref = useRef(null);
  const shown = visibleCount == null ? logs.length : visibleCount;

  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [shown]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between text-xs font-mono">
        <span className="flex items-center gap-2 text-emerald-400 font-bold">
          <Terminal className="w-4 h-4" /> {title}
        </span>
        <div className="flex items-center gap-2">
          {isLive && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/50">
              LIVE
            </span>
          )}
          {isRunning && (
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping-slow" />
          )}
        </div>
      </div>

      <div
        ref={ref}
        className={`bg-darkbg-900/90 rounded-xl p-3 border border-slate-800 ${heightClass} overflow-y-auto space-y-2 text-xs`}
      >
        {shown === 0 && (
          <div className="h-full flex items-center justify-center text-slate-600 font-mono text-[11px]">
            Awaiting simulation…
          </div>
        )}

        {logs.slice(0, shown).map((log, index) => {
          const isReject = log.type === 'reject';
          // Backend emits 'warn'; the mock chatter uses 'warning'.
          const isWarning = log.type === 'warning' || log.type === 'warn';
          const isSuccess = log.type === 'success';

          return (
            <motion.div
              key={`${log.step}-${index}`}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className={`p-2 rounded-lg border leading-relaxed ${
                isReject
                  ? 'bg-rose-950/50 border-rose-500/60 text-rose-200'
                  : isWarning
                  ? 'bg-amber-950/40 border-amber-500/50 text-amber-200'
                  : isSuccess
                  ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-200'
                  : 'bg-darkbg-800 border-slate-800 text-slate-300'
              }`}
            >
              <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                <span className="text-cyan-400 font-semibold">[{log.agent}]</span>
                <span>#{log.step}</span>
              </div>
              <div className="break-words">{log.text}</div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
