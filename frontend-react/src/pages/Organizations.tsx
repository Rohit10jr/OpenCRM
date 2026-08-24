import { useParams, useSearch } from '@tanstack/react-router'
import { ListView } from '@/list/ListView'

export function OrganizationsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })

  return (
    <ListView
      doctype="CRM Organization"
      title="Organizations"
      basePath="/organizations/view"
      viewType={viewType}
      savedViewName={view}
    />
  )
}
