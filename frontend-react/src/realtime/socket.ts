import { getAccessToken, refreshAccessToken } from '@/auth/tokens'

/**
 * The realtime client — a raw WebSocket wearing socket.io's clothes.
 *
 * **A port of `frontend/src/socket.js`, not a rewrite.** The reconnect logic here —
 * backoff, full jitter, re-subscribe, refresh-once-per-delayed-attempt — was written and
 * tested in phase 6 and is load-bearing; `CLAUDE.md` rule 6 says not to reimplement it
 * from memory, and this does not. The comments below are the originals because each one
 * records a decision or a trap.
 *
 * Frappe pushes over socket.io, Django Channels speaks raw WebSocket, and there is no way
 * to keep the socket.io client. That is the second sanctioned frontend deviation, after
 * the JWT interceptor.
 *
 * **One thing that had to change for React**, and only one: the Vue version reached into
 * `frappe-ui`'s resource caches to service `refetch_resource`. There are no such caches
 * here, so the frame is handed to an `onRefetchResource` callback and the React binding
 * decides what to invalidate. The socket stays framework-agnostic, which is what let it
 * be ported rather than rewritten.
 */

/**
 * Matches `CLOSE_UNAUTHENTICATED` in backend/crm_app/consumers.py.
 *
 * Rarely seen, and that is deliberate on the server's side: it closes *before* accepting,
 * so a rejected handshake arrives here as an HTTP failure and a generic 1006, not as this
 * code. Refusing before accept is the stronger behaviour and worth keeping, so the "the
 * token was rejected" signal we actually act on is `looksLikeAuth` below, which also
 * covers a close that never opened. This constant still matters for any future close
 * that happens after accept.
 */
const CLOSE_UNAUTHENTICATED = 4001

const BASE_DELAY = 1000
const MAX_DELAY = 30000

export type SocketHandler = (payload: unknown) => void

export type CrmSocket = {
  on: (event: string, handler: SocketHandler) => CrmSocket
  off: (event: string, handler?: SocketHandler) => CrmSocket
  emit: (event: string, ...args: unknown[]) => CrmSocket
  close: () => void
  readonly connected: boolean
}

