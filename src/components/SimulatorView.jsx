import React, { useState, useEffect } from 'react';
import { Sparkles, MapPin, Send, Cpu, CheckCircle2, AlertTriangle,
         FileText, Trees, ShieldCheck } from 'lucide-react';
import { cn, Panel, Button, Badge, Label, Divider } from './ui/primitives';
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

  };

  return (
    <div className="space-y-12">
      {/* Region header */}
      <div className="flex flex-wrap items-end justify-between gap-6 pb-8 border-b border-line">
        <div className="space-y-2 min-w-0">
          <Label>Counterfactual simulator</Label>
          <h2 className="text-h1 font-medium text-ink-primary truncate">
            {selectedRegion.name}
          </h2>
          <p className="text-label text-ink-tertiary">
            {selectedRegion.state}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-x-10 gap-y-4">
          {[
            ['Climate zone', selectedRegion.climateZone],
            ['Baseline NDVI', selectedRegion.baselineMetrics.ndvi],
            ['Built-up', selectedRegion.baselineMetrics.builtUp ?? '—'],
            ['Rainfall', selectedRegion.baselineMetrics.rainfall],
          ].map(([label, value]) => (
            <div key={label} className="space-y-1">
              <Label>{label}</Label>
              <div className="font-mono text-label text-ink-primary">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Main Grid: Left Control Panel vs Right Visual Output */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 xl:gap-16 items-start">
        {/* Left Column (5/12): 3D Globe + Intervention Input Panel */}
        <div className="lg:col-span-5 space-y-10">
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
          <div className={cn(
            'rounded-lg border px-4 py-3 flex items-start gap-3',
            targetIsVerified
              ? 'border-line bg-surface-1'
              : 'border-caution/30 bg-caution/5',
          )}>
            {targetIsVerified ? (
              <>
                <CheckCircle2 className="w-4 h-4 text-positive shrink-0 mt-0.5" strokeWidth={1.75} />
                <div>
                  <div className="text-label text-ink-primary">Verified pilot zone</div>
                  <div className="text-micro text-ink-tertiary mt-1 leading-relaxed">
                    {selectedRegion.name} — calibrated baseline, DEM and cloud-free window on file.
                  </div>
                </div>
              </>
            ) : (
              <>
                <AlertTriangle className="w-4 h-4 text-caution shrink-0 mt-0.5" strokeWidth={1.75} />
                <div className="flex-1">
                  <div className="text-label text-caution">Unverified target</div>
                  <div className="text-micro text-ink-tertiary mt-1 leading-relaxed">
                    {freeTarget.lat.toFixed(3)}°, {freeTarget.lng.toFixed(3)}° has no calibrated
                    baseline or agro-climatic validation. Explore freely; simulation is
                    restricted to the {MOCK_REGIONS.length} pilot watersheds.
                  </div>
                  <button
                    onClick={() => setFreeTarget(null)}
                    className="mt-2.5 px-2.5 h-7 rounded-md bg-surface-2 hover:bg-surface-3 text-ink-secondary hover:text-ink-primary text-micro border border-line transition-colors duration-150"
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
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Send className="w-3.5 h-3.5 text-ink-tertiary" strokeWidth={1.75} />
                <Label>Intervention</Label>
              </div>
            </div>

            {/* Prompt Textarea */}
            <div className="relative">
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                rows={3}
                placeholder="Describe your rural land intervention in natural language (e.g. 'Build 3 check-dams along stream bed')..."
                className="w-full rounded-lg bg-surface-2 border border-line hover:border-line-strong focus:border-accent focus:outline-none p-3.5 text-body text-ink-primary placeholder-ink-tertiary resize-none transition-colors duration-150"
              />
              <div className="absolute bottom-3 right-3 font-mono text-micro text-ink-tertiary">
                {inputText.length} chars
              </div>
            </div>

            {/* Presets List */}
            <div className="space-y-2">
              <Label>Presets</Label>
              <div className="space-y-1.5">
                {selectedRegion.presets.map((preset) => {
                  const isSelected = preset.id === selectedPresetId;
                  return (
                    <button
                      key={preset.id}
                      onClick={() => handleSelectPreset(preset)}
                      className={cn(
                        'w-full text-left px-3 py-2.5 rounded-lg flex items-start justify-between gap-3',
                        'transition-colors duration-150',
                        isSelected
                          ? 'bg-accent-subtle'
                          : 'hover:bg-surface-2',
                      )}
                    >
                      <div>
                        <div className="text-label text-ink-primary">{preset.title}</div>
                        <div className="text-micro text-ink-tertiary line-clamp-1 mt-0.5">{preset.text}</div>
                      </div>
                      <span className="font-mono text-micro text-ink-tertiary shrink-0 mt-0.5">
                        {preset.metricsDelta.plausibilityScore}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Run Simulation Action Button */}
            <Button
              variant="primary"
              size="lg"
              className="w-full"
              onClick={handleRunSimulation}
              disabled={isSimulating || !inputText.trim() || !targetIsVerified}
              title={!targetIsVerified
                ? 'Simulation is restricted to verified pilot watersheds'
                : undefined}
              icon={isSimulating ? undefined : !targetIsVerified ? AlertTriangle : Sparkles}
            >
              {isSimulating ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  Running pipeline
                </>
              ) : !targetIsVerified ? (
                'Select a verified pilot zone'
              ) : (
                'Simulate counterfactual'
              )}
            </Button>

            {/* Pipeline Execution HUD Step Progress */}
            {isSimulating && (
              <div className="p-4 rounded-lg bg-surface-2 border border-line space-y-3">
                <div className="flex items-center justify-between">
                  <Label>Orchestrating agents</Label>
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
        <div className="lg:col-span-7 space-y-10">
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
          <div className="grid grid-cols-1 xl:grid-cols-5 gap-8 items-start">
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
