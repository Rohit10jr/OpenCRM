/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // The Vue app inherits these from frappe-ui's tailwind preset, which is a Vue
        // package we are not pulling in. The names are kept — `text-ink-gray-7`,
        // `bg-surface-white` — so ported markup keeps reading the same, but the values
        // are plain Tailwind greys rather than frappe-ui's design tokens.
        'ink-gray-1': '#ffffff',
        'ink-gray-2': '#f8fafc',
        'ink-gray-3': '#94a3b8',
        'ink-gray-4': '#64748b',
        'ink-gray-5': '#475569',
        'ink-gray-6': '#334155',
        'ink-gray-7': '#1e293b',
        'ink-gray-8': '#0f172a',
        'ink-gray-9': '#020617',
        'surface-white': '#ffffff',
        'surface-gray-1': '#f8fafc',
        'surface-gray-2': '#f1f5f9',
        'surface-gray-3': '#e2e8f0',
        'surface-gray-4': '#cbd5e1',
        'outline-gray-1': '#e2e8f0',
        'outline-gray-2': '#cbd5e1',
        'outline-gray-3': '#94a3b8',
      },
    },
  },
  plugins: [],
}
