import { useState } from 'react'
import type { RowSelectionState } from '@tanstack/react-table'
import { AlertCircle, Loader2 } from 'lucide-react'
import { errorMessage } from '@/api/client'
import type { DocRow, Filters, ViewType } from '@/api/types'
import { Button } from '@/components/ui/button'
import type { CellOverride } from './Cell'
import { KanbanBoard } from './KanbanBoard'
import { ListTable } from './ListTable'
import { useListView } from './useListView'
import { useStatuses } from './useLookups'
import { ViewControls } from './ViewControls'

/**
 * A whole list screen: header, toolbar, table or kanban, load-more.
 *
 * **This is the shared engine, and it is what makes screens two through seven cheap.** In
 * the Vue app the equivalent is `ViewControls.vue` (1,365 lines, shared) *plus* a
 * per-page `Deals.vue` / `Leads.vue` (~560 lines each) that repeats the row-parsing,
 * the empty state and the kanban wiring. Here a page supplies its doctype, its title and
 * anything genuinely doctype-specific, and nothing else.
 *
 * If a future screen needs something this does not offer, add it here rather than in the
 * page — the whole point is that there is one of it.
 */
export function ListView({
  doctype,
  title,
  basePath,
  statusDoctype,
  viewType,
  savedViewName,
  allowedViews = ['list'],
  defaultFilters,
  kanbanTitleField = 'name',
  cellOverrides,
  onRowClick,
  headerActions,
}: {
  doctype: string
  title: string
  /** e.g. `/deals/view`. The view switch appends the view type to it. */
  basePath: string
  /** The doctype holding this list's statuses, e.g. `CRM Deal Status`. */
  statusDoctype?: string
  viewType?: string
  savedViewName?: string
  allowedViews?: ViewType[]
  defaultFilters?: Filters
  kanbanTitleField?: string
  cellOverrides?: Record<string, CellOverride>
  onRowClick?: (row: DocRow) => void
  headerActions?: React.ReactNode
}) {
  const list = useListView({ doctype, viewType, savedViewName, defaultFilters })
  const { getStatus } = useStatuses(statusDoctype)
  const [selection, setSelection] = useState<RowSelectionState>({})

  const getStatusColor = statusDoctype
    ? (value: string) => getStatus(value)?.color
    : undefined

  const selectedCount = Object.keys(selection).length

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
        <h1 className="text-lg font-semibold text-ink-gray-8">{title}</h1>
        <div className="ml-auto flex items-center gap-2">{headerActions}</div>
      </header>

      <ViewControls
        basePath={basePath}
        allowedViews={allowedViews}
        viewType={list.viewType}
        fields={list.fields}
        allColumns={list.allColumns}
        hiddenColumns={list.hiddenColumns}
        onToggleColumn={list.toggleColumn}
        filters={list.filters}
        onFiltersChange={list.setFilters}
        orderBy={list.orderBy}
        onOrderByChange={list.setOrderBy}
        totalCount={list.totalCount}
        isFetching={list.isFetching}
        onRefresh={() => void list.refetch()}
      />

      {selectedCount > 0 ? (
        <div className="flex items-center gap-3 border-b border-outline-gray-1 bg-surface-gray-1 px-4 py-1.5 text-sm text-ink-gray-6">
          <span>
            {selectedCount} {selectedCount === 1 ? 'row' : 'rows'} selected
          </span>
          <Button variant="ghost" size="sm" onClick={() => setSelection({})}>
            Clear
          </Button>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto">
        {list.error ? (
          <Message icon={AlertCircle} text={errorMessage(list.error)} />
        ) : list.isPending ? (
          <Message icon={Loader2} text="Loading…" spin />
        ) : list.viewType === 'kanban' ? (
          <KanbanBoard
            groups={list.kanbanGroups}
            fields={list.fields}
            titleField={list.payload?.title_field || kanbanTitleField}
            onCardClick={onRowClick}
            getStatusColor={getStatusColor}
          />
        ) : list.rows.length === 0 ? (
          <Message icon={AlertCircle} text={`No ${title.toLowerCase()} found.`} />
        ) : (
          <>
            <ListTable
              rows={list.rows}
              columns={list.columns}
              selection={selection}
              onSelectionChange={setSelection}
              onRowClick={onRowClick}
              getStatusColor={getStatusColor}
              overrides={cellOverrides}
            />
            {list.hasMore ? (
              <div className="flex justify-center p-3">
                <Button variant="subtle" size="sm" onClick={list.loadMore}>
                  Load more
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}

function Message({
  icon: Icon,
  text,
  spin,
}: {
  icon: typeof AlertCircle
  text: string
  spin?: boolean
}) {
  return (
    <div className="flex h-full items-center justify-center gap-2 text-ink-gray-4">
      <Icon className={spin ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
      <span className="text-base">{text}</span>
    </div>
  )
}
