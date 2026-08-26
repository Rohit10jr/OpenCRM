import { useEffect, useState } from 'react'
import { useDocList } from '@/api/hooks'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/primitives'
import { cn } from '@/lib/utils'
import type { PanelField } from './types'

/**
 * One editable field, chosen by fieldtype.
 *
 * This is the write-side twin of the list engine's `Cell`, which renders the same
 * fieldtypes read-only. They are deliberately *not* one component: a Currency cell is a
 * formatted string and a Currency input is a number box, and the branch that tried to be
 * both would be longer than the two of them.
 *
 * Every input commits on blur or Enter rather than per keystroke — each commit is a
 * `set_value` round trip, and the list engine learned the same lesson about refetching
 * per character.
 */
export function FieldInput({
  field,
  value,
  onCommit,
  disabled,
}: {
  field: PanelField
  value: unknown
  onCommit: (value: unknown) => void
  disabled?: boolean
}) {
  const readOnly = disabled || Boolean(field.read_only)

  switch (field.fieldtype) {
    case 'Check':
      return (
        <Switch
          checked={Boolean(value)}
          onCheckedChange={(checked) => onCommit(checked ? 1 : 0)}
          disabled={readOnly}
        />
      )

    case 'Select':
      return (
        <SelectInput field={field} value={value} onCommit={onCommit} disabled={readOnly} />
      )

    case 'Link':
      return (
        <LinkInput field={field} value={value} onCommit={onCommit} disabled={readOnly} />
      )

    case 'Date':
      return (
        <TextLike
          field={field}
          type="date"
          // The API returns `2026-08-24`; `<input type="date">` wants exactly that, but a
          // Datetime field arrives with a time part that would make the input blank.
          value={String(value ?? '').slice(0, 10)}
          onCommit={onCommit}
          disabled={readOnly}
        />
      )

    case 'Datetime':
      return (
        <TextLike
          field={field}
          type="datetime-local"
          value={toLocalInput(value)}
          onCommit={(next) => onCommit(next ? new Date(next).toISOString() : null)}
          disabled={readOnly}
        />
      )

    case 'Currency':
    case 'Float':
    case 'Percent':
    case 'Int':
      return (
        <TextLike
          field={field}
          type="number"
          value={value == null ? '' : String(value)}
          onCommit={(next) => onCommit(next === '' ? null : Number(next))}
          disabled={readOnly}
        />
      )

    default:
      return (
        <TextLike
          field={field}
          type="text"
          value={value == null ? '' : String(value)}
          onCommit={onCommit}
          disabled={readOnly}
        />
      )
  }
}

/**
 * A stored UTC timestamp as the local wall-clock value `<input type="datetime-local">`
 * expects.
 *
 * **Slicing the ISO string would have been wrong**, and quietly: the API stores and
 * returns UTC (`2026-09-01T14:30:00Z`), while `datetime-local` has no timezone at all. A
 * `.slice(0, 16)` shows 14:30 to a reader in Berlin whose deadline is really 16:30, and
 * saving it back writes their local 14:30 as 14:30 UTC. It round-trips consistently and
 * is off by the offset for everyone outside UTC.
 */
function toLocalInput(value: unknown): string {
  if (!value) return ''
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return ''
  const offsetMs = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16)
}

/** The shared text-ish input: draft locally, commit on blur or Enter. */
function TextLike({
  field,
  type,
  value,
  onCommit,
  disabled,
}: {
  field: PanelField
  type: string
  value: string
  onCommit: (value: string) => void
  disabled?: boolean
}) {
  const [draft, setDraft] = useState(value)

  // The saved value can change underneath this — another field's save refetches the
  // document — so the draft follows it.
  useEffect(() => setDraft(value), [value])

  return (
    <Input
      type={type}
      value={draft}
      placeholder={field.placeholder}
      disabled={disabled}
      className="border-transparent bg-transparent hover:border-outline-gray-2 focus:border-outline-gray-2"
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => draft !== value && onCommit(draft)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          e.currentTarget.blur()
        }
      }}
    />
  )
}

