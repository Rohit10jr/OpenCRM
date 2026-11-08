import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'

export default {
  presets: [frappeUIPreset],
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
    ...frappeUIContent,
    // linked @framework/ui source (apps/frappe/ui/src) — scan so its utility and
    // arbitrary-variant classes (e.g. Notifications TabButtons overrides) are generated
    '../../frappe/ui/src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  safelist: [{ pattern: /!(text|bg)-/, variants: ['hover', 'active'] }],
  theme: {
    extend: {},
  },
  plugins: [],
}
