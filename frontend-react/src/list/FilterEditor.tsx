import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import type { DocField } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { ListFilter } from './useListView'

/**
 * The filter editor, lifted out of `ViewControls` when that file reached 340 lines doing
 * three jobs. Nothing about it changed in the move.
 */

const FILTER_OPERATORS = [
  { value: '=', label: 'equals' },
  { value: '!=', label: 'not equals' },
  { value: 'like', label: 'like' },
  { value: 'not like', label: 'not like' },
  { value: '>', label: 'greater than' },
  { value: '<', label: 'less than' },
] as const


/**
 * A filter value that commits on blur or Enter rather than on every keystroke.
 *
 * The filter value is part of the query key, so a controlled input would fire a
 * `get_data` request per character typed. `Filter.vue:107` binds on `change` for the same
 * reason; a debounce would work too, but "the request goes when you finish typing" is
 * easier to reason about than "the request goes 300ms after you stop".
 */
function FilterValueInput({
  value,
  onCommit,
}: {
  value: string
  onCommit: (value: string) => void
}) {
  const [draft, setDraft] = useState(value)

  // The committed value can change underneath this — removing a filter row shifts the
  // rest up — so the draft follows it when it does.
  useEffect(() => setDraft(value), [value])

  return (
    <Input
      className="flex-1"
      placeholder="Value"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => draft !== value && onCommit(draft)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          onCommit(draft)
        }
      }}
    />
  )
}

export function FilterEditor({
  fields,
  filters,
  onChange,
}: {
  fields: DocField[]
  filters: ListFilter[]
  onChange: (filters: ListFilter[]) => void
}) {
  function update(index: number, patch: Partial<ListFilter>) {
    onChange(filters.map((f, i) => (i === index ? { ...f, ...patch } : f)))
  }

  return (
    <div className="flex flex-col gap-2">
      {filters.length === 0 ? (
        <p className="text-sm text-ink-gray-4">No filters applied.</p>
      ) : null}

      {filters.map((filter, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <select
            className="h-8 min-w-0 flex-1 rounded border border-outline-gray-2 bg-surface-white px-1 text-base"
            value={filter.fieldname}
            onChange={(e) => update(index, { fieldname: e.target.value })}
          >
            {fields.map((field) => (
              <option key={field.fieldname} value={field.fieldname}>
                {field.label}
              </option>
            ))}
          </select>
          <select
            className="h-8 w-28 rounded border border-outline-gray-2 bg-surface-white px-1 text-base"
            value={filter.operator}
            onChange={(e) => update(index, { operator: e.target.value })}
          >
            {FILTER_OPERATORS.map((op) => (
              <option key={op.value} value={op.value}>
                {op.label}
              </option>
            ))}
          </select>
          <FilterValueInput
            value={filter.value}
            onCommit={(value) => update(index, { value })}
          />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onChange(filters.filter((_, i) => i !== index))}
            title="Remove filter"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}

      <Button
        variant="subtle"
        size="sm"
        className="self-start"
        onClick={() =>
          onChange([
            ...filters,
            {
              fieldname: fields[0]?.fieldname ?? 'name',
              operator: 'like',
              value: '',
            },
          ])
        }
      >
        Add filter
      </Button>
    </div>
  )
}