/** A Select's choices are newline-joined in `options` — Frappe's format, not ours. */
function SelectInput({
  field,
  value,
  onCommit,
  disabled,
}: {
  field: PanelField
  value: unknown
  onCommit: (value: unknown) => void
  disabled?: boolean
}) {
  const choices = (field.options ?? '').split('\n')

  return (
    <select
      value={String(value ?? '')}
      disabled={disabled}
      onChange={(e) => onCommit(e.target.value)}
      className={selectClass}
    >
      {choices.map((choice) => (
        <option key={choice} value={choice}>
          {choice || '—'}
        </option>
      ))}
    </select>
  )
}

/**
 * A Link field's `options` names the target doctype, so the choices are that doctype's
 * documents.
 *
 * A `<select>` of the 100 most recently modified rows, not a searchable combobox. That is
 * a real difference from the Vue `Link` component, which searches server-side and pages.
 *
 * **Concretely, what breaks:** with more than 100 rows in the target doctype, the 101st
 * cannot be chosen at all. The current value is prepended so it never *displays* wrong,
 * but a user cannot link a deal to an organization outside the recent hundred. Fine for
 * Territory with six rows; wrong for Organization at scale. It needs the combobox, and it
 * is in the run report as such rather than hidden behind an ellipsis here.
 */
function LinkInput({
  field,
  value,
  onCommit,
  disabled,
}: {
  field: PanelField
  value: unknown
  onCommit: (value: unknown) => void
  disabled?: boolean
}) {
  const target = field.options ?? ''
  const unmodelled = UNMODELLED_LINK_TARGETS.has(target)
  const options = useDocList<{ name: string }>(
    target,
    { fields: ['name'], limit_page_length: 100, order_by: 'modified desc' },
    { enabled: Boolean(target) && !disabled && !unmodelled },
  )

  /**
   * A Link target this backend does not serve falls back to free text, which is what the
   * value is anyway — an empty dropdown would be a field the user cannot fill.
   *
   * Both conditions, deliberately: the list below skips the request so the console stays
   * clean, and `isError` catches anything the list has not heard of, so the list going
   * stale degrades instead of breaking.
   */
  if (unmodelled || options.isError) {
    return (
      <TextLike
        field={field}
        type="text"
        value={value == null ? '' : String(value)}
        onCommit={onCommit}
        disabled={disabled}
      />
    )
  }

  const current = String(value ?? '')
  const names = options.data?.map((row) => row.name) ?? []
  // The saved value may sit outside the first 100 rows; without this the select would
  // silently show a different record's name.
  const choices = current && !names.includes(current) ? [current, ...names] : names

  return (
    <select
      value={current}
      disabled={disabled}
      onChange={(e) => onCommit(e.target.value || null)}
      className={selectClass}
    >
      <option value="">{field.placeholder ?? '—'}</option>
      {choices.map((name) => (
        <option key={name} value={name}>
          {name}
        </option>
      ))}
    </select>
  )
}

/**
 * Frappe core doctypes the stock layouts link to and this port deliberately does not
 * model (`PORT_PLAN.md` section 3: *"Link to Frappe's Currency / Address — not
 * modelled"*). All three appear in the stock Quick Entry layout and all three 404.
 *
 * A list rather than a probe only so the console stays clean; the `isError` branch above
 * is what actually makes it safe.
 */
const UNMODELLED_LINK_TARGETS = new Set(['Salutation', 'Gender', 'Currency', 'Address'])

const selectClass = cn(
  'h-8 w-full truncate rounded border border-transparent bg-transparent px-2 text-base text-ink-gray-8',
  'hover:border-outline-gray-2 focus:border-outline-gray-2 focus:outline-none disabled:opacity-50',
)
