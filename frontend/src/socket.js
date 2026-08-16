/**
 * The realtime client — a raw WebSocket wearing socket.io's clothes.
 *
 * PHASE_6_REALTIME.md section 1: Frappe pushes over socket.io, Django Channels speaks
 * raw WebSocket, and there is no way to keep the socket.io client. This is the second
 * (and last) sanctioned frontend deviation, after the JWT interceptor — see
 * ../JWT_PATCH.md, which lists it alongside the first.
 *
 * **Only the transport changes.** The surface the app already calls is reproduced
 * exactly, because every one of the seven call sites uses it:
 *
 *     $socket.on('crm_notification', handler)
 *     $socket.off('crm_notification')            // all handlers for the event
 *     $socket.off('docinfo_update', handler)     // just that one
 *     $socket.emit('doc_subscribe', doctype, docname)
 *
 * so `Notifications.vue`, `Activities.vue`, `ERPNextSettings.vue`, `ExotelCallUI.vue`
 * and `Deal.vue` need no edit at all. Event names and payloads are the backend's, which
 * are upstream's (PHASE_6_REALTIME.md section 2).
 *
 * Two things socket.io did for free and this has to do by hand:
 *
 *   1. **Reconnect with backoff.** A dropped socket that never comes back is worse than
 *      no socket, because the UI looks live and is not.
 *   2. **Re-subscribe on reconnect.** Server-side group membership dies with the
 *      connection, so the doc subscriptions have to be replayed or a reconnected client
 *      silently stops receiving document events.
 */

import { getCachedListResource, getCachedResource } from 'frappe-ui'
import { getAccessToken, refreshAccessToken } from './auth/tokens'

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

function socketUrl(token) {
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
function subscriptionKey([doctype, name]) {
  return JSON.stringify([String(doctype), String(name)])
}

export function initSocket() {
  const handlers = new Map()
  /** doc subscriptions to replay after a reconnect, as JSON `[doctype, name]` */
  const subscriptions = new Set()

  let ws = null
  let attempts = 0
  let closedByUs = false
  let retriedAfterRefresh = false
  let reconnectTimer = null
  let opened = false

  function dispatch(event, payload) {
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
      let frame
      try {
        frame = JSON.parse(raw.data)
      } catch {
        return
      }
      if (!frame?.event) return

      // Kept from the socket.io client: frappe-ui caches list and doc resources, and
      // this is how the server tells one to reload.
      if (frame.event === 'refetch_resource') {
        const key = frame.message?.cache_key
        if (key) {
          const resource =
            getCachedResource(key) || getCachedListResource(key)
          if (resource) resource.reload()
        }
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
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      // One refresh per *delayed* attempt, not one ever. The backoff is what prevents a
      // tight loop; without this reset, a token that expires during a long outage would
      // never be renewed and the socket would retry with a dead credential forever.
      retriedAfterRefresh = false
      connect()
    }, Math.random() * delay)
  }

  function send(event, args) {
    if (ws?.readyState !== WebSocket.OPEN) return false
    ws.send(JSON.stringify({ event, args }))
    return true
  }

  const socket = {
    on(event, handler) {
      if (!handlers.has(event)) handlers.set(event, [])
      handlers.get(event).push(handler)
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
