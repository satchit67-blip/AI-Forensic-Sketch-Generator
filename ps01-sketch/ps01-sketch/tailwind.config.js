export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: { extend: {
    fontFamily: { mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'], sans: ['"Space Grotesk"', 'system-ui', 'sans-serif'] },
    colors: { nexus: { 950: '#070b14', 900: '#0b1220', 800: '#111b2e', cyan: '#4fe6d2' } },
    boxShadow: { glow: '0 0 24px rgba(79,230,210,.25)' }
  } },
  plugins: []
};
