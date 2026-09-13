import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldCheck, GitBranch, Cpu } from 'lucide-react';
import Header from './components/Header';
import LandingPage from './components/LandingPage';
import SimulatorView from './components/SimulatorView';
import MethodologyView from './components/MethodologyView';

export default function App() {
  const [entered, setEntered] = useState(false);
  const [activeTab, setActiveTab] = useState('simulator');
  const [activeRegionId, setActiveRegionId] = useState('anantapur');
  // The agent stream lives inside the Command Center alongside the imagery,
  // so the separate flowchart tab is gone. Kept lifted so another consumer
  // can read the same run.
  const [liveLogs, setLiveLogs] = useState([]);

  return (
    <AnimatePresence mode="wait">
      {!entered ? (
        <motion.div
          key="landing"
          exit={{ opacity: 0 }}
          transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        >
          <LandingPage onEnter={() => setEntered(true)} />
        </motion.div>
      ) : (
        <motion.div
          key="app"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="min-h-screen bg-surface-base text-ink-primary flex flex-col"
        >
          <Header activeTab={activeTab} setActiveTab={setActiveTab} />

          <main className="flex-1 w-full max-w-[1600px] mx-auto px-6 sm:px-8 lg:px-10 py-6 lg:py-8">
            <AnimatePresence mode="wait">
              {activeTab === 'simulator' && (
                <motion.div
                  key="simulator"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                >
                  <SimulatorView
                    activeRegionId={activeRegionId}
                    setActiveRegionId={setActiveRegionId}
                    onLogsChange={setLiveLogs}
                  />
                </motion.div>
              )}

              {activeTab === 'methodology' && (
                <motion.div
                  key="methodology"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                >
                  <MethodologyView />
                </motion.div>
              )}
            </AnimatePresence>
          </main>

          <footer className="border-t border-line py-4">
            <div className="max-w-[1600px] mx-auto px-6 sm:px-8 lg:px-10 flex flex-col sm:flex-row items-center justify-between gap-3 text-micro text-ink-tertiary">
              <span>
                GeoCounterfactual · final-year engineering research prototype
              </span>
              <div className="flex items-center gap-6">
                <span className="flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5" strokeWidth={1.75} />
                  Physics critic
                </span>
                <span className="flex items-center gap-1.5">
                  <GitBranch className="w-3.5 h-3.5" strokeWidth={1.75} />
                  LangGraph
                </span>
                <span className="flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5" strokeWidth={1.75} />
                  ControlNet diffusion
                </span>
              </div>
            </div>
          </footer>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
