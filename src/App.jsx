import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Header from './components/Header';
import SimulatorView from './components/SimulatorView';
import AgentOrchestrationView from './components/AgentOrchestrationView';
import MethodologyView from './components/MethodologyView';
import { Globe2, ShieldCheck, GitBranch, Cpu, Terminal } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('simulator');
  const [activeRegionId, setActiveRegionId] = useState('anantapur');

  return (
    <div className="min-h-screen bg-darkbg-900 text-slate-100 flex flex-col selection:bg-cyan-500 selection:text-black bg-tech-grid">
      {/* Top Header Navigation */}
      <Header activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Content Viewport */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <AnimatePresence mode="wait">
          {activeTab === 'simulator' && (
            <motion.div
              key="simulator"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.25 }}
            >
              <SimulatorView
                activeRegionId={activeRegionId}
                setActiveRegionId={setActiveRegionId}
              />
            </motion.div>
          )}

          {activeTab === 'orchestration' && (
            <motion.div
              key="orchestration"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.25 }}
            >
              <AgentOrchestrationView />
            </motion.div>
          )}

          {activeTab === 'methodology' && (
            <motion.div
              key="methodology"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.25 }}
            >
              <MethodologyView />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Footer Command Bar */}
      <footer className="border-t border-slate-800 glass-panel py-6 text-xs font-mono text-slate-400">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Globe2 className="w-4 h-4 text-cyan-400" />
            <span>GeoCounterfactual — Final-Year Engineering Project Prototype</span>
          </div>

          <div className="flex items-center gap-4 text-[11px]">
            <span className="flex items-center gap-1 text-emerald-400">
              <ShieldCheck className="w-3.5 h-3.5" /> Physics Critic Guarded
            </span>
            <span className="flex items-center gap-1 text-cyan-400">
              <GitBranch className="w-3.5 h-3.5" /> LangGraph Orchestration
            </span>
            <span className="flex items-center gap-1 text-indigo-400">
              <Cpu className="w-3.5 h-3.5" /> ControlNet Diffusion
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
