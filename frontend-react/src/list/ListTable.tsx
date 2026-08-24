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
}: {
  rows: DocRow[]
  columns: ListColumn[]
  selection: RowSelectionState
  onSelectionChange: (updater: React.SetStateAction<RowSelectionState>) => void
  onRowClick?: (row: DocRow) => void
  getStatusColor?: (value: string) => string | undefined
  overrides?: Record<string, CellOverride>
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
      <thead className="sticky top-0 z-10 bg-surface-white">
        {table.getHeaderGroups().map((group) => (
          <tr key={group.id} className="border-b border-outline-gray-1">
            {group.headers.map((header) => (
              <th
                key={header.id}
                style={widthOf(header.column.id, columns)}
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
            onClick={() => onRowClick?.(row.original)}
            className="cursor-pointer border-b border-outline-gray-1 hover:bg-surface-gray-1"
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

function widthOf(columnId: string, columns: ListColumn[]) {
  if (columnId === 'select') return { width: '2.5rem' }
  const width = columns.find((c) => c.key === columnId)?.width
  return width ? { width } : undefined
}
