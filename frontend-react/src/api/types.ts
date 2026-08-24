/**
 * The wire shapes this client consumes. These are transcribed from the backend, not
 * guessed: `crm.api.doc.get_data`'s return statement is `backend/frappe_core/api/doc.py:353`
 * and every key below appears there.
 *
 * The backend is a fixed contract, so these types are a description of it rather than a
 * design. Where a field is `unknown` it is because the payload genuinely varies by
 * doctype and narrowing it here would be a guess.
 */

/** A row as returned in `data` — the selected `rows` fields, keyed by fieldname. */
export type DocRow = Record<string, unknown> & { name: string }

/** One column of the list table (`FALLBACK_COLUMNS`, doc.py:39). */
export type ListColumn = {
  label: string
  type: string
  key: string
  width?: string
  /** Present on Link columns; the target doctype. */
  options?: string
}

/** A doctype field descriptor (`STANDARD_FIELDS`, doc.py:46 and `get_doctype_fields`). */
export type DocField = {
  label: string
  fieldtype: string
  fieldname: string
  options?: string
}

/** A kanban column. `name` is the value of `column_field` the column groups on. */
export type KanbanColumn = {
  name: string
  label?: string
  /** Rows already fetched for this column. Kanban paginates per column. */
  data?: DocRow[]
  page_length?: number
  all_loaded?: boolean
  order?: string[]
  [key: string]: unknown
}

/** A saved `CRM View Settings` row, as returned in `views`. */
export type SavedView = {
  name: string
  label?: string
  type?: string
  icon?: string
  filters?: string
  order_by?: string
  group_by_field?: string
  column_field?: string
  title_field?: string
  kanban_columns?: string
  kanban_fields?: string
  columns?: string
  rows?: string
  route_name?: string
  load_default_columns?: boolean
  pinned?: boolean
  public?: boolean
  dt?: string
}

export type ViewType = 'list' | 'group_by' | 'kanban'

/** Exactly the object `get_data` returns (doc.py:353-372). */
export type GetDataResponse = {
  data: DocRow[] | KanbanColumn[]
  columns: ListColumn[]
  rows: string[]
  fields: DocField[]
  column_field: string | null
  title_field: string | null
  kanban_columns: KanbanColumn[]
  kanban_fields: string[]
  group_by_field: unknown
  page_length: number
  page_length_count: number
  is_default: boolean
  views: SavedView[]
  total_count: number
  row_count: number
  form_script: unknown
  list_script: unknown
  view_type: ViewType | null
}

/**
 * Frappe's filter grammar. The backend accepts both the dict form and the
 * list-of-tuples form and deliberately does not narrow it (`_as_filters`, doc.py:68),
 * so neither does this.
 */
export type Filters = Record<string, unknown> | Array<[string, string, unknown]>

/** The `view` sub-object of a `get_data` request (doc.py:238-240). */
export type ViewParam = {
  custom_view_name: string
  view_type: ViewType
  group_by_field: string
}

/** Every parameter `get_data` accepts, in the order it declares them (doc.py:212). */
export type GetDataParams = {
  doctype: string
  filters?: Filters
  order_by?: string
  page_length?: number
  page_length_count?: number
  column_field?: string | null
  title_field?: string | null
  columns?: ListColumn[] | string
  rows?: string[] | string
  kanban_columns?: KanbanColumn[] | string
  kanban_fields?: string[] | string
  view?: ViewParam
  default_filters?: Filters
}
