import { Link } from '@tanstack/react-router'
import {
  ArrowDownUp,
  Columns3,
  Filter,
  LayoutGrid,
  List as ListIcon,
  RefreshCw,
  Rows3,
} from 'lucide-react'
import type { Filters, ListColumn, SavedView, ViewType } from '@/api/types'
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/primitives'
import { cn } from '@/lib/utils'
import { FilterEditor } from './FilterEditor'
import {
  useFilterableFields,
  useGroupByFields,
  useSortOptions,
} from './useFieldOptions'
import type { ListFilter } from './useListView'
import { ViewPicker } from './ViewPicker'

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
  groupBy,
  onGroupByChange,
  views,
  savedViewName,
  onSelectView,
  savedFilters,
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
  groupBy?: string
  onGroupByChange: (fieldname: string) => void
  views: SavedView[]
  savedViewName?: string
  onSelectView: (name?: string) => void
  savedFilters: Filters
  onDeleteView: (name: string) => void
  totalCount: number
  isFetching: boolean
  onRefresh: () => void
}) {
  const [sortField, sortDirection] = orderBy.split(' ')
  // The curated subsets, not `get_data`'s `fields` — see `useFieldOptions.ts`.
  const sortOptions = useSortOptions(doctype)
  const filterableFields = useFilterableFields(doctype)
  const groupByFields = useGroupByFields(doctype)

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-2">
      <ViewTypeTabs basePath={basePath} allowed={allowedViews} current={viewType} />

      <ViewPicker
        doctype={doctype}
        views={views}
        current={savedViewName}
        viewType={viewType}
        // What "save this view" would capture: the filters and sort on screen right now.
        filters={savedFilters}
        orderBy={orderBy}
        onSelect={onSelectView}
        onDeleted={onDeleteView}
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

        {/* Only where it means something. A group-by picker on a list view is a control
            with nothing to control. */}
        {viewType === 'group_by' ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm">
                <Rows3 className="h-4 w-4" />
                Group by
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
              <DropdownMenuLabel>Group rows by</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={groupBy ?? 'owner'}
                onValueChange={onGroupByChange}
              >
                {groupByFields.map((field) => (
                  <DropdownMenuRadioItem key={field.fieldname} value={field.fieldname}>
                    {field.label}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}

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
