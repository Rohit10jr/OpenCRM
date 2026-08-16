/**
 * JWT storage for the Django port.
 *
 * Frappe authenticates with an `sid` cookie; this port uses bearer tokens
 * (PORT_PLAN.md section 10, PHASE_0_FOUNDATION.md section 7). That is the ONE
 * sanctioned deviation from the Frappe wire protocol.
 *
 * Nothing here touches the 225 `createResource` call sites.
 *
 * `refreshAccessToken` moved here in phase 6, from `jwtRequest.js`. It now has two
 * callers — the request interceptor and the WebSocket client, which needs a fresh token
 * when the server closes the socket with 4001 — and the single-flight guard is only a
 * guarantee if there is one of it.
 */

const ACCESS_KEY = 'crm:access_token'
const REFRESH_KEY = 'crm:refresh_token'
const REFRESH_URL = '/api/method/token/refresh'

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens({ access, refresh }) {
  if (access) localStorage.setItem(ACCESS_KEY, access)
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

let refreshInFlight = null

/**
 * Exchange the refresh token for a new pair. Resolves to true on success.
 *
 * Concurrent callers collapse into one request: a list screen can fire a dozen requests
 * at once and each must not spend a refresh token, and with `ROTATE_REFRESH_TOKENS` the
 * loser of that race would be redeeming a token the winner has already blacklisted.
 */
export function refreshAccessToken() {
  const refresh = getRefreshToken()
  if (!refresh) return Promise.resolve(false)

  if (!refreshInFlight) {
    refreshInFlight = fetch(REFRESH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!body?.message?.access) return false
        setTokens(body.message)
        return true
      })
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null
      })
  }

  return refreshInFlight
}

/**
 * The user id (an email) carried in the access token's `user_id` claim.
 *
 * Replaces `sessionStore.sessionUser()`'s read of the `user_id` cookie, which no
 * longer exists once cookies are gone. Decode only - never trust this for anything
 * the server must enforce; the server re-validates the signature on every request.
 */
export function getTokenUser() {
  const token = getAccessToken()
  if (!token) return null
  try {
    const payload = token.split('.')[1]
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    const claims = JSON.parse(json)
    if (claims.exp && claims.exp * 1000 < Date.now()) return null
    return claims.user_id || null
  } catch {
    return null
  }
}
