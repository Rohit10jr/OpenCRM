import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, ChevronDown, X } from 'lucide-react'
import { callGet } from '@/api/client'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/primitives'
import { cn } from '@/lib/utils'

/**
 * Pick a linked document, searching the server.
 *
 * **Replaces a `<select>` of the 100 most recently modified rows**, which run 2 shipped and
 * recorded as a defect: past a hundred rows the 101st could not be chosen at all. This is
 * what the Vue `Link` control does — `frappe.desk.search.search_link` filters server-side
 * (`client.py:312`) and returns `{ value, description }`, so the list is never truncated in
 * a way the user cannot get around.
 *
 * A Popover with an input rather than a full combobox library: the whole behaviour is
 * "type, get ten results, click one", and cmdk would be a dependency for a keystroke
 * handler and a list.
 */
export function LinkCombobox({
  doctype,
  value,
  placeholder,
  disabled,
  onChange,
}: {
  /** The target doctype — a Link field's `options`. */
  doctype: string
  value: string
  placeholder?: string
  disabled?: boolean
  onChange: (value: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')

  // One request per pause in typing, not per keystroke — the list engine learned the same
  // lesson about `get_data`.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search), 250)
    return () => clearTimeout(timer)
  }, [search])

  const results = useQuery({
    queryKey: ['search_link', doctype, debounced],
    queryFn: () =>
      callGet<{ value: string; description: string }[]>('frappe.desk.search.search_link', {
        doctype,
        txt: debounced,
        page_length: 10,
      }),
    enabled: open && Boolean(doctype),
    // Results for a given search term do not change while a popover is open.
    staleTime: 30_000,
  })

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setSearch('')
      }}
    >
      <PopoverTrigger asChild disabled={disabled}>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            'flex h-8 w-full items-center gap-1 rounded border border-transparent bg-transparent px-2 text-left text-base',
            'hover:border-outline-gray-2 focus:border-outline-gray-2 focus:outline-none disabled:opacity-50',
            value ? 'text-ink-gray-8' : 'text-ink-gray-4',
          )}
        >
          <span className="flex-1 truncate">{value || placeholder || 'Select…'}</span>
          {value ? (
            <span
              role="button"
              aria-label="Clear"
              className="shrink-0 text-ink-gray-4 hover:text-ink-gray-7"
              onClick={(event) => {
                // Clearing must not also open the picker.
                event.preventDefault()
                event.stopPropagation()
                onChange(null)
              }}
            >
              <X className="h-3.5 w-3.5" />
            </span>
          ) : null}
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-ink-gray-4" />
        </button>
      </PopoverTrigger>

      <PopoverContent className="w-72 p-1.5">
        <Input
          autoFocus
          value={search}
          placeholder={`Search ${doctype}…`}
          onChange={(event) => setSearch(event.target.value)}
        />
        <ul className="mt-1.5 max-h-64 overflow-y-auto">
          {results.isFetching && !results.data ? (
            <li className="px-2 py-1.5 text-sm text-ink-gray-4">Searching…</li>
          ) : null}
          {results.data?.map((row) => (
            <li key={row.value}>
              <button
                type="button"
                onClick={() => {
                  onChange(row.value)
                  setOpen(false)
                }}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-base text-ink-gray-7 hover:bg-surface-gray-2"
              >
                <span className="min-w-0 flex-1 truncate">
                  {row.value}
                  {row.description ? (
                    <span className="ml-2 text-sm text-ink-gray-4">{row.description}</span>
                  ) : null}
                </span>
                {row.value === value ? <Check className="h-3.5 w-3.5 shrink-0" /> : null}
              </button>
            </li>
          ))}
          {results.data?.length === 0 ? (
            <li className="px-2 py-1.5 text-sm text-ink-gray-4">No matches.</li>
          ) : null}
        </ul>
      </PopoverContent>
    </Popover>
  )
}
