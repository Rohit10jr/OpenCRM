/**
 * Token storage — the JWT patch's second half, docs/FINDINGS.md 38.
 *
 * frappe-ui has its own "who is signed in" helper, `frappe-ui/frappe/session.js`, which
 * reads the `user_id` cookie Frappe sets at login. This app never had one, so
 * `useOnboarding()` in the sidebar saw nobody and the layout failed to render. The
 * cookie is now written and cleared beside the tokens; these tests read it back the way
 * that helper does. The helper itself is not exported by the package, so its two-line
 * parse is reproduced here verbatim.
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { clearTokens, getTokenUser, setTokens } from '@/auth/tokens'

// `frappe-ui/frappe/session.js:2-3`.
function libraryReadsUser() {
  let cookies = new URLSearchParams(document.cookie.split('; ').join('&'))
  return cookies.get('user_id')
}

function fakeJwt(claims) {
  const part = (obj) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${part({ alg: 'HS256', typ: 'JWT' })}.${part(claims)}.signature`
}

const far = Math.floor(Date.now() / 1000) + 3600

beforeEach(() => {
  localStorage.clear()
  document.cookie = 'user_id=; path=/; Max-Age=0'
})

describe('the user_id cookie frappe-ui reads', () => {
  it('is written from the access token at login', () => {
    setTokens({ access: fakeJwt({ user_id: 'alice@example.com', exp: far }), refresh: 'r' })
    expect(getTokenUser()).toBe('alice@example.com')
    expect(libraryReadsUser()).toBe('alice@example.com')
  })

  it('survives the @ in an address, which the library decodes', () => {
    setTokens({ access: fakeJwt({ user_id: 'grace@example.com', exp: far }) })
    expect(document.cookie).toContain('user_id=grace%40example.com')
    expect(libraryReadsUser()).toBe('grace@example.com')
  })

  it('is removed with the tokens at sign-out', () => {
    setTokens({ access: fakeJwt({ user_id: 'alice@example.com', exp: far }), refresh: 'r' })
    clearTokens()
    expect(getTokenUser()).toBeNull()
    expect(libraryReadsUser()).toBeNull()
  })
})
