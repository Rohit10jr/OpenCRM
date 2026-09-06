import { useEffect, useState } from 'react'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/primitives'

/**
 * One labelled setting.
 *
 * Deliberately *not* `record/FieldInput`: that one is driven by server field metadata
 * (`fieldtype`, `options`, `placeholder`) because the side panel's whole contract is
 * "render whatever the layout says". A settings screen knows its own fields at author time,
 * so it passes a type here rather than fetching a descriptor to be told one.
 *
 * Commits on blur or Enter, same as everywhere else — each commit is a `set_value` round
 * trip.
 */
export function SettingsField({
  label,
  hint,
  value,
  type = 'text',
  disabled,
  placeholder,
  onCommit,
}: {
  label: string
  hint?: string
  value: unknown
  type?: 'text' | 'email' | 'password' | 'number' | 'url' | 'checkbox' | 'textarea'
  disabled?: boolean
  placeholder?: string
  onCommit: (value: unknown) => void
}) {
  const asText = value == null ? '' : String(value)
  const [draft, setDraft] = useState(asText)

  // Follows the saved value, which changes under us when another field's save refetches.
  useEffect(() => setDraft(asText), [asText])

  const commit = () => {
    if (draft !== asText) onCommit(type === 'number' ? Number(draft) : draft)
  }

  return (
    <label className="flex items-start gap-4 border-b border-outline-gray-1 py-3 last:border-0">
      <div className="w-52 shrink-0 pt-1.5">
        <span className="text-base text-ink-gray-7">{label}</span>
        {hint ? <p className="mt-0.5 text-sm text-ink-gray-4">{hint}</p> : null}
      </div>

      <div className="min-w-0 flex-1">
        {type === 'checkbox' ? (
          <div className="pt-1.5">
            <Switch
              checked={Boolean(value)}
              disabled={disabled}
              onCheckedChange={(checked) => onCommit(checked ? 1 : 0)}
            />
          </div>
        ) : type === 'textarea' ? (
          <textarea
            rows={4}
            value={draft}
            disabled={disabled}
            placeholder={placeholder}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commit}
            className="w-full resize-y rounded border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-base text-ink-gray-8 focus:outline-none focus:ring-2 focus:ring-ink-gray-4 disabled:opacity-50"
          />
        ) : (
          <Input
            type={type}
            value={draft}
            disabled={disabled}
            placeholder={placeholder}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commit}
            onKeyDown={(event) => {
              if (event.key === 'Enter') event.currentTarget.blur()
            }}
          />
        )}
      </div>
    </label>
  )
}
