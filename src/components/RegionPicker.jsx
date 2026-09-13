import React, { useMemo, useState } from 'react';
import { Search, MapPin, ShieldCheck } from 'lucide-react';

/**
 * Searchable target list, grouped by state.
 *
 * With three pilot zones the globe markers were a usable selector. With
 * fifteen they are not -- the markers overlap at any sensible zoom and half
 * of them sit on the far side of the sphere. The globe stays the spatial
 * context; this is the actual control.
 */
export default function RegionPicker({ regions, selectedId, onSelect,
                                       disabled = false }) {
  const [query, setQuery] = useState('');

  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matches = regions.filter((r) =>
      !q ||
      r.name.toLowerCase().includes(q) ||
      r.state.toLowerCase().includes(q) ||
      (r.climateZone || '').toLowerCase().includes(q));

    const byState = new Map();
    for (const r of matches) {
      const key = r.state.split(',')[0].trim();
      if (!byState.has(key)) byState.set(key, []);
      byState.get(key).push(r);
    }
    return [...byState.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [regions, query]);

  const total = regions.length;
  const shown = grouped.reduce((n, [, rs]) => n + rs.length, 0);

  return (
    <div className="glass-panel p-4 rounded-2xl border border-slate-800 space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-mono font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
          <MapPin className="w-4 h-4 text-cyan-400" /> TARGET WATERSHED
        </label>
        <span className="text-[11px] font-mono text-emerald-400 flex items-center gap-1">
          <ShieldCheck className="w-3.5 h-3.5" />
          {shown === total ? `${total} verified` : `${shown} of ${total}`}
        </span>
      </div>

      <div className="relative">
        <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by district, state or agro-climatic zone…"
          className="w-full bg-darkbg-900 border border-slate-700 focus:border-cyan-500 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition"
        />
      </div>

      <div className="max-h-[260px] overflow-y-auto space-y-2.5 pr-1">
        {grouped.length === 0 && (
          <div className="text-[11px] font-mono text-slate-500 py-4 text-center">
            No watershed matches “{query}”.
          </div>
        )}

        {grouped.map(([state, rs]) => (
          <div key={state}>
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 px-1 pb-1 sticky top-0 bg-darkbg-900/80 backdrop-blur-sm">
              {state}
            </div>
            <div className="space-y-1">
              {rs.map((r) => {
                const active = r.id === selectedId;
                return (
                  <button
                    key={r.id}
                    disabled={disabled}
                    onClick={() => onSelect(r.id)}
                    className={`w-full text-left px-2.5 py-2 rounded-lg border text-xs transition flex items-center justify-between gap-2 ${
                      active
                        ? 'bg-cyan-950/50 border-cyan-500/60 text-cyan-100'
                        : 'bg-darkbg-800/50 border-slate-800 text-slate-300 hover:bg-slate-800/70 hover:border-slate-700'
                    } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <span className="min-w-0">
                      <span className="block font-semibold text-white truncate">
                        {r.name}
                      </span>
                      <span className="block text-[10px] text-slate-400 truncate">
                        {r.climateZone} · NDVI {r.baselineMetrics?.ndvi}
                      </span>
                    </span>
                    <span className="text-[10px] font-mono text-slate-500 shrink-0">
                      {r.lat.toFixed(2)}°N
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
