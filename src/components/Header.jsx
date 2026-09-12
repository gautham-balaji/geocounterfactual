import React from 'react';
import { Globe2, Play, GitBranch, Database, ShieldCheck, Activity } from 'lucide-react';

export default function Header({ activeTab, setActiveTab }) {
  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-slate-800 backdrop-blur-xl bg-darkbg-900/85">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand Logo & Title */}
        <div className="flex items-center gap-3 cursor-pointer" onClick={() => setActiveTab('simulator')}>
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-emerald-500 p-0.5 shadow-glow-cyan">
            <div className="w-full h-full bg-darkbg-900 rounded-[10px] flex items-center justify-center text-cyan-400">
              <Globe2 className="w-5 h-5 animate-pulse-slow" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-extrabold tracking-tight text-white font-mono">
                Geo<span className="text-cyan-400">Counterfactual</span>
              </h1>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                PROTOTYPE v1.0
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono hidden sm:block">
              Multi-Agent Generative Satellite Intervention Platform
            </p>
          </div>
        </div>

        {/* Tab Navigation Pills */}
        <nav className="flex items-center gap-1 bg-darkbg-800/90 p-1 rounded-xl border border-slate-800">
          {[
            { id: 'simulator', label: '1. Command Center', icon: Play },
            { id: 'methodology', label: '2. Data & Methodology', icon: Database }
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-mono font-medium transition ${
                  isActive
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/60 font-bold shadow-glow-cyan'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Status Indicators */}
        <div className="hidden lg:flex items-center gap-3 text-xs font-mono">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-darkbg-800 border border-slate-800 text-slate-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping-slow" />
            <span>Agent Graph: <strong className="text-emerald-400">ONLINE</strong></span>
          </div>

          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-darkbg-800 border border-slate-800 text-slate-300">
            <Activity className="w-3.5 h-3.5 text-cyan-400" />
            <span>GEE: <strong className="text-cyan-400">CONNECTED</strong></span>
          </div>
        </div>
      </div>
    </header>
  );
}
