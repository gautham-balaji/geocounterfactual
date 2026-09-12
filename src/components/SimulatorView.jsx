import React, { useState, useEffect } from 'react';
import confetti from 'canvas-confetti';
import { Sparkles, Play, RotateCcw, MapPin, Send, Cpu, CheckCircle2, AlertTriangle, Layers } from 'lucide-react';
import Globe3D from './Globe3D';
import SatelliteSlider from './SatelliteSlider';
import MetricsPanel from './MetricsPanel';
import { MOCK_REGIONS } from '../data/mockData';
import { simulateStreaming, checkHealth } from '../services/api';

export default function SimulatorView({ activeRegionId, setActiveRegionId, onLogsChange }) {
  const selectedRegion = MOCK_REGIONS.find(r => r.id === activeRegionId) || MOCK_REGIONS[0];
  const [selectedPresetId, setSelectedPresetId] = useState(selectedRegion.presets[0]?.id || 'checkdams');
  const [inputText, setInputText] = useState(selectedRegion.presets[0]?.text || '');
  const [activeLayer, setActiveLayer] = useState('optical');

  const [isSimulating, setIsSimulating] = useState(false);
  const [simStep, setSimStep] = useState(0); // 0 = idle, 1..5 = steps, 6 = completed
  const [result, setResult] = useState(null);
  const [backend, setBackend] = useState({ online: false });

  // Probe once so the banner can say honestly whether the numbers on screen
  // came from the pipeline or from mock data.
  useEffect(() => {
    let cancelled = false;
    checkHealth().then((h) => { if (!cancelled) setBackend(h); });
    return () => { cancelled = true; };
  }, []);

  const activePreset = selectedRegion.presets.find(p => p.id === selectedPresetId) || selectedRegion.presets[0];

  const handleSelectPreset = (preset) => {
    setSelectedPresetId(preset.id);
    setInputText(preset.text);
  };

  // Node completion order -> the 5-step progress bar.
  const NODE_STEP = {
    input_handler: 1, planner: 2, dynamics: 3, generator: 4, critic: 5,
  };

  const handleRunSimulation = async () => {
    setIsSimulating(true);
    setSimStep(1);
    setResult(null);
    onLogsChange?.([]);

    // The progress bar is now driven by real node completions rather than
    // five hardcoded setTimeouts, so it tracks the pipeline -- including the
    // critic sending the generator back around.
    const collected = [];
    const payload = await simulateStreaming({
      regionId: selectedRegion.id,
      interventionText: inputText,
      targetYears: 5,
      onNode: ({ node, logs }) => {
        if (logs?.length) {
          collected.push(...logs);
          onLogsChange?.([...collected]);
        }
        const step = NODE_STEP[node];
        if (step) setSimStep(step);
      },
    });

    setResult(payload);
    if (payload.execution_logs?.length) onLogsChange?.(payload.execution_logs);
    setSimStep(6);
    setIsSimulating(false);

    if (payload.is_approved !== false) {
      confetti({
        particleCount: 50,
        spread: 60,
        origin: { y: 0.7 },
        colors: ['#10b981', '#06b6d4', '#3b82f6']
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Upper Status Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 glass-panel p-4 rounded-2xl border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <Cpu className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-cyan-400">
              <span>COUNTERFACTUAL SIMULATOR ENGINE</span>
              <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px]">READY</span>
            </div>
            <h2 className="text-base font-bold text-white mt-0.5">
              Region: <span className="text-cyan-300">{selectedRegion.name}</span> ({selectedRegion.state})
            </h2>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <span className="bg-darkbg-800 px-3 py-1.5 rounded-lg border border-slate-700">
            Climate: <strong className="text-slate-200">{selectedRegion.climateZone}</strong>
          </span>
          <span className="bg-darkbg-800 px-3 py-1.5 rounded-lg border border-slate-700">
            Baseline NDVI: <strong className="text-slate-200">{selectedRegion.baselineMetrics.ndvi}</strong>
          </span>
        </div>
      </div>

      {/* Main Grid: Left Control Panel vs Right Visual Output */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column (5/12): 3D Globe + Intervention Input Panel */}
        <div className="lg:col-span-5 space-y-6">
          {/* 3D Interactive Rotating Earth Globe */}
          <Globe3D
            regions={MOCK_REGIONS}
            selectedRegionId={activeRegionId}
            onSelectRegion={(id) => {
              setActiveRegionId(id);
              const newReg = MOCK_REGIONS.find(r => r.id === id);
              if (newReg && newReg.presets.length > 0) {
                setSelectedPresetId(newReg.presets[0].id);
                setInputText(newReg.presets[0].text);
              }
            }}
          />

          {/* Intervention Input Box & Preset Buttons */}
          <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
            <div className="flex items-center justify-between">
              <label className="text-xs font-mono font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                <Send className="w-4 h-4 text-cyan-400" /> NATURAL LANGUAGE INTERVENTION
              </label>
              <span className="text-[11px] font-mono text-cyan-400">Prompt Guided</span>
            </div>

            {/* Prompt Textarea */}
            <div className="relative">
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                rows={3}
                placeholder="Describe your rural land intervention in natural language (e.g. 'Build 3 check-dams along stream bed')..."
                className="w-full bg-darkbg-900 border border-slate-700 focus:border-cyan-500 rounded-xl p-3 text-sm text-slate-100 placeholder-slate-500 font-sans focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition resize-none"
              />
              <div className="absolute bottom-2.5 right-3 text-[10px] font-mono text-slate-500">
                {inputText.length} chars
              </div>
            </div>

            {/* Presets List */}
            <div className="space-y-2">
              <div className="text-[11px] font-mono text-slate-400 uppercase">Quick Presets for {selectedRegion.name.split(' ')[0]}:</div>
              <div className="space-y-1.5">
                {selectedRegion.presets.map((preset) => {
                  const isSelected = preset.id === selectedPresetId;
                  return (
                    <button
                      key={preset.id}
                      onClick={() => handleSelectPreset(preset)}
                      className={`w-full text-left p-2.5 rounded-xl border text-xs transition flex items-start justify-between ${
                        isSelected
                          ? 'bg-cyan-950/40 border-cyan-500/60 text-cyan-200'
                          : 'bg-darkbg-800/60 border-slate-800 text-slate-300 hover:bg-slate-800/80 hover:border-slate-700'
                      }`}
                    >
                      <div>
                        <div className="font-semibold text-white">{preset.title}</div>
                        <div className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">{preset.text}</div>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono shrink-0 ml-2 ${isSelected ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' : 'bg-slate-800 text-slate-400'}`}>
                        {preset.metricsDelta.plausibilityScore}% Score
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Run Simulation Action Button */}
            <button
              onClick={handleRunSimulation}
              disabled={isSimulating || !inputText.trim()}
              className={`w-full py-3.5 px-4 rounded-xl font-mono text-sm font-bold transition flex items-center justify-center gap-2.5 shadow-xl ${
                isSimulating
                  ? 'bg-cyan-950 text-cyan-400 border border-cyan-500/50 cursor-wait'
                  : 'bg-gradient-to-r from-emerald-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-slate-950 font-extrabold shadow-glow-emerald hover:scale-[1.01]'
              }`}
            >
              {isSimulating ? (
                <>
                  <div className="w-4 h-4 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
                  <span>EXECUTING MULTI-AGENT PIPELINE...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>SIMULATE COUNTERFACTUAL</span>
                </>
              )}
            </button>

            {/* Pipeline Execution HUD Step Progress */}
            {isSimulating && (
              <div className="p-3 rounded-xl bg-darkbg-900 border border-cyan-500/40 space-y-2 animate-fadeIn">
                <div className="flex items-center justify-between text-xs font-mono text-cyan-400 font-bold">
                  <span>ORCHESTRATING AGENTS</span>
                  <span>Step {simStep} of 5</span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-emerald-400 to-cyan-400 h-full transition-all duration-500"
                    style={{ width: `${(simStep / 5) * 100}%` }}
                  />
                </div>
                <div className="text-xs font-mono text-slate-300">
                  {simStep === 1 && '📥 Input Handler: Ingesting Sentinel-2 Bands & Text...'}
                  {simStep === 2 && '🗺️ Intervention Planner: Painting Spatial Stream Mask...'}
                  {simStep === 3 && '🌱 Eco-Hydrological Dynamics: Computing 5-Year Infiltration...'}
                  {simStep === 4 && '🎨 Generator (Diffusion): Synthesizing Counterfactual Scene...'}
                  {simStep === 5 && '🛡️ Physical-Plausibility Critic: Evaluating Slope & DEM Constraints...'}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column (7/12): Satellite Slider + Metrics Audit Panel */}
        <div className="lg:col-span-7 space-y-6">
          {/* Before & After Satellite Image Slider */}
          <SatelliteSlider
            imagery={result?.imagery ?? null}
            region={selectedRegion}
            activePreset={activePreset}
            activeLayer={activeLayer}
            setActiveLayer={setActiveLayer}
          />

          {/* Metrics & Physical Plausibility Audit Panel */}
          <MetricsPanel
            selectedRegion={selectedRegion}
            activePreset={activePreset}
            simulationResult={simStep === 6}
            liveResult={result}
          />
        </div>
      </div>
    </div>
  );
}
