import { useParams, useSearch } from '@tanstack/react-router'
import { ListView } from '@/list/ListView'

/** `FCRM Note`, not `CRM Note` — the doctype really is spelled that way upstream. */
export function NotesPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })

  return (
    <ListView
      doctype="FCRM Note"
      title="Notes"
      basePath="/notes/view"
      viewType={viewType}
      savedViewName={view}
    />
  )
}
