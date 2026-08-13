/**
 * JWT storage for the Django port.
 *
 * Frappe authenticates with an `sid` cookie; this port uses bearer tokens
 * (PORT_PLAN.md section 10, PHASE_0_FOUNDATION.md section 7). That is the ONE
 * sanctioned deviation from the Frappe wire protocol.
 *
 * Nothing here touches the 225 `createResource` call sites.
 */

const ACCESS_KEY = 'crm:access_token'
const REFRESH_KEY = 'crm:refresh_token'

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
