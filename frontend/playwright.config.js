// Playwright end-to-end suite: docs/TESTING_GUIDE.md, "Browser tests".
//
// The tests drive the real app in a real browser against the two dev servers: Vite on
// 8080, reused when a developer's own is up and started here otherwise, and Django on
// 8000, which must already be running with the demo data loaded (every request the
// browser makes goes through Vite's proxy, so the tests only ever talk to 8080).
//
// The suite is sequential on purpose: the machine this was written on compiles Vue
// files at a few dozen milliseconds each, and every worker would share one database.
import { defineConfig, devices } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))

// docs/http/.env holds the demo passwords the http suite uses (ADMIN_PWD, MANAGER_PWD,
// SALES_PWD). They are read into the environment and never printed; a value that is
// already set wins, so CI can pass its own.
function loadDotEnv(file) {
  if (!fs.existsSync(file)) return
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/)
    if (match && process.env[match[1]] === undefined) process.env[match[1]] = match[2]
  }
}
loadDotEnv(path.join(here, '..', 'docs', 'http', '.env'))

/** Where the app is. Set E2E_BASE_URL when your own Vite server sits on another port. */
export const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8080'

/** The signed-in browser state the `setup` project writes and every other test reuses. */
export const ADMIN_STATE = path.join(here, 'tests', 'e2e', '.auth', 'admin.json')

export default defineConfig({
  testDir: path.join(here, 'tests', 'e2e'),
  outputDir: path.join(here, 'test-results'),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  // A warm dev server answers a page in a few seconds; a cold one compiles the app on
  // the first navigation and can take minutes on a slow machine.
  timeout: 180_000,
  expect: { timeout: 20_000 },
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: path.join(here, 'playwright-report') }],
  ],
  use: {
    baseURL: BASE_URL,
    actionTimeout: 30_000,
    navigationTimeout: 240_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'en-US',
  },
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.js/ },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1366, height: 800 },
        storageState: ADMIN_STATE,
      },
      dependencies: ['setup'],
    },
  ],
  webServer: {
    command: 'yarn dev',
    url: `${BASE_URL}/crm/login`,
    reuseExistingServer: true,
    timeout: 300_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
})
