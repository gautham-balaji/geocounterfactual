import React, { useState, useRef } from 'react';
import { Layers, Sliders, Maximize2, ShieldCheck, Eye, Sparkles } from 'lucide-react';

// Maps the layer-selector ids to the keys in the backend's `imagery` payload.
// Layers that are model output rather than measured reflectance.
const MODELLED_LAYERS = new Set(['moisture', 'ndvi']);

const LAYER_TO_IMAGERY_KEY = {
  optical: 'optical',
  ndvi: 'ndvi',
  moisture: 'moisture',
  critic_mask: 'critic',
};

export default function SatelliteSlider({
  region, activePreset, activeLayer, setActiveLayer,
  imagery = null, children = null,
  blink = false, loupe = false, loupeZoom = 3,
}) {
  const [sliderPosition, setSliderPosition] = useState(50);
  const [isDragging, setIsDragging] = useState(false);
  const [blinkShowBefore, setBlinkShowBefore] = useState(false);
  const [cursor, setCursor] = useState(null);   // {xPct, yPct} for the loupe
  const viewportRef = useRef(null);

  // A/B blink. Alternating the two frames in place is markedly better than a
  // slider for spotting small changes -- the eye detects the flicker where a
  // static side-by-side comparison hides it behind a saccade.
  React.useEffect(() => {
    if (!blink) { setBlinkShowBefore(false); return; }
    const id = setInterval(() => setBlinkShowBefore((v) => !v), 500);
    return () => clearInterval(id);
  }, [blink]);

  // Real rasters when the backend supplied them; otherwise the original
  // client-side SVG scene, so the demo still works with the backend down.
  const imageryKey = LAYER_TO_IMAGERY_KEY[activeLayer] ?? 'optical';
  const layerUrls = imagery?.[imageryKey] ?? null;
  const hasRaster = Boolean(layerUrls?.before && layerUrls?.after);

  const handleMouseMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    if (loupe) {
      setCursor({
        xPct: ((e.clientX - rect.left) / rect.width) * 100,
        yPct: ((e.clientY - rect.top) / rect.height) * 100,
      });
    }
    if (!isDragging) return;
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    setSliderPosition((x / rect.width) * 100);
  };

  const handleTouchMove = (e) => {
    if (!isDragging || !e.touches[0]) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.touches[0].clientX - rect.left, rect.width));
    setSliderPosition((x / rect.width) * 100);
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Layer Selector Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 glass-panel p-2.5 rounded-xl border border-slate-800">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-mono font-semibold text-slate-300">SPECTRAL BAND VIEW:</span>
        </div>

        <div className="flex items-center gap-1 overflow-x-auto">
          {[
            { id: 'optical', label: 'Sentinel-2 Optical (RGB)' },
            { id: 'ndvi', label: 'NDVI Vegetation Heatmap' },
            { id: 'moisture', label: 'Soil Moisture Index' },
            { id: 'critic_mask', label: 'Critic Constraint Mask' }
          ].map((layer) => (
            <button
              key={layer.id}
              onClick={() => setActiveLayer(layer.id)}
              className={`text-xs px-3 py-1.5 rounded-lg font-mono transition ${
                activeLayer === layer.id
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/60 font-semibold shadow-glow-cyan'
                  : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-transparent'
              }`}
            >
              {layer.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Image Slider Viewport */}
      <div
        ref={viewportRef}
        className="relative w-full h-[460px] rounded-2xl overflow-hidden glass-panel border border-slate-800 select-none cursor-ew-resize group"
        onMouseDown={() => setIsDragging(true)}
        onMouseUp={() => setIsDragging(false)}
        onMouseLeave={() => { setIsDragging(false); setCursor(null); }}
        onMouseMove={handleMouseMove}
        onTouchStart={() => setIsDragging(true)}
        onTouchEnd={() => setIsDragging(false)}
        onTouchMove={handleTouchMove}
      >
        {/* Layer 1: AFTER (Generated Counterfactual Scene - Base Layer) */}
        <div className="absolute inset-0 w-full h-full">
          {hasRaster
            ? <RasterLayer src={layerUrls.after} alt="Generated counterfactual scene" />
            : <SatelliteImageGraphics layer={activeLayer} mode="after" region={region} />}
          {/* xAI overlays and the amplification canvas sit here so they
              inherit the same object-cover geometry as the raster and stay
              pixel-registered with it. */}
          {children}
          {/* Top Right Label */}
          <div className="absolute top-4 right-4 z-10 bg-emerald-950/80 backdrop-blur-md border border-emerald-500/60 px-3 py-1.5 rounded-lg flex items-center gap-2 shadow-glow-emerald">
            <Sparkles className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            <span className="text-xs font-mono font-bold text-emerald-300 uppercase tracking-wider">
              AFTER: SIMULATED COUNTERFACTUAL
            </span>
            {/* Moisture is the Dynamics agent's own prediction, not an
                observation. Saying so on the image removes the sharpest
                line of attack on the work. */}
            {MODELLED_LAYERS.has(activeLayer) && (
              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-500/20 text-amber-200 border border-amber-500/50">
                MODELLED
              </span>
            )}
          </div>
        </div>

        {/* Layer 2: BEFORE (Baseline Sentinel-2 Image - Clipped Layer)
            clip-path keeps this layer at full container size and simply hides
            the right-hand part, so BEFORE and AFTER stay pixel-registered.
            The previous approach shrank the wrapper and propped it open with
            a fixed minWidth, which cannot align two real georeferenced
            rasters -- the baseline would slide as the handle moved. */}
        <div
          className="absolute inset-0 w-full h-full"
          style={{
            clipPath: blink
              ? (blinkShowBefore ? 'inset(0 0 0 0)' : 'inset(0 100% 0 0)')
              : `inset(0 ${100 - sliderPosition}% 0 0)`,
            transition: blink ? 'none' : undefined,
          }}
        >
          <div className="relative w-full h-full">
            {hasRaster
              ? <RasterLayer src={layerUrls.before} alt="Baseline Sentinel-2 scene" />
              : <SatelliteImageGraphics layer={activeLayer} mode="before" region={region} />}
            {/* Top Left Label */}
            <div className="absolute top-4 left-4 z-10 bg-slate-900/80 backdrop-blur-md border border-slate-700 px-3 py-1.5 rounded-lg flex items-center gap-2">
              <Eye className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider">
                BEFORE: BASELINE SATELLITE
              </span>
            </div>
          </div>
        </div>

        {/* Vertical Divider Handle Line */}
        <div
          className="absolute top-0 bottom-0 w-1 bg-cyan-400 shadow-glow-cyan z-20 pointer-events-none"
          style={{ left: `${sliderPosition}%`, opacity: blink ? 0 : 1 }}
        >
          {/* Handle Pill */}
          <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-9 h-9 rounded-full bg-darkbg-900 border-2 border-cyan-400 flex items-center justify-center text-cyan-300 shadow-xl">
            <Sliders className="w-4 h-4 rotate-90" />
          </div>
        </div>

        {/* Loupe magnifier: before (left) and after (right) at 3x */}
        {loupe && cursor && hasRaster && (
          <div
            className="absolute z-30 pointer-events-none rounded-xl overflow-hidden border-2 border-sky-400/80 shadow-2xl"
            style={{
              width: 208, height: 104,
              left: `calc(${cursor.xPct}% - 104px)`,
              top: `calc(${cursor.yPct}% - 130px)`,
            }}
          >
            <div className="relative w-full h-full flex">
              {['before', 'after'].map((which) => (
                <div key={which} className="relative w-1/2 h-full overflow-hidden border-r border-sky-400/40 last:border-r-0">
                  <div
                    className="absolute inset-0"
                    style={{
                      backgroundImage: `url(${layerUrls[which]})`,
                      backgroundSize: `${loupeZoom * 100}% ${loupeZoom * 100}%`,
                      backgroundPosition: `${cursor.xPct}% ${cursor.yPct}%`,
                      backgroundRepeat: 'no-repeat',
                    }}
                  />
                  <span className="absolute bottom-0.5 left-1 text-[8px] font-mono font-bold text-white/90 drop-shadow">
                    {which.toUpperCase()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {blink && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 px-3 py-1 rounded-lg bg-violet-950/85 border border-violet-500/60 text-[11px] font-mono font-bold text-violet-200">
            A/B BLINK — showing {blinkShowBefore ? 'BEFORE' : 'AFTER'}
          </div>
        )}

        {/* Bottom Metadata HUD */}
        <div className="absolute bottom-4 left-4 right-4 z-10 flex items-center justify-between pointer-events-none">
          <div className="bg-darkbg-900/85 backdrop-blur-md border border-slate-700 px-3 py-1.5 rounded-lg text-[11px] font-mono text-slate-300">
            Coordinates: <span className="text-cyan-400">{region?.lat}°N, {region?.lng}°E</span> • Scale: 10m/px
          </div>

          <div className="bg-darkbg-900/85 backdrop-blur-md border border-slate-700 px-3 py-1.5 rounded-lg text-[11px] font-mono text-slate-300 flex items-center gap-1.5">
            <Sliders className="w-3 h-3 text-cyan-400" /> Drag horizontal slider to compare
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Renders a georeferenced PNG produced by the backend.
 *
 * `object-cover` with a fixed transform origin, identical on both halves, is
 * what keeps BEFORE and AFTER registered: the two rasters share a grid and an
 * affine transform on the server, and any difference in how they are fitted
 * here would break that correspondence and make the comparison meaningless.
 */
function RasterLayer({ src, alt }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-darkbg-900 text-slate-500 text-xs font-mono">
        Raster unavailable
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      draggable={false}
      onError={() => setFailed(true)}
      className="absolute inset-0 w-full h-full object-cover select-none pointer-events-none"
      style={{ imageRendering: 'auto' }}
    />
  );
}

// Custom Satellite Image Graphics Renderer (Generates rich SVG Satellite scene client-side)
function SatelliteImageGraphics({ layer, mode, region }) {
  const isBefore = mode === 'before';

  if (layer === 'ndvi') {
    // NDVI Vegetation Heatmap View
    return (
      <svg className="w-full h-full object-cover" viewBox="0 0 800 500" preserveAspectRatio="none">
        {/* Background Terrain Matrix */}
        <rect width="800" height="500" fill={isBefore ? '#1e241e' : '#0d2218'} />
        {/* Grid lines */}
        <path d="M 0,100 L 800,100 M 0,250 L 800,250 M 0,400 L 800,400 M 200,0 L 200,500 M 400,0 L 400,500 M 600,0 L 600,500" stroke="#ffffff10" strokeWidth="1" />

        {/* Central Dry Stream vs Vegetated Corridor */}
        {isBefore ? (
          <>
            {/* Low NDVI Sparse Brown Patch */}
            <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#ca8a04" strokeWidth="24" fill="none" opacity="0.6" />
            <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#854d0e" strokeWidth="8" fill="none" />
            <circle cx="450" cy="220" r="40" fill="#a16207" opacity="0.4" />
            <text x="460" y="225" fill="#fef08a" fontSize="12" fontFamily="monospace">NDVI: 0.22 (Sparse)</text>
          </>
        ) : (
          <>
            {/* High NDVI Lush Green Corridor */}
            <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#16a34a" strokeWidth="48" fill="none" opacity="0.7" />
            <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#22c55e" strokeWidth="24" fill="none" opacity="0.9" />
            <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#4ade80" strokeWidth="8" fill="none" />
            
            {/* Check Dam Reservoir Green Plumes */}
            <ellipse cx="280" cy="330" rx="65" ry="45" fill="#15803d" opacity="0.8" />
            <ellipse cx="450" cy="220" rx="75" ry="50" fill="#16a34a" opacity="0.8" />
            <ellipse cx="600" cy="120" rx="60" ry="40" fill="#22c55e" opacity="0.8" />

            <text x="460" y="225" fill="#86efac" fontSize="12" fontFamily="monospace" fontWeight="bold">NDVI: 0.37 (+0.15 Lush Canopy)</text>
          </>
        )}
      </svg>
    );
  }

  if (layer === 'moisture') {
    // Soil Moisture Index (Blue / Cyan Hydrological Plumes)
    return (
      <svg className="w-full h-full object-cover" viewBox="0 0 800 500" preserveAspectRatio="none">
        <rect width="800" height="500" fill={isBefore ? '#0e1726' : '#07162c'} />
        {isBefore ? (
          <>
            <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#1e3a8a" strokeWidth="12" fill="none" opacity="0.5" />
            <circle cx="450" cy="220" r="30" fill="#1d4ed8" opacity="0.3" />
            <text x="460" y="225" fill="#93c5fd" fontSize="12" fontFamily="monospace">Soil Moisture: 18%</text>
          </>
        ) : (
          <>
            <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#0284c7" strokeWidth="56" fill="none" opacity="0.6" />
            <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#06b6d4" strokeWidth="28" fill="none" opacity="0.8" />
            
            {/* Water Infiltration Retention Zones */}
            <circle cx="280" cy="330" r="70" fill="#0369a1" opacity="0.6" />
            <circle cx="450" cy="220" r="85" fill="#0284c7" opacity="0.7" />
            <circle cx="600" cy="120" r="65" fill="#06b6d4" opacity="0.6" />

            <text x="460" y="225" fill="#67e8f9" fontSize="12" fontFamily="monospace" fontWeight="bold">Soil Moisture: 30% (+12% Infiltration)</text>
          </>
        )}
      </svg>
    );
  }

  if (layer === 'critic_mask') {
    // Physical Constraint & Slope Map
    return (
      <svg className="w-full h-full object-cover" viewBox="0 0 800 500" preserveAspectRatio="none">
        <rect width="800" height="500" fill="#0a0f1d" />
        {/* DEM Slope Lines */}
        <path d="M 50,50 Q 200,120 400,60 T 750,80" stroke="#334155" strokeWidth="2" fill="none" strokeDasharray="4,4" />
        <path d="M 50,150 Q 250,220 500,160 T 750,180" stroke="#334155" strokeWidth="2" fill="none" strokeDasharray="4,4" />
        <path d="M 50,300 Q 300,380 550,290 T 750,320" stroke="#334155" strokeWidth="2" fill="none" strokeDasharray="4,4" />

        {/* Valid Stream Channel Bounds */}
        <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#10b981" strokeWidth="40" fill="none" opacity="0.3" />
        <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#10b981" strokeWidth="2" fill="none" strokeDasharray="6,4" />

        {/* Rejection / Pass Indicators */}
        {isBefore ? (
          <g>
            <rect x="230" y="140" width="220" height="60" rx="8" fill="#881337" opacity="0.8" stroke="#f43f5e" strokeWidth="2" />
            <text x="245" y="165" fill="#fecdd3" fontSize="11" fontFamily="monospace" fontWeight="bold">CRITIC REJECTION MASK</text>
            <text x="245" y="185" fill="#ffe4e6" fontSize="10" fontFamily="monospace">Slope &gt; 12° Illegal Water</text>
          </g>
        ) : (
          <g>
            <rect x="230" y="140" width="230" height="60" rx="8" fill="#064e3b" opacity="0.85" stroke="#10b981" strokeWidth="2" />
            <text x="245" y="165" fill="#a7f3d0" fontSize="11" fontFamily="monospace" fontWeight="bold">CRITIC VERIFIED VALID</text>
            <text x="245" y="185" fill="#d1fae5" fontSize="10" fontFamily="monospace">Slope &lt; 2.5° Reservoir Ok</text>
          </g>
        )}
      </svg>
    );
  }

  // Default Optical RGB View
  return (
    <svg className="w-full h-full object-cover" viewBox="0 0 800 500" preserveAspectRatio="none">
      {/* Background Terrain Palette */}
      <defs>
        <linearGradient id="dryLand" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#45382b" />
          <stop offset="50%" stopColor="#5c4d3c" />
          <stop offset="100%" stopColor="#3d3124" />
        </linearGradient>
        <linearGradient id="greenLand" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#1e3a29" />
          <stop offset="50%" stopColor="#2a4e37" />
          <stop offset="100%" stopColor="#193322" />
        </linearGradient>
      </defs>

      <rect width="800" height="500" fill={isBefore ? 'url(#dryLand)' : 'url(#greenLand)'} />

      {/* Terrain Contour / Ridge Texture */}
      <path d="M 0,80 Q 250,160 500,70 T 800,110" stroke={isBefore ? '#6b5945' : '#395e46'} strokeWidth="18" fill="none" opacity="0.4" />
      <path d="M 0,220 Q 300,310 600,200 T 800,250" stroke={isBefore ? '#6b5945' : '#395e46'} strokeWidth="22" fill="none" opacity="0.4" />

      {/* Central Stream & Interventions */}
      {isBefore ? (
        <>
          {/* Dry Sandy Stream Bed */}
          <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#d4b483" strokeWidth="18" fill="none" />
          <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#a38560" strokeWidth="6" fill="none" />
          <text x="320" y="340" fill="#fef08a" fontSize="11" fontFamily="monospace">Dry Ephemeral Bed</text>
        </>
      ) : (
        <>
          {/* Vegetated River Basin with Check Dams */}
          <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#15803d" strokeWidth="42" fill="none" opacity="0.8" />
          <path d="M 120,450 Q 300,300 450,220 T 720,50" stroke="#0284c7" strokeWidth="14" fill="none" />

          {/* Check-Dam Barrier Wall 1 */}
          <line x1="265" y1="345" x2="295" y2="315" stroke="#f8fafc" strokeWidth="4" />
          <polygon points="255,350 270,325 310,345 295,370" fill="#0369a1" opacity="0.85" />
          <text x="220" y="375" fill="#38bdf8" fontSize="10" fontFamily="monospace" fontWeight="bold">Check Dam #1 Reservoir</text>

          {/* Check-Dam Barrier Wall 2 */}
          <line x1="435" y1="235" x2="465" y2="205" stroke="#f8fafc" strokeWidth="4" />
          <polygon points="425,240 440,215 485,230 470,255" fill="#0284c7" opacity="0.85" />
          <text x="390" y="270" fill="#38bdf8" fontSize="10" fontFamily="monospace" fontWeight="bold">Check Dam #2 Reservoir</text>

          {/* Check-Dam Barrier Wall 3 */}
          <line x1="585" y1="135" x2="615" y2="105" stroke="#f8fafc" strokeWidth="4" />
          <polygon points="575,140 590,115 625,125 610,150" fill="#0369a1" opacity="0.85" />

          {/* Forest Canopy Clusters */}
          <circle cx="200" cy="380" r="28" fill="#166534" opacity="0.9" />
          <circle cx="230" cy="400" r="22" fill="#15803d" opacity="0.9" />
          <circle cx="480" cy="180" r="32" fill="#166534" opacity="0.9" />
          <circle cx="510" cy="160" r="24" fill="#22c55e" opacity="0.9" />
        </>
      )}
    </svg>
  );
}
