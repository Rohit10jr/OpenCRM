/**
 * JWT PATCH, second half (see ../../JWT_PATCH.md): the bearer header for every request
 * that does not go through `resourceFetcher`.
 *
 * `setConfig('resourceFetcher', jwtRequest)` in main.js covers the 225 createResource
 * call sites and nothing else. frappe-ui's `call()` - imported directly in 32 files, and
 * used by the router guard itself - and its two upload helpers build their own `fetch`
 * or `XMLHttpRequest`, so every one of those requests went out without a token and
 * answered 401 (docs/FINDINGS.md 30). Upstream never sees this: its `sid` cookie rides
 * on every request for free, which is exactly what a bearer header does not do.
 *
 * Rather than touch 32 components, the header is attached at the two browser
 * primitives, for same-origin `/api/` URLs only, and only when the caller has not set
 * one (jwtRequest sets its own). The login and refresh endpoints are left alone: a stale
 * access token on the refresh call would be authenticated before the refresh ran.
 *
 * No refresh-on-401 here. That stays in jwtRequest; a bare `call()` that meets an
 * expired token fails as it did upstream with an expired session.
 */
import { getAccessToken } from './tokens'

const API_PATH = /^\/api\//
const SKIP = new Set(['/api/method/login', '/api/method/token/refresh'])

function wantsToken(url) {
  try {
    const parsed = new URL(url, window.location.origin)
    return (
      parsed.origin === window.location.origin &&
      API_PATH.test(parsed.pathname) &&
      !SKIP.has(parsed.pathname)
    )
  } catch {
    return false
  }
}

export function installAuthInterceptor() {
  const nativeFetch = window.fetch.bind(window)
  window.fetch = (input, init) => {
    const url =
      typeof input === 'string' ? input : input instanceof URL ? input.href : input?.url
    const token = url && wantsToken(url) ? getAccessToken() : null
    if (!token) return nativeFetch(input, init)
    const headers = new Headers(
      init?.headers || (input instanceof Request ? input.headers : undefined),
    )
    if (!headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    return nativeFetch(input, { ...init, headers })
  }

  const nativeOpen = XMLHttpRequest.prototype.open
  const nativeSend = XMLHttpRequest.prototype.send
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__crmWantsToken = wantsToken(String(url))
    return nativeOpen.call(this, method, url, ...rest)
  }
  XMLHttpRequest.prototype.send = function (body) {
    const token = this.__crmWantsToken ? getAccessToken() : null
    if (token) {
      this.setRequestHeader('Authorization', `Bearer ${token}`)
    }
    return nativeSend.call(this, body)
  }
}
