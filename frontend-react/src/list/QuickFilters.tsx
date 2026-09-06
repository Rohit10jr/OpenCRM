import { useQuery } from '@tanstack/react-query'
import { callGet } from '@/api/client'
import { Input } from '@/components/ui/input'
import type { DocField } from '@/api/types'
import type { ListFilter } from './useListView'

/**
 * The row of one-click filters above a list.
 *
 * `crm.api.doc.get_quick_filters` returns the handful of fields an admin picked out as worth
 * filtering on directly (`doc.py:146`), rather than through the filter popover. It has been
 * served and unused since run 1 — the React list has had no equivalent at all.
 *
 * These write into the same URL `filters` the popover does, so a quick filter and a popover
 * filter on the same field are the same filter, and clearing either clears it. That is why
 * this takes the whole filter list rather than owning its own state: two sources for one
 * query parameter is how they drift.
 */
export function QuickFilters({
  doctype,
  filters,
  onChange,
}: {
  doctype: string
  filters: ListFilter[]
  onChange: (filters: ListFilter[]) => void
}) {
  const quick = useQuery({
    queryKey: ['quick-filters', doctype],
    queryFn: () =>
      callGet<DocField[]>('crm.api.doc.get_quick_filters', { doctype, cached: true }),
    staleTime: Infinity,
    retry: false,
  })

  const fields = quick.data ?? []
  if (!fields.length) return null

  const valueOf = (fieldname: string) =>
    filters.find((filter) => filter.fieldname === fieldname)?.value ?? ''

  const set = (field: DocField, value: string) => {
    const rest = filters.filter((filter) => filter.fieldname !== field.fieldname)
    if (!value) {
      onChange(rest)
      return
    }
    // `like` for text so a partial match works, `=` for anything with a fixed value set —
    // a Select or a Link matched with wildcards would surprise.
    const operator =
      field.fieldtype === 'Select' || field.fieldtype === 'Link' || field.fieldtype === 'Check'
        ? '='
        : 'like'
    onChange([...rest, { fieldname: field.fieldname, operator, value }])
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-2">
      {fields.map((field) => (
        <div key={field.fieldname} className="flex items-center gap-1.5">
          <span className="text-sm text-ink-gray-5">{field.label}</span>
          {field.fieldtype === 'Select' ? (
            <select
              value={valueOf(field.fieldname)}
              onChange={(event) => set(field, event.target.value)}
              className="h-7 rounded border border-outline-gray-2 bg-surface-white px-1.5 text-sm"
            >
              <option value="">Any</option>
              {selectChoices(field.options).map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </select>
          ) : (
            <Input
              className="h-7 w-36 text-sm"
              placeholder="Any"
              defaultValue={valueOf(field.fieldname)}
              // Commits on blur or Enter, like every other filter input — each change is a
              // navigation and a refetch.
              onBlur={(event) => set(field, event.target.value.trim())}
              onKeyDown={(event) => {
                if (event.key === 'Enter') event.currentTarget.blur()
              }}
            />
          )}
        </div>
      ))}
    </div>
  )
}

/** Select options arrive newline-joined here and as `{label,value}[]` elsewhere. Accept both. */
function selectChoices(options: DocField['options']): string[] {
  if (Array.isArray(options)) {
    return (options as { value?: string }[]).map((choice) => String(choice?.value ?? ''))
  }
  return String(options ?? '')
    .split('\n')
    .filter(Boolean)
}
