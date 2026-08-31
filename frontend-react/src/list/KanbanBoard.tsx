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
 * **Dragging a card to another column changes the record's `column_field`** — the field
 * the board groups on, `status` for deals and leads. That is one `set_value`, and it is
 * what a user means by moving a card.
 *
 * *Re*ordering within a column is not built: it persists a card order into
 * `CRM View Settings` and the server only honours it through `get_records_based_on_order`
 * (`doc.py:531`). Cross-column is the useful half and it stands alone.
 *
 * Native HTML5 drag-and-drop rather than a library: a board with columns and cards is what
 * the API was designed for, and dnd-kit would be a dependency for two event handlers.
 */
export function KanbanBoard({
  groups,
  fields,
  titleField,
  columnField,
  onCardClick,
  onCardMove,
  getStatusColor,
}: {
  groups: KanbanGroup[]
  /** Field metadata, for card labels. */
  fields: DocField[]
  titleField: string
  /** The field the board groups on — what a drop writes to. */
  columnField?: string
  onCardClick?: (row: DocRow) => void
  onCardMove?: (name: string, toColumn: string) => void
  getStatusColor?: (value: string) => string | undefined
}) {
  const labelOf = (fieldname: string) =>
    fields.find((f) => f.fieldname === fieldname)?.label ?? fieldname

  const canDrag = Boolean(onCardMove && columnField)

  return (
    <div className="flex h-full gap-3 overflow-x-auto p-4">
      {groups.map(({ column, fields: cardFields, data }) => (
        <div
          key={column.name}
          data-kanban-column={column.name}
          // `preventDefault` on dragover is what makes an element a drop target at all —
          // the one piece of the HTML5 API that reads as backwards.
          onDragOver={canDrag ? (event) => event.preventDefault() : undefined}
          onDrop={
            canDrag
              ? (event) => {
                  event.preventDefault()
                  const name = event.dataTransfer.getData('text/plain')
                  // Dropping a card back where it started is not a change; writing it
                  // anyway would bump `modified` and reorder the list for nothing.
                  if (name && !data.some((row) => row.name === name)) {
                    onCardMove?.(name, column.name)
                  }
                }
              : undefined
          }
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
                draggable={canDrag}
                onDragStart={
                  canDrag
                    ? (event) => event.dataTransfer.setData('text/plain', row.name)
                    : undefined
                }
                onClick={() => onCardClick?.(row)}
                className="cursor-pointer rounded-lg border border-outline-gray-1 bg-surface-white p-3 text-left shadow-sm hover:border-outline-gray-2"
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
