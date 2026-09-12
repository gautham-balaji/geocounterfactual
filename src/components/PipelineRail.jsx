import React from 'react';
import { FileText, MapPin, Trees, Cpu, ShieldCheck, CornerUpLeft } from 'lucide-react';

/**
 * Compact vertical status rail for the Command Center side pane.
 *
 * A condensed stand-in for the full flowchart: five nodes, current state,
 * and the critic feedback edge lighting up when the loop actually fires.
 * Derived from the live logs rather than a playback timer.
 */

const NODES = [
  { id: 'node-1', agent: 'Input Handler', label: 'Input Handler', icon: FileText },
  { id: 'node-2', agent: 'Intervention-Planner', label: 'Planner', icon: MapPin },
  { id: 'node-3', agent: 'Eco-Hydrological Dynamics', label: 'Dynamics', icon: Trees },
  { id: 'node-4', agent: 'Generator (Diffusion)', label: 'Generator', icon: Cpu },
  { id: 'node-5', agent: 'Physical-Plausibility Critic', label: 'Critic', icon: ShieldCheck },
];

export default function PipelineRail({ logs = [], isRunning = false,
                                       iterations = 0 }) {
  const seen = new Set(logs.map((l) => l.agent));
  const last = logs[logs.length - 1];
  const rejected = logs.some((l) => l.type === 'reject');
  // Loop is "hot" while a rejection is the most recent verdict.
  const loopActive = logs.slice(-3).some((l) => l.type === 'reject');

  return (
    <div className="glass-panel p-3 rounded-xl border border-slate-800">
      <div className="flex items-center justify-between text-xs font-mono border-b border-slate-800 pb-2 mb-2">
        <span className="text-cyan-400 font-bold">AGENT PIPELINE</span>
        {iterations > 0 && (
          <span className="text-slate-400">
            iteration {iterations}
          </span>
        )}
      </div>

      <div className="space-y-1">
        {NODES.map((node, i) => {
          const done = seen.has(node.agent);
          const active = isRunning && last?.agent === node.agent;
          const Icon = node.icon;
          return (
            <div key={node.id}>
              <div
                className={`flex items-center gap-2.5 px-2 py-1.5 rounded-lg border transition ${
                  active
                    ? 'bg-cyan-500/15 border-cyan-500/50'
                    : done
                    ? 'bg-darkbg-800/70 border-slate-800'
                    : 'bg-transparent border-transparent opacity-45'
                }`}
              >
                <Icon
                  className={`w-3.5 h-3.5 shrink-0 ${
                    active ? 'text-cyan-300 animate-pulse'
                           : done ? 'text-emerald-400' : 'text-slate-600'
                  }`}
                />
                <span className={`text-[11px] font-mono flex-1 ${
                  active ? 'text-cyan-200 font-semibold'
                         : done ? 'text-slate-300' : 'text-slate-500'
                }`}>
                  {node.label}
                </span>
                <span className={`w-1.5 h-1.5 rounded-full ${
                  active ? 'bg-cyan-400 animate-ping-slow'
                         : done ? 'bg-emerald-400' : 'bg-slate-700'
                }`} />
              </div>

              {/* The critic -> generator feedback edge, between nodes 4 and 5 */}
              {i === 3 && rejected && (
                <div className={`flex items-center gap-1.5 pl-3 py-0.5 text-[10px] font-mono ${
                  loopActive ? 'text-rose-300' : 'text-rose-400/50'
                }`}>
                  <CornerUpLeft className={`w-3 h-3 ${loopActive ? 'animate-pulse' : ''}`} />
                  critic feedback loop
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
