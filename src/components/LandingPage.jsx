import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowRight, Layers, ShieldCheck, Satellite, GitBranch } from 'lucide-react';
import { Button, Label, cn } from './ui/primitives';

/**
 * Entry point.
 *
 * Hard constraint: fits one 1366x768 screen with no scroll. The root is
 * h-screen / overflow-hidden and the layout is a three-row grid (masthead /
 * hero / proof strip) so the hero absorbs the leftover space rather than
 * pushing the call to action past the fold. Hero type is sized with clamp()
 * so it scales down on a laptop instead of overflowing.
 */

const PROOF_POINTS = [
  { icon: Satellite, value: '15', label: 'verified watersheds' },
  { icon: ShieldCheck, value: '4', label: 'physics rules' },
  { icon: Layers, value: '10 m', label: 'Sentinel-2 sampling' },
];

const EASE = [0.16, 1, 0.3, 1];

export default function LandingPage({ onEnter }) {
  const reduce = useReducedMotion();

  const rise = (delay = 0) => (reduce
    ? { initial: { opacity: 0 }, animate: { opacity: 1 },
        transition: { duration: 0.3, delay: delay * 0.5 } }
    : { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 },
        transition: { duration: 0.7, delay, ease: EASE } });

  const titleWords = ['GeoCounterfactual', 'Simulation', 'Engine'];

  return (
    <div className="relative h-screen overflow-hidden bg-surface-base text-ink-primary">
      <div className="absolute inset-0 hero-wash pointer-events-none" />

      {/* Column rules. transformOrigin is load-bearing: scaleY without it
          grows from the centre, so the rules would open from mid-page. */}
      <div className="absolute inset-0 pointer-events-none hidden md:block">
        <div className="mx-auto w-full max-w-5xl h-full px-6 sm:px-10 relative">
          {[0, 33.333, 66.666, 100].map((pct, i) => (
            <motion.div
              key={pct}
              className="absolute top-0 bottom-0 w-px bg-line/60"
              style={{ left: `${pct}%`, transformOrigin: 'top' }}
              initial={reduce ? { opacity: 0 } : { scaleY: 0, opacity: 0 }}
              animate={{ scaleY: 1, opacity: 1 }}
              transition={{ duration: 1.2, delay: 0.1 + i * 0.07, ease: EASE }}
            />
          ))}
        </div>
      </div>

      <div className="relative mx-auto w-full max-w-5xl h-full px-6 sm:px-10
                      grid grid-rows-[auto_1fr_auto]">

        <motion.header
          {...rise(0)}
          className="h-16 flex items-center justify-between border-b border-line/60"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-md border border-line bg-surface-1 flex items-center justify-center">
              <GitBranch className="w-3.5 h-3.5 text-accent-soft" strokeWidth={1.75} />
            </div>
            <span className="text-label font-medium text-ink-secondary">
              GeoCounterfactual
            </span>
          </div>
          <Label>Final-year research prototype</Label>
        </motion.header>

        <main className="min-h-0 flex flex-col justify-center py-6">
          <motion.div {...rise(0.08)}>
            <Label className="text-accent-soft">
              Multi-agent generative earth observation
            </Label>
          </motion.div>

          {/* clamp() keeps the hero inside a 768px-tall viewport instead of
              driving the button below the fold. */}
          <h1
            className="mt-4 font-semibold text-ink-primary"
            style={{
              fontSize: 'clamp(2rem, 4.4vw, 3.25rem)',
              lineHeight: 1.08,
              letterSpacing: '-0.03em',
            }}
          >
            {titleWords.map((word, i) => (
              <motion.span
                key={word}
                className={cn('inline-block mr-[0.26em]', i === 2 && 'text-ink-tertiary')}
                initial={reduce ? { opacity: 0 } : { opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.75, delay: 0.14 + i * 0.08, ease: EASE }}
              >
                {word}
              </motion.span>
            ))}
          </h1>

          <motion.p
            {...rise(0.4)}
            className="mt-6 max-w-[48ch] text-body leading-relaxed text-ink-secondary"
          >
            Rural water and land interventions in semi-arid India are funded
            without any way to see the outcome. This engine generates the
            satellite image of that outcome. Five specialised agents plan the
            intervention against real terrain, and a physics critic rejects
            and regenerates anything that could not physically occur.
          </motion.p>

          <motion.p
            {...rise(0.5)}
            className="mt-3 max-w-[54ch] text-label leading-relaxed text-ink-tertiary"
          >
            Water cannot rest on a slope. Vegetation cannot outgrow its
            biological rate. Terrain outside the intervention must survive
            untouched. The critic enforces all of it, and shows you every
            pixel it threw away.
          </motion.p>

          <motion.div {...rise(0.6)} className="mt-8 flex items-center gap-5">
            <Button size="lg" variant="primary" iconRight={ArrowRight} onClick={onEnter}>
              Enter command center
            </Button>
            <span className="text-micro text-ink-tertiary hidden sm:block">
              Live Sentinel-2 · Copernicus DEM
            </span>
          </motion.div>
        </main>

        <motion.section
          {...rise(0.72)}
          className="h-[84px] grid grid-cols-3 border-t border-line/60"
        >
          {PROOF_POINTS.map(({ icon: Icon, value, label }) => (
            <div
              key={label}
              className="flex items-center gap-3 px-6 first:pl-0 border-r border-line/60 last:border-r-0"
            >
              <Icon className="w-4 h-4 text-ink-tertiary shrink-0" strokeWidth={1.75} />
              <div className="min-w-0">
                <div className="font-mono text-h2 font-medium text-ink-primary leading-none">
                  {value}
                </div>
                <div className="text-micro text-ink-tertiary mt-1 truncate">
                  {label}
                </div>
              </div>
            </div>
          ))}
        </motion.section>
      </div>
    </div>
  );
}
