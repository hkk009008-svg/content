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
          'ivory-mute': '#928a82', // muted body — WCAG AA on #0a0a0a (4.7:1)
          'ivory-faint': '#6e6961', // disabled / placeholder — large-text AA (3.0:1)
          curtain: '#bf3737',      // single arterial red
          'curtain-deep': '#8a2828',
          brass: '#d4a85a',        // lamp / brass
          'brass-deep': '#a37e3e',
          /* Status tones — desaturated film-stock */
          ready: '#7fb069',        // muted print-room green
          warn: '#e9c46a',
          fail: '#bf3737',
        },

        // Director's Console — warm sepia palette (Slice C)
        // Sourced directly from design/directors-console.html :root variables.
        // Note: the plan sketch used cool-tinted approximations (#0D0B12, #15131C);
        // the mockup is warm-tinted throughout — these are the actual values. (DIVERGENCE)
        console: {
          'bg':             '#0d0a08', // --bg: body background (warm near-black)
          'bg-warm':        '#100c0a', // --bg-warm: viewport frame ring
          'surface':        '#181310', // --surface: panels, frame thumbnails
          'surface-2':      '#221c17', // --surface-2: cast avatar background
          'ink':            '#efe6d5', // --ink: primary text (warm ivory)
          'ink-dim':        '#a89c8a', // --ink-dim: secondary text
          'ink-mute':       '#6b5f54', // --ink-mute: label / placeholder text
          'ink-deep':       '#3f372e', // --ink-deep: dividers / deepest text
          'accent':         '#c8312a', // --accent: arterial red (live/rec/active)
          'accent-hover':   '#d63a33', // primary button hover
          'gold':           '#c4a366', // --gold: brass cast indicator / done status
          'rule':           '#2a241e', // --rule: default hairline rule
          'rule-strong':    '#4a3f33', // --rule-strong: elevated rule / border
        },
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['"Be Vietnam Pro"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
        // Director's Console — mono alias kept: `mono` has no Menlo fallback,
        // console panels need metric-compatible fallback for tight number columns. (Slice C)
        'console-mono': ['"JetBrains Mono"', 'Menlo', 'monospace'],
        // console-display dropped: identical to `display` — use font-display instead.
        // Plan sketch named 'Cormorant Garamond'; actual mockup uses 'Fraunces' (DIVERGENCE).
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
        'gradient-panel': 'linear-gradient(180deg, #141414 0%, #0a0a0a 100%)',
        'gradient-header': 'linear-gradient(180deg, #0a0a0a 0%, transparent 100%)',
        'gradient-accent': 'linear-gradient(135deg, #d4a85a 0%, #e0bf7b 100%)',
        'gradient-gold': 'linear-gradient(135deg, #d4a85a 0%, #e0bf7b 100%)',
        'gradient-card': 'linear-gradient(180deg, rgba(20,20,20,0.9) 0%, rgba(10,10,10,0.95) 100%)',
        'gradient-curtain': 'linear-gradient(180deg, #bf3737 0%, #8a2828 100%)',

        // Director's Console — viewport render-fill (Slice C)
        // Sourced from .viewport .render-fill in the mockup.
        // Plan sketch proposed masthead/hero gradients that do not appear in the mockup (DIVERGENCE).
        'console-render-fill':
          'linear-gradient(135deg, #1a1612 0%, #14171b 100%)',
        // Director's Console — frame label scrim
        'console-frame-scrim':
          'linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.6) 60%, transparent 100%)',
        // Director's Console — phase hover accent wash
        'console-phase-hover':
          'linear-gradient(to right, transparent, rgba(196,163,102,0.04) 30%, transparent)',
        // Director's Console — vignette overlay
        'console-vignette':
          'radial-gradient(ellipse 110% 90% at 50% 45%, transparent 40%, rgba(0,0,0,0.75) 100%)',
      },
      boxShadow: {
        'glow-accent': '0 0 0 1px rgba(212, 168, 90, 0.4), 0 0 30px rgba(212, 168, 90, 0.15)',
        'glow-gold': '0 0 0 1px rgba(212, 168, 90, 0.4), 0 0 30px rgba(212, 168, 90, 0.15)',
        'glow-success': '0 0 0 1px rgba(127, 176, 105, 0.4)',
        'panel': '0 1px 0 0 #2a2a2a',
        'elevated': '0 24px 48px -16px rgba(0,0,0,0.6)',
        'edge': '0 1px 0 0 #2a2a2a, 0 -1px 0 0 #2a2a2a',

        // Director's Console — viewport monitor frame ring (Slice C)
        // Sourced from .viewport box-shadow in the mockup.
        // Plan sketch had an inset panel shadow; mockup uses this ring instead (DIVERGENCE).
        'console-viewport':
          '0 0 0 6px #100c0a, 0 0 0 7px #4a3f33, 0 24px 60px rgba(0,0,0,0.5)',
        // Director's Console — active filmstrip frame glow (accent red)
        'console-frame-active':
          '0 0 0 1px #c8312a, 0 0 28px rgba(200,49,42,0.35)',
        // Director's Console — filmstrip well inset
        'console-filmstrip-inset':
          'inset 0 0 60px rgba(0,0,0,0.8)',
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
