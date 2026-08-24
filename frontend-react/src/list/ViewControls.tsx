import { useEffect, useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  ArrowDownUp,
  Columns3,
  Filter,
  LayoutGrid,
  List as ListIcon,
  RefreshCw,
  X,
} from 'lucide-react'
import type { DocField, ListColumn, ViewType } from '@/api/types'
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
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/primitives'
import { cn } from '@/lib/utils'
import type { ListFilter } from './useListView'

/**
 * The list toolbar: view switch, filters, sort, columns, refresh.
 *
 * This is the visible half of `ViewControls.vue`. It renders nothing doctype-specific —
 * every option comes from the `fields` and `columns` the server sent — so the seven pages
 * that share it get the same controls without any of them configuring it.
 *
 * Saved views are read-only here: the payload's `views` are listed and can be selected,
 * but creating and editing one is `CRM View Settings` write traffic that no screen in
 * this conversion has reached yet.
 */

const FILTER_OPERATORS = [
  { value: '=', label: 'equals' },
  { value: '!=', label: 'not equals' },
  { value: 'like', label: 'like' },
  { value: 'not like', label: 'not like' },
  { value: '>', label: 'greater than' },
  { value: '<', label: 'less than' },
] as const

export function ViewControls({
  basePath,
  allowedViews,
  viewType,
  fields,
  allColumns,
  hiddenColumns,
  onToggleColumn,
  filters,
  onFiltersChange,
  orderBy,
  onOrderByChange,
  totalCount,
  isFetching,
  onRefresh,
}: {
  /** e.g. `/deals/view` — the view type is appended to it. */
  basePath: string
  allowedViews: ViewType[]
  viewType: ViewType
  fields: DocField[]
  allColumns: ListColumn[]
  hiddenColumns: string[]
  onToggleColumn: (key: string) => void
  filters: ListFilter[]
  onFiltersChange: (filters: ListFilter[]) => void
  orderBy: string
  onOrderByChange: (orderBy: string) => void
  totalCount: number
  isFetching: boolean
  onRefresh: () => void
}) {
  const [sortField, sortDirection] = orderBy.split(' ')

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-2">
      <ViewTypeTabs basePath={basePath} allowed={allowedViews} current={viewType} />

      <div className="ml-auto flex items-center gap-2">
        <span className="text-sm text-ink-gray-4">
          {totalCount} {totalCount === 1 ? 'row' : 'rows'}
        </span>

        <Popover>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="sm">
              <Filter className="h-4 w-4" />
              Filter
              {filters.length ? (
                <span className="rounded bg-surface-gray-3 px-1 text-sm">
                  {filters.length}
                </span>
              ) : null}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[28rem]">
            <FilterEditor
              fields={fields}
              filters={filters}
              onChange={onFiltersChange}
            />
          </PopoverContent>
        </Popover>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              <ArrowDownUp className="h-4 w-4" />
              Sort
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
            <DropdownMenuLabel>Sort by</DropdownMenuLabel>
            {fields.map((field) => (
              <DropdownMenuCheckboxItem
                key={field.fieldname}
                checked={sortField === field.fieldname}
                onCheckedChange={() =>
                  onOrderByChange(`${field.fieldname} ${sortDirection || 'desc'}`)
                }
              >
                {field.label}
              </DropdownMenuCheckboxItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() =>
                onOrderByChange(
                  `${sortField} ${sortDirection === 'asc' ? 'desc' : 'asc'}`,
                )
              }
            >
              {sortDirection === 'asc' ? 'Descending' : 'Ascending'}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              <Columns3 className="h-4 w-4" />
              Columns
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
            <DropdownMenuLabel>Show columns</DropdownMenuLabel>
            {allColumns.map((column) => (
              <DropdownMenuCheckboxItem
                key={column.key}
                checked={!hiddenColumns.includes(column.key)}
                onCheckedChange={() => onToggleColumn(column.key)}
                // Radix closes the menu on select; hiding several columns in a row is the
                // normal case, so it stays open.
                onSelect={(event) => event.preventDefault()}
              >
                {column.label}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <Button variant="ghost" size="icon" onClick={onRefresh} title="Refresh">
          <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
        </Button>
      </div>
    </div>
  )
}

function ViewTypeTabs({
  basePath,
  allowed,
  current,
}: {
  basePath: string
  allowed: ViewType[]
  current: ViewType
}) {
  const labels: Record<ViewType, { label: string; icon: typeof ListIcon }> = {
    list: { label: 'List', icon: ListIcon },
    group_by: { label: 'Group By', icon: ListIcon },
    kanban: { label: 'Kanban', icon: LayoutGrid },
  }

  return (
    <div className="flex items-center gap-1">
      {allowed.map((type) => {
        const { label, icon: Icon } = labels[type]
        return (
          <Link
            key={type}
            to={type === 'list' ? basePath : `${basePath}/$viewType`}
            params={{ viewType: type }}
            className={cn(
              'flex items-center gap-1.5 rounded px-2 py-1 text-base text-ink-gray-6 hover:bg-surface-gray-2',
              current === type && 'bg-surface-gray-3 font-medium text-ink-gray-8',
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        )
      })}
    </div>
  )
}

/**
 * A filter value that commits on blur or Enter rather than on every keystroke.
 *
 * The filter value is part of the query key, so a controlled input would fire a
 * `get_data` request per character typed. `Filter.vue:107` binds on `change` for the same
 * reason; a debounce would work too, but "the request goes when you finish typing" is
 * easier to reason about than "the request goes 300ms after you stop".
 */
function FilterValueInput({
  value,
  onCommit,
}: {
  value: string
  onCommit: (value: string) => void
}) {
  const [draft, setDraft] = useState(value)

  // The committed value can change underneath this — removing a filter row shifts the
  // rest up — so the draft follows it when it does.
  useEffect(() => setDraft(value), [value])

  return (
    <Input
      className="flex-1"
      placeholder="Value"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => draft !== value && onCommit(draft)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          onCommit(draft)
        }
      }}
    />
  )
}

function FilterEditor({
  fields,
  filters,
  onChange,
}: {
  fields: DocField[]
  filters: ListFilter[]
  onChange: (filters: ListFilter[]) => void
}) {
  function update(index: number, patch: Partial<ListFilter>) {
    onChange(filters.map((f, i) => (i === index ? { ...f, ...patch } : f)))
  }

  return (
    <div className="flex flex-col gap-2">
      {filters.length === 0 ? (
        <p className="text-sm text-ink-gray-4">No filters applied.</p>
      ) : null}

      {filters.map((filter, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <select
            className="h-8 min-w-0 flex-1 rounded border border-outline-gray-2 bg-surface-white px-1 text-base"
            value={filter.fieldname}
            onChange={(e) => update(index, { fieldname: e.target.value })}
          >
            {fields.map((field) => (
              <option key={field.fieldname} value={field.fieldname}>
                {field.label}
              </option>
            ))}
          </select>
          <select
            className="h-8 w-28 rounded border border-outline-gray-2 bg-surface-white px-1 text-base"
            value={filter.operator}
            onChange={(e) => update(index, { operator: e.target.value })}
          >
            {FILTER_OPERATORS.map((op) => (
              <option key={op.value} value={op.value}>
                {op.label}
              </option>
            ))}
          </select>
          <FilterValueInput
            value={filter.value}
            onCommit={(value) => update(index, { value })}
          />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onChange(filters.filter((_, i) => i !== index))}
            title="Remove filter"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}

      <Button
        variant="subtle"
        size="sm"
        className="self-start"
        onClick={() =>
          onChange([
            ...filters,
            {
              fieldname: fields[0]?.fieldname ?? 'name',
              operator: 'like',
              value: '',
            },
          ])
        }
      >
        Add filter
      </Button>
    </div>
  )
}
