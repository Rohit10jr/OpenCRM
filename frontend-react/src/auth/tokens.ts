/**
 * JWT storage. A direct port of `frontend/src/auth/tokens.js`.
 *
 * Frappe authenticates with an `sid` cookie; this port uses bearer tokens
 * (PORT_PLAN.md section 10). That is the ONE sanctioned deviation from the Frappe wire
 * protocol, so this file and the interceptor in `client.ts` are the whole of it.
 *
 * The single-flight guard in `refreshAccessToken` is load-bearing and was not
 * reimplemented from memory — see the comment on it.
 *
 * `fetch` rather than the axios instance, deliberately: the instance's response
 * interceptor is what calls this, and routing the refresh back through it would let a
 * 401 on the refresh endpoint recurse.
 */

const ACCESS_KEY = 'crm:access_token'
const REFRESH_KEY = 'crm:refresh_token'
const REFRESH_URL = '/api/method/token/refresh'

export type TokenPair = { access?: string; refresh?: string }

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens({ access, refresh }: TokenPair) {
  if (access) localStorage.setItem(ACCESS_KEY, access)
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

let refreshInFlight: Promise<boolean> | null = null

/**
 * Exchange the refresh token for a new pair. Resolves to true on success.
 *
 * Concurrent callers collapse into one request: a list screen can fire a dozen requests
 * at once and each must not spend a refresh token, and with `ROTATE_REFRESH_TOKENS` the
 * loser of that race would be redeeming a token the winner has already blacklisted.
 */
export function refreshAccessToken(): Promise<boolean> {
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
 * Decode only — never trust this for anything the server must enforce; the server
 * re-validates the signature on every request.
 */
export function getTokenUser(): string | null {
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
