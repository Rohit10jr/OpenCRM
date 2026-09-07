import { ChevronDown, ChevronUp, Columns3, RotateCcw } from 'lucide-react'
import type { DocField, ListColumn, SavedView, ViewType } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useColumnSettings } from './useColumnSettings'

/**
 * The Columns menu — `ColumnSettings.vue`.
 *
 * The old version toggled a `hiddenColumns` array in component state, which lasted until
 * the page reloaded. Columns live on the view and `get_data` reads them back, so a change
 * here is a write. `useColumnSettings` decides which of the two endpoints it is.
 *
 * Unchecking removes a column and checking a field adds it, which is the same operation
 * from both ends of the list: the stored value is the array of columns, so a column that is
 * off is a column that is absent. The doctype's other fields are offered below the ones in
 * use, so adding one is not a separate dialog.
 *
 * Reordering is two arrows per row rather than upstream's drag handle — see `move` for why.
 *
 * **Still not ported: per-column width.** Upstream stores a `width` on each column and
 * drags the header edge to change it. New columns get `10rem` here and nothing adjusts it.
 */
export function ColumnMenu({
  doctype,
  viewType,
  view,
  columns,
  fields,
}: {
  doctype: string
  viewType: ViewType
  view?: SavedView
  /** The columns in use, from the payload. */
  columns: ListColumn[]
  /** Every field on the doctype — the candidates to add. */
  fields: DocField[]
}) {
  const { save, reset } = useColumnSettings({ doctype, viewType, view })

  const inUse = new Set(columns.map((column) => column.key))
  const addable = fields.filter((field) => !inUse.has(field.fieldname))

  function remove(key: string) {
    save.mutate(columns.filter((column) => column.key !== key))
  }

  /**
   * Move a column one place, and save the whole array.
   *
   * Buttons rather than drag-and-drop, which is what upstream uses. Dragging inside an open
   * Radix menu means fighting its pointer handling and its focus management, and a menu
   * that closes halfway through a drag is worse than two arrows. The stored value is an
   * ordered array either way, so this writes exactly what a drag would.
   */
  function move(index: number, by: -1 | 1) {
    const target = index + by
    if (target < 0 || target >= columns.length) return
    const next = [...columns]
    ;[next[index], next[target]] = [next[target], next[index]]
    save.mutate(next)
  }

  function add(field: DocField) {
    save.mutate([
      ...columns,
      {
        label: field.label ?? field.fieldname,
        key: field.fieldname,
        // The payload's own column shape. `type` is what `Cell` branches on, so a column
        // added without it would render as plain text whatever it holds.
        type: field.fieldtype ?? 'Data',
        options: typeof field.options === 'string' ? field.options : undefined,
        width: '10rem',
      },
    ])
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" loading={save.isPending || reset.isPending}>
          <Columns3 className="h-4 w-4" />
          Columns
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-96 w-60 overflow-y-auto">
        <DropdownMenuLabel>In this list</DropdownMenuLabel>
        {columns.map((column, index) => (
          <DropdownMenuCheckboxItem
            key={column.key}
            checked
            onCheckedChange={() => remove(column.key)}
            // Radix closes the menu on select; changing several columns in a row is the
            // normal case, so it stays open.
            onSelect={(event) => event.preventDefault()}
          >
            <span className="flex-1 truncate">{column.label}</span>
            <Reorder
              disabled={save.isPending}
              canMoveUp={index > 0}
              canMoveDown={index < columns.length - 1}
              onMove={(by) => move(index, by)}
            />
          </DropdownMenuCheckboxItem>
        ))}

        {addable.length ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Add a column</DropdownMenuLabel>
            {addable.map((field) => (
              <DropdownMenuCheckboxItem
                key={field.fieldname}
                checked={false}
                onCheckedChange={() => add(field)}
                onSelect={(event) => event.preventDefault()}
              >
                {field.label ?? field.fieldname}
              </DropdownMenuCheckboxItem>
            ))}
          </>
        ) : null}

        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => reset.mutate()}>
          <RotateCcw className="h-4 w-4" />
          Reset to default
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/**
 * The two arrows on a column row.
 *
 * `stopPropagation` on both, because the row they sit in is a checkbox item and its
 * handler *removes the column* — without this, reordering would delete what it was
 * reordering. `preventDefault` keeps the menu open, same as everywhere else here.
 */
function Reorder({
  disabled,
  canMoveUp,
  canMoveDown,
  onMove,
}: {
  disabled: boolean
  canMoveUp: boolean
  canMoveDown: boolean
  onMove: (by: -1 | 1) => void
}) {
  const button = (by: -1 | 1, enabled: boolean, Icon: typeof ChevronUp, label: string) => (
    <button
      type="button"
      aria-label={label}
      disabled={disabled || !enabled}
      className="rounded p-0.5 text-ink-gray-4 hover:bg-surface-gray-3 hover:text-ink-gray-7 disabled:opacity-30"
      onClick={(event) => {
        event.preventDefault()
        event.stopPropagation()
        onMove(by)
      }}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
  )

  return (
    <span className="ml-1 flex shrink-0 items-center">
      {button(-1, canMoveUp, ChevronUp, 'Move up')}
      {button(1, canMoveDown, ChevronDown, 'Move down')}
    </span>
  )
}
