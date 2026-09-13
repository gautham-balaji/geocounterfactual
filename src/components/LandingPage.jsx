import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowRight, Layers, ShieldCheck, Satellite, GitBranch } from 'lucide-react';
import { Button, Label, cn } from './ui/primitives';

/**
 * Entry point.
 *
 * Deliberately typographic and still. The obvious move is a spinning globe,
 * but the globe already carries the simulator and a rotating planet on a
 * title screen reads as a product demo. A quiet page reads as research,
 * which is what this work needs to look like in front of a jury.
 */

const PROOF_POINTS = [
  { icon: Satellite, value: '15', label: 'verified watersheds',
    caption: 'screened for built-up cover and terrain' },
  { icon: ShieldCheck, value: '4', label: 'physics rules',
    caption: 'gravity, growth rate, spectra, conservation' },
  { icon: Layers, value: '10 m', label: 'Sentinel-2 ground sample',
    caption: 'surface reflectance, cloud-masked' },
];

// Word-by-word reveal. Small offsets and a long ease -- the motion should be
// noticed only in aggregate, not as individual animating elements.
const EASE = [0.16, 1, 0.3, 1];

export default function LandingPage({ onEnter }) {
  const reduce = useReducedMotion();

  const rise = (delay = 0) => (reduce
    ? { initial: { opacity: 0 }, animate: { opacity: 1 },
        transition: { duration: 0.3, delay: delay * 0.5 } }
    : { initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 },
        transition: { duration: 0.8, delay, ease: EASE } });

  const titleWords = ['GeoCounterfactual', 'Simulation', 'Engine'];

  return (
    <div className="relative min-h-screen bg-surface-base text-ink-primary overflow-hidden">
      <div className="absolute inset-0 hero-wash pointer-events-none" />

      <div className="relative mx-auto w-full max-w-5xl px-6 sm:px-10 min-h-screen flex flex-col">
        {/* Masthead */}
        <motion.header
          {...rise(0)}
          className="pt-10 flex items-center justify-between"
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

        {/* Hero */}
        <main className="flex-1 flex flex-col justify-center py-20">
          <motion.div {...rise(0.1)}>
            <Label className="text-accent-soft">
              Multi-agent generative earth observation
            </Label>
          </motion.div>

          <h1 className="mt-6 text-display sm:text-display-lg font-semibold text-ink-primary">
            {titleWords.map((word, i) => (
              <motion.span
                key={word}
                className={cn('inline-block mr-[0.28em]',
                  i === 2 && 'text-ink-tertiary')}
                initial={reduce ? { opacity: 0 } : { opacity: 0, y: 26 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.9, delay: 0.18 + i * 0.09, ease: EASE }}
              >
                {word}
              </motion.span>
            ))}
          </h1>

          <motion.p
            {...rise(0.5)}
            className="mt-8 max-w-2xl text-body sm:text-[0.95rem] leading-relaxed text-ink-secondary"
          >
            Rural water and land interventions in semi-arid India are funded
            without any way to see their outcome. This engine generates the
            satellite image of that outcome — five specialised agents plan the
            intervention against real terrain, and a physics critic rejects
            and regenerates anything that could not physically occur.
          </motion.p>

          <motion.p
            {...rise(0.62)}
            className="mt-4 max-w-2xl text-label leading-relaxed text-ink-tertiary"
          >
            Water cannot rest on a slope. Vegetation cannot outgrow its
            biological rate. Terrain outside the intervention must survive
            untouched. The critic enforces all of it, and shows you every
            pixel it threw away.
          </motion.p>

          <motion.div {...rise(0.74)} className="mt-12 flex items-center gap-5">
            <Button
              size="lg"
              variant="primary"
              iconRight={ArrowRight}
              onClick={onEnter}
            >
              Enter command center
            </Button>
            <span className="text-micro text-ink-tertiary hidden sm:block">
              Live Sentinel-2 · Copernicus DEM
            </span>
          </motion.div>
        </main>

        {/* Proof points */}
        <motion.section
          {...rise(0.9)}
          className="pb-14 grid grid-cols-1 sm:grid-cols-3 gap-px bg-line rounded-xl overflow-hidden border border-line"
        >
          {PROOF_POINTS.map(({ icon: Icon, value, label, caption }) => (
            <div key={label} className="bg-surface-1 px-6 py-6 flex flex-col gap-2">
              <Icon className="w-4 h-4 text-ink-tertiary" strokeWidth={1.75} />
              <div className="flex items-baseline gap-2 mt-1">
                <span className="font-mono text-h1 font-medium text-ink-primary">
                  {value}
                </span>
                <span className="text-label text-ink-secondary">{label}</span>
              </div>
              <span className="text-micro text-ink-tertiary leading-relaxed">
                {caption}
              </span>
            </div>
          ))}
        </motion.section>
      </div>
    </div>
  );
}
