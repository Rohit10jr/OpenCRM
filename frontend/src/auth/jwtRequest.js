/**
 * The frappe-ui request-layer patch.
 *
 * `main.js` centralises HTTP in a single line:
 *
 *     setConfig('resourceFetcher', frappeRequest)
 *
 * so swapping in this wrapper is the entire integration. Every `createResource`,
 * `createListResource` and `createDocumentResource` in the app routes through it
 * unchanged - PHASE_0_FOUNDATION.md section 7: "Do not touch the 225 createResource
 * call sites."
 *
 * Responsibilities:
 *   1. attach `Authorization: Bearer <access>`
 *   2. on 401, refresh once and replay the original request
 *   3. on refresh failure, clear tokens and bounce to login
 *
 * CSRF handling is deliberately absent: it existed to protect cookie auth, and there
 * are no cookies any more.
 *
 * See ../../JWT_PATCH.md - a frappe-ui upgrade must not silently revert this.
 */

import { frappeRequest } from 'frappe-ui'
import { clearTokens, getAccessToken, refreshAccessToken } from './tokens'

function withAuthHeader(options) {
  const token = getAccessToken()
  if (!token) return options
  return {
    ...options,
    headers: { ...(options?.headers || {}), Authorization: `Bearer ${token}` },
  }
}

function isAuthError(error) {
  // The backend emits Frappe's own envelope (frappe_core/exceptions.py), so an
  // expired token arrives as exc_type AuthenticationError with HTTP 401.
  return (
    error?.exc_type === 'AuthenticationError' ||
    error?.status === 401 ||
    error?.response?.status === 401
  )
}

export async function jwtRequest(options) {
  try {
    return await frappeRequest(withAuthHeader(options))
  } catch (error) {
    if (!isAuthError(error)) throw error

    const refreshed = await refreshAccessToken()
    if (!refreshed) {
      clearTokens()
      throw error
    }
    return frappeRequest(withAuthHeader(options))
  }
}

export default jwtRequest
