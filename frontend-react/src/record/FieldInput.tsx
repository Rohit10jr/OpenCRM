import { useEffect, useState } from 'react'
import { RichTextEditor } from '@/components/RichText'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/primitives'
import { toLocalInput } from '@/lib/format'
import { cn } from '@/lib/utils'
import { LinkCombobox } from './LinkCombobox'
import type { PanelField, SelectChoice } from './types'

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

    // `_frappe_fieldtype` maps every Django `TextField` to `Small Text`
    // (`frappe_core/metadata.py:181`), so this is what a description or an address arrives
    // as. A single-line input for one is not wrong so much as unusable.
    case 'Small Text':
    case 'Long Text':
    case 'Text':
      return (
        <TextArea
          field={field}
          value={value == null ? '' : String(value)}
          onCommit={onCommit}
          disabled={readOnly}
        />
      )

    case 'Text Editor':
      return (
        <RichTextEditor
          value={typeof value === 'string' ? value : ''}
          placeholder={field.placeholder}
          disabled={readOnly}
          onChange={onCommit}
        />
      )

    /**
     * Read-only, deliberately.
     *
     * A JSON field is a structured value the server put there, and a side-panel text box is
     * the wrong instrument for editing one — a stray comma writes a string where an object
     * was. Showing it beats hiding it; editing it belongs to whatever wrote it.
     */
    case 'JSON':
      return (
        <pre className="max-h-32 overflow-auto rounded bg-surface-gray-1 p-2 text-sm text-ink-gray-7">
          {value == null ? '' : JSON.stringify(value, null, 2)}
        </pre>
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

/** The textarea twin of `TextLike`: same draft-then-commit-on-blur contract. */
function TextArea({
  field,
  value,
  onCommit,
  disabled,
}: {
  field: PanelField
  value: string
  onCommit: (value: string) => void
  disabled?: boolean
}) {
  const [draft, setDraft] = useState(value)

  useEffect(() => setDraft(value), [value])

  return (
    <textarea
      className="min-h-16 w-full resize-y rounded border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-base text-ink-gray-8 focus:outline-none focus:ring-2 focus:ring-ink-gray-4 disabled:opacity-50"
      placeholder={field.placeholder}
      value={draft}
      disabled={disabled}
      onChange={(event) => setDraft(event.target.value)}
      // No Enter-to-commit here: Enter is a newline in a textarea, which is the point of it.
      onBlur={() => draft !== value && onCommit(draft)}
    />
  )
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

/**
 * A Select's choices.
 *
 * **Two shapes, because there are two.** This port sends an array of `{label, value}`
 * (`no_of_employees` on CRM Organization is the one that found this); upstream Frappe
 * sends them newline-joined in the same field, and the stock layouts are authored against
 * that. Accepting only the Frappe shape called `.split` on an array and took the whole
 * record screen down behind an error boundary.
 */
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
  const choices: SelectChoice[] = Array.isArray(field.options)
    ? field.options
    : String(field.options ?? '')
        .split('\n')
        .map((choice) => ({ label: choice, value: choice }))

  return (
    <select
      value={String(value ?? '')}
      disabled={disabled}
      onChange={(e) => onCommit(e.target.value)}
      className={selectClass}
    >
      {/* The stored value can be empty even when no choice is; without this the select
          would display the first choice for a field that is genuinely unset. */}
      {choices.some((choice) => choice.value === '') ? null : (
        <option value="">{field.placeholder ?? '—'}</option>
      )}
      {choices.map((choice) => (
        <option key={choice.value} value={choice.value}>
          {choice.label || '—'}
        </option>
      ))}
    </select>
  )
}

/**
 * A Link field's `options` names the target doctype, so the choices are that doctype's
 * documents — searched server-side through `LinkCombobox`.
 *
 * This was a `<select>` of the 100 most recently modified rows until run 3. Past a hundred
 * rows the 101st could not be selected at all, which is fine for Territory with six and
 * wrong for Organization at scale.
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
  // A Link's `options` is always the target doctype name; the array shape is Select's.
  const target = typeof field.options === 'string' ? field.options : ''

  /**
   * A Link target this backend does not model falls back to free text, which is what the
   * value is anyway — a picker that can never return a result is a field the user cannot
   * fill.
   */
  if (!target || UNMODELLED_LINK_TARGETS.has(target)) {
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

  return (
    <LinkCombobox
      doctype={target}
      value={String(value ?? '')}
      placeholder={field.placeholder}
      disabled={disabled}
      onChange={onCommit}
    />
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
