/**
 * The Exotel call state machine, ported from `ExotelCallUI.vue:476-545`.
 *
 * Kept as a pure function of the webhook payload because that is what it is: Exotel sends a
 * flat bag of strings over the `exotel_call` socket event and the UI derives one of five
 * labels from it. The Vue version does this inline inside a component and mutates a timer
 * ref from the middle of the branch tree; that entanglement is the reason it is hard to
 * read, not the logic.
 *
 * **Ported literally, including the parts that look wrong.** The odd bits — outgoing calls
 * keyed on `Status`, incoming ones on `DialCallStatus`; `Legs[0][Status]` arriving as a
 * literal bracketed string key rather than a nested array; the missing `else` that lets an
 * unrecognised payload return `undefined` — are Exotel's shape and upstream's reading of
 * it. Tidying them would be inventing a protocol.
 */

/** Exotel's payload: flat, all-string, keys with literal brackets in them. */
export type ExotelCallPayload = Record<string, string | undefined>

export type CallStatus =
  | 'Ringing...'
  | 'In progress'
  | 'No answer'
  | 'Call ended'
  | 'Incoming call'

export type CallStatusResult = {
  status: CallStatus | undefined
  /** Which way the timer should move. The Vue original starts/stops a ref from inside
   *  the branches; returning the intent instead keeps this function pure. */
  timer: 'start' | 'stop' | 'none'
  /** Seconds, present only once the call is over. */
  durationSeconds?: number
  /** The other party, when this payload is the one that reveals it. */
  phoneNumber?: string
}

const NONE: CallStatusResult = { status: undefined, timer: 'none' }

export function exotelCallStatus(data: ExotelCallPayload): CallStatusResult {
  const leg0 = data['Legs[0][Status]']
  const leg1 = data['Legs[1][Status]']

  // Outgoing. Exotel dials the agent first, then the customer, so leg 1 going
  // `in-progress` is the moment the two are actually connected.
  if (data.EventType === 'answered' && data.Direction === 'outbound-api') {
    if (data.Status === 'in-progress' && leg0 === 'in-progress' && leg1 === '') {
      return { status: 'Ringing...', timer: 'none' }
    }
    if (data.Status === 'in-progress' && leg1 === 'in-progress') {
      return { status: 'In progress', timer: 'start' }
    }
  }

  if (data.EventType === 'terminal' && data.Direction === 'outbound-api') {
    const unanswered = ['no-answer', 'busy']
    if (
      (data.Status === 'no-answer' || data.Status === 'busy') &&
      (unanswered.includes(leg1 ?? '') || unanswered.includes(leg0 ?? ''))
    ) {
      return { status: 'No answer', timer: 'stop' }
    }
    if (data.Status === 'completed') {
      return { status: 'Call ended', timer: 'stop', durationSeconds: duration(data) }
    }
  }

  // Incoming. A different set of keys entirely — `CallType` and `DialCallStatus` rather
  // than `EventType` and `Status`.
  if (data.EventType === 'Dial' && data.Direction === 'incoming' && data.Status === 'busy') {
    return {
      status: 'Incoming call',
      timer: 'none',
      phoneNumber: data.From || data.CallFrom,
    }
  }
  if (
    data.Direction === 'incoming' &&
    data.CallType === 'incomplete' &&
    data.DialCallStatus === 'no-answer'
  ) {
    return { status: 'No answer', timer: 'stop' }
  }
  if (
    data.Direction === 'incoming' &&
    (data.CallType === 'completed' || data.CallType === 'client-hangup') &&
    (data.DialCallStatus === 'completed' || data.DialCallStatus === 'canceled')
  ) {
    return { status: 'Call ended', timer: 'stop', durationSeconds: duration(data) }
  }

  return NONE
}

function duration(data: ExotelCallPayload): number | undefined {
  const raw = data['Legs[0][OnCallDuration]'] || data.DialCallDuration
  const seconds = Number.parseInt(raw ?? '', 10)
  return Number.isNaN(seconds) ? undefined : seconds
}

/** `mm:ss`, or `h:mm:ss` past an hour. Matches `CountUpTimer.vue`'s output. */
export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return hours ? `${hours}:${pad(minutes)}:${pad(rest)}` : `${pad(minutes)}:${pad(rest)}`
}
