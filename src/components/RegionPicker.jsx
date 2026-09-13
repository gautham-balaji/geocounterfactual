import React, { useMemo, useState } from 'react';
import { Search, ShieldCheck } from 'lucide-react';
import { cn, Label } from './ui/primitives';

/**
 * Searchable target list, grouped by state.
 *
 * With three pilot zones the globe markers were a usable selector. With
 * fifteen they are not -- the markers overlap at any sensible zoom and half
 * sit on the far side of the sphere. The globe stays spatial context; this
 * is the control.
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
      const key = r.state.split(',').pop().trim();
      if (!byState.has(key)) byState.set(key, []);
      byState.get(key).push(r);
    }
    return [...byState.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [regions, query]);

  const total = regions.length;
  const shown = grouped.reduce((n, [, rs]) => n + rs.length, 0);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label>Target</Label>
        <span className="flex items-center gap-1.5 text-micro text-ink-tertiary">
          <ShieldCheck className="w-3 h-3" strokeWidth={2} />
          <span className="font-mono">
            {shown === total ? total : `${shown}/${total}`}
          </span>
          verified
        </span>
      </div>

      <div className="relative">
        <Search
          className="w-3.5 h-3.5 text-ink-tertiary absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
          strokeWidth={1.75}
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter watersheds"
          className={cn(
            'w-full h-9 pl-9 pr-3 rounded-lg text-label',
            'bg-surface-2 border border-line text-ink-primary placeholder-ink-tertiary',
            'transition-colors duration-150',
            'hover:border-line-strong focus:border-accent focus:outline-none',
          )}
        />
      </div>

      <div className="max-h-[210px] overflow-y-auto -mx-1 px-1">
        {grouped.length === 0 && (
          <div className="py-8 text-center text-micro text-ink-tertiary">
            No watershed matches “{query}”.
          </div>
        )}

        {grouped.map(([state, rs], gi) => (
          <div key={state} className={gi > 0 ? 'mt-4' : ''}>
            <div className="sticky top-0 z-10 bg-surface-1 py-1.5">
              <Label className="text-ink-tertiary/80">{state}</Label>
            </div>
            <div className="space-y-0.5 mt-1">
              {rs.map((r) => {
                const active = r.id === selectedId;
                return (
                  <button
                    key={r.id}
                    disabled={disabled}
                    onClick={() => onSelect(r.id)}
                    className={cn(
                      'w-full text-left px-2.5 py-2 rounded-md',
                      'flex items-center justify-between gap-3',
                      // Hover is a background shift only -- no scale, no
                      // border flash. Fifteen rows that all jump on hover
                      // would be noise.
                      'transition-colors duration-150',
                      active
                        ? 'bg-accent-subtle'
                        : 'hover:bg-surface-2',
                      disabled && 'opacity-50 cursor-not-allowed',
                    )}
                  >
                    <span className="min-w-0 flex items-center gap-2.5">
                      <span
                        className={cn('w-1 h-1 rounded-full shrink-0',
                          active ? 'bg-accent' : 'bg-line-strong')}
                      />
                      <span className="min-w-0">
                        <span className={cn('block text-label truncate',
                          active ? 'text-ink-primary font-medium' : 'text-ink-secondary')}>
                          {r.name}
                        </span>
                        <span className="block text-micro text-ink-tertiary truncate">
                          {r.climateZone}
                        </span>
                      </span>
                    </span>
                    <span className="font-mono text-micro text-ink-tertiary shrink-0">
                      {r.baselineMetrics?.ndvi}
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
