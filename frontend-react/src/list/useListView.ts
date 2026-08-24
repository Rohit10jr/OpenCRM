import { useCallback, useMemo, useState } from 'react'
import { useGetData } from '@/api/hooks'
import type {
  Filters,
  GetDataParams,
  GetDataResponse,
  KanbanGroup,
  DocRow,
  SavedView,
  ViewType,
} from '@/api/types'

/**
 * The list engine's state. This is `ViewControls.vue` (1,365 lines) minus its markup —
 * filters, sort, columns, page length, saved views and the list/kanban switch, all of
 * which resolve into one `crm.api.doc.get_data` request.
 *
 * **It is deliberately doctype-agnostic.** Seven pages share `ViewControls.vue` in the
 * Vue app; anything here that knows the word "deal" would have to be written six more
 * times.
 *
 * The Vue version rebuilt its params imperatively (`getParams()`, then
 * `list.value.params = getParams()`, then `reload()`). Here the params are derived from
 * state, and the query key is the params — so changing a filter refetches because the key
 * changed, and there is no `reload()` to forget to call.
 */

export type ListFilter = {
  fieldname: string
  operator: string
  value: string
}

export type UseListViewOptions = {
  doctype: string
  /** Which view types the page offers. `Deals` allows all three; `Notes` only list. */
  allowedViews?: ViewType[]
  /** From the route: `/deals/view/kanban`. */
  viewType?: string
  /** From the route: `?view=<saved view name>`. */
  savedViewName?: string
  /** Filters the *page* imposes, which the user cannot remove (`props.filters` in Vue). */
  defaultFilters?: Filters
  /** The field kanban columns group on. `ViewControls.vue:468` defaults it to `status`. */
  columnField?: string
}

const DEFAULT_PAGE_LENGTH = 20
const DEFAULT_ORDER_BY = 'modified desc'

export function useListView({
  doctype,
  viewType,
  savedViewName,
  defaultFilters,
  columnField = 'status',
}: UseListViewOptions) {
  const [filters, setFilters] = useState<ListFilter[]>([])
  const [orderBy, setOrderBy] = useState(DEFAULT_ORDER_BY)
  const [pageLength, setPageLength] = useState(DEFAULT_PAGE_LENGTH)
  /** Column keys the user has hidden. Empty means "whatever the server sends". */
  const [hiddenColumns, setHiddenColumns] = useState<string[]>([])

  const currentViewType: ViewType =
    viewType === 'kanban' || viewType === 'group_by' ? viewType : 'list'

  const params = useMemo<GetDataParams>(
    () => ({
      doctype,
      filters: toFilterDict(filters),
      order_by: orderBy,
      default_filters: defaultFilters,
      view: {
        custom_view_name: savedViewName ?? '',
        view_type: currentViewType,
        group_by_field: 'owner',
      },
      // Only in kanban mode: `_kanban` uses it to build the columns, and sending it for a
      // list view would put a `column_field` the list does not use into the query key.
      ...(currentViewType === 'kanban' ? { column_field: columnField } : {}),
      page_length: pageLength,
      page_length_count: pageLength,
    }),
    [
      doctype,
      filters,
      orderBy,
      defaultFilters,
      savedViewName,
      currentViewType,
      columnField,
      pageLength,
    ],
  )

  const query = useGetData(params)
  const payload = query.data

  const rows = useMemo<DocRow[]>(
    () => (currentViewType === 'kanban' ? [] : ((payload?.data as DocRow[]) ?? [])),
    [payload, currentViewType],
  )

  const kanbanGroups = useMemo<KanbanGroup[]>(
    () => (currentViewType === 'kanban' ? ((payload?.data as KanbanGroup[]) ?? []) : []),
    [payload, currentViewType],
  )

  const columns = useMemo(
    () => (payload?.columns ?? []).filter((c) => !hiddenColumns.includes(c.key)),
    [payload, hiddenColumns],
  )

  const toggleColumn = useCallback((key: string) => {
    setHiddenColumns((current) =>
      current.includes(key) ? current.filter((k) => k !== key) : [...current, key],
    )
  }, [])

  /**
   * "Load more" grows the page rather than paging. That is what the Vue list does —
   * `updatePageLength(value, true)` adds 20 to `page_length` — and it is why the server
   * takes `page_length` and `page_length_count` rather than an offset.
   */
  const loadMore = useCallback(
    () => setPageLength((n) => n + DEFAULT_PAGE_LENGTH),
    [],
  )

  const hasMore = (payload?.total_count ?? 0) > rows.length && currentViewType !== 'kanban'

  return {
    /** The raw payload, for the rare caller that needs a field these do not expose. */
    payload: payload as GetDataResponse | undefined,
    params,
    rows,
    kanbanGroups,
    columns,
    allColumns: payload?.columns ?? [],
    fields: payload?.fields ?? [],
    totalCount: payload?.total_count ?? 0,
    views: (payload?.views ?? []) as SavedView[],
    viewType: currentViewType,
    isPending: query.isPending,
    isFetching: query.isFetching,
    error: query.error,
    refetch: query.refetch,

    filters,
    setFilters,
    orderBy,
    setOrderBy,
    hiddenColumns,
    toggleColumn,
    pageLength,
    loadMore,
    hasMore,
  }
}

/**
 * The UI edits filters as a list — it has to, because a user can add two rows before
 * either has a field chosen — but the wire format is a dict keyed by fieldname
 * (`PHASE_0_FOUNDATION.md` section 5). The backend accepts the list-of-tuples form too,
 * but the dict is what `ViewControls.vue` sends and what the saved views store.
 *
 * Incomplete rows are dropped rather than sent: `{"status": ["like", ""]}` matches
 * everything, so a half-typed filter would silently look like no filter at all.
 */
function toFilterDict(filters: ListFilter[]): Filters {
  const out: Record<string, unknown> = {}
  for (const filter of filters) {
    if (!filter.fieldname || filter.value === '') continue
    out[filter.fieldname] =
      filter.operator === '=' ? filter.value : [filter.operator, filter.value]
  }
  return out
}
