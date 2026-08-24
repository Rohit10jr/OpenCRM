import { useParams, useSearch } from '@tanstack/react-router'
import { ListView } from '@/list/ListView'

/**
 * Contacts. `Contact` is a Frappe core doctype rather than a CRM one, which is why the
 * doctype name has no prefix — the same distinction the Vue page carries
 * (`Contacts.vue:25`).
 *
 * List only: `ViewControls` defaults `allowedViews` to `['list']` and this page does not
 * override it.
 */
export function ContactsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })

  return (
    <ListView
      doctype="Contact"
      title="Contacts"
      basePath="/contacts/view"
      viewType={viewType}
      savedViewName={view}
    />
  )
}
