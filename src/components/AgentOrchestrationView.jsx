import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  MapPin,
  Trees,
  Cpu,
  ShieldCheck,
  RotateCcw,
  Play,
  Pause,
  SkipForward,
  Terminal,
  AlertTriangle,
  CheckCircle2,
  GitBranch,
  CornerUpLeft
} from 'lucide-react';
import { MOCK_AGENT_NODES, MOCK_CRITIC_CHATTER } from '../data/mockData';

// Agent names emitted by backend/agents/logs.py -> flowchart node ids.
const AGENT_TO_NODE = {
  'Input Handler': 'node-1',
  'Intervention-Planner': 'node-2',
  'Eco-Hydrological Dynamics': 'node-3',
  'Generator (Diffusion)': 'node-4',
  'Physical-Plausibility Critic': 'node-5',
};

export default function AgentOrchestrationView({ liveLogs = null, isRunning = false }) {
  const [activeStep, setActiveStep] = useState(1);
  const [isPlaying, setIsPlaying] = useState(true);
  const [playbackSpeed, setPlaybackSpeed] = useState(1500); // ms per step
  const [activeNodeId, setActiveNodeId] = useState('node-1');
  const terminalRef = useRef(null);

  // When the backend is streaming, its logs replace the canned chatter and
  // the simulated playback timer stands down -- the real pipeline sets the
  // pace. With no backend the original demo loop is untouched.
  const isLive = Array.isArray(liveLogs) && liveLogs.length > 0;
  const logs = isLive ? liveLogs : MOCK_CRITIC_CHATTER;
  const visibleCount = isLive ? logs.length : activeStep;

  // Auto playback of agent steps (mock mode only)
  useEffect(() => {
    if (!isPlaying || isLive) return;
    const interval = setInterval(() => {
      setActiveStep((prev) => {
        const next = prev >= MOCK_CRITIC_CHATTER.length ? 1 : prev + 1;
        // Map chatter step to active node
        if (next === 1 || next === 2) setActiveNodeId('node-1');
        else if (next === 3 || next === 4) setActiveNodeId('node-2');
        else if (next === 5) setActiveNodeId('node-3');
        else if (next === 6 || next === 9 || next === 10) setActiveNodeId('node-4');
        else setActiveNodeId('node-5');
        return next;
      });
    }, playbackSpeed);

    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, isLive]);

  // In live mode the highlighted node follows whichever agent last spoke.
  useEffect(() => {
    if (!isLive) return;
    const last = logs[logs.length - 1];
    const nodeId = AGENT_TO_NODE[last?.agent];
    if (nodeId) setActiveNodeId(nodeId);
  }, [isLive, logs]);

  // Keep the newest line in view; a jury demo should not need scrolling.
  useEffect(() => {
    const el = terminalRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [visibleCount]);

  const handleStepForward = () => {
    setActiveStep((prev) => (prev >= MOCK_CRITIC_CHATTER.length ? 1 : prev + 1));
  };

  // The critic loop is "hot" whenever a rejection is the most recent verdict
  // and the generator is retrying -- derived from the logs in live mode
  // rather than from hardcoded step numbers.
  const isCriticLoopActive = isLive
    ? logs.slice(-3).some((l) => l.type === 'reject')
    : activeStep === 7 || activeStep === 8 || activeStep === 9;

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono font-bold text-cyan-400 uppercase tracking-wider">
            <GitBranch className="w-4 h-4" /> LANGGRAPH SYSTEM ARCHITECTURE
          </div>
          <h2 className="text-xl font-extrabold text-white mt-1">
            Multi-Agent Orchestration & Closed Critic Loop
          </h2>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            A society of specialized agents negotiating in a cyclic state graph. The Physical-Plausibility Critic evaluates candidate scenes and triggers automated regeneration feedback loops when rules are violated.
          </p>
        </div>

        {/* Playback Controls */}
        <div className="flex items-center gap-2 bg-darkbg-900/90 p-2 rounded-xl border border-slate-700/80">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className={`p-2 rounded-lg font-mono text-xs transition flex items-center gap-1.5 ${
              isPlaying
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
            }`}
          >
            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            {isPlaying ? 'Pause Simulation' : 'Play Simulation'}
          </button>

          <button
            onClick={handleStepForward}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs flex items-center gap-1 font-mono transition"
          >
            <SkipForward className="w-3.5 h-3.5" /> Step
          </button>

          <button
            onClick={() => setActiveStep(1)}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700 text-xs font-mono transition"
            title="Reset to Step 1"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          <div className="h-4 w-px bg-slate-800 mx-1" />

          {/* Speed Selector */}
          <select
            value={playbackSpeed}
            onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
            className="bg-darkbg-800 text-slate-300 text-xs font-mono px-2 py-1.5 rounded-lg border border-slate-700 focus:outline-none"
          >
            <option value={2500}>0.5x Speed</option>
            <option value={1500}>1.0x Speed</option>
            <option value={800}>2.0x Speed</option>
          </select>
        </div>
      </div>

      {/* Main Flowchart & Terminal Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Flowchart Diagram Canvas (7/12) */}
        <div className="lg:col-span-7 glass-panel p-6 rounded-2xl border border-slate-800 relative overflow-hidden min-h-[580px] flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs font-mono text-slate-400 border-b border-slate-800 pb-3">
            <span className="flex items-center gap-1.5 text-cyan-400 font-bold">
              <GitBranch className="w-4 h-4" /> CYCLIC AGENT STATE MACHINE
            </span>
            <span className="text-slate-500">Step {visibleCount} of {logs.length}{isLive ? ' · LIVE' : ''}</span>
          </div>

          {/* Nodes Container */}
          <div className="relative py-8 space-y-6 my-auto">
            {/* SVG Connecting Flow Lines & Critic Rejection Loop Arrow */}
            <svg className="absolute inset-0 w-full h-full pointer-events-none z-0" overflow="visible">
              <defs>
                <linearGradient id="flowGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#06b6d4" />
                  <stop offset="100%" stopColor="#10b981" />
                </linearGradient>
                <filter id="glowRed" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="4" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>

              {/* Vertical Linear Flow Line connecting Node 1 to Node 5 */}
              <line x1="50%" y1="20" x2="50%" y2="440" stroke="#1e293b" strokeWidth="4" />
              <line x1="50%" y1="20" x2="50%" y2="440" stroke="url(#flowGrad)" strokeWidth="2" className="flow-line-active" />

              {/* HIGHLIGHTED RED FEEDBACK LOOP ARROW (Node 5 Critic -> Node 4 Generator) */}
              <path
                d="M 58%, 420 C 85%, 420 85%, 310 58%, 310"
                fill="none"
                stroke={isCriticLoopActive ? '#f43f5e' : '#334155'}
                strokeWidth={isCriticLoopActive ? '4' : '2'}
                strokeDasharray={isCriticLoopActive ? '8,4' : '4,4'}
                filter={isCriticLoopActive ? 'url(#glowRed)' : 'none'}
                className={isCriticLoopActive ? 'flow-line-active' : ''}
              />

              {/* Red Feedback Arrow Head */}
              <polygon
                points="58%,305 58%,315 50%,310"
                fill={isCriticLoopActive ? '#f43f5e' : '#475569'}
              />
            </svg>

            {/* Render 5 Architecture Nodes */}
            {MOCK_AGENT_NODES.map((node, index) => {
              const isActive = activeNodeId === node.id;
              const isGenerator = node.id === 'node-4';
              const isCritic = node.id === 'node-5';

              return (
                <div key={node.id} className="relative z-10 flex items-center justify-center">
                  <motion.div
                    animate={{
                      scale: isActive ? 1.03 : 1,
                      borderColor: isActive
                        ? isCritic && isCriticLoopActive
                          ? '#f43f5e'
                          : '#06b6d4'
                        : 'rgba(30, 41, 59, 0.8)'
                    }}
                    className={`w-full max-w-md p-4 rounded-xl backdrop-blur-md transition-all duration-300 border ${
                      isActive
                        ? isCritic && isCriticLoopActive
                          ? 'bg-rose-950/60 border-rose-500 shadow-glow-red'
                          : 'bg-cyan-950/40 border-cyan-500 shadow-glow-cyan'
                        : 'bg-darkbg-800/80 border-slate-800'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-9 h-9 rounded-lg flex items-center justify-center font-mono font-bold text-xs ${
                            isActive
                              ? isCritic && isCriticLoopActive
                                ? 'bg-rose-500 text-white animate-bounce'
                                : 'bg-cyan-500 text-black'
                              : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          {node.shortCode}
                        </div>

                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-bold text-white">{node.name}</h4>
                            {isActive && (
                              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping-slow" />
                            )}
                          </div>
                          <div className="text-[11px] font-mono text-cyan-400">{node.role}</div>
                        </div>
                      </div>

                      {/* Loop Tag for Generator & Critic */}
                      {isGenerator && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 flex items-center gap-1">
                          <CornerUpLeft className="w-3 h-3 text-indigo-400" /> Target
                        </span>
                      )}

                      {isCritic && (
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border flex items-center gap-1 ${
                          isCriticLoopActive
                            ? 'bg-rose-500/20 text-rose-300 border-rose-500/60 animate-pulse font-bold'
                            : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                        }`}>
                          <ShieldCheck className="w-3 h-3" /> Gatekeeper
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-slate-300 mt-2 leading-relaxed">
                      {node.description}
                    </p>

                    {/* Animated Data Packet Glow Line */}
                    {isActive && (
                      <motion.div
                        layoutId="dataPacket"
                        className="mt-3 h-1 bg-gradient-to-r from-emerald-400 via-cyan-400 to-indigo-500 rounded-full"
                      />
                    )}
                  </motion.div>
                </div>
              );
            })}
          </div>

          {/* Critic Feedback Banner Overlay */}
          {isCriticLoopActive && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mt-4 p-3 rounded-xl bg-rose-950/80 border border-rose-500/60 flex items-center justify-between text-xs font-mono shadow-glow-red"
            >
              <div className="flex items-center gap-2 text-rose-300">
                <AlertTriangle className="w-4 h-4 text-rose-400 animate-bounce" />
                <span>CRITIC REJECTION ENGAGED: RE-SYNTHESIZING CONTROLNET MASK (ITERATION #2)</span>
              </div>
              <span className="text-rose-400 font-bold">NODE 5 → NODE 4</span>
            </motion.div>
          )}
        </div>

        {/* Live Log Terminal Console (5/12) */}
        <div className="lg:col-span-5 glass-panel p-5 rounded-2xl border border-slate-800 space-y-4 font-mono">
          <div className="flex items-center justify-between text-xs text-slate-300 border-b border-slate-800 pb-3">
            <span className="flex items-center gap-2 text-emerald-400 font-bold">
              <Terminal className="w-4 h-4" /> LIVE AGENT CHATTER STREAM
            </span>
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping-slow" />
          </div>

          {/* Terminal Output Window */}
          <div ref={terminalRef} className="bg-darkbg-900/90 rounded-xl p-4 border border-slate-800 h-[500px] overflow-y-auto space-y-3 text-xs">
            {logs.slice(0, visibleCount).map((log, index) => {
              const isReject = log.type === 'reject';
              // Backend emits 'warn'; the mock chatter uses 'warning'.
              const isWarning = log.type === 'warning' || log.type === 'warn';
              const isSuccess = log.type === 'success';

              return (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={`p-2.5 rounded-lg border leading-relaxed ${
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
                    <span>Step #{log.step}</span>
                  </div>
                  <div>{log.text}</div>
                </motion.div>
              );
            })}
          </div>

          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>Terminal Status: Active</span>
            <span className="text-cyan-400">LangGraph Cyclic Graph v2.4</span>
          </div>
        </div>
      </div>
    </div>
  );
}
