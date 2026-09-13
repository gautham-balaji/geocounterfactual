import React, { useEffect, useState } from 'react';
import { Play, Database, GitBranch } from 'lucide-react';
import { checkHealth } from '../services/api';
import { cn, Badge } from './ui/primitives';

const TABS = [
  { id: 'simulator', label: 'Command center', icon: Play },
  { id: 'methodology', label: 'Data & methodology', icon: Database },
];

export default function Header({ activeTab, setActiveTab }) {
  // These badges used to be hardcoded to "ONLINE" and "CONNECTED" -- they
  // said so with the backend dead. A status indicator that cannot report a
  // problem is worse than none, so it now reflects the real health check.
  const [health, setHealth] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const poll = () => checkHealth().then((h) => { if (!cancelled) setHealth(h); });
    poll();
    const id = setInterval(poll, 20000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const online = health?.online;
  const geeUp = health?.gee === 'available';

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-surface-base/85 backdrop-blur-xl">
      <div className="max-w-[1600px] mx-auto px-6 sm:px-8 lg:px-10 h-14 flex items-center justify-between gap-8">
        {/* Wordmark */}
        <button
          onClick={() => setActiveTab('simulator')}
          className="flex items-center gap-3 group shrink-0"
        >
          <div className="w-8 h-8 rounded-lg border border-line bg-surface-1 flex items-center justify-center transition-colors duration-150 group-hover:border-line-strong">
            <GitBranch className="w-4 h-4 text-accent-soft" strokeWidth={1.75} />
          </div>
          <div className="text-left hidden sm:block">
            <div className="text-body font-medium text-ink-primary leading-tight">
              GeoCounterfactual
            </div>
            <div className="text-micro text-ink-tertiary leading-tight">
              Simulation engine
            </div>
          </div>
        </button>

        {/* Tabs -- underline, not pills */}
        <nav className="flex items-center gap-1">
          {TABS.map(({ id, label, icon: Icon }) => {
            const isActive = activeTab === id;
            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={cn(
                  'relative flex items-center gap-2 px-3 h-14 text-label font-medium',
                  'transition-colors duration-150',
                  isActive
                    ? 'text-ink-primary'
                    : 'text-ink-tertiary hover:text-ink-secondary',
                )}
              >
                <Icon className="w-3.5 h-3.5" strokeWidth={1.75} />
                <span className="whitespace-nowrap">{label}</span>
                {isActive && (
                  <span className="absolute inset-x-2 bottom-0 h-px bg-accent" />
                )}
              </button>
            );
          })}
        </nav>

        {/* Real status */}
        <div className="hidden lg:flex items-center gap-2 shrink-0">
          <Badge tone={online ? 'positive' : 'neutral'}>
            <span
              className={cn('w-1.5 h-1.5 rounded-full mr-0.5',
                online ? 'bg-positive' : 'bg-ink-tertiary')}
            />
            {health === null ? 'Checking' : online ? 'Backend live' : 'Offline · mock data'}
          </Badge>
          {online && (
            <Badge tone={geeUp ? 'info' : 'caution'}>
              {geeUp ? 'Earth Engine' : 'EE unavailable'}
            </Badge>
          )}
        </div>
      </div>
    </header>
  );
}
