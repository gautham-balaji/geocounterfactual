import React from 'react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Shared UI primitives.
 *
 * Components currently build class strings with nested ternaries, which is
 * how conflicting utilities and dead styles accumulate. `cn` resolves the
 * conflicts (last wins, properly), and the primitives below mean panel
 * padding, border colour and radius are decided once rather than re-guessed
 * in every file.
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/* ------------------------------------------------------------------ */
/* Surface                                                             */
/* ------------------------------------------------------------------ */

export function Panel({ as: Tag = 'div', className, inset = false,
                        bordered = true, children, ...rest }) {
  return (
    <Tag
      className={cn(
        'rounded-xl bg-surface-1',
        bordered && 'border border-line',
        inset ? 'p-4' : 'p-6',
        className,
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/** Section heading. Sentence case, no uppercase tracking on real headings. */
export function SectionTitle({ icon: Icon, children, trailing, className }) {
  return (
    <div className={cn('flex items-center justify-between gap-4', className)}>
      <div className="flex items-center gap-2.5 min-w-0">
        {Icon && <Icon className="w-4 h-4 text-ink-tertiary shrink-0" strokeWidth={1.75} />}
        <h3 className="text-body font-medium text-ink-primary truncate">{children}</h3>
      </div>
      {trailing}
    </div>
  );
}

/** Micro label. The ONLY place uppercase + tracking is appropriate. */
export function Label({ children, className }) {
  return (
    <span className={cn('text-micro uppercase tracking-wider text-ink-tertiary',
      className)}>
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Button                                                              */
/* ------------------------------------------------------------------ */

const BUTTON_VARIANTS = {
  primary:
    'bg-accent text-white hover:bg-accent-muted disabled:bg-surface-2 disabled:text-ink-tertiary',
  secondary:
    'bg-surface-2 text-ink-primary border border-line hover:bg-surface-3 hover:border-line-strong disabled:text-ink-tertiary',
  ghost:
    'bg-transparent text-ink-secondary hover:bg-surface-2 hover:text-ink-primary',
  quiet:
    'bg-transparent text-ink-tertiary hover:text-ink-primary',
};

const BUTTON_SIZES = {
  sm: 'h-8 px-3 text-label gap-1.5 rounded-lg',
  md: 'h-10 px-4 text-body gap-2 rounded-lg',
  lg: 'h-12 px-6 text-body gap-2.5 rounded-xl',
};

export function Button({ variant = 'secondary', size = 'md', icon: Icon,
                         iconRight: IconRight, className, children,
                         disabled, ...rest }) {
  return (
    <button
      disabled={disabled}
      className={cn(
        'inline-flex items-center justify-center font-medium',
        // Colour-only transitions. No scale, no bounce -- movement on hover
        // reads as playful, which is the opposite of what this needs.
        'transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:opacity-70',
        BUTTON_SIZES[size],
        BUTTON_VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {Icon && <Icon className="w-4 h-4 shrink-0" strokeWidth={1.75} />}
      {children}
      {IconRight && <IconRight className="w-4 h-4 shrink-0" strokeWidth={1.75} />}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Badge                                                               */
/* ------------------------------------------------------------------ */

const BADGE_TONES = {
  neutral: 'bg-surface-2 text-ink-secondary border-line',
  accent: 'bg-accent-subtle text-accent-soft border-accent/30',
  positive: 'bg-positive/10 text-positive border-positive/25',
  critical: 'bg-critical/10 text-critical border-critical/25',
  caution: 'bg-caution/10 text-caution border-caution/30',
  info: 'bg-info/10 text-info border-info/25',
};

export function Badge({ tone = 'neutral', icon: Icon, className, children }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-1.5 py-0.5 rounded border',
        'text-micro font-medium whitespace-nowrap',
        BADGE_TONES[tone],
        className,
      )}
    >
      {Icon && <Icon className="w-3 h-3 shrink-0" strokeWidth={2} />}
      {children}
    </span>
  );
}

/**
 * Provenance marker. Predicted layers must be visually distinct from
 * measured ones -- it is the cheapest possible defence of the work's
 * honesty, so it gets a named component rather than an ad-hoc badge.
 */
export function ModelledBadge({ className }) {
  return <Badge tone="caution" className={className}>MODELLED</Badge>;
}

export function MeasuredBadge({ className, children = 'SENTINEL-2' }) {
  return <Badge tone="info" className={className}>{children}</Badge>;
}

/* ------------------------------------------------------------------ */
/* Numeric display                                                     */
/* ------------------------------------------------------------------ */

/** Figures are mono; the label around them is not. */
export function Stat({ label, value, unit, caption, tone = 'default',
                       badge, className }) {
  const valueTone = {
    default: 'text-ink-primary',
    accent: 'text-accent-soft',
    positive: 'text-positive',
    critical: 'text-critical',
  }[tone];

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <Label>{label}</Label>
      <div className="flex items-baseline gap-1">
        <span className={cn('font-mono text-h2 font-medium tracking-tight',
          valueTone)}>
          {value}
        </span>
        {unit && <span className="font-mono text-label text-ink-tertiary">{unit}</span>}
      </div>
      {caption && <span className="text-micro text-ink-tertiary">{caption}</span>}
      {badge}
    </div>
  );
}

/** Hairline rule used instead of bordered sub-panels. */
export function Divider({ className }) {
  return <div className={cn('h-px bg-line', className)} />;
}
