import { describe, expect, it } from 'vitest'
import { likeWrap, toFilterDict } from './useListView'

/**
 * The filter grammar, which is where run 1 shipped a real bug: `like` values were sent
 * unwrapped, the backend's `_like_to_lookup` read the absent wildcards as "no pattern" and
 * chose `iexact`, and the filter box returned nothing while looking like it worked.
 *
 * These are the cases that would have caught it.
 */
describe('likeWrap', () => {
  it('wraps a like value in wildcards, because the backend reads them', () => {
    // `filters.py:144`: `%foo%` -> icontains, bare `foo` -> iexact. Unwrapped means
    // "equals", not "contains".
    expect(likeWrap('like', 'acme')).toBe('%acme%')
    expect(likeWrap('not like', 'acme')).toBe('%acme%')
  })

  it('leaves a value the user already wildcarded alone', () => {
    expect(likeWrap('like', 'acme%')).toBe('acme%')
    expect(likeWrap('like', '%acme')).toBe('%acme')
  })

  it('does not touch operators that are not like', () => {
    expect(likeWrap('=', 'acme')).toBe('acme')
    expect(likeWrap('>', '5')).toBe('5')
  })
})

describe('toFilterDict', () => {
  it('sends an equality as a bare value and anything else as [operator, value]', () => {
    expect(toFilterDict([{ fieldname: 'status', operator: '=', value: 'Open' }])).toEqual({
      status: 'Open',
    })
    expect(toFilterDict([{ fieldname: 'probability', operator: '>', value: '50' }])).toEqual(
      { probability: ['>', '50'] },
    )
  })

  it('wraps like values on the way through', () => {
    expect(toFilterDict([{ fieldname: 'email', operator: 'like', value: 'buyer' }])).toEqual({
      email: ['like', '%buyer%'],
    })
  })

  /**
   * A half-typed filter must not reach the server. `{"status": ["like", ""]}` becomes
   * `%%`, which matches every row — so an incomplete filter would silently look like no
   * filter at all rather than like an error.
   */
  it('drops rows with no value or no fieldname', () => {
    expect(
      toFilterDict([
        { fieldname: 'email', operator: 'like', value: '' },
        { fieldname: '', operator: 'like', value: 'acme' },
      ]),
    ).toEqual({})
  })

  it('keeps a zero, which is a value even though it is falsy', () => {
    expect(toFilterDict([{ fieldname: 'converted', operator: '=', value: '0' }])).toEqual({
      converted: '0',
    })
  })

  it('lets a later filter on the same field win, since the wire format is a dict', () => {
    expect(
      toFilterDict([
        { fieldname: 'status', operator: '=', value: 'Open' },
        { fieldname: 'status', operator: '=', value: 'Won' },
      ]),
    ).toEqual({ status: 'Won' })
  })
})
