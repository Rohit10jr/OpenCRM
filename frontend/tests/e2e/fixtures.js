// The shared `test`: every spec imports it from here instead of from @playwright/test.
//
// It adds two things. `pageErrors` (automatic) fails a test when the page throws an
// uncaught exception, which is the class of fault that blanked the sidebar
// (docs/FINDINGS.md 38) and the leads list (40) without a single failed request, and
// reports every failed /api/ request beside it; a test that expects one opts out with
// `test.info().annotations.push({ type: 'allow-page-errors' })`. `api` is a backend
// client signed in as Administrator for seeding rows and cleaning them up, so the
// browser only does what the test is about.
import { test as base, expect } from '@playwright/test'
import { backendClient } from './helpers.js'
import { users } from './users.js'

// Backend answers the suite tolerates, each tied to an open finding in docs/FINDINGS.md.
// A page error that only such a request explains does not fail the test. Take an entry
// out when its finding is fixed, and the tests will insist on the fix. The shape of an
// entry: { finding, method, status, matches: (body) => bool, pageError: /regex/ }.
// (Finding 45, the Address search, lived here until Address was built.)
const KNOWN_OPEN = []

function parseBody(request) {
  try {
    return JSON.parse(request.postData() || '{}')
  } catch {
    return {}
  }
}

export const test = base.extend({
  pageErrors: [
    async ({ page }, use, testInfo) => {
      const errors = []
      const tolerated = []
      const unexplained = []
      page.on('pageerror', (error) => errors.push(error))
      page.on('response', (response) => {
        const url = new URL(response.url())
        if (!url.pathname.startsWith('/api/') || response.status() < 400) return
        const body = parseBody(response.request())
        const known = KNOWN_OPEN.find(
          (k) => url.pathname.endsWith(k.method) && response.status() === k.status && k.matches(body),
        )
        const entry = { path: url.pathname, status: response.status(), body, finding: known?.finding }
        ;(known ? tolerated : unexplained).push(entry)
      })

      await use(errors)

      // An error is dropped only when a tolerated request explains it and no
      // unexplained request of the same kind could be behind it instead.
      const remaining = errors.filter((error) => {
        const known = KNOWN_OPEN.find((k) => k.pageError.test(error.message))
        if (!known) return true
        const explained = tolerated.some((t) => t.finding === known.finding)
        const shadowed = unexplained.some(
          (u) => u.path.endsWith(known.method) && u.status === known.status,
        )
        return !(explained && !shadowed)
      })
      const allowed = testInfo.annotations.some((a) => a.type === 'allow-page-errors')
      if (remaining.length && !allowed) {
        const text = remaining.map((e) => e.stack || e.message).join('\n\n')
        const requests = unexplained
          .map((u) => `  ${u.status} ${u.path} ${JSON.stringify(u.body).slice(0, 200)}`)
          .join('\n')
        throw new Error(
          `The page threw ${remaining.length} uncaught error(s):\n${text}` +
            (requests ? `\n\nFailed requests during the test:\n${requests}` : ''),
        )
      }
    },
    { auto: true },
  ],

  api: async ({ baseURL }, use) => {
    const client = await backendClient(baseURL, users.admin)
    await use(client)
    await client.dispose()
  },
})

export { expect }
