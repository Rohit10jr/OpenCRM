/**
 * The realtime client — phase 6.
 *
 * PHASE_6_REALTIME.md section 4 has two criteria nothing else covers: *"Client reconnects
 * with backoff and re-subscribes on reconnect"*. Both are invisible in normal use and
 * only show up as "realtime quietly stopped working after the backend restarted", so they
 * are tested here against a fake WebSocket rather than left to be discovered in
 * production.
 */

import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

const tokens = vi.hoisted(() => ({
  access: 'header.payload.signature',
  refreshed: true,
  refreshCalls: 0,
}))

vi.mock('@/auth/tokens', () => ({
  getAccessToken: () => tokens.access,
  refreshAccessToken: async () => {
    tokens.refreshCalls += 1
    return tokens.refreshed
  },
}))

vi.mock('frappe-ui', () => ({
  getCachedResource: (key) => reloadable[key] || null,
  getCachedListResource: () => null,
}))

let reloadable = {}
let sockets = []

/** Just enough WebSocket to drive the client, with the transitions under our control. */
class FakeWebSocket {
  static OPEN = 1
  static CLOSED = 3

  constructor(url) {
    this.url = url
    this.readyState = 0
    this.sent = []
    sockets.push(this)
  }

  send(data) {
    this.sent.push(JSON.parse(data))
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED
  }

  // -- test-side drivers --
  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  deliver(frame) {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }

  drop(code = 1006) {
    this.readyState = FakeWebSocket.CLOSED
    return this.onclose?.({ code })
  }
}

let initSocket

beforeEach(async () => {
  sockets = []
  reloadable = {}
  tokens.access = 'header.payload.signature'
  tokens.refreshed = true
  tokens.refreshCalls = 0
  globalThis.WebSocket = FakeWebSocket
  globalThis.window.location = { protocol: 'http:', host: 'localhost:8080' }
  vi.useFakeTimers()
  vi.resetModules()
  ;({ initSocket } = await import('@/socket'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('event surface', () => {
  it('keeps socket.io’s on/off/emit shape so no component changes', () => {
    const socket = initSocket()
    expect(typeof socket.on).toBe('function')
    expect(typeof socket.off).toBe('function')
    expect(typeof socket.emit).toBe('function')
  })

  it('delivers an event to its handler', () => {
    const socket = initSocket()
    const seen = []
    socket.on('crm_notification', (payload) => seen.push(payload))
    sockets[0].open()
    sockets[0].deliver({ event: 'crm_notification', message: null })
    expect(seen).toEqual([null])
  })

  it('off(event) removes every handler for that event', () => {
    // Notifications.vue:128 calls `off` with no handler; Activities.vue:565 passes one.
    const socket = initSocket()
    const seen = []
    socket.on('crm_notification', () => seen.push(1))
    socket.on('crm_notification', () => seen.push(2))
    socket.off('crm_notification')
    sockets[0].open()
    sockets[0].deliver({ event: 'crm_notification' })
    expect(seen).toEqual([])
  })

  it('off(event, handler) removes only that handler', () => {
    const socket = initSocket()
    const seen = []
    const first = () => seen.push(1)
    socket.on('docinfo_update', first)
    socket.on('docinfo_update', () => seen.push(2))
    socket.off('docinfo_update', first)
    sockets[0].open()
    sockets[0].deliver({ event: 'docinfo_update' })
    expect(seen).toEqual([2])
  })

  it('a throwing handler does not stop the others', () => {
    const socket = initSocket()
    const seen = []
    socket.on('crm_notification', () => {
      throw new Error('boom')
    })
    socket.on('crm_notification', () => seen.push('ran'))
    sockets[0].open()
    sockets[0].deliver({ event: 'crm_notification' })
    expect(seen).toEqual(['ran'])
  })

  it('reloads a cached resource on refetch_resource', () => {
    // Carried over from the socket.io client verbatim — frappe-ui's cache invalidation
    // depends on it.
    const reload = vi.fn()
    reloadable['some-key'] = { reload }
    initSocket()
    sockets[0].open()
    sockets[0].deliver({
      event: 'refetch_resource',
      message: { cache_key: 'some-key' },
    })
    expect(reload).toHaveBeenCalled()
  })

  it('ignores a malformed frame instead of throwing', () => {
    initSocket()
    sockets[0].open()
    expect(() => sockets[0].onmessage({ data: '}{' })).not.toThrow()
  })
})

describe('emit', () => {
  it('sends doc_subscribe in the shape the consumer parses', () => {
    const socket = initSocket()
    sockets[0].open()
    socket.emit('doc_subscribe', 'CRM Lead', 'CRM-LEAD-0001')
    expect(sockets[0].sent).toEqual([
      { event: 'doc_subscribe', args: ['CRM Lead', 'CRM-LEAD-0001'] },
    ])
  })

  it('drops an emit while the socket is down rather than throwing', () => {
    const socket = initSocket()
    expect(() => socket.emit('doc_subscribe', 'CRM Lead', 'x')).not.toThrow()
  })
})

describe('reconnect', () => {
  it('reconnects after an unexpected close', () => {
    initSocket()
    sockets[0].open()
    sockets[0].drop()
    vi.runOnlyPendingTimers()
    expect(sockets).toHaveLength(2)
  })

  it('backs off — each successive attempt waits longer', async () => {
    // Full jitter means the delay is random within a growing window, so the property to
    // assert is the *ceiling*, not an exact value. Pin Math.random to its maximum and the
    // window itself becomes observable.
    //
    // The sockets are never opened and the refresh always fails, which is what a backend
    // that is simply down looks like — and the only path where the counter keeps
    // climbing. A successful open resets it, on purpose.
    vi.spyOn(Math, 'random').mockReturnValue(0.999999)
    tokens.refreshed = false
    initSocket()

    const delays = []
    for (let i = 0; i < 3; i++) {
      await sockets[sockets.length - 1].drop()
      delays.push(nextDelay())
    }
    expect(delays[1]).toBeGreaterThan(delays[0])
    expect(delays[2]).toBeGreaterThan(delays[1])
    Math.random.mockRestore()
  })

  it('caps the backoff so it keeps trying', async () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.999999)
    tokens.refreshed = false
    initSocket()
    for (let i = 0; i < 12; i++) {
      await sockets[sockets.length - 1].drop()
      vi.runOnlyPendingTimers()
    }
    await sockets[sockets.length - 1].drop()
    expect(nextDelay()).toBeLessThanOrEqual(30000)
    Math.random.mockRestore()
  })

  it('a successful connection resets the backoff', async () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.999999)
    tokens.refreshed = false
    initSocket()
    for (let i = 0; i < 4; i++) {
      await sockets[sockets.length - 1].drop()
      vi.runOnlyPendingTimers()
    }
    await sockets[sockets.length - 1].drop()
    const grown = nextDelay()

    sockets[sockets.length - 1].open()
    sockets[sockets.length - 1].drop()
    expect(nextDelay()).toBeLessThan(grown)
    Math.random.mockRestore()
  })

  it('re-subscribes to open documents on reconnect', () => {
    // The one that matters. Group membership dies with the connection, so without this
    // a reconnected client looks live and receives nothing.
    //
    // The doctype deliberately contains a space, because every CRM doctype does. An
    // earlier draft keyed the subscription set on `${doctype} ${name}` and split on the
    // space, which turned "CRM Lead" into a doctype of "CRM" on replay.
    const socket = initSocket()
    sockets[0].open()
    socket.emit('doc_subscribe', 'CRM Lead', 'CRM-LEAD-0001')

    sockets[0].drop()
    vi.runOnlyPendingTimers()
    sockets[1].open()

    expect(sockets[1].sent).toEqual([
      { event: 'doc_subscribe', args: ['CRM Lead', 'CRM-LEAD-0001'] },
    ])
  })

  it('does not re-subscribe to a document the user has closed', () => {
    const socket = initSocket()
    sockets[0].open()
    socket.emit('doc_subscribe', 'CRM Lead', 'CRM-LEAD-0001')
    socket.emit('doc_unsubscribe', 'CRM Lead', 'CRM-LEAD-0001')

    sockets[0].drop()
    vi.runOnlyPendingTimers()
    sockets[1].open()

    expect(sockets[1].sent).toEqual([])
  })

  it('does not reconnect after an explicit close', () => {
    const socket = initSocket()
    sockets[0].open()
    socket.close()
    sockets[0].drop()
    vi.runOnlyPendingTimers()
    expect(sockets).toHaveLength(1)
  })
})

