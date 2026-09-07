import { describe, expect, it } from 'vitest'
import { exotelCallStatus, formatDuration, type ExotelCallPayload } from './callStatus'

/**
 * The Exotel state machine, pinned.
 *
 * **This is the one piece of run 5 the browser harness can never reach.** The panel is
 * driven by an `exotel_call` socket event published by the server when a real call happens;
 * nothing in a test run can make one occur. So the branch logic is checked here, where it
 * is a pure function of a flat bag of strings, and the harness is left to prove the panel
 * mounts.
 *
 * Everything below pins **upstream's** behaviour (`ExotelCallUI.vue:476-545`), including
 * the parts that look like mistakes. If a test here looks wrong, read that file before
 * changing it — the odd shapes are Exotel's, and "fixing" one silently invents a protocol.
 */

/** Exotel sends every key on every event; omitting one is not the same as it being blank. */
const outbound = (extra: ExotelCallPayload): ExotelCallPayload => ({
  Direction: 'outbound-api',
  ...extra,
})

describe('exotelCallStatus — outgoing', () => {
  it('reads leg 1 being blank as still ringing', () => {
    const result = exotelCallStatus(
      outbound({
        EventType: 'answered',
        Status: 'in-progress',
        'Legs[0][Status]': 'in-progress',
        'Legs[1][Status]': '',
      }),
    )
    expect(result.status).toBe('Ringing...')
    // The customer has not picked up, so nothing is being timed yet.
    expect(result.timer).toBe('none')
  })

  /**
   * The subtle one, and the reason this file exists.
   *
   * Upstream tests `Legs[1][Status] == ''` — an *empty* string, not a missing key. Exotel
   * dials the agent first and the customer second, so leg 1 exists and is blank while the
   * second leg is still being placed. Relaxing this to a falsy check would call a payload
   * that never mentions leg 1 "Ringing", which is a different call state entirely.
   */
  it('does not call it ringing when leg 1 is absent rather than blank', () => {
    const result = exotelCallStatus(
      outbound({
        EventType: 'answered',
        Status: 'in-progress',
        'Legs[0][Status]': 'in-progress',
      }),
    )
    expect(result.status).toBeUndefined()
  })

  it('starts the timer only once both legs are connected', () => {
    const result = exotelCallStatus(
      outbound({
        EventType: 'answered',
        Status: 'in-progress',
        'Legs[1][Status]': 'in-progress',
      }),
    )
    expect(result.status).toBe('In progress')
    expect(result.timer).toBe('start')
  })

  it('reports no answer when either leg was unanswered', () => {
    for (const leg of ['Legs[0][Status]', 'Legs[1][Status]']) {
      for (const value of ['no-answer', 'busy']) {
        const result = exotelCallStatus(
          outbound({ EventType: 'terminal', Status: 'busy', [leg]: value }),
        )
        expect(result.status).toBe('No answer')
        expect(result.timer).toBe('stop')
      }
    }
  })

  it('ends the call with a duration, preferring the leg over the dial total', () => {
    const result = exotelCallStatus(
      outbound({
        EventType: 'terminal',
        Status: 'completed',
        'Legs[0][OnCallDuration]': '95',
        DialCallDuration: '120',
      }),
    )
    expect(result.status).toBe('Call ended')
    expect(result.timer).toBe('stop')
    // `Legs[0][OnCallDuration]` is talk time; `DialCallDuration` includes the ringing.
    expect(result.durationSeconds).toBe(95)
  })

  it('falls back to the dial duration when the leg has none', () => {
    const result = exotelCallStatus(
      outbound({ EventType: 'terminal', Status: 'completed', DialCallDuration: '42' }),
    )
    expect(result.durationSeconds).toBe(42)
  })

  it('reports no duration rather than NaN when neither field parses', () => {
    const result = exotelCallStatus(
      outbound({ EventType: 'terminal', Status: 'completed', DialCallDuration: '' }),
    )
    expect(result.status).toBe('Call ended')
    // `Number.parseInt('')` is NaN, and NaN reaching `formatDuration` renders "NaN:NaN".
    expect(result.durationSeconds).toBeUndefined()
  })
})

describe('exotelCallStatus — incoming', () => {
  /**
   * Incoming calls key on an entirely different set of fields — `CallType` and
   * `DialCallStatus` rather than `EventType` and `Status`. That is Exotel's shape, not a
   * porting slip, and it is why the function has two halves that share nothing.
   */
  it('surfaces the caller number on the ringing event', () => {
    const result = exotelCallStatus({
      EventType: 'Dial',
      Direction: 'incoming',
      Status: 'busy',
      From: '+919000000001',
    })
    expect(result.status).toBe('Incoming call')
    expect(result.phoneNumber).toBe('+919000000001')
  })

  it('falls back to CallFrom when From is absent', () => {
    const result = exotelCallStatus({
      EventType: 'Dial',
      Direction: 'incoming',
      Status: 'busy',
      CallFrom: '+919000000002',
    })
    expect(result.phoneNumber).toBe('+919000000002')
  })

  it('reports a missed incoming call', () => {
    const result = exotelCallStatus({
      Direction: 'incoming',
      CallType: 'incomplete',
      DialCallStatus: 'no-answer',
    })
    expect(result.status).toBe('No answer')
    expect(result.timer).toBe('stop')
  })

  it('treats a client hangup as an ended call, not a missed one', () => {
    const result = exotelCallStatus({
      Direction: 'incoming',
      CallType: 'client-hangup',
      DialCallStatus: 'canceled',
      DialCallDuration: '17',
    })
    expect(result.status).toBe('Call ended')
    expect(result.durationSeconds).toBe(17)
  })
})

describe('exotelCallStatus — unrecognised payloads', () => {
  /**
   * Exotel sends intermediate events this machine does not name, and upstream's `if` chain
   * has no `else`. The panel relies on that: an unnamed payload leaves the last known
   * status on screen rather than blanking mid-call.
   */
  it('returns no status so the caller can keep the last one', () => {
    for (const payload of [{}, { EventType: 'answered' }, { Direction: 'outbound-api' }]) {
      const result = exotelCallStatus(payload)
      expect(result.status).toBeUndefined()
      expect(result.timer).toBe('none')
    }
  })
})

describe('formatDuration', () => {
  it('pads to mm:ss below an hour', () => {
    expect(formatDuration(0)).toBe('00:00')
    expect(formatDuration(9)).toBe('00:09')
    expect(formatDuration(95)).toBe('01:35')
    expect(formatDuration(3599)).toBe('59:59')
  })

  it('grows an hours field rather than showing 60+ minutes', () => {
    expect(formatDuration(3600)).toBe('1:00:00')
    expect(formatDuration(3661)).toBe('1:01:01')
  })

  it('does not render a negative or fractional duration', () => {
    // A clock skew between the webhook and the browser produced a negative once.
    expect(formatDuration(-5)).toBe('00:00')
    expect(formatDuration(12.7)).toBe('00:12')
  })
})
