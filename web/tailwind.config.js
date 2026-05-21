/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        /* Editorial Cinema — paper-black + ivory + single arterial accent.
           One dominant color, two restrained accents. */
        editorial: {
          ink: '#0a0a0a',          // film leader / page
          'ink-soft': '#141414',   // surface
          'ink-rise': '#1c1c1c',   // raised surface
          rule: '#2a2a2a',         // hairline rules
          'rule-bright': '#3a3a3a',
          ivory: '#f0ebe1',        // primary text — projection screen
          'ivory-soft': '#d8d2c5',
          'ivory-mute': '#807872', // muted body
          'ivory-faint': '#4a4540',
          curtain: '#bf3737',      // single arterial red
          'curtain-deep': '#8a2828',
          brass: '#d4a85a',        // lamp / brass
          'brass-deep': '#a37e3e',
          /* Status tones — desaturated film-stock */
          ready: '#7fb069',        // muted print-room green
          warn: '#e9c46a',
          fail: '#bf3737',
        },
        /* Legacy `cinema.*` aliased to the new ivory/ink so existing
           components don't break while you migrate. */
        cinema: {
          bg: '#0a0a0a',
          'bg-deep': '#080808',
          panel: '#141414',
          'panel-hover': '#1c1c1c',
          'panel-elevated': '#202020',
          border: '#2a2a2a',
          'border-subtle': '#1c1c1c',
          accent: '#d4a85a',
          accent2: '#e0bf7b',
          'accent-glow': '#d4a85a33',
          gold: '#d4a85a',
          'gold-dim': '#a37e3e',
          text: '#f0ebe1',
          'text-secondary': '#d8d2c5',
          muted: '#807872',
          success: '#7fb069',
          'success-dim': '#5a8a4a',
          warning: '#e9c46a',
          danger: '#bf3737',
          'danger-dim': '#8a2828',
        },
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['"Be Vietnam Pro"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      letterSpacing: {
        'tight-display': '-0.02em',
        'tight-body': '-0.01em',
        'wide-eyebrow': '0.18em',
      },
      backgroundImage: {
        'gradient-panel': 'linear-gradient(180deg, #141414 0%, #0a0a0a 100%)',
        'gradient-header': 'linear-gradient(180deg, #0a0a0a 0%, transparent 100%)',
        'gradient-accent': 'linear-gradient(135deg, #d4a85a 0%, #e0bf7b 100%)',
        'gradient-gold': 'linear-gradient(135deg, #d4a85a 0%, #e0bf7b 100%)',
        'gradient-card': 'linear-gradient(180deg, rgba(20,20,20,0.9) 0%, rgba(10,10,10,0.95) 100%)',
        'gradient-curtain': 'linear-gradient(180deg, #bf3737 0%, #8a2828 100%)',
      },
      boxShadow: {
        'glow-accent': '0 0 0 1px rgba(212, 168, 90, 0.4), 0 0 30px rgba(212, 168, 90, 0.15)',
        'glow-gold': '0 0 0 1px rgba(212, 168, 90, 0.4), 0 0 30px rgba(212, 168, 90, 0.15)',
        'glow-success': '0 0 0 1px rgba(127, 176, 105, 0.4)',
        'panel': '0 1px 0 0 #2a2a2a',
        'elevated': '0 24px 48px -16px rgba(0,0,0,0.6)',
        'edge': '0 1px 0 0 #2a2a2a, 0 -1px 0 0 #2a2a2a',
      },
      animation: {
        marquee: 'marquee 32s linear infinite',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'ink-up': 'ink-up 700ms cubic-bezier(0.16, 1, 0.3, 1) both',
        flicker: 'projection-flicker 3.2s infinite',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 0 1px rgba(212,168,90,0.3)' },
          '100%': { boxShadow: '0 0 0 1px rgba(212,168,90,0.7)' },
        },
      },
    },
  },
  plugins: [],
}
