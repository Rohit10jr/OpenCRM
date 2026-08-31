import { defineConfig } from 'vitest/config'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Unit tests for the pure functions only.
 *
 * The browser harness (`npm run verify`) is the integration net and stays that way — it is
 * what has caught every real bug in this conversion. What it is bad at is *legibility*: it
 * is stateful, it drives a real database, and run 3 spent more time on assertions that had
 * drifted than on the app. These tests exist so a red harness means "the app broke" rather
 * than "something moved".
 *
 * No jsdom, no component rendering. Everything here takes values and returns values.
 */
export default defineConfig({
  resolve: {
    // `import.meta.url`, not `__dirname`: this config is ESM and Vite's native loader
    // warns about the CJS global.
    alias: {
      '@': path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'src'),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
