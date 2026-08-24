import type { DocField, DocRow, KanbanGroup } from '@/api/types'
import { Tooltip } from '@/components/ui/primitives'
import { formatDate, timeAgo } from '@/lib/format'
import { statusDotClass } from './statusColor'

/**
 * The kanban board.
 *
 * The payload shape changes with `view_type`: in kanban mode `data` is a list of
 * `{ column, fields, data }` rather than a list of rows (`doc.py:526`). That is the
 * single most surprising thing about `get_data`, so the board takes `KanbanGroup[]`
 * explicitly instead of pretending both modes look alike.
 *
 * Cards are read-only. Dragging a card between columns is a `CRM View Settings` write
 * plus a status change, and neither the settings write path nor the edit modal exists in
 * this conversion yet — an inert drag handle would be worse than none.
 */
export function KanbanBoard({
  groups,
  fields,
  titleField,
  onCardClick,
  getStatusColor,
}: {
  groups: KanbanGroup[]
  /** Field metadata, for card labels. */
  fields: DocField[]
  titleField: string
  onCardClick?: (row: DocRow) => void
  getStatusColor?: (value: string) => string | undefined
}) {
  const labelOf = (fieldname: string) =>
    fields.find((f) => f.fieldname === fieldname)?.label ?? fieldname

  return (
    <div className="flex h-full gap-3 overflow-x-auto p-4">
      {groups.map(({ column, fields: cardFields, data }) => (
        <div
          key={column.name}
          className="flex w-72 shrink-0 flex-col rounded-lg bg-surface-gray-1 p-2"
        >
          <div className="mb-2 flex items-center gap-2 px-1">
            <span className={statusDotClass(getStatusColor?.(column.name))} />
            <span className="truncate text-base font-medium text-ink-gray-8">
              {column.name}
            </span>
            <span className="ml-auto text-sm text-ink-gray-4">
              {column.all_count ?? data.length}
            </span>
          </div>

          <div className="flex flex-col gap-2 overflow-y-auto">
            {data.map((row) => (
              <button
                key={row.name}
                type="button"
                onClick={() => onCardClick?.(row)}
                className="rounded-lg border border-outline-gray-1 bg-surface-white p-3 text-left shadow-sm hover:border-outline-gray-2"
              >
                <div className="truncate text-base font-medium text-ink-gray-8">
                  {String(row[titleField] ?? row.name)}
                </div>
                <dl className="mt-2 flex flex-col gap-1">
                  {cardFields
                    .filter((fieldname) => fieldname !== titleField && row[fieldname])
                    .map((fieldname) => (
                      <div key={fieldname} className="flex gap-2 text-sm">
                        <dt className="shrink-0 text-ink-gray-4">
                          {labelOf(fieldname)}
                        </dt>
                        <dd className="truncate text-ink-gray-6">
                          {renderCardValue(fieldname, row[fieldname])}
                        </dd>
                      </div>
                    ))}
                </dl>
              </button>
            ))}

            {data.length === 0 ? (
              <p className="px-1 py-4 text-sm text-ink-gray-4">Nothing here yet.</p>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Card fields come back as raw values with no column descriptor, so there is no fieldtype
 * to switch on the way `Cell` does — only the two timestamps are worth special-casing.
 */
function renderCardValue(fieldname: string, value: unknown) {
  if (value == null) return ''
  if (fieldname === 'modified' || fieldname === 'creation') {
    return <Tooltip text={formatDate(value, true)}>
      <span>{timeAgo(value)}</span>
    </Tooltip>
  }
  return String(value)
}
