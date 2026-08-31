import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  ArrowDownUp,
  BookmarkPlus,
  Columns3,
  Filter,
  LayoutGrid,
  List as ListIcon,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import type { ListColumn, SavedView, ViewType } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { FormControl } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/primitives'
import { cn } from '@/lib/utils'
import { FilterEditor } from './FilterEditor'
import { useFilterableFields, useSortOptions } from './useFieldOptions'
import type { ListFilter } from './useListView'

/**
 * The list toolbar: view switch, saved views, filters, sort, columns, refresh.
 *
 * This is the visible half of `ViewControls.vue`. It renders nothing doctype-specific —
 * every option comes from the server, keyed on the doctype — so the seven pages that share
 * it get the same controls without any of them configuring it.
 *
 * Sort and filter options come from `sort_options` and `get_filterable_fields`, the
 * curated subsets, rather than from `get_data`'s `fields`, which is every field on the
 * doctype. Columns still come from the payload, because the column set *is* the payload's.
 *
 * `FilterEditor` moved to its own file when this one reached 340 lines doing three jobs.
 */
export function ViewControls({
  doctype,
  basePath,
  allowedViews,
  viewType,
  allColumns,
  hiddenColumns,
  onToggleColumn,
  filters,
  onFiltersChange,
  orderBy,
  onOrderByChange,
  views,
  savedViewName,
  onSelectView,
  onSaveView,
  onDeleteView,
  totalCount,
  isFetching,
  onRefresh,
}: {
  doctype: string
  /** e.g. `/deals/view` — the view type is appended to it. */
  basePath: string
  allowedViews: ViewType[]
  viewType: ViewType
  allColumns: ListColumn[]
  hiddenColumns: string[]
  onToggleColumn: (key: string) => void
  filters: ListFilter[]
  onFiltersChange: (filters: ListFilter[]) => void
  orderBy: string
  onOrderByChange: (orderBy: string) => void
  views: SavedView[]
  savedViewName?: string
  onSelectView: (name?: string) => void
  onSaveView: (label: string) => void
  onDeleteView: (name: string) => void
  totalCount: number
  isFetching: boolean
  onRefresh: () => void
}) {
  const [sortField, sortDirection] = orderBy.split(' ')
  // The curated subsets, not `get_data`'s `fields` — see `useFieldOptions.ts`.
  const sortOptions = useSortOptions(doctype)
  const filterableFields = useFilterableFields(doctype)

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-2">
      <ViewTypeTabs basePath={basePath} allowed={allowedViews} current={viewType} />

      <ViewPicker
        views={views}
        current={savedViewName}
        onSelect={onSelectView}
        onSave={onSaveView}
        onDelete={onDeleteView}
        canSave={filters.length > 0}
      />

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
              fields={filterableFields}
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
            {/* A radio group, not checkboxes: `order_by` holds one field. */}
            <DropdownMenuRadioGroup
              value={sortField}
              onValueChange={(fieldname) =>
                onOrderByChange(`${fieldname} ${sortDirection || 'desc'}`)
              }
            >
              {sortOptions.map((field) => (
                <DropdownMenuRadioItem key={field.fieldname} value={field.fieldname}>
                  {field.label}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
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

/**
 * The saved-view picker.
 *
 * "Save current view" is offered only when there are filters to save: a view whose stored
 * filters are `{}` renders the same list as no view at all, and offering to create one is
 * offering to make a row that does nothing.
 */
function ViewPicker({
  views,
  current,
  onSelect,
  onSave,
  onDelete,
  canSave,
}: {
  views: SavedView[]
  current?: string
  onSelect: (name?: string) => void
  onSave: (label: string) => void
  onDelete: (name: string) => void
  canSave: boolean
}) {
  const selected = views.find((view) => String(view.name) === String(current))
  const [naming, setNaming] = useState(false)
  const [label, setLabel] = useState('')

  return (
    <>
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm">
          {selected?.label ?? 'All'}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 w-56 overflow-y-auto">
        <DropdownMenuLabel>Views</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={current ?? ''}
          onValueChange={(value) => onSelect(value || undefined)}
        >
          <DropdownMenuRadioItem value="">All</DropdownMenuRadioItem>
          {views.map((view) => (
            <DropdownMenuRadioItem key={view.name} value={String(view.name)}>
              <span className="flex-1 truncate">{view.label || view.name}</span>
              <button
                type="button"
                aria-label={`Delete ${view.label || view.name}`}
                className="text-ink-gray-4 hover:text-red-600"
                onClick={(event) => {
                  // Without this the radio item selects the view it is about to delete.
                  event.preventDefault()
                  event.stopPropagation()
                  onDelete(String(view.name))
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>

        {canSave ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setNaming(true)}>
              <BookmarkPlus className="h-4 w-4" />
              Save current view
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>

    <Dialog open={naming} onOpenChange={setNaming}>
      <DialogContent title="Save this view">
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!label.trim()) return
            onSave(label.trim())
            setLabel('')
            setNaming(false)
          }}
        >
          <FormControl
            label="Name"
            value={label}
            autoFocus
            required
            onChange={(event) => setLabel(event.target.value)}
          />
          <Button type="submit" variant="solid" className="self-end">
            Save view
          </Button>
        </form>
      </DialogContent>
    </Dialog>
    </>
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
