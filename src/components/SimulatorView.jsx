import React, { useState, useEffect } from 'react';
import confetti from 'canvas-confetti';
import { Sparkles, Play, RotateCcw, MapPin, Send, Cpu, CheckCircle2,
         AlertTriangle, Layers, FileText, Trees, ShieldCheck } from 'lucide-react';
import Globe3D from './Globe3D';
import SatelliteSlider from './SatelliteSlider';
import MetricsPanel from './MetricsPanel';
import { MOCK_REGIONS } from '../data/mockData';
import { simulateStreaming, checkHealth } from '../services/api';
import XAIOverlay, { XAIToolbar } from './XAIOverlay';
import DiffCanvas from './DiffCanvas';
import AgentTerminal from './AgentTerminal';
import PipelineRail from './PipelineRail';
import RegionPicker from './RegionPicker';

export default function SimulatorView({ activeRegionId, setActiveRegionId, onLogsChange }) {
  const selectedRegion = MOCK_REGIONS.find(r => r.id === activeRegionId) || MOCK_REGIONS[0];
  const [selectedPresetId, setSelectedPresetId] = useState(selectedRegion.presets[0]?.id || 'checkdams');
  const [inputText, setInputText] = useState(selectedRegion.presets[0]?.text || '');
  const [activeLayer, setActiveLayer] = useState('optical');

  const [isSimulating, setIsSimulating] = useState(false);
  const [simStep, setSimStep] = useState(0); // 0 = idle, 1..5 = steps, 6 = completed
  const [result, setResult] = useState(null);
  const [backend, setBackend] = useState({ online: false });
  const [logs, setLogs] = useState([]);

  // Free-roam target picked off the globe. Null means "a pilot zone is
  // selected"; anything else is an unverified location.
  const [freeTarget, setFreeTarget] = useState(null);

  // xAI overlay state
  const [activeOverlays, setActiveOverlays] = useState(new Set());
  const [overlayOpacity, setOverlayOpacity] = useState(0.85);
  const [amplify, setAmplify] = useState(false);
  const [gain, setGain] = useState(6);
  const [blink, setBlink] = useState(false);
  const [loupe, setLoupe] = useState(false);

  const toggleOverlay = (id) => setActiveOverlays((prev) => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  // Only verified pilot zones can be simulated: the backend has a curated
  // bbox, CRS and baseline window for each, and nothing else. Free-roam
  // exploration stays available, it just cannot arm a run.
  const targetIsVerified = freeTarget === null;

  // Probe once so the banner can say honestly whether the numbers on screen
  // came from the pipeline or from mock data.
  useEffect(() => {
    let cancelled = false;
    checkHealth().then((h) => { if (!cancelled) setBackend(h); });
    return () => { cancelled = true; };
  }, []);

  // Drop stale output when the target changes, or the panel keeps showing
  // another region's imagery and metrics next to the new region's name.
  useEffect(() => {
    setResult(null);
    setLogs([]);
    setActiveOverlays(new Set());
    setSimStep(0);
    onLogsChange?.([]);
  }, [activeRegionId]);

  const activePreset = selectedRegion.presets.find(p => p.id === selectedPresetId) || selectedRegion.presets[0];

  const handleSelectRegion = (id) => {
    setFreeTarget(null);
    setActiveRegionId(id);
    const next = MOCK_REGIONS.find((r) => r.id === id);
    if (next && next.presets.length > 0) {
      setSelectedPresetId(next.presets[0].id);
      setInputText(next.presets[0].text);
    }
  };

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
    setLogs([]);
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
          setLogs([...collected]);
          onLogsChange?.([...collected]);
        }
        const step = NODE_STEP[node];
        if (step) setSimStep(step);
      },
    });

    setResult(payload);
    if (payload.execution_logs?.length) {
      setLogs(payload.execution_logs);
      onLogsChange?.(payload.execution_logs);
    }
    // Surface the critic's rejection immediately -- it is the single most
    // informative overlay and the reason the loop exists.
    if (payload.overlay_stats?.rejection_px > 0) {
      setActiveOverlays(new Set(['rejection', 'footprint']));
    } else if (payload.overlays) {
      setActiveOverlays(new Set(['footprint']));
    }
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
    <div className="space-y-10">
      {/* Upper Status Banner */}
      <div className="flex flex-wrap items-center justify-between gap-6 glass-panel p-6 rounded-xl">
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
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 xl:gap-12 items-start">
        {/* Left Column (5/12): 3D Globe + Intervention Input Panel */}
        <div className="lg:col-span-5 space-y-8">
          {/* 3D Interactive Rotating Earth Globe */}
          <Globe3D
            regions={MOCK_REGIONS}
            selectedRegionId={activeRegionId}
            freeTarget={freeTarget}
            onPickTarget={(t) => setFreeTarget(t)}
            onSelectRegion={handleSelectRegion}
          />

          {/* Target status: free navigation is always allowed, simulation is
              not. Saying exactly why is better than a dead button. */}
          <div className={`glass-panel p-3 rounded-xl border text-xs font-mono flex items-start gap-2.5 ${
            targetIsVerified
              ? 'border-emerald-500/40 bg-emerald-950/20'
              : 'border-amber-500/50 bg-amber-950/20'
          }`}>
            {targetIsVerified ? (
              <>
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <div>
                  <div className="text-emerald-300 font-bold">VERIFIED PILOT ZONE</div>
                  <div className="text-slate-400 mt-0.5">
                    {selectedRegion.name} — calibrated baseline, DEM and cloud-free window on file.
                  </div>
                </div>
              </>
            ) : (
              <>
                <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <div className="text-amber-300 font-bold">UNVERIFIED TARGET</div>
                  <div className="text-slate-400 mt-0.5 leading-relaxed">
                    {freeTarget.lat.toFixed(3)}°, {freeTarget.lng.toFixed(3)}° has no calibrated
                    baseline or agro-climatic validation. Explore freely; simulation is
                    restricted to the {MOCK_REGIONS.length} pilot watersheds.
                  </div>
                  <button
                    onClick={() => setFreeTarget(null)}
                    className="mt-2 px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] border border-slate-700 transition"
                  >
                    Return to {selectedRegion.name.split(',')[0]}
                  </button>
                </div>
              </>
            )}
          </div>

          <RegionPicker
            regions={MOCK_REGIONS}
            selectedId={activeRegionId}
            onSelect={handleSelectRegion}
            disabled={isSimulating}
          />

          {/* Intervention Input Box & Preset Buttons */}
          <div className="glass-panel p-6 rounded-xl space-y-5">
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
              disabled={isSimulating || !inputText.trim() || !targetIsVerified}
              title={!targetIsVerified
                ? 'Simulation is restricted to verified pilot watersheds'
                : undefined}
              className={`w-full py-3.5 px-4 rounded-xl font-mono text-sm font-bold transition flex items-center justify-center gap-2.5 shadow-xl ${
                isSimulating
                  ? 'bg-cyan-950 text-cyan-400 border border-cyan-500/50 cursor-wait'
                  : !targetIsVerified || !inputText.trim()
                  ? 'bg-slate-800/70 text-slate-500 border border-slate-700 cursor-not-allowed'
                  : 'bg-gradient-to-r from-emerald-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-slate-950 font-extrabold shadow-glow-emerald hover:scale-[1.01]'
              }`}
            >
              {isSimulating ? (
                <>
                  <div className="w-4 h-4 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
                  <span>EXECUTING MULTI-AGENT PIPELINE...</span>
                </>
              ) : !targetIsVerified ? (
                <>
                  <AlertTriangle className="w-4 h-4" />
                  <span>SELECT A VERIFIED PILOT ZONE</span>
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
              <div className="p-4 rounded-lg bg-surface-2 border border-line space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-micro uppercase tracking-wider text-ink-tertiary">Orchestrating agents</span>
                  <span className="font-mono text-micro text-ink-secondary">{simStep} / 5</span>
                </div>
                <div className="w-full bg-surface-3 h-1 rounded-full overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-emerald-400 to-cyan-400 h-full transition-all duration-500"
                    style={{ width: `${(simStep / 5) * 100}%` }}
                  />
                </div>
                <div className="text-label text-ink-secondary">
                {(() => {
                  const STEP_STATUS = [
                    null,
                    [FileText, 'Input Handler', 'Ingesting Sentinel-2 bands and DEM'],
                    [MapPin, 'Intervention Planner', 'Routing drainage, siting structures'],
                    [Trees, 'Eco-Hydrological Dynamics', 'Computing the 5-year growth envelope'],
                    [Cpu, 'Generator', 'Synthesizing the counterfactual scene'],
                    [ShieldCheck, 'Physical-Plausibility Critic', 'Evaluating slope and DEM constraints'],
                  ];
                  const entry = STEP_STATUS[simStep];
                  if (!entry) return null;
                  const [Icon, agent, detail] = entry;
                  return (
                    <span className="flex items-center gap-2 min-w-0">
                      <Icon className="w-3.5 h-3.5 text-accent-soft shrink-0" strokeWidth={1.75} />
                      <span className="truncate">
                        <span className="text-ink-primary">{agent}</span>
                        <span className="text-ink-tertiary"> \u2014 {detail}</span>
                      </span>
                    </span>
                  );
                })()}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column (7/12): Satellite Slider + xAI + live terminal */}
        <div className="lg:col-span-7 space-y-8">
          {/* Before & After Satellite Image Slider */}
          <SatelliteSlider
            imagery={result?.imagery ?? null}
            region={selectedRegion}
            activePreset={activePreset}
            activeLayer={activeLayer}
            setActiveLayer={setActiveLayer}
            blink={blink}
            loupe={loupe}
          >
            <XAIOverlay
              overlays={result?.overlays}
              active={activeOverlays}
              opacity={overlayOpacity}
            />
            <DiffCanvas
              beforeSrc={result?.imagery?.optical?.before}
              afterSrc={result?.imagery?.optical?.after}
              gain={gain}
              visible={amplify && Boolean(result?.imagery)}
            />
          </SatelliteSlider>

          <XAIToolbar
            overlays={result?.overlays}
            stats={result?.overlay_stats}
            active={activeOverlays}
            onToggle={toggleOverlay}
            opacity={overlayOpacity}
            onOpacity={setOverlayOpacity}
            amplify={amplify}
            onAmplify={() => setAmplify((v) => !v)}
            gain={gain}
            onGain={setGain}
            blink={blink}
            onBlink={() => setBlink((v) => !v)}
            loupe={loupe}
            onLoupe={() => setLoupe((v) => !v)}
          />

          {/* Command-center side-by-side: the agent stream sits next to the
              imagery, so the Critic's rejection and the pixels it rejected
              are visible in one glance instead of on separate tabs. */}
          <div className="grid grid-cols-1 xl:grid-cols-5 gap-6 items-start">
            <div className="xl:col-span-2 space-y-4">
              <PipelineRail
                logs={logs}
                isRunning={isSimulating}
                iterations={result?.critic_iterations ?? 0}
              />
            </div>
            <div className="xl:col-span-3">
              <AgentTerminal
                logs={logs}
                isLive={logs.length > 0}
                isRunning={isSimulating}
                heightClass="h-[360px]"
                title="AGENT CHATTER"
              />
            </div>
          </div>

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
