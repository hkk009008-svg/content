/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Indigo tokens — the single color namespace (sourced from web/src/theme/tokens.css).
        // The former editorial-*/console-* scales were removed once all reused components
        // migrated to these plain top-level token names (see ARCHITECTURE.md §14.3).
        app:'var(--bg)', gutter:'var(--gutter)', panel:'var(--panel)', head:'var(--head)', line:'var(--line)',
        tx:'var(--tx)', mut:'var(--mut)', dim:'var(--dim)',
        acc:'var(--acc)', 'acc-dim':'var(--acc-dim)', pri:'var(--pri)', 'pri-bg':'var(--pri-bg)',
        local:'var(--local)', 'local-bg':'var(--local-bg)', ok:'var(--ok)', warn:'var(--warn)', fail:'var(--fail)',
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['"Be Vietnam Pro"', 'system-ui', 'sans-serif'],
        // Menlo folded in as metric-compatible fallback for tight number columns
        // (was the separate console-mono alias before the namespace merge).
        mono: ['"JetBrains Mono"', 'Menlo', 'monospace'],
      },
      letterSpacing: {
        'tight-display': '-0.02em',
        'tight-body': '-0.01em',
        'wide-eyebrow': '0.26em',
      },
      fontSize: {
        /* Editorial micro-scale — sub-Tailwind sizes for eyebrows, chips,
           mono badges, and metadata. Replaces 400+ arbitrary text-[9-11px]
           usages with semantic tokens. Default leading inherited. */
        'eyebrow-sm': '9px',
        'eyebrow':    '10px',
        'eyebrow-lg': '11px',
      },
      backgroundImage: {
        'gradient-panel': 'linear-gradient(180deg, #1c1c20 0%, #141417 100%)',
        'gradient-header': 'linear-gradient(180deg, #141417 0%, transparent 100%)',
        'gradient-accent': 'linear-gradient(135deg, #7c83e0 0%, #9aa0ee 100%)',
        'gradient-card': 'linear-gradient(180deg, rgba(28,28,32,0.9) 0%, rgba(20,20,23,0.95) 100%)',

        // Video-monitor viewport render-fill (RunPage console Monitor).
        // Renamed from console-render-fill; the frame-scrim / phase-hover / vignette
        // gradients went out with the deleted console shells (no live consumer).
        'viewport-fill':
          'linear-gradient(135deg, #1c1c20 0%, #141417 100%)',
      },
      boxShadow: {
        'glow-accent': '0 0 0 1px rgba(124, 131, 224, 0.4), 0 0 30px rgba(124, 131, 224, 0.15)',
        'glow-success': '0 0 0 1px rgba(90, 164, 105, 0.4)',
        'panel': '0 1px 0 0 #2e2e35',
        'elevated': '0 24px 48px -16px rgba(0,0,0,0.6)',
        'edge': '0 1px 0 0 #2e2e35, 0 -1px 0 0 #2e2e35',

        // Video-monitor frame ring (RunPage console Monitor). Renamed from
        // console-viewport; frame-active / filmstrip-inset went out with the
        // deleted console shells (no live consumer).
        'viewport':
          '0 0 0 6px #141417, 0 0 0 7px #2e2e35, 0 24px 60px rgba(0,0,0,0.5)',
      },
      animation: {
        marquee: 'marquee 32s linear infinite',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'ink-up': 'ink-up 700ms cubic-bezier(0.16, 1, 0.3, 1) both',
        flicker: 'projection-flicker 3.2s infinite',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 0 1px rgba(124,131,224,0.3)' },
          '100%': { boxShadow: '0 0 0 1px rgba(124,131,224,0.7)' },
        },
      },
    },
  },
  plugins: [],
}
