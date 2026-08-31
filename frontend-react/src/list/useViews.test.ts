import { describe, expect, it } from 'vitest'
import { viewParams } from './useViews'
import { byFieldname } from './useFieldOptions'

/**
 * Saved views store their parameters as JSON *strings* in `Code` columns, byte-identical to
 * upstream (`metadata.py:69`). Everything here is about what happens when one of those
 * strings is not what we hoped.
 */
describe('viewParams', () => {
  it('parses the stored JSON strings', () => {
    const parsed = viewParams({
      name: '1',
      filters: '{"status":"Open"}',
      order_by: 'creation desc',
      columns: '[{"key":"name"}]',
      rows: '["name","status"]',
      column_field: 'status',
      group_by_field: 'owner',
    })
    expect(parsed.filters).toEqual({ status: 'Open' })
    expect(parsed.orderBy).toBe('creation desc')
    expect(parsed.rows).toEqual(['name', 'status'])
    expect(parsed.columnField).toBe('status')
  })

  it('accepts the list-of-tuples filter form as well as the dict', () => {
    // `doc.py:68` deliberately accepts both and does not narrow the grammar.
    expect(viewParams({ name: '1', filters: '[["status","=","Open"]]' }).filters).toEqual([
      ['status', '=', 'Open'],
    ])
  })

  /**
   * Codex found this one: `parseJson` alone accepted anything JSON-valid, so a stored
   * `"123"` survived and went into the request as `filters: 123`. The column is free-form
   * text on the server, so a hand-edited or half-migrated row is a real possibility, and an
   * unusable filter should mean "no filter" rather than a 500.
   */
  it.each(['123', '"a string"', 'null', 'true', 'not json at all', ''])(
    'falls back to no filter for stored %j',
    (stored) => {
      expect(viewParams({ name: '1', filters: stored }).filters).toEqual({})
    },
  )

  it('returns empty parameters for no view at all', () => {
    expect(viewParams(undefined)).toEqual({ filters: {} })
  })

  it('treats empty strings as absent, not as values', () => {
    const parsed = viewParams({ name: '1', order_by: '', column_field: '', rows: '' })
    expect(parsed.orderBy).toBeUndefined()
    expect(parsed.columnField).toBeUndefined()
    expect(parsed.rows).toBeUndefined()
  })
})

/**
 * `sort_options` and `get_filterable_fields` can both return `name` twice — once from the
 * standard fields and once from the doctype's own — and the server does not merge them.
 * React then warns about duplicate keys and may drop one.
 */
describe('byFieldname', () => {
  it('keeps the first of each fieldname, preserving server order', () => {
    expect(
      byFieldname([
        { fieldname: 'name', label: 'first' },
        { fieldname: 'owner', label: 'owner' },
        { fieldname: 'name', label: 'second' },
      ]),
    ).toEqual([
      { fieldname: 'name', label: 'first' },
      { fieldname: 'owner', label: 'owner' },
    ])
  })

  it('handles the not-yet-loaded case', () => {
    expect(byFieldname(undefined)).toEqual([])
  })
})
