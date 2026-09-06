import { useParams, useSearch } from '@tanstack/react-router'
import { ListView } from '@/list/ListView'

/**
 * Call logs.
 *
 * **No Create button, deliberately.** A call log is written by the telephony integration
 * when a call happens (`crm.integrations.*`), not typed in by hand — the Vue page has no
 * create action either. Adding one here would offer to fabricate call history.
 */
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