function socketUrl(token: string) {
  // Same origin by default: in production one reverse proxy fronts the SPA, the API and
  // /ws alike. `VITE_WS_ORIGIN` overrides it for a dev server that is not proxying ws.
  const configured = import.meta.env?.VITE_WS_ORIGIN
  const origin =
    configured ||
    `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
  // The token rides in the query string because a browser cannot set headers on a
  // WebSocket handshake. It therefore lands in server access logs, which is why access
  // tokens are short-lived and this reconnects with a fresh one.
  return `${origin}/ws/realtime?token=${encodeURIComponent(token)}`
}

/**
 * The set key for one document subscription.
 *
 * JSON rather than a delimited string: every CRM doctype name contains a space
 * ("CRM Lead"), and document names contain spaces and slashes routinely, so any
 * separator you pick is one a real key already uses.
 */
function subscriptionKey(args: unknown[]) {
  return JSON.stringify([String(args[0]), String(args[1])])
}

export function initSocket(
  onRefetchResource?: (cacheKey: unknown) => void,
): CrmSocket {
  const handlers = new Map<string, SocketHandler[]>()
  /** doc subscriptions to replay after a reconnect, as JSON `[doctype, name]` */
  const subscriptions = new Set<string>()

  let ws: WebSocket | null = null
  let attempts = 0
  let closedByUs = false
  let retriedAfterRefresh = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let opened = false

  function dispatch(event: string, payload: unknown) {
    const list = handlers.get(event)
    if (!list) return
    // Copy first: a handler is allowed to `off` itself, and mutating the array we are
    // iterating would skip the next one.
    for (const handler of [...list]) {
      try {
        handler(payload)
      } catch (error) {
        console.error(`[socket] handler for ${event} threw`, error)
      }
    }
  }

  function connect() {
    const token = getAccessToken()
    if (!token) {
      // Not logged in yet. The login flow calls `initSocket` again once tokens exist.
      return
    }

    opened = false
    ws = new WebSocket(socketUrl(token))

    ws.onopen = () => {
      opened = true
      attempts = 0
      retriedAfterRefresh = false
      for (const key of subscriptions) {
        const [doctype, name] = JSON.parse(key)
        send('doc_subscribe', [doctype, name])
      }
      dispatch('connect', null)
    }

    ws.onmessage = (raw) => {
      let frame: { event?: string; message?: unknown }
      try {
        frame = JSON.parse(raw.data)
      } catch {
        return
      }
      if (!frame?.event) return

      // The server's way of saying "this cached query is stale". In Vue this reached into
      // frappe-ui's resource caches; here the binding invalidates a query key.
      if (frame.event === 'refetch_resource') {
        const key = (frame.message as { cache_key?: unknown } | undefined)?.cache_key
        if (key) onRefetchResource?.(key)
        return
      }
      dispatch(frame.event, frame.message)
    }

    ws.onclose = async (closeEvent) => {
      dispatch('disconnect', null)
      if (closedByUs) return

      // A handshake the server refused never reaches `onopen`. That is what an expired
      // token looks like from here — the server closes before accepting, so its 4001 is
      // not delivered and the browser reports a generic 1006. Refresh once and retry;
      // it is also what a restarting backend looks like, which is why failure falls
      // through to the ordinary backoff instead of giving up.
      const looksLikeAuth = !opened || closeEvent.code === CLOSE_UNAUTHENTICATED
      if (looksLikeAuth && !retriedAfterRefresh) {
        retriedAfterRefresh = true
        const refreshed = await refreshAccessToken()
        if (refreshed) {
          connect()
          return
        }
      }

      scheduleReconnect()
    }

    ws.onerror = () => {
      // `onclose` always follows, so the backoff lives there and not in two places.
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    // Exponential with full jitter: without the jitter, every tab in every browser
    // reconnects on the same tick after a backend restart.
    const delay = Math.min(BASE_DELAY * 2 ** attempts, MAX_DELAY)
    attempts += 1
    reconnectTimer = setTimeout(
      () => {
        reconnectTimer = null
        // One refresh per *delayed* attempt, not one ever. The backoff is what prevents a
        // tight loop; without this reset, a token that expires during a long outage would
        // never be renewed and the socket would retry with a dead credential forever.
        retriedAfterRefresh = false
        connect()
      },
      Math.random() * delay,
    )
  }

  function send(event: string, args: unknown[]) {
    if (ws?.readyState !== WebSocket.OPEN) return false
    ws.send(JSON.stringify({ event, args }))
    return true
  }

  const socket: CrmSocket = {
    on(event, handler) {
      if (!handlers.has(event)) handlers.set(event, [])
      handlers.get(event)!.push(handler)
      return socket
    },

    off(event, handler) {
      if (!handler) {
        handlers.delete(event)
        return socket
      }
      const list = handlers.get(event)
      if (!list) return socket
      const index = list.indexOf(handler)
      if (index !== -1) list.splice(index, 1)
      return socket
    },

    emit(event, ...args) {
      // `doc_subscribe` / `doc_unsubscribe` are remembered so a reconnect can replay
      // them; anything else is best-effort and dropped if the socket is down.
      if (event === 'doc_subscribe' && args.length >= 2) {
        subscriptions.add(subscriptionKey(args))
      } else if (event === 'doc_unsubscribe' && args.length >= 2) {
        subscriptions.delete(subscriptionKey(args))
      }
      send(event, args)
      return socket
    },

    close() {
      closedByUs = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
    },

    get connected() {
      return ws?.readyState === WebSocket.OPEN
    },
  }

  connect()
  return socket
}
