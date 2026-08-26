import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { callGet } from '@/api/client'
import { createDoc, deleteDoc, updateDoc } from '@/api/resource'
import type { Filters, SavedView, ViewType } from '@/api/types'

/**
 * Saved views — `CRM View Settings`.
 *
 * Run 1's largest known gap: it sent `custom_view_name` and nothing else, and the backend
 * uses that name only for the default-columns flag (`doc.py:343`), so selecting a saved
 * view silently rendered default parameters.
 *
 * The fix is the one Vue uses: **resolve the view client-side and send its stored
 * parameters**, because the server does not hydrate them from the name
 * (`ViewControls.vue:459`). That is why this is a separate query rather than reading the
 * `views` array `get_data` already returns — the view's filters are an *input* to the
 * `get_data` request, so they must be known before it is built.
 */

const VIEW_DOCTYPE = 'CRM View Settings'

export function useViews(doctype: string) {
  const query = useQuery({
    queryKey: ['views', doctype],
    queryFn: () => callGet<SavedView[]>('crm.api.views.get_views', { doctype }),
    staleTime: 60_000,
  })

  const views = query.data ?? []

  /** `name` is an integer PK here, so the URL carries it as a string. */
  const getView = (name?: string) =>
    name ? views.find((view) => String(view.name) === String(name)) : undefined

  return { views, getView, isPending: query.isPending }
}

/**
 * The parameters a saved view contributes to `get_data`, in the shape `getParams()`
 * builds them (`ViewControls.vue:459-508`).
 *
 * The `Code` columns hold JSON strings upstream and are stored byte-identically here
 * (`metadata.py:69`), so `filters`, `columns`, `rows`, `kanban_columns` and
 * `kanban_fields` all need parsing. A malformed one yields the empty default rather than
 * throwing: a saved view with a corrupt filter should render an unfiltered list, not a
 * blank screen.
 */
export type ViewParams = {
  filters: Filters
  orderBy?: string
  columns?: unknown
  rows?: unknown
  columnField?: string
  titleField?: string
  kanbanColumns?: unknown
  kanbanFields?: unknown
  groupByField?: string
  viewType?: ViewType
}

export function viewParams(view: SavedView | undefined): ViewParams {
  if (!view) return { filters: {} }
  return {
    filters: asFilters(parseJson(view.filters)),
    orderBy: view.order_by || undefined,
    columns: parseJson(view.columns) ?? undefined,
    rows: parseJson(view.rows) ?? undefined,
    columnField: view.column_field || undefined,
    titleField: view.title_field || undefined,
    kanbanColumns: parseJson(view.kanban_columns) ?? undefined,
    kanbanFields: parseJson(view.kanban_fields) ?? undefined,
    groupByField: view.group_by_field || undefined,
    viewType: (view.type as ViewType) || undefined,
  }
}

/**
 * Only the two shapes the filter grammar actually has: a dict, or a list of tuples
 * (`doc.py:68`).
 *
 * `parseJson` alone was not enough — a stored `"123"` is valid JSON and survived it, then
 * went into the request as `filters: 123`. The column is free-form text on the server, so
 * a hand-edited or half-migrated row is a real possibility, and an unusable filter should
 * mean "no filter" rather than a 500.
 */
function asFilters(value: unknown): Filters {
  if (Array.isArray(value)) return value as Filters
  if (value && typeof value === 'object') return value as Filters
  return {}
}

function parseJson(value: unknown): unknown {
  if (!value || typeof value !== 'string') return null
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

/**
 * Create, rename and delete a saved view.
 *
 * Plain `/api/resource` CRUD rather than a dedicated endpoint: upstream has
 * `crm.api.views.create_or_update_default_view` for the *standard* per-user view, but a
 * named view is an ordinary document and the generic surface already serves it.
 */
export function useViewMutations(doctype: string) {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['views', doctype] })

  const create = useMutation({
    mutationFn: (view: {
      label: string
      type: ViewType
      filters: Filters
      order_by: string
    }) =>
      createDoc<SavedView>(VIEW_DOCTYPE, {
        dt: doctype,
        label: view.label,
        type: view.type,
        // Stored as JSON strings, matching what upstream writes and what `viewParams`
        // above expects to read back.
        filters: JSON.stringify(view.filters),
        order_by: view.order_by,
      }),
    onSuccess: invalidate,
  })

  const update = useMutation({
    mutationFn: ({ name, changes }: { name: string; changes: Record<string, unknown> }) =>
      updateDoc(VIEW_DOCTYPE, name, changes),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (name: string) => deleteDoc(VIEW_DOCTYPE, name),
    onSuccess: invalidate,
  })

  return { create, update, remove }
}
