import { useQuery } from '@tanstack/react-query'
import { callGet } from '@/api/client'
import type { DocField } from '@/api/types'

/**
 * The fields the CRM means you to sort and filter by.
 *
 * Runs 1 and 2 built both menus from `get_data`'s `fields` array, which is *every* field on
 * the doctype. That made the React menus longer than Vue's and offered fields that filter
 * badly — `_liked_by`, child tables, layout fields. These two endpoints return the curated
 * subsets, and Vue has always used them (`ViewControls.vue`).
 *
 * Cached hard: both are doctype metadata, identical for every user and every row, and a
 * menu that reopens should not refetch.
 */

const STALE = { staleTime: Infinity }

/**
 * Both endpoints can return the same `fieldname` twice — `name` appears in the standard
 * fields and again in the doctype's own, and the server does not merge them. React then
 * warns about duplicate keys and may drop one. First occurrence wins, which keeps the
 * server's ordering.
 */
export function byFieldname<T extends { fieldname: string }>(rows: T[] | undefined): T[] {
  const seen = new Set<string>()
  return (rows ?? []).filter((row) =>
    seen.has(row.fieldname) ? false : (seen.add(row.fieldname), true),
  )
}

/** `crm.api.doc.sort_options` — `{ label, value, fieldname }`. */
export function useSortOptions(doctype: string) {
  const query = useQuery({
    queryKey: ['sort_options', doctype],
    queryFn: () =>
      callGet<{ label: string; value: string; fieldname: string }[]>(
        'crm.api.doc.sort_options',
        { doctype },
      ),
    enabled: Boolean(doctype),
    ...STALE,
  })
  return byFieldname(query.data)
}

/**
 * `crm.api.doc.get_filterable_fields` — the same shape as a `DocField` plus `value`.
 *
 * Typed as `DocField` because that is what `FilterEditor` already consumes; the extra
 * `value` key is the endpoint's own duplicate of `fieldname` and nothing here reads it.
 */
export function useFilterableFields(doctype: string): DocField[] {
  const query = useQuery({
    queryKey: ['filterable_fields', doctype],
    queryFn: () =>
      callGet<DocField[]>('crm.api.doc.get_filterable_fields', { doctype }),
    enabled: Boolean(doctype),
    ...STALE,
  })
  return byFieldname(query.data)
}