describe('authentication', () => {
  it('does not connect at all without a token', () => {
    tokens.access = null
    initSocket()
    expect(sockets).toHaveLength(0)
  })

  it('puts the token in the query string', () => {
    initSocket()
    expect(sockets[0].url).toContain('token=header.payload.signature')
  })

  it('refreshes and retries when the server rejects the token', async () => {
    // Close code 4001 is CLOSE_UNAUTHENTICATED in backend/crm_app/consumers.py. Retrying
    // with the same token would spin forever, so the client refreshes first.
    initSocket()
    sockets[0].open()
    await sockets[0].drop(4001)
    expect(tokens.refreshCalls).toBe(1)
    expect(sockets).toHaveLength(2)
  })

  it('treats a handshake that never opened as an auth failure', async () => {
    // The realistic case. The server rejects *before* accepting, so its 4001 never
    // reaches the browser — an expired token arrives here as a plain 1006 on a socket
    // that never opened. Keying only on 4001 would leave the refresh path dead.
    initSocket()
    await sockets[0].drop(1006)
    expect(tokens.refreshCalls).toBe(1)
    expect(sockets).toHaveLength(2)
  })

  it('backs off instead of tight-looping when the refresh fails', async () => {
    tokens.refreshed = false
    initSocket()
    sockets[0].open()
    await sockets[0].drop(4001)
    // No immediate retry...
    expect(sockets).toHaveLength(1)
    // ...but it does come back, because this also looks like a restarting backend.
    vi.runOnlyPendingTimers()
    expect(sockets).toHaveLength(2)
  })

  it('does not refresh twice for one reconnect attempt', async () => {
    initSocket()
    sockets[0].open()
    await sockets[0].drop(4001)
    await sockets[1].drop(4001)
    expect(tokens.refreshCalls).toBe(1)
    expect(sockets).toHaveLength(2)
  })

  it('refreshes again on a later delayed attempt', async () => {
    // A token that expires during a long outage must still be renewed.
    initSocket()
    sockets[0].open()
    await sockets[0].drop(4001)
    await sockets[1].drop(1006)
    vi.runOnlyPendingTimers()
    await sockets[2].drop(1006)
    expect(tokens.refreshCalls).toBe(2)
  })
})

/** The delay of the single pending reconnect timer. */
function nextDelay() {
  const timers = vi.getTimerCount()
  if (!timers) return 0
  // vitest exposes no delay introspection, so measure it: advance until the timer fires.
  let elapsed = 0
  const step = 1
  while (vi.getTimerCount() > 0 && elapsed < 60000) {
    vi.advanceTimersByTime(step)
    elapsed += step
  }
  return elapsed
}
