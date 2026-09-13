/** @type {import('tailwindcss').Config} */

// Phase 1 theme. Two things are happening here at once:
//
// 1. New semantic tokens (surface / ink / accent) that refactored components
//    will use going forward.
// 2. The OLD token names -- darkbg, brand, and Tailwind's own cyan/emerald
//    scales -- are remapped onto the new palette rather than deleted.
//
// (2) is deliberate. Nine components still reference the old names in ~111
// places. Deleting the tokens would leave those files rendering transparent
// backgrounds and invisible text, so the app would look broken during review
// rather than merely un-refactored. Remapping means every screen adopts the
// new palette immediately, and later passes clean up the class names with no
// visual change. The glow shadows are simply removed: an undefined utility
// compiles to nothing, so all 11 call sites lose their neon with no edits.

const surface = {
  base: '#0A0A0B',
  1: '#111113',
  2: '#1A1A1D',
  3: '#242428',
};

const ink = {
  primary: '#ECECEE',
  secondary: '#A1A1A8',
  tertiary: '#6E6E76',
};

// One accent. Previously cyan AND emerald both read as primary, so nothing
// on screen was more important than anything else.
const accent = {
  DEFAULT: '#6366F1',
  muted: '#4F46E5',
  soft: '#818CF8',
  subtle: 'rgba(99, 102, 241, 0.10)',
};

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        surface,
        ink,
        accent,
        line: { DEFAULT: '#26262B', strong: '#35353C' },

        positive: '#4ADE80',
        critical: '#F87171',
        caution: '#FBBF24',
        info: '#38BDF8',

        // ---- compatibility remaps (see header note) ----
        darkbg: {
          900: surface.base,
          800: surface[1],
          700: surface[2],
          600: surface[3],
        },
        brand: {
          50: '#EEF0FF', 100: '#E0E3FF', 200: '#C7CBFE', 300: '#A5AAFC',
          400: '#818CF8', 500: accent.DEFAULT, 600: accent.muted,
          700: '#4338CA', 800: '#3730A3', 900: '#312E81', 950: '#1E1B4B',
        },
        // Chrome that used cyan now reads as the single accent.
        cyan: {
          50: '#EEF0FF', 100: '#E0E3FF', 200: '#C7CBFE', 300: '#A5AAFC',
          400: accent.soft, 500: accent.DEFAULT, 600: accent.muted,
          700: '#4338CA', 800: '#3730A3', 900: '#312E81', 950: '#1E1B4B',
        },
        // Emerald keeps its MEANING (a rule passed) but loses the neon.
        emerald: {
          50: '#ECFDF3', 100: '#D1FAE0', 200: '#A7F3C4', 300: '#6EE7A5',
          400: positiveShade(), 500: '#34D399', 600: '#22A06B',
          700: '#1B7F55', 800: '#186246', 900: '#14513B', 950: '#052E20',
        },
        // Slate is used for borders and muted text throughout; retune it to
        // the warm-neutral ramp so panels stop reading blue.
        slate: {
          50: '#F7F7F8', 100: '#ECECEE', 200: '#D4D4D8', 300: '#A1A1A8',
          400: '#8A8A92', 500: '#6E6E76', 600: '#52525A', 700: '#3A3A41',
          800: '#26262B', 900: '#18181B', 950: '#0A0A0B',
        },
      },

      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },

      fontSize: {
        micro: ['0.6875rem', { lineHeight: '0.875rem', letterSpacing: '0.04em' }],
        label: ['0.75rem', { lineHeight: '1rem' }],
        body: ['0.875rem', { lineHeight: '1.375rem' }],
        h2: ['1.25rem', { lineHeight: '1.75rem', letterSpacing: '-0.01em' }],
        h1: ['1.875rem', { lineHeight: '2.375rem', letterSpacing: '-0.02em' }],
        display: ['3rem', { lineHeight: '3.5rem', letterSpacing: '-0.03em' }],
        'display-lg': ['4.5rem', { lineHeight: '4.75rem', letterSpacing: '-0.035em' }],
      },

      // Depth from one soft elevation, not coloured glow.
      boxShadow: {
        elevated: '0 1px 2px rgba(0,0,0,0.40), 0 8px 24px -8px rgba(0,0,0,0.50)',
        inset: 'inset 0 1px 0 rgba(255,255,255,0.03)',
      },

      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'ping-slow': 'ping 2.5s cubic-bezier(0, 0, 0.2, 1) infinite',
        'dash-move': 'dashMove 2s linear infinite',
      },
      keyframes: {
        dashMove: {
          '0%': { strokeDashoffset: '24' },
          '100%': { strokeDashoffset: '0' },
        },
      },
    },
  },
  plugins: [],
};

function positiveShade() {
  return '#4ADE80';
}
