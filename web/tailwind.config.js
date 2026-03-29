/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cinema: {
          bg: '#161622',
          'bg-deep': '#111119',
          panel: '#1e1e2e',
          'panel-hover': '#262638',
          'panel-elevated': '#282840',
          border: '#353550',
          'border-subtle': '#2a2a40',
          accent: '#8b7cf0',
          accent2: '#b49dfa',
          'accent-glow': '#8b7cf044',
          gold: '#e0b860',
          'gold-dim': '#c8a440',
          text: '#f0f1f8',
          'text-secondary': '#c0c4d8',
          muted: '#8890b0',
          success: '#4ade80',
          'success-dim': '#16a34a',
          warning: '#fbbf24',
          danger: '#f87171',
          'danger-dim': '#dc2626',
        },
      },
      backgroundImage: {
        'gradient-panel': 'linear-gradient(135deg, #1e1e2e 0%, #242438 100%)',
        'gradient-header': 'linear-gradient(180deg, #1e1e2e 0%, #161622 100%)',
        'gradient-accent': 'linear-gradient(135deg, #8b7cf0 0%, #b49dfa 100%)',
        'gradient-gold': 'linear-gradient(135deg, #e0b860 0%, #f0d070 100%)',
        'gradient-card': 'linear-gradient(180deg, rgba(30,30,46,0.8) 0%, rgba(22,22,34,0.9) 100%)',
      },
      boxShadow: {
        'glow-accent': '0 0 20px rgba(139, 124, 240, 0.2)',
        'glow-gold': '0 0 20px rgba(224, 184, 96, 0.2)',
        'glow-success': '0 0 15px rgba(74, 222, 128, 0.2)',
        'panel': '0 2px 8px rgba(0,0,0,0.25)',
        'elevated': '0 8px 32px rgba(0,0,0,0.35)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(139, 124, 240, 0.25)' },
          '100%': { boxShadow: '0 0 20px rgba(139, 124, 240, 0.5)' },
        },
      },
    },
  },
  plugins: [],
}
