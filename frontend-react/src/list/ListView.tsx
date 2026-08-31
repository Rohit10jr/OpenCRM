import { useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import type { RowSelectionState } from '@tanstack/react-table'
import { AlertCircle, Loader2, type LucideIcon } from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { DocRow, Filters, ViewType } from '@/api/types'
import { Button } from '@/components/ui/button'
import { BulkActions } from './BulkActions'
import type { CellOverride } from './Cell'
import { KanbanBoard } from './KanbanBoard'
import { ListTable, ListTableHeader } from './ListTable'
import { useListView, type ListFilter } from './useListView'
import { useStatuses } from './useLookups'
import { useViewMutations } from './useViews'
import { ViewControls } from './ViewControls'
import type { ListSearch } from '@/router'

/** A stable empty array: a fresh `[]` per render would change the query key every time. */
const EMPTY_FILTERS: ListFilter[] = []

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
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as ListSearch
  const filters = search.filters ?? EMPTY_FILTERS

  /**
   * Filters and sort live in the URL, so changing one is a navigation.
   *
   * `replace: true` — a filter is a refinement of the current view, not a place. Pushing
   * each keystroke-committed filter onto the history stack would make Back mean "undo my
   * last filter" several times before it meant "the screen I came from".
   */
  const setSearch = (next: Partial<ListSearch>) => {
    void navigate({
      to: '.',
      search: (current: ListSearch) => ({ ...current, ...next }),
      replace: true,
    })
  }

  const list = useListView({
    doctype,
    viewType,
    savedViewName,
    defaultFilters,
    filters,
    // Undefined when the user has not chosen, so the saved view's sort wins.
    orderBy: search.order_by,
  })
  const { getStatus } = useStatuses(statusDoctype)
  const viewMutations = useViewMutations(doctype)
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
        filters={filters}
        onFiltersChange={(next) => setSearch({ filters: next.length ? next : undefined })}
        orderBy={list.orderBy}
        onOrderByChange={(next) => setSearch({ order_by: next })}
        views={list.views}
        savedViewName={savedViewName}
        // Selecting a view drops the ad-hoc filters, because the view carries its own and
        // `getParams()` reads them from the view — keeping both would silently AND a
        // saved view with whatever the user last typed.
        onSelectView={(name) =>
          setSearch({ view: name, filters: undefined, order_by: undefined })
        }
        onSaveView={(label) =>
          viewMutations.create.mutate(
            { label, type: list.viewType, filters: list.params.filters ?? {}, order_by: list.orderBy },
            {
              onSuccess: (view) =>
                setSearch({ view: String(view.name), filters: undefined }),
              onError: (error) => toast.error(errorMessage(error, 'Could not save the view')),
            },
          )
        }
        onDeleteView={(name) =>
          viewMutations.remove.mutate(name, {
            onSuccess: () => {
              if (String(name) === String(savedViewName)) setSearch({ view: undefined })
            },
            onError: (error) => toast.error(errorMessage(error, 'Could not delete the view')),
          })
        }
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
          {/* `getRowId` is the document name, so the selection keys *are* the ids. */}
          <BulkActions
            doctype={doctype}
            selected={Object.keys(selection)}
            onDone={() => setSelection({})}
          />
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
            {list.viewType === 'group_by' ? (
              <>
                {/* One shared header, then a headerless table per group. */}
                <ListTableHeader columns={list.columns} />
                {list.groups.map((group) => (
                  <section key={group.value || '__empty'}>
                    <h2 className="bg-surface-gray-1 px-4 py-1.5 text-sm font-medium text-ink-gray-6">
                      {group.label}
                      <span className="ml-2 text-ink-gray-4">{group.rows.length}</span>
                    </h2>
                    <ListTable
                      rows={group.rows}
                      columns={list.columns}
                      selection={selection}
                      onSelectionChange={setSelection}
                      onRowClick={onRowClick}
                      getStatusColor={getStatusColor}
                      overrides={cellOverrides}
                      showHeader={false}
                    />
                  </section>
                ))}
              </>
            ) : (
              <ListTable
                rows={list.rows}
                columns={list.columns}
                selection={selection}
                onSelectionChange={setSelection}
                onRowClick={onRowClick}
                getStatusColor={getStatusColor}
                overrides={cellOverrides}
              />
            )}
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
  icon: LucideIcon
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
