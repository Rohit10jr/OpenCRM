import { useParams, useSearch } from '@tanstack/react-router'
import { ListView } from '@/list/ListView'

export function CallLogsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })

  return (
    <ListView
      doctype="CRM Call Log"
      title="Call Logs"
      basePath="/call-logs/view"
      viewType={viewType}
      savedViewName={view}
    />
  )
}
