/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eefbff',
          100: '#d5f5ff',
          200: '#b3efff',
          300: '#7ce5ff',
          400: '#3bd2ff',
          500: '#06b6d4',
          600: '#0092b8',
          700: '#027494',
          800: '#0a5e78',
          900: '#0e4e64',
          950: '#043243',
        },
        darkbg: {
          900: '#060911',
          800: '#0b111e',
          700: '#121b2d',
          600: '#1b273e',
        },
        emeraldGlow: '#10b981',
        alertRed: '#f43f5e',
        cyanGlow: '#06b6d4',
        amberGlow: '#f59e0b',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow-spin': 'spin 12s linear infinite',
        'ping-slow': 'ping 2.5s cubic-bezier(0, 0, 0.2, 1) infinite',
        'radar-scan': 'radarScan 4s linear infinite',
        'dash-move': 'dashMove 2s linear infinite',
      },
      keyframes: {
        radarScan: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
        dashMove: {
          '0%': { strokeDashoffset: '24' },
          '100%': { strokeDashoffset: '0' },
        }
      },
      boxShadow: {
        'glow-cyan': '0 0 20px -3px rgba(6, 182, 212, 0.4)',
        'glow-emerald': '0 0 20px -3px rgba(16, 185, 129, 0.4)',
        'glow-red': '0 0 25px -2px rgba(244, 63, 94, 0.5)',
      }
    },
  },
  plugins: [],
}
