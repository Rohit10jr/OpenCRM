/**
 * The auth routing rules — phase 8.
 *
 * Three properties, and the first is the one this phase exists for: an unauthenticated
 * visitor must reach a login form rather than leaving the SPA for a URL nothing serves.
 * `router.js` used to do `window.location.href = '/login?redirect-to=/crm'`, and
 * `config/urls.py` has only `admin/` and `api/`, so that was a 404.
 *
 * The redirect-sanitising test is the one worth keeping honest: `?redirect=` comes off the
 * query string, so without a check the login page is an open redirect — a link that really
 * does log you in and then lands you on somebody else's site.
 */

import { describe, expect, it } from 'vitest'

/**
 * The rule from `stores/session.js`'s `onSuccess`, extracted so it can be tested without
 * standing up pinia, the router and a live login.
 *
 * Kept in step with the source by `test_the_rule_matches_the_source` below, which reads
 * the actual file — a copy that silently drifts would be worse than no test.
 */
function safeRedirect(target) {
  return typeof target === 'string' && /^\/(?!\/)/.test(target) ? target : '/'
}

describe('post-login redirect', () => {
  it('returns the user to where they were headed', () => {
    expect(safeRedirect('/leads/CRM-LEAD-2026-00001')).toBe(
      '/leads/CRM-LEAD-2026-00001',
    )
  })

  it('falls back home when there is no target', () => {
    expect(safeRedirect(undefined)).toBe('/')
    expect(safeRedirect('')).toBe('/')
  })

  it('refuses an absolute URL', () => {
    // The open-redirect case: a phishing link that logs you in, then sends you on.
    expect(safeRedirect('https://elsewhere.example/steal')).toBe('/')
    expect(safeRedirect('http://elsewhere.example')).toBe('/')
  })

  it('refuses a protocol-relative URL', () => {
    // `//host` is the one that slips past a naive "must start with /" check — the browser
    // reads it as a full URL with the current scheme.
    expect(safeRedirect('//elsewhere.example/steal')).toBe('/')
  })

  it('refuses a non-string', () => {
    // Vue Router hands back an array when a query key repeats: `?redirect=/a&redirect=/b`.
    expect(safeRedirect(['/a', '/b'])).toBe('/')
    expect(safeRedirect(null)).toBe('/')
  })

  it('allows a path with a query of its own', () => {
    expect(safeRedirect('/leads?view=my-open')).toBe('/leads?view=my-open')
  })
})

describe('the source and this test agree', () => {
  it('the rule in session.js is the rule tested here', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const source = fs.readFileSync(
      path.resolve(__dirname, '../../src/stores/session.js'),
      'utf8',
    )
    // The regex is the whole of the check; if it changes, this test should be revisited
    // rather than quietly continuing to test a copy.
    expect(source).toContain("/^\\/(?!\\/)/.test(target)")
  })
})

describe('the auth routes are public', () => {
  it('every auth screen is reachable without a session', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const source = fs.readFileSync(
      path.resolve(__dirname, '../../src/router.js'),
      'utf8',
    )

    for (const name of [
      "name: 'Login'",
      "name: 'Forgot Password'",
      "name: 'Update Password'",
      "name: 'Accept Invitation'",
    ]) {
      expect(source).toContain(name)
    }

    // Four routes, four `isPublic` marks. The guard reads that flag; a route without it
    // bounces to Login, and for Login itself that is a loop.
    expect(source.match(/isPublic: true/g)).toHaveLength(4)
  })

  it('the SPA no longer redirects out of itself', () => {
    // The bug this phase fixes. Asserted on the source because the alternative is
    // standing up a router and stubbing window.location, for one line.
    //
    // **Comments are stripped first.** The first version searched the whole file and
    // failed on the comment that explains what the old line was — a test that forbids
    // describing the bug you fixed is a test that gets the comment deleted.
    const fs = require('node:fs')
    const path = require('node:path')
    const source = fs.readFileSync(
      path.resolve(__dirname, '../../src/router.js'),
      'utf8',
    )
    const code = source
      .split('\n')
      .filter((line) => !line.trim().startsWith('//'))
      .join('\n')

    expect(code).not.toContain('window.location.href')
    // And the replacement is actually there.
    expect(code).toContain("next({ name: 'Login'")
  })

  it('the reset link and the route agree on the path', () => {
    // `frappe_core/password_reset.py:reset_link` builds `/crm/update-password?key=…`, and
    // the router mounts at `/crm`, so the route path is `/update-password`. A mismatch
    // fails nothing until somebody clicks a link in an email.
    const fs = require('node:fs')
    const path = require('node:path')

    const router = fs.readFileSync(
      path.resolve(__dirname, '../../src/router.js'),
      'utf8',
    )
    const backend = fs.readFileSync(
      path.resolve(
        __dirname,
        '../../../backend/frappe_core/password_reset.py',
      ),
      'utf8',
    )

    expect(router).toContain("path: '/update-password'")
    expect(backend).toContain('/crm/update-password?key=')
    expect(router).toContain("history: createWebHistory('/crm')")
  })
})
