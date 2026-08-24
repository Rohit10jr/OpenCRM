import { useMemo } from 'react'
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table'
import type { DocRow, ListColumn } from '@/api/types'
import { Checkbox } from '@/components/ui/primitives'
import { cn } from '@/lib/utils'
import { Cell, type CellOverride } from './Cell'

/**
 * The list table.
 *
 * Sorting and filtering are **not** TanStack Table's — they are the server's, through
 * `get_data`. The table here is layout and selection only, which is why every column is
 * `enableSorting: false` by implication: sorting a page of 20 rows out of 900 would sort
 * the wrong thing.
 *
 * Column widths come from the payload (`"16rem"`), so the table matches the saved view.
 */
export function ListTable({
  rows,
  columns,
  selection,
  onSelectionChange,
  onRowClick,
  getStatusColor,
  overrides,
  showHeader = true,
}: {
  rows: DocRow[]
  columns: ListColumn[]
  selection: RowSelectionState
  onSelectionChange: (updater: React.SetStateAction<RowSelectionState>) => void
  onRowClick?: (row: DocRow) => void
  getStatusColor?: (value: string) => string | undefined
  overrides?: Record<string, CellOverride>
  /**
   * A group_by view stacks one table per group under a single `ListTableHeader`. The
   * widths are fixed from the column descriptors, so the tables line up.
   */
  showHeader?: boolean
}) {
  const tableColumns = useMemo<ColumnDef<DocRow>[]>(() => {
    const select: ColumnDef<DocRow> = {
      id: 'select',
      size: 32,
      header: ({ table }) => (
        <Checkbox
          checked={
            table.getIsAllRowsSelected()
              ? true
              : table.getIsSomeRowsSelected()
                ? 'indeterminate'
                : false
          }
          onCheckedChange={(checked) => table.toggleAllRowsSelected(checked === true)}
          aria-label="Select all rows"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(checked) => row.toggleSelected(checked === true)}
          aria-label={`Select ${row.original.name}`}
          // Selecting a row must not also open it.
          onClick={(event) => event.stopPropagation()}
        />
      ),
    }

    const rest: ColumnDef<DocRow>[] = columns.map((column) => ({
      id: column.key,
      accessorKey: column.key,
      header: column.label,
      cell: ({ row }) => (
        <Cell
          row={row.original}
          column={column}
          getStatusColor={getStatusColor}
          overrides={overrides}
        />
      ),
    }))

    return [select, ...rest]
  }, [columns, getStatusColor, overrides])

  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
    state: { rowSelection: selection },
    onRowSelectionChange: onSelectionChange,
    // The document name, so a selection survives a refetch that reorders rows.
    getRowId: (row) => row.name,
  })

  return (
    <table className="w-full table-fixed border-collapse text-base">
      <ColumnWidths columns={columns} />
      <thead className={showHeader ? 'sticky top-0 z-10 bg-surface-white' : 'hidden'}>
        {table.getHeaderGroups().map((group) => (
          <tr key={group.id} className="border-b border-outline-gray-1">
            {group.headers.map((header) => (
              <th
                key={header.id}
                className="truncate px-3 py-2 text-left text-sm font-medium text-ink-gray-5"
              >
                {flexRender(header.column.columnDef.header, header.getContext())}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr
            key={row.id}
            onClick={onRowClick ? () => onRowClick(row.original) : undefined}
            // No pointer cursor without a handler: there is no record screen yet, and a
            // row that looks clickable and is not reads as a broken app.
            className={cn(
              'border-b border-outline-gray-1 hover:bg-surface-gray-1',
              onRowClick && 'cursor-pointer',
            )}
          >
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id} className="truncate px-3 py-2 text-ink-gray-7">
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/**
 * The column header on its own, for a group_by view: one of these above a stack of
 * `ListTable`s with `showHeader={false}`.
 *
 * A separate component rather than an empty `ListTable`, which read as a puzzle.
 */
export function ListTableHeader({ columns }: { columns: ListColumn[] }) {
  return (
    <table className="w-full table-fixed border-collapse text-base">
      <ColumnWidths columns={columns} />
      <thead className="sticky top-0 z-10 bg-surface-white">
        <tr className="border-b border-outline-gray-1">
          {/* Matches the selection column the tables below render. */}
          <th />
          {columns.map((column) => (
            <th
              key={column.key}
              className="truncate px-3 py-2 text-left text-sm font-medium text-ink-gray-5"
            >
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
    </table>
  )
}

/**
 * Widths live on `<col>` rather than `<th>` so a group_by section, which hides its own
 * header, still lines up with the shared header above it.
 */
function ColumnWidths({ columns }: { columns: ListColumn[] }) {
  return (
    <colgroup>
      <col style={{ width: '2.5rem' }} />
      {columns.map((column) => (
        <col key={column.key} style={column.width ? { width: column.width } : undefined} />
      ))}
    </colgroup>
  )
}
