import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'
import { clearTokens, getAccessToken, refreshAccessToken } from '@/auth/tokens'

/**
 * The single HTTP client. This is the React equivalent of `frontend/src/auth/jwtRequest.js`,
 * which patched `frappe-ui`'s request layer; here the same three responsibilities live in
 * axios interceptors:
 *
 *   1. attach `Authorization: Bearer <access>`
 *   2. on 401, refresh once and replay the original request
 *   3. on refresh failure, clear tokens and bounce to login
 *
 * CSRF handling is deliberately absent: it existed to protect cookie auth, and there are
 * no cookies any more.
 */
export const client: AxiosInstance = axios.create({ baseURL: '/' })

client.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/** Marks a config that has already been replayed, so a second 401 gives up. */
type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean }

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<FrappeErrorBody>) => {
    const config = error.config as RetriableConfig | undefined

    // The backend emits Frappe's own envelope (frappe_core/exceptions.py), so an expired
    // token arrives as exc_type AuthenticationError with HTTP 401.
    const isAuthError =
      error.response?.status === 401 ||
      error.response?.data?.exc_type === 'AuthenticationError'

    if (!isAuthError || !config || config._retried) throw error

    config._retried = true
    const refreshed = await refreshAccessToken()
    if (!refreshed) {
      clearTokens()
      // A full reload rather than a router navigation: this runs outside React, and the
      // query cache holds data belonging to a session that no longer exists.
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
      throw error
    }
    return client(config)
  },
)

export type FrappeErrorBody = {
  exc_type?: string
  exception?: string
  /** A JSON string whose items are themselves JSON strings. Frappe's shape, not ours. */
  _server_messages?: string
  message?: string
}

/**
 * The human-readable message behind a failed request.
 *
 * `_server_messages` is the load-bearing field — `frappe-ui` derives `error.messages`
 * from it and so does this — and its double-encoding is Frappe's, faithfully reproduced
 * by the backend (`exceptions.py:92`). Hence the nested parse.
 */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (!axios.isAxiosError(error)) return fallback
  const body = error.response?.data as FrappeErrorBody | undefined
  if (!body) return error.message || fallback

  if (body._server_messages) {
    try {
      const outer = JSON.parse(body._server_messages) as string[]
      const first = JSON.parse(outer[0]) as { message?: string }
      if (first?.message) return first.message
    } catch {
      // Malformed envelope — fall through to the plainer fields below.
    }
  }
  return body.message || body.exception || fallback
}

/**
 * `POST /api/method/<dotted.path>` — the React answer to `frappe-ui`'s `call`, which the
 * Vue app uses at 32 sites.
 *
 * The `{ message: ... }` envelope is unwrapped here so that no caller has to know about
 * it (PORT_PLAN.md section 3).
 */
export async function call<T = unknown>(
  method: string,
  args: Record<string, unknown> = {},
): Promise<T> {
  const response = await client.post<{ message: T }>(`/api/method/${method}`, args)
  return response.data?.message as T
}

/**
 * `GET /api/method/<dotted.path>`.
 *
 * Frappe's whitelisted methods accept either verb, but GET keeps read-only calls
 * cacheable and matches what the Vue app sends for list reads.
 */
export async function callGet<T = unknown>(
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  const response = await client.get<{ message: T }>(`/api/method/${method}`, {
    // Frappe expects JSON-encoded values in the query string for anything non-scalar.
    params: encodeParams(params),
  })
  return response.data?.message as T
}

/** Frappe reads structured query params as JSON strings; scalars pass through. */
export function encodeParams(params: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    out[key] =
      typeof value === 'object' ? JSON.stringify(value) : String(value)
  }
  return out
}
