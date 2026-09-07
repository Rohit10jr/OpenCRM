import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { callGet } from '@/api/client'
import { Input } from '@/components/ui/input'

/**
 * The To / Cc field, with contact autocomplete.
 *
 * `crm.api.contact.search_emails` returns **lists, not dicts** — upstream passes
 * `as_list=True` and its own autocomplete indexes positionally (`contact.py:131`). The
 * order is `[full_name, email_id, name]`. Reading it as objects yields `undefined`
 * everywhere and no error, which is the kind of thing that looks like an empty database.
 *
 * The field itself stays a free-text comma-separated string, because that is what the send
 * takes and because an address that is not a Contact must remain typeable. The suggestions
 * append to it rather than replacing it.
 */
export function EmailRecipients({
  id,
  label,
  value,
  onChange,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
}) {
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)

  const matches = useQuery({
    queryKey: ['search-emails', query],
    queryFn: () =>
      callGet<[string, string, string][]>('crm.api.contact.search_emails', { txt: query }),
    // Only once there is something to search on, and only while the field has focus.
    enabled: focused && query.trim().length > 1,
    retry: false,
  })

  /** The part after the last comma — the address being typed right now. */
  function currentTerm(text: string) {
    return text.split(',').pop()?.trim() ?? ''
  }

  function append(email: string) {
    const parts = value.split(',')
    parts[parts.length - 1] = ` ${email}`
    onChange(`${parts.join(',').trim()}, `)
    setQuery('')
  }

  const suggestions = (matches.data ?? []).filter(
    ([, email]) => email && !value.includes(email),
  )

  return (
    <div className="relative flex flex-1 items-center gap-2">
      <label className="w-10 shrink-0 text-sm text-ink-gray-5" htmlFor={id}>
        {label}
      </label>
      <div className="min-w-0 flex-1">
        <Input
          id={id}
          name={id}
          type="text"
          autoComplete="off"
          value={value}
          onFocus={() => setFocused(true)}
          // A blur delay, because clicking a suggestion blurs the input first and an
          // immediately hidden list is a list that cannot be clicked.
          onBlur={() => window.setTimeout(() => setFocused(false), 150)}
          onChange={(event) => {
            onChange(event.target.value)
            setQuery(currentTerm(event.target.value))
          }}
        />

        {focused && suggestions.length ? (
          <ul className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded border border-outline-gray-2 bg-surface-white shadow-lg">
            {suggestions.map(([fullName, email, name]) => (
              <li key={name}>
                <button
                  type="button"
                  className="flex w-full flex-col items-start px-3 py-1.5 text-left hover:bg-surface-gray-1"
                  onClick={() => append(email)}
                >
                  <span className="text-base text-ink-gray-8">{fullName || email}</span>
                  <span className="text-sm text-ink-gray-5">{email}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  )
}
