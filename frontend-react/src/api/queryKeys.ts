/**
 * Query keys, in one place.
 *
 * `createResource` took a `cache: [...]` array and the Vue app spelled one out at each
 * call site — `cache: [props.doctype, route.query.view, route.params.viewType]`
 * (ViewControls.vue:518). That works until two call sites disagree about the order, and
 * then one of them silently gets the other's data.
 *
 * A key factory is the conventional TanStack answer and it also makes invalidation
 * legible: `invalidateQueries({ queryKey: keys.doc.all })` drops every document read
 * without anyone needing to remember what the arrays looked like.
 */
export const keys = {
  session: ['session'] as const,

  list: {
    all: ['list'] as const,
    /** One list view. `params` is the whole `get_data` request — it *is* the identity. */
    view: (doctype: string, params: unknown) => ['list', doctype, params] as const,
    /** Everything for one doctype, for invalidating after a write. */
    doctype: (doctype: string) => ['list', doctype] as const,
  },

  doc: {
    all: ['doc'] as const,
    one: (doctype: string, name: string) => ['doc', doctype, name] as const,
    list: (doctype: string, params: unknown) => ['doc', doctype, 'list', params] as const,
  },

  users: ['users'] as const,
  statuses: (doctype: string) => ['statuses', doctype] as const,
  fields: (doctype: string) => ['fields', doctype] as const,
} as const
