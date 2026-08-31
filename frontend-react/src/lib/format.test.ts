import { describe, expect, it } from 'vitest'
import { formatCurrency, parseAssignees, toLocalInput } from './format'

/**
 * The timezone bug Codex found in run 2, pinned.
 *
 * The API stores and returns UTC; `<input type="datetime-local">` has no timezone. Slicing
 * the ISO string showed 14:30 to a reader in Berlin whose deadline was really 16:30, and
 * saved their local 14:30 back as 14:30 UTC — consistent, and wrong by the offset for
 * everyone outside UTC.
 *
 * These assertions are written against the *runner's* offset rather than a fixed zone, so
 * they hold wherever this is run — including in UTC, where the bug is invisible.
 */
describe('toLocalInput', () => {
  it('shifts a stored UTC timestamp into local wall-clock time', () => {
    const stored = '2026-09-01T14:30:00Z'
    const local = toLocalInput(stored)

    // Reading it back as a local time must land on the same instant as the input.
    expect(new Date(local).getTime()).toBe(new Date(stored).getTime())
    expect(local).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
  })

  it('is the inverse of what the input sends back', () => {
    // What `FieldInput` commits: `new Date(<local value>).toISOString()`.
    const stored = '2026-01-15T08:05:00Z'
    const roundTripped = new Date(toLocalInput(stored)).toISOString()
    expect(roundTripped).toBe(stored.replace('Z', '.000Z'))
  })

  it.each([null, undefined, '', 'not a date'])('is empty for %j', (value) => {
    expect(toLocalInput(value)).toBe('')
  })
})

describe('parseAssignees', () => {
  /**
   * Frappe stores `_assign` as a JSON string; this port sometimes returns a real array.
   * Both shapes appear against the same backend, so both are accepted.
   */
  it('reads both the JSON-string and the array shape', () => {
    expect(parseAssignees('["a@example.com","b@example.com"]')).toEqual([
      'a@example.com',
      'b@example.com',
    ])
    expect(parseAssignees(['a@example.com'])).toEqual(['a@example.com'])
  })

  it('never throws on a malformed value, because one bad row must not take out the table', () => {
    expect(parseAssignees('{not json')).toEqual([])
    expect(parseAssignees('{"a":1}')).toEqual([])
    expect(parseAssignees(null)).toEqual([])
    expect(parseAssignees(42)).toEqual([])
  })
})

describe('formatCurrency', () => {
  it('falls back to a plain number when Intl rejects the code', () => {
    // The row's `currency` is free text on the server, so an unknown code is reachable.
    expect(formatCurrency(1234.5, 'NOTACURRENCY')).toBe('1,234.5')
  })

  it.each([null, undefined, ''])('is empty for %j rather than showing a zero', (value) => {
    expect(formatCurrency(value)).toBe('')
  })

  it('formats a real amount', () => {
    expect(formatCurrency(1000, 'USD')).toContain('1,000')
  })
})
