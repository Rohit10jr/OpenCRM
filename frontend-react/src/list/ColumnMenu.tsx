import { Columns3, RotateCcw } from 'lucide-react'
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
 * The Columns menu — `ColumnSettings.vue`, minus the drag handle.
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
 * **Not ported: reordering and resizing.** Upstream drags columns into order and stores a
 * `width` per column; both are real and both are their own piece of work.
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
        {columns.map((column) => (
          <DropdownMenuCheckboxItem
            key={column.key}
            checked
            onCheckedChange={() => remove(column.key)}
            // Radix closes the menu on select; changing several columns in a row is the
            // normal case, so it stays open.
            onSelect={(event) => event.preventDefault()}
          >
            {column.label}
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
