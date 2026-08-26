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

/** One section of a group_by view. */
export type RowGroup = {
  label: string
  value: string
  rows: DocRow[]
}

export type UseListViewOptions = {
  doctype: string
  /** From the route: `/deals/view/kanban`. */
  viewType?: string
  /** From the route: `?view=<saved view name>`. */
  savedViewName?: string
  /** Filters the *page* imposes, which the user cannot remove (`props.filters` in Vue). */
  defaultFilters?: Filters
  /** The field kanban columns group on. `ViewControls.vue:468` defaults it to `status`. */
  columnField?: string
  /** The field a group_by view groups on. `ViewControls.vue:464` defaults it to `owner`. */
  groupByField?: string
  /**
   * The user's filters and sort, owned by the caller.
   *
   * They live in the URL rather than in this hook, so a filtered list can be linked,
   * survives a reload, and — the reason it changed this run — is still there after opening
   * a record and pressing back.
   */
  filters: ListFilter[]
  orderBy: string
}

const DEFAULT_PAGE_LENGTH = 20
export const DEFAULT_ORDER_BY = 'modified desc'

export function useListView({
  doctype,
  viewType,
  savedViewName,
  defaultFilters,
  columnField = 'status',
  groupByField = 'owner',
  filters,
  orderBy,
}: UseListViewOptions) {
  const [pageLength, setPageLength] = useState(DEFAULT_PAGE_LENGTH)
  /**
   * The page *increment*, not the page size — `page_length` grows past it as the user
   * loads more, and `page_length_count` stays put. `updatePageLength` does exactly this
   * (`ViewControls.vue:1052`); setting both to the accumulated length sends a request
   * the Vue client never sends.
   */
  const [pageLengthCount, setPageLengthCount] = useState(DEFAULT_PAGE_LENGTH)
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
        group_by_field: groupByField,
      },
      // Only in kanban mode: `_kanban` uses it to build the columns, and sending it for a
      // list view would put a `column_field` the list does not use into the query key.
      ...(currentViewType === 'kanban' ? { column_field: columnField } : {}),
      page_length: pageLength,
      page_length_count: pageLengthCount,
    }),
    [
      doctype,
      filters,
      orderBy,
      defaultFilters,
      savedViewName,
      currentViewType,
      columnField,
      groupByField,
      pageLength,
      pageLengthCount,
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

  /**
   * A group_by view returns flat rows plus a descriptor of what to group them by; the
   * grouping itself is the client's job (`Deals.vue:341`). Empty is a real group — the
   * server puts `""` in `options` when any row has no value.
   */
  const groups = useMemo<RowGroup[]>(() => {
    if (currentViewType !== 'group_by') return []
    const field = payload?.group_by_field
    if (!field || typeof field === 'string') return []
    return field.options.map((option) => ({
      label: option || 'No value',
      value: option,
      rows: rows.filter((row) =>
        option ? row[field.fieldname] === option : !row[field.fieldname],
      ),
    }))
  }, [payload, rows, currentViewType])

  const toggleColumn = useCallback((key: string) => {
    setHiddenColumns((current) =>
      current.includes(key) ? current.filter((k) => k !== key) : [...current, key],
    )
  }, [])

  /**
   * "Load more" grows the page rather than paging. That is what the Vue list does —
   * `page_length += page_length_count` (`ViewControls.vue:1059`) — and it is why the
   * server takes both numbers rather than an offset.
   */
  const loadMore = useCallback(
    () => setPageLength((n) => n + pageLengthCount),
    [pageLengthCount],
  )

  /** Changing the page size resets the accumulated length, as `updatePageLength` does. */
  const setPageSize = useCallback((size: number) => {
    setPageLength(size)
    setPageLengthCount(size)
  }, [])

  const hasMore = (payload?.total_count ?? 0) > rows.length && currentViewType !== 'kanban'

  return {
    /** The raw payload, for the rare caller that needs a field these do not expose. */
    payload: payload as GetDataResponse | undefined,
    params,
    rows,
    groups,
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

    hiddenColumns,
    toggleColumn,
    pageLength,
    setPageSize,
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
      filter.operator === '='
        ? filter.value
        : [filter.operator, likeWrap(filter.operator, filter.value)]
  }
  return out
}

/**
 * `like` values are sent pre-wrapped in `%`, as `Filter.vue:595` does.
 *
 * **The client must do this, not the server.** `_like_to_lookup`
 * (`backend/frappe_core/filters.py:144`) reads the wildcards to pick the narrowest
 * lookup — `%foo%` becomes `icontains`, a bare `foo` becomes `iexact`. So an unwrapped
 * value does not search for "contains foo", it searches for exactly "foo", and a
 * search box that looks like it works returns nothing.
 */
function likeWrap(operator: string, value: string): string {
  if (!operator.includes('like') || value.includes('%')) return value
  return `%${value}%`
}
